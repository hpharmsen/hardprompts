from justai import Model
from justai.models.basemodel import BadRequestException, GeneralException, RatelimitException

from output import MAGENTA, RESET, GREEN, RED
from storage import Storage


def get_jobs(models, test_cases, passes, use_cache) -> list[dict]:
    storage = Storage()
    results = []
    for test_name in list(test_cases.keys()):
        test_case = test_cases[test_name]
        test_case['name'] = test_name
        for model in models:
            if "4.1" in model and test_case.get("image"):
                continue

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


def run_jobs(jobs):
    storage = Storage()
    current_run = 0
    for job in jobs:
        current_run += 1
        test_case, model_name, _pass = job['test_case'], job['model'], job['pass']
        test_name = test_case["name"]
        print(
            f"\n******** Running prompt {test_name} for {model_name} run {current_run}/{len(jobs)} "
            + "*" * (32 - len(model_name) - len(test_name))
        )
        show, duration = run_prompt(_pass, model_name, test_case)
        storage.add(model_name, test_name, show, duration)


def run_prompt(pass_, model_name, test_case: dict) -> tuple[str, float | None]:
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
    except (BadRequestException, GeneralException):
        print(MAGENTA, model_name, 'BAD REQUEST', RESET)
        return 'B', None
    except RatelimitException:
        print(MAGENTA, model_name, 'RATE LIMIT', RESET)
        return 'R', None

    if test_case.get('follow_up_prompt'):
        follow_up_prompt = test_case['follow_up_prompt'].replace('{antwoord}', message)
        with Model('gpt-5') as reviewer:
            message = reviewer.chat(follow_up_prompt, return_json=True, cached=False)
        try:
            passed = str(message['aantal_goed'])
        except KeyError:
            print('ERROR', message)
            passed = '?'
        print('Resultaat: ', passed)
    else:
        answer_contains = test_case.get('answer_contains')
        answer = test_case.get('answer')
        if return_json and not isinstance(message, dict):
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
    return passed, agent.last_response_time
