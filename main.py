import sys
import tomllib

from justai import Agent

RED = '\033[31m'
GREEN = '\033[32m'
RESET = '\033[0m'

def run_prompt(model_name, test_case: dict):
    agent = Agent(model_name, temperature=0)
    prompt = test_case['prompt']
    agent.system = test_case.get('system_prompt', '')
    return_json = test_case.get('json', False)
    image_path = test_case.get('image', '')
    images = [open(img, 'rb').read() for img in image_path] if image_path else None
    message = agent.chat(prompt, images=images, return_json=return_json, cached=False)
    print(message)

    if test_case.get('follow_up_prompt'):
        reviewer = Agent('gpt-4o', temperature=0)
        follow_up_prompt = test_case['follow_up_prompt'].replace('{antwoord}', message)
        message = reviewer.chat(follow_up_prompt, return_json=True, cached=False)
        try:
            passed = message['aantal_goed']
        except KeyError:
            print('ERROR', message)
            passed = '?'
        print('Resultaat: ', passed)
    else:
        answer_contains = test_case.get('answer_contains')
        answer = test_case.get('answer')
        if answer_contains and (answer_contains in message or answer_contains in message.replace('**','')):
            print(GREEN, model_name, 'CORRECT', RESET)
            passed = True
        elif answer and answer == message:
            print(GREEN, model_name, 'CORRECT', RESET)
            passed = True
        else:
            print(RED, model_name, 'WRONG', RESET)
            passed = False

    print(agent.last_token_count(), 'tokens')  # (input_token_count, output_token_count, total_token_count)
    print(f'{agent.last_response_time:.1f} seconds')
    return passed


def print_results(models, results):
    W = 13
    print(' ' * (W + 1), end='')
    for model in models:
        print(model[:W].ljust(W), end='  ')
    print()
    for line in results:
        for index, res in enumerate(line):
            print(res[:W].ljust(W), end='  ')
            if index == 0:
                print('   ', end='')
        print()

if __name__ == "__main__":
    models = ["gpt-3.5-turbo", "gpt-4o-mini" ,"gpt-4-turbo", "gpt-4o", "claude-3-5-sonnet-20240620",
              "claude-3-opus-20240229", "gemini-1.5-flash", "gemini-1.5-pro"]

    with open('prompts.toml', 'rb') as f:
        prompts = tomllib.load(f)
    if sys.argv[1:]:
        specific_prompt = sys.argv[1]
        prompts = {specific_prompt: prompts[specific_prompt]}

    results = []

    for test_name in prompts.keys():
        resultline = [test_name]
        test_case = prompts[test_name]
        for model in models:
            if 'turbo' in model and test_case.get('image'):
                resultline += ['🆓'] # 〰️◻️⬜️⬜️🆓
                continue
            print(f"\n******** Running prompt {test_name} for {model} *************")
            res = run_prompt(model, test_case)
            if res is True:
                resultline += ['✅']
            elif res is False:
                resultline += ['❌']
            else:
                resultline += [str(res)]

        results.append(resultline)

    print_results(models, results)


