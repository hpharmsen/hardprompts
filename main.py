import tomllib

from justai import Agent

RED = '\033[31m'
GREEN = '\033[32m'
RESET = '\033[0m'

def run_prompt(model_name, test_case: dict):
    agent = Agent(model_name)
    prompt = test_case['prompt']
    agent.system = test_case.get('system_prompt', '')
    return_json = test_case.get('json', False)
    image_path = test_case.get('image', '')
    image = open(image_path, 'rb').read() if image_path else None
    message = agent.chat(prompt, image=image, return_json=return_json, cached=True)
    print(message)

    answer_contains = test_case.get('answer_contains')
    answer = test_case.get('answer')
    if answer_contains and answer_contains in message:
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
    models = ["gpt-3.5-turbo", "gpt-4-turbo", "gpt-4o", "claude-3-5-sonnet-20240620", "claude-3-opus-20240229"]

    with open('prompts.toml', 'rb') as f:
        prompts = tomllib.load(f)

    results = []

    for test_name in prompts.keys():
        resultline = [test_name]
        #if test_name != 'BALKON1' and test_name != 'TERRAS2' and test_name != 'TERRAS3':
        #    continue
        test_case = prompts[test_name]
        for model in models:
            if 'turbo' in model and test_case.get('image'):
                resultline += ['🆓'] # 〰️◻️⬜️⬜️🆓
                continue
            print(f"\n******** Running prompt {test_name} for {model} *************")
            if run_prompt(model, test_case):
                resultline += ['✅']
            else:
                resultline += ['❌']

        results.append(resultline)

    print_results(models, results)


