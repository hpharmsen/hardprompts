import json
import re
from collections import defaultdict
from pathlib import Path

from storage import Storage

RED = '\033[31m'
GREEN = '\033[32m'
YELLOW = '\033[33m'
MAGENTA = '\033[35m'
RESET = '\033[0m'


def print_results(models, test_cases):
    storage = Storage()
    test_names = list(test_cases.keys())
    correct = defaultdict(int)
    W = 13
    MODEL_W = 30

    # Header row with test names
    print(' ' * MODEL_W, end='')
    for test_name in test_names:
        print(test_name[:W].ljust(W), end='   ')
    print()

    # Data rows with models
    for model_name in models:
        print(f'{model_name:<{MODEL_W}}', end='')
        for test_name in test_names:
            res, duration, passes = storage.read(model_name, test_name)
            entry1 = f"{res[:5]:<5}" if res else '?    '

            if res == '√':
                entry1 = f"{GREEN}{entry1}{RESET}"
            elif res == 'X':
                entry1 = f"{RED}{entry1}{RESET}"

            if duration and duration > 0:
                entry = entry1 + f"{duration:>5.1f}"
            else:
                entry = entry1 + '  N/A'

            print(entry + '      ', end='')
            if res == '√':
                correct[model_name] += passes
            elif is_int(res):
                correct[model_name] += int(res)
        # Print model total at end of row
        print(f'  {correct[model_name]}')


def is_int(s):
    try:
        int(s)
        return True
    except (TypeError, ValueError):
        return False


def print_report(models, test_cases, passes):
    """Prints a summary report table with model, correct count, and avg duration."""
    storage = Storage()
    test_names = list(test_cases.keys())
    max_correct = passes * len(test_names)

    print(f'\n{"Model":<30} {"Correct":>10} {"Avg Duration":>14}')
    print('-' * 56)

    for model in models:
        correct, avg_duration = storage.get_last_n(model, test_names, passes)
        duration_str = f'{avg_duration:.2f}s' if avg_duration else 'N/A'
        print(f'{model:<30} {correct:>5}/{max_correct:<4} {duration_str:>14}')


def generate_standalone_html(output_path: str = 'visualize.html'):
    """Generates a standalone HTML file with embedded data that works with file:// protocol."""
    base_path = Path(__file__).parent

    # Read source HTML template (use template file to avoid circular reads)
    html_template = (base_path / 'visualize_template.html').read_text()

    # Read data files
    prompts_text = (base_path / 'data' / 'prompts.toml').read_text()
    models_yaml_text = (base_path / 'data' / 'models.yaml').read_text()
    results_text = (base_path / 'data' / 'results.jsonl').read_text()
    models_text = (base_path / 'data' / 'models.jsonl').read_text()

    # json.dumps doubles as the escaper for JavaScript string literals
    embedded_data_js = (
        'const EMBEDDED_DATA = {\n'
        f'            prompts: {json.dumps(prompts_text)},\n'
        f'            models_yaml: {json.dumps(models_yaml_text)},\n'
        f'            results: {json.dumps(results_text)},\n'
        f'            models: {json.dumps(models_text)}\n'
        '        };'
    )

    # Find and replace the empty EMBEDDED_DATA block using string methods
    pattern = r'const EMBEDDED_DATA = \{[^}]+\};'
    match = re.search(pattern, html_template)
    if match:
        html_output = html_template[:match.start()] + embedded_data_js + html_template[match.end():]
    else:
        raise ValueError('EMBEDDED_DATA block not found in template')

    # Write output
    output_file = base_path / output_path
    output_file.write_text(html_output)
    print(f'Generated standalone HTML: {output_file}')
