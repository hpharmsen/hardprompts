import asyncio
import logging
import signal
import time
from pathlib import Path
from random import shuffle

from justai import Model
from justai.models.basemodel import BadRequestException, GeneralException, RatelimitException

from modelspecs import output_limit, split_effort
from output import GREEN, MAGENTA, RED, RESET, YELLOW
from storage import Storage

MAX_CONCURRENT_JOBS = 12
REVIEW_MODEL = 'claude-opus-4-5'

# Reasoning effort buys thinking time, so the job timeout has to move with it. Without this a
# high-effort run measures our own alarm instead of the model and lands as a T.
JOB_TIMEOUTS = {None: 300, 'low': 300, 'medium': 300, 'high': 600, 'xhigh': 900, 'max': 900}

# Track models to skip due to rate limits or credit issues
skipped_models: dict[str, str] = {}  # model_name -> reason

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s', filename='jobs.log', filemode='a')


def get_jobs(models, test_cases, passes, use_cache) -> list[dict]:
    storage = Storage()
    results = []
    for test_name, test_case in test_cases.items():
        test_case['name'] = test_name
        for model in models:
            if use_cache:
                _, _, model_passes = storage.read(model, test_name)
            else:
                model_passes = 0

            if model_passes >= passes:
                continue

            for _pass in range(model_passes, passes):
                results.append({'test_case': test_case, 'model': model, 'pass': _pass + 1})
    return results


def run_jobs(jobs, concurrent=False) -> dict[str, str]:
    """Run jobs and return dict of skipped models with reasons."""
    global skipped_models
    skipped_models = {}
    storage = Storage()
    if concurrent:
        asyncio.run(run_jobs_concurrently(jobs, storage))
    else:
        run_jobs_sequentially(jobs, storage)
    return skipped_models


def start_job(job, job_id, total_jobs) -> tuple[dict, str, int, str] | None:
    """Announce a job and unpack it, or return None if its model is being skipped."""
    test_case, model_name, _pass = job['test_case'], job['model'], job['pass']
    test_name = test_case['name']
    progress = f'{job_id}/{total_jobs}'

    if model_name in skipped_models:
        logging.info(f'Skipping job {progress}: {test_name} for {model_name} (previously skipped)')
        return None

    logging.info(f'Starting job {progress}: {test_name} for {model_name}')
    print(
        f'\n******** Running prompt {test_name} for {model_name} run {progress} '
        + '*' * (32 - len(model_name) - len(test_name))
    )
    return test_case, model_name, _pass, test_name


def report_timeout(test_name, model_name, job_id, total_jobs):
    logging.warning(f'Job {job_id}/{total_jobs}: {test_name} for {model_name} timed out.')
    print(f'Job {test_name} for {model_name} timed out.')


def spent_tokens(agent) -> tuple[int, int] | None:
    """What a call that failed still burned. justai records the provider's usage before it
    raises, so a run that never produced an answer is billed and belongs in the benchmark cost.
    None when nothing came back at all. With retries this is the last attempt, not their sum.
    """
    if agent is None:
        return None
    tokens = tuple(agent.last_token_count()[:2])
    return tokens if tokens[1] else None


def job_timeout(model_name: str) -> int:
    """Seconds we allow one job, based on the effort level in the model key."""
    return JOB_TIMEOUTS[split_effort(model_name)[1]]


def finish_job(storage, model_name, test_name, show, duration, job_id, total_jobs, tokens=None):
    storage.add(model_name, test_name, show, duration, tokens)
    logging.info(f'Finished job {job_id}/{total_jobs}: {test_name} for {model_name}')


def run_jobs_sequentially(jobs, storage):
    signal.signal(signal.SIGALRM, timeout_handler)

    for current_run, job in enumerate(jobs, start=1):
        started = start_job(job, current_run, len(jobs))
        if not started:
            continue
        test_case, model_name, _pass, test_name = started

        signal.alarm(job_timeout(model_name))
        tokens = None
        try:
            show, duration, skip_reason, tokens = run_prompt(_pass, model_name, test_case)
            if skip_reason:
                skipped_models[model_name] = skip_reason
                continue  # Don't store result for skipped runs
        except TimeoutException:
            show, duration = 'T', None
            report_timeout(test_name, model_name, current_run, len(jobs))
        finally:
            signal.alarm(0)

        finish_job(storage, model_name, test_name, show, duration, current_run, len(jobs), tokens)


# Deliberately our own, not justai's identically named TimeoutException: this one is raised
# by the SIGALRM handler below. Adding justai's to the imports above would silently break it.
class TimeoutException(Exception):
    pass


