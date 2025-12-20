import asyncio
import logging
import signal
import time
from random import random, shuffle
from typing import List, Dict, Tuple, Set

from justai import Model
from justai.models.basemodel import BadRequestException, GeneralException, RatelimitException

from output import MAGENTA, RESET, GREEN, RED, YELLOW
from storage import Storage

MAX_CONCURRENT_JOBS = 12
REVIEW_MODEL = 'claude-opus-4-5'

# Track models to skip due to rate limits or credit issues
skipped_models: Dict[str, str] = {}  # model_name -> reason

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    filename='jobs.log',
    filemode='a'
)


def get_jobs(models, test_cases, passes, use_cache) -> List[Dict]:
    storage = Storage()
    results = []
    for test_name in list(test_cases.keys()):
        test_case = test_cases[test_name]
        test_case['name'] = test_name
        for model in models:
            # if "4.1" in model and test_case.get("image"):
            #     continue

            if use_cache:
                _, _, model_passes = storage.read(model, test_name)
            else:
                model_passes = 0

            if model_passes >= passes:
                continue

            for _pass in range(model_passes, passes):
                job = {'test_case': test_case, 'model': model, 'pass': _pass + 1}
                results += [job]
    return results


def run_jobs(jobs, concurrent=False) -> Dict[str, str]:
    """Run jobs and return dict of skipped models with reasons."""
    global skipped_models
    skipped_models = {}  # Reset at start of run
    storage = Storage()
    if concurrent:
        asyncio.run(run_jobs_concurrently(jobs, storage))
    else:
        run_jobs_sequentially(jobs, storage)
    return skipped_models


def run_jobs_sequentially(jobs, storage):
    current_run = 0
    signal.signal(signal.SIGALRM, timeout_handler)

    for job in jobs:
        current_run += 1
        test_case, model_name, _pass = job['test_case'], job['model'], job['pass']
        test_name = test_case["name"]

        # Skip if model already marked as skipped
        if model_name in skipped_models:
            logging.info(f'Skipping job {current_run}/{len(jobs)}: {test_name} for {model_name} (previously skipped)')
            continue

        logging.info(f'Starting job {current_run}/{len(jobs)}: {test_name} for {model_name}')
        print(
            f"\n******** Running prompt {test_name} for {model_name} run {current_run}/{len(jobs)} "
            + "*" * (32 - len(model_name) - len(test_name))
        )

        signal.alarm(300)  # 5 minutes
        try:
            show, duration, skip_reason = run_prompt(_pass, model_name, test_case)
            if skip_reason:
                skipped_models[model_name] = skip_reason
                continue  # Don't store result for skipped runs
        except TimeoutException:
            show, duration = 'T', None
            logging.warning(f'Job {current_run}/{len(jobs)}: {test_name} for {model_name} timed out.')
            print(f"Job {test_name} for {model_name} timed out.")
        finally:
            signal.alarm(0)

        storage.add(model_name, test_name, show, duration)
        logging.info(f'Finished job {current_run}/{len(jobs)}: {test_name} for {model_name}')


class TimeoutException(Exception): pass

def timeout_handler(signum, frame):
    raise TimeoutException


async def run_jobs_concurrently(jobs, storage):
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)  # Limit to 3 concurrent jobs
    
    async def run_job_with_semaphore(job, job_id, total_jobs):
        async with semaphore:
            return await run_job_async(job, storage, job_id, total_jobs)
    
    tasks = []
    shuffle(jobs)
    for i, job in enumerate(jobs):
        tasks.append(run_job_with_semaphore(job, i + 1, len(jobs)))
    
    await asyncio.gather(*tasks)


async def run_job_async(job, storage, job_id, total_jobs):
    test_case, model_name, _pass = job['test_case'], job['model'], job['pass']
    test_name = test_case["name"]

    # Skip if model already marked as skipped
    if model_name in skipped_models:
        logging.info(f'Skipping job {job_id}/{total_jobs}: {test_name} for {model_name} (previously skipped)')
        return

    logging.info(f'Starting job {job_id}/{total_jobs}: {test_name} for {model_name}')
    print(
        f"\n******** Running prompt {test_name} for {model_name} run {job_id}/{total_jobs} "
        + "*" * (32 - len(model_name) - len(test_name))
    )

    try:
        show, duration, skip_reason = await asyncio.wait_for(
            asyncio.to_thread(run_prompt, _pass, model_name, test_case),
            timeout=300.0
        )
        if skip_reason:
            skipped_models[model_name] = skip_reason
            return  # Don't store result for skipped runs
    except asyncio.TimeoutError:
        show, duration = 'T', None
        logging.warning(f'Job {job_id}/{total_jobs}: {test_name} for {model_name} timed out.')
        print(f"Job {test_name} for {model_name} timed out.")

    storage.add(model_name, test_name, show, duration)
    logging.info(f'Finished job {job_id}/{total_jobs}: {test_name} for {model_name}')


