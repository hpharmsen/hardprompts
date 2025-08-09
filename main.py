import sys
import tomllib
from collections import defaultdict

from justai import Model
from justai.models.basemodel import BadRequestException, GeneralException, RatelimitException

from storage import Storage

ALL_MODELS = [
    "gpt-5",
    "gpt-5-mini",
    "gpt-5-nano",
    "gpt-4.1",
    "o3-mini",
    "claude-3-7-sonnet-latest",
    "claude-sonnet-4-20250514",
    "claude-opus-4-1-20250805",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.5-pro",
    "deepseek-chat", # "deepseek-reasoner", does not support json
    "sonar-pro",  # Error met output format
    #"sonar-reasoning", # idem
    "grok-3-mini",
    "grok-4"
]
with open("prompts.toml", "rb") as f:
    ALL_PROMPTS = tomllib.load(f)

RED = '\033[31m'
GREEN = '\033[32m'
MAGENTA = '\033[35m'
RESET = '\033[0m'


def run_prompt(pass_, model_name, test_case: dict, use_cache: bool) -> tuple[int | str, int | None]:
    prompt = str(pass_) + '. ' + test_case['prompt']
    return_json = test_case.get('json', False)
    image_path = test_case.get('image', [])
    if isinstance(image_path, str):
        image_path = [image_path]
    images = [open(img, 'rb').read() for img in image_path] if image_path else None
    try:
        with Model(model_name, temperature=0) as agent:
            agent.system = test_case.get("system_prompt", "")
            message = agent.chat(prompt, images=images, return_json=return_json, cached=use_cache)
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


def print_results(models, results, use_cache: bool):
    correct = defaultdict(int)
    W = 13
    print(' ' * (W + 1), end='')
    for model in models:
        print(model[:W].ljust(W), end='   ')
    print()

    for line in results:
        print(f'{line[0]:<14}', end='')
        for index, result in enumerate(line[1:]):
            res, duration = result
            entry1 = f"{res[:5]:<5}"

            if res == str(passes) or res == '√':
                entry1 = f"{GREEN}{entry1}{RESET}"
            elif res == '0' or res == 'X':
                entry1 = f"{RED}{entry1}{RESET}"

            if duration > 0:
                entry = entry1 + f"{duration:>5.1f}"
            else:
                entry = entry1 + '  N/A'

            print(entry + '      ', end='')
            if res == '√':
                correct[models[index]] += passes
            elif is_int(res):
                correct[models[index]] += int(res)
        print()
    print(" " * (W - 2), end="")
    for model in models:
        print("   ", end="")
        print(str(correct[model]).ljust(W), end='')


def is_int(s):
    try:
        int(s)
        return True
    except ValueError:
        return False

if __name__ == "__main__":
    models = []
    prompts = {}
    include_visual_prompts = False
    use_cache = True
    passes = 1
    for arg in sys.argv[1:]:
        if arg == '--no-cache':
            use_cache = False
        elif arg == '--visual' or arg == '-v':
            include_visual_prompts = True
        elif arg.startswith('-n='):
            passes = int(arg[3:])
        elif arg in ALL_MODELS:
            models.append(arg)
        elif arg in ALL_PROMPTS:
            prompts[arg] = ALL_PROMPTS[arg]
        else:
            print('Unknown argument:', arg)
            sys.exit(1)

    if not models:
        models = ALL_MODELS

    if not prompts:
        if include_visual_prompts:
            prompts = ALL_PROMPTS
        else:
            prompts = {k: v for k, v in ALL_PROMPTS.items() if not v.get('image')}

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
            print(f"\n******** Running prompt {test_name} for {model} run {current_run}/{total_to_run} " + '*' * (32-len(model)-len(test_name)))
            if passes == 1:
                current_run += 1
                res, duration = run_prompt(1, model, test_case, False)
                if res == 1:
                    show = "√"
                elif res == 0:
                    show = "X"
                elif res is None:
                    show = "⬜"
                else:
                    show = str(res)[:1]
            else:
                tot = 0
                duration = 0.0
                show = None
                for p in range(passes):
                    current_run += 1
                    res, dur = run_prompt(p + 1, model, test_case, use_cache=False)
                    try:
                        tot += int(res)
                        duration += dur / passes
                    except ValueError:
                        show = res
                        duration = 0.0
                        break
                if show is None:
                    show = str(tot)
                    #show = "√" if tot == passes else 'X' if tot == 0 else str(tot)
            duration = round(duration, 1)
            storage.save(model, test_name, passes, show, duration)
            resultline += [[show, duration]]
        results.append(resultline)

    print_results(models, results, use_cache)