def timeout_handler(signum, frame):
    raise TimeoutException


async def run_jobs_concurrently(jobs, storage):
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)

    async def run_job_with_semaphore(job, job_id, total_jobs):
        async with semaphore:
            return await run_job_async(job, storage, job_id, total_jobs)

    tasks = []
    shuffle(jobs)
    for i, job in enumerate(jobs):
        tasks.append(run_job_with_semaphore(job, i + 1, len(jobs)))

    await asyncio.gather(*tasks)


async def run_job_async(job, storage, job_id, total_jobs):
    started = start_job(job, job_id, total_jobs)
    if not started:
        return
    test_case, model_name, _pass, test_name = started

    tokens = None
    try:
        show, duration, skip_reason, tokens = await asyncio.wait_for(
            asyncio.to_thread(run_prompt, _pass, model_name, test_case),
            timeout=float(job_timeout(model_name)),
        )
        if skip_reason:
            skipped_models[model_name] = skip_reason
            return  # Don't store result for skipped runs
    except TimeoutError:
        show, duration = 'T', None
        report_timeout(test_name, model_name, job_id, total_jobs)

    finish_job(storage, model_name, test_name, show, duration, job_id, total_jobs, tokens)


def backoff_or_give_up(label: str, try_: int, error: Exception) -> bool:
    """Sleeps with exponential backoff and returns True, or False on the 5th and last attempt."""
    if try_ == 4:
        print(MAGENTA, f'{label} after 5 attempts: {str(error)[:100]}', RESET)
        return False
    wait = 2**try_ * 5  # 5, 10, 20, 40 seconds
    logging.warning(f'{label} (attempt {try_ + 1}), retrying in {wait}s')
    print(YELLOW, f'{label} (attempt {try_ + 1}), retrying in {wait}s...', RESET)
    time.sleep(wait)
    return True