def run_prompt(pass_, model_name, test_case: Dict) -> Tuple[str, float | None, str | None]:
    """Run a prompt and return (result, duration, skip_reason).

    skip_reason is set when the model should be skipped for remaining runs.
    """
    prompt = str(pass_) + '. ' + test_case['prompt']
    return_json = test_case.get('json', False)
    image_path = test_case.get('image', [])
    if isinstance(image_path, str):
        image_path = [image_path]
    images = [open(img, 'rb').read() for img in image_path] if image_path else None
    for try_ in range(5):
        try:
            try:
                with Model(model_name, temperature=0) as agent:
                    agent.system = test_case.get("system_prompt", "")
                    message = agent.prompt(prompt, images=images, return_json=return_json, cached=False)
                print(message)
                break
            except Exception as e:
                error_type = type(e).__name__
                error_msg = str(e)
                error_msg_lower = error_msg.lower()
                log_msg = f"{model_name} {error_type} in run_prompt (attempt {try_ + 1}): {error_msg}"
                logging.error(log_msg)

                if any(x in error_msg_lower for x in ['import', 'attribute', 'circular import', 'cannot import']):
                    print(MAGENTA, f"{model_name} MODEL INITIALIZATION ERROR: {error_msg[:100]}", RESET)
                    return 'I', None, None

                # Retryable server errors (504, 503, 500, overloaded, etc.)
                retryable_errors = ['deadline', '504', '503', '500', 'overloaded', 'server error',
                                    'service unavailable', 'internal error', 'temporarily unavailable']
                if any(x in error_msg_lower for x in retryable_errors):
                    logging.warning(f"{model_name} SERVER ERROR (attempt {try_ + 1}): {error_msg[:100]}")
                    print(YELLOW, f"{model_name} SERVER ERROR (attempt {try_ + 1}), retrying...", RESET)
                    if try_ == 4:
                        print(MAGENTA, f"{model_name} SERVER ERROR after retries: {error_msg[:100]}", RESET)
                        return 'E', None, None
                    time.sleep(5 + try_ * 5)  # Increasing backoff
                    continue

                # For other errors, let them be handled by the outer try-except
                if try_ == 4:  # If this was the last try
                    print(MAGENTA, f"{model_name} ERROR: {error_msg[:100]}", RESET)
                    return 'E', None, None
                raise e
        except NotImplementedError as e:
            error_msg = f"{model_name} NOT IMPLEMENTED: {str(e)}"
            logging.error(error_msg)
            print(MAGENTA, error_msg, RESET)
            return 'N', None, None
        except BadRequestException as e:
            error_msg = f"{model_name} BAD REQUEST (attempt {try_ + 1}): {str(e)}"
            logging.error(error_msg)
            print(MAGENTA, error_msg, RESET)
            return 'B', None, None
        except GeneralException as e:
            error_msg = str(e).lower()
            # Check for credit/quota exhaustion
            if any(x in error_msg for x in ['insufficient_quota', 'quota', 'credit', 'billing', 'payment']):
                print(YELLOW, f"{model_name} SKIPPING (credits/quota): {str(e)[:100]}", RESET)
                return None, None, 'Insufficient credits/quota'
            error_msg = f"{model_name} GENERAL ERROR (attempt {try_ + 1}): {str(e)}"
            logging.error(error_msg)
            print(MAGENTA, error_msg, RESET)
            return 'G', None, None
        except RatelimitException as e:
            error_msg = str(e).lower()
            # Check if it's quota exhaustion (won't resolve by waiting)
            if any(x in error_msg for x in ['insufficient_quota', 'quota_exceeded', 'billing', 'payment', 'credit']):
                print(YELLOW, f"{model_name} SKIPPING (quota exhausted): {str(e)[:100]}", RESET)
                return None, None, 'Quota exhausted'
            # Temporary rate limit - retry
            logging.warning(f"{model_name} RATE LIMIT (attempt {try_ + 1}): {str(e)}")
            if try_ == 4:
                print(YELLOW, f"{model_name} SKIPPING (rate limit after retries): {str(e)[:100]}", RESET)
                return None, None, 'Rate limited (after retries)'
            time.sleep(5 + try_ * 5)  # Increasing backoff

    if test_case.get('follow_up_prompt'):
        follow_up_prompt = test_case['follow_up_prompt'].replace('{antwoord}', message)
        with Model(REVIEW_MODEL) as reviewer:
            message = reviewer.prompt(follow_up_prompt, return_json=True, cached=False)
        try:
            passed = str(message['aantal_goed'])
        except KeyError:
            print('ERROR', message)
            passed = '?'
        print('Resultaat: ', passed)
    else:
        answer_contains = test_case.get('answer_contains')
        answer = test_case.get('answer')
        if return_json and not isinstance(message, Dict):
            print(MAGENTA, model_name, "NO JSON", RESET)
            passed = 'X'
        elif answer_contains and (answer_contains in message or answer_contains in str(message).replace('**', '')):
            print(GREEN, model_name, 'CORRECT', RESET)
            passed = '√'
        elif answer and answer == message:
            print(GREEN, model_name, 'CORRECT', RESET)
            passed = '√'
        else:
            print(RED, model_name, 'WRONG', RESET)
            passed = 'X'

    print(agent.last_token_count(), 'tokens')  # (input_token_count, output_token_count, total_token_count)
    print(f'{agent.last_response_time:.1f} seconds')
    return passed, agent.last_response_time, None
