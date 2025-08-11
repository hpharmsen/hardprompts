from collections import defaultdict

from storage import Storage

RED = '\033[31m'
GREEN = '\033[32m'
MAGENTA = '\033[35m'
RESET = '\033[0m'


def print_results(models, test_cases):
    storage = Storage()
    test_names = list(test_cases.keys())
    correct = defaultdict(int)
    W = 13
    print(' ' * (W + 1), end='')
    for model in models:
        print(model[:W].ljust(W), end='   ')
    print()

    for test_name in test_names:
        print(f'{test_name:<14}', end='')
        for index, model_name in enumerate(models):
            res, duration, passes = storage.read(model_name, test_name)
            entry1 = f"{res[:5]:<5}"

            if res == '√':
                entry1 = f"{GREEN}{entry1}{RESET}"
            elif res == 'X':
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