def run_prompt(pass_, model_name, test_case: dict) -> tuple[str, float | None, str | None, tuple[int, int] | None]:
    """Run a prompt and return (result, duration, skip_reason, tokens).

    skip_reason is set when the model should be skipped for remaining runs.
    tokens is (input, output) for the model under test, or None when nothing was billed.
    model_name may carry an effort suffix: "claude-fable-5@max".
    """
    agent = None
    base_model, effort = split_effort(model_name)
    # Just under our own job timeout, so justai's default of 120s never preempts a slow
    # high-effort call and the alarm stays the single authority on when a run is too long.
    timeout = JOB_TIMEOUTS[effort] - 10
    # Without this the thinking models hit justai's Anthropic default of 800 tokens, spend it
    # all on reasoning and return no text block, which the benchmark then scores as a B.
    limit = output_limit(model_name)
    prompt = str(pass_) + '. ' + test_case['prompt']
    return_json = test_case.get('json', False)
    image_path = test_case.get('image', [])
    if isinstance(image_path, str):
        image_path = [image_path]
    images = [Path(img).read_bytes() for img in image_path] if image_path else None
    for try_ in range(5):
        try:
            try:
                with Model(base_model, effort=effort, timeout=timeout, **limit) as agent:
                    agent.system = test_case.get('system_prompt', '')
                    # cached=False: a cache hit would replay an earlier answer and void the benchmark
                    message = agent.prompt(prompt, images=images, return_json=return_json, cached=False)
                print(message)
                break
            except Exception as e:
                error_type = type(e).__name__
                error_msg = str(e)
                error_msg_lower = error_msg.lower()
                log_msg = f'{model_name} {error_type} in run_prompt (attempt {try_ + 1}): {error_msg}'
                logging.error(log_msg)

                if any(x in error_msg_lower for x in ['import', 'attribute', 'circular import', 'cannot import']):
                    print(MAGENTA, f'{model_name} MODEL INITIALIZATION ERROR: {error_msg[:100]}', RESET)
                    return 'I', None, None, spent_tokens(agent)

                # Retryable server errors (504, 503, 500, overloaded, etc.)
                retryable_errors = [
                    'deadline',
                    '504',
                    '503',
                    '500',
                    'overloaded',
                    'server error',
                    'service unavailable',
                    'internal error',
                    'temporarily unavailable',
                ]
                if any(x in error_msg_lower for x in retryable_errors):
                    logging.warning(f'{model_name} SERVER ERROR (attempt {try_ + 1}): {error_msg[:100]}')
                    print(YELLOW, f'{model_name} SERVER ERROR (attempt {try_ + 1}), retrying...', RESET)
                    if try_ == 4:
                        print(MAGENTA, f'{model_name} SERVER ERROR after retries: {error_msg[:100]}', RESET)
                        return 'E', None, None, spent_tokens(agent)
                    time.sleep(5 + try_ * 5)  # Increasing backoff
                    continue

                # For other errors, let them be handled by the outer try-except
                if try_ == 4:  # If this was the last try
                    print(MAGENTA, f'{model_name} ERROR: {error_msg[:100]}', RESET)
                    return 'E', None, None, spent_tokens(agent)
                # This generic handler does the logging and the string-based classification;
                # re-raise so the typed handlers below can map the justai exception to a code.
                raise e
        except NotImplementedError as e:
            error_msg = f'{model_name} NOT IMPLEMENTED: {e!s}'
            logging.error(error_msg)
            print(MAGENTA, error_msg, RESET)
            return 'N', None, None, spent_tokens(agent)
        except BadRequestException as e:
            error_msg = f'{model_name} BAD REQUEST (attempt {try_ + 1}): {e!s}'
            logging.error(error_msg)
            print(MAGENTA, error_msg, RESET)
            return 'B', None, None, spent_tokens(agent)
        except GeneralException as e:
            error_msg = str(e).lower()
            # Check for credit/quota exhaustion
            if any(x in error_msg for x in ['insufficient_quota', 'quota', 'credit', 'billing', 'payment']):
                print(YELLOW, f'{model_name} SKIPPING (credits/quota): {str(e)[:100]}', RESET)
                return None, None, 'Insufficient credits/quota', None
            error_msg = f'{model_name} GENERAL ERROR (attempt {try_ + 1}): {e!s}'
            logging.error(error_msg)
            print(MAGENTA, error_msg, RESET)
            return 'G', None, None, spent_tokens(agent)
        except RatelimitException as e:
            error_msg = str(e).lower()
            # Check if it's quota exhaustion (won't resolve by waiting)
            if any(x in error_msg for x in ['insufficient_quota', 'quota_exceeded', 'billing', 'payment', 'credit']):
                print(YELLOW, f'{model_name} SKIPPING (quota exhausted): {str(e)[:100]}', RESET)
                return None, None, 'Quota exhausted', None
            if not backoff_or_give_up(f'{model_name} RATE LIMIT', try_, e):
                return 'R', None, None, spent_tokens(agent)
            continue
        except Exception as e:
            # Safety net: justai also raises Connection/Authorization/ModelOverload/Timeout/
            # RefusalException. Without this, those escape run_prompt and abort the whole run.
            logging.error(f'{model_name} UNHANDLED {type(e).__name__}: {str(e)[:200]}')
            print(MAGENTA, f'{model_name} UNHANDLED {type(e).__name__}: {str(e)[:100]}', RESET)
            return 'E', None, None, spent_tokens(agent)

    # The call under test is done here, so the tokens it burned are known. They are reported
    # even when the reviewer fails below: that spend happened and belongs in the benchmark cost.
    tokens = tuple(agent.last_token_count()[:2])

    if test_case.get('follow_up_prompt'):
        follow_up_prompt = test_case['follow_up_prompt'].replace('{antwoord}', message)
        message = None
        for review_try in range(5):
            try:
                with Model(REVIEW_MODEL) as reviewer:
                    message = reviewer.prompt(follow_up_prompt, return_json=True, cached=False)
                break
            except RatelimitException as e:
                # No quota-skip here: a reviewer limit says nothing about the model under test.
                if not backoff_or_give_up(f'REVIEWER RATE LIMIT for {model_name}', review_try, e):
                    return 'R', None, None, tokens
            except Exception as e:
                logging.error(f'REVIEWER ERROR for {model_name}: {type(e).__name__}: {str(e)[:200]}')
                print(MAGENTA, f'REVIEWER ERROR: {str(e)[:100]}', RESET)
                return 'E', None, None, tokens
        try:
            passed = str(message['aantal_goed'])
        except (KeyError, TypeError):
            print('ERROR', message)
            passed = '?'
        print('Resultaat: ', passed)
    else:
        answer_contains = test_case.get('answer_contains')
        answer = test_case.get('answer')
        if return_json and not isinstance(message, dict):
            print(MAGENTA, model_name, 'NO JSON', RESET)
            passed = 'X'
        elif (
            answer_contains
            and (answer_contains in message or answer_contains in str(message).replace('**', ''))
            or answer
            and answer == message
        ):
            print(GREEN, model_name, 'CORRECT', RESET)
            passed = '√'
        else:
            print(RED, model_name, 'WRONG', RESET)
            passed = 'X'

    print(tokens, 'tokens in/out')
    print(f'{agent.last_response_time:.1f} seconds')
    return passed, agent.last_response_time, None, tokens
