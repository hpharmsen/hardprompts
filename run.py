from justai import Model
from justai.models.basemodel import BadRequestException, GeneralException, RatelimitException

from output import MAGENTA, RESET, GREEN, RED
from storage import Storage


def run_all(models, prompts, passes, use_cache) -> list[list[str]]:
    storage = Storage()
    results = []
    total_to_run = len(prompts) * len(models) * passes
    current_run = 0
    for test_name in list(prompts.keys()):
        resultline = [test_name]
        test_case = prompts[test_name]

        for model in models:
            if use_cache:
                res, duration = storage.read(model, test_name, passes)
                if res is not None:
                    resultline += [[res, duration]]
                    current_run += passes
                    continue

            if '4.1' in model and test_case.get('image'):
                resultline += [['⬜', None]] # 〰️◻️⬜️⬜️🆓
                continue

            current_run += passes
            print(
                f"\n******** Running prompt {test_name} for {model} run {current_run}/{total_to_run} "
                + "*" * (32 - len(model) - len(test_name))
            )
            show, duration = run_testcase_on_model(test_case, model, test_name, passes, storage)
            resultline += [[show, duration]]
        results.append(resultline)
    return results


def run_testcase_on_model(test_case: dict, model: str, test_name: str, passes: int, storage: Storage) -> tuple[str, float | None]:
    tot = 0
    duration = 0.0
    show = None
    for p in range(passes):
        res, dur = run_prompt(p + 1, model, test_case)
        try:
            tot += int(res)
            duration += dur / passes
        except ValueError:
            show = res
            duration = 0.0
            break
    if show is None:
        show = str(tot)
    duration = round(duration, 1)
    storage.save(model, test_name, passes, show, duration)
    return show, duration


def run_prompt(pass_, model_name, test_case: dict) -> tuple[int | str, int | None]:
    prompt = str(pass_) + '. ' + test_case['prompt']
    return_json = test_case.get('json', False)
    image_path = test_case.get('image', [])
    if isinstance(image_path, str):
        image_path = [image_path]
    images = [open(img, 'rb').read() for img in image_path] if image_path else None
    try:
        with Model(model_name, temperature=0) as agent:
            agent.system = test_case.get("system_prompt", "")
            message = agent.chat(prompt, images=images, return_json=return_json, cached=False)
        print(message)
    except NotImplementedError:
        print(MAGENTA, model_name, 'NOT IMPLEMENTED', RESET)
        return 'N', None
    except (BadRequestException, GeneralException) as e:
        print(MAGENTA, model_name, 'BAD REQUEST', RESET)
        return 'B', None
    except RatelimitException:
        print(MAGENTA, model_name, 'RATE LIMIT', RESET)
        return 'R', None

    if test_case.get('follow_up_prompt'):
        follow_up_prompt = test_case['follow_up_prompt'].replace('{antwoord}', message)
        with Model('gpt-5') as reviewer:
            message = reviewer.chat(follow_up_prompt, return_json=True, cached=use_cache)
        try:
            passed = message['aantal_goed']
        except KeyError:
            print('ERROR', message)
            passed = '?'
        print('Resultaat: ', passed)
    else:
        answer_contains = test_case.get('answer_contains')
        answer = test_case.get('answer')
        if return_json and not isinstance(message, dict):
            print(MAGENTA, model_name, "NO JSON", RESET)
            passed = 0
        elif answer_contains and (answer_contains in message or answer_contains in str(message).replace('**','')):
            print(GREEN, model_name, 'CORRECT', RESET)
            passed = 1
        elif answer and answer == message:
            print(GREEN, model_name, 'CORRECT', RESET)
            passed = 1
        else:
            print(RED, model_name, 'WRONG', RESET)
            passed = 0

    print(agent.last_token_count(), 'tokens')  # (input_token_count, output_token_count, total_token_count)
    print(f'{agent.last_response_time:.1f} seconds')
    return passed, agent.last_response_time
