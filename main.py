import sys
import tomllib
import webbrowser
import yaml
from pathlib import Path

from run import run_jobs, get_jobs
from output import print_results, print_report, generate_standalone_html, YELLOW, RESET


def process_arguments() -> tuple[list[str], dict[str, dict[str, str]], int, bool, bool, bool]:
    with open('data/prompts.toml', 'rb') as f:
        ALL_PROMPTS = tomllib.load(f)

    with open('data/models.yaml') as f:
        ALL_MODELS = yaml.safe_load(f)['models']

    models = []
    test_cases = {}
    include_visual_prompts = False
    use_cache = True
    passes = 1
    concurrent = False
    report = False
    for arg in sys.argv[1:]:
        if arg == '--no-cache':
            use_cache = False
        elif arg in ('--visual', '-v'):
            include_visual_prompts = True
        elif arg.startswith('-n='):
            passes = int(arg[3:])
        elif arg in ('-c', '--concurrent'):
            concurrent = True
        elif arg in ('-r', '--report'):
            report = True
        elif arg in ALL_MODELS:
            models.append(arg)
        elif arg in ALL_PROMPTS:
            test_cases[arg] = ALL_PROMPTS[arg]
        else:
            print('Unknown argument:', arg)
            sys.exit(1)

    if not models:
        models = ALL_MODELS

    if not test_cases:
        if include_visual_prompts:
            test_cases = ALL_PROMPTS
        else:
            test_cases = {k: v for k, v in ALL_PROMPTS.items() if not v.get('image')}

    return models, test_cases, passes, use_cache, concurrent, report


if __name__ == '__main__':
    models, test_cases, passes, use_cache, concurrent, report = process_arguments()
    jobs = get_jobs(models, test_cases, passes, use_cache)
    skipped = run_jobs(jobs, concurrent)
    if report:
        print_report(models, test_cases, passes)
    else:
        print_results(models, test_cases)

    # Report skipped models at the end
    if skipped:
        print(f'\n{YELLOW}Skipped models:{RESET}')
        for model, reason in skipped.items():
            print(f'  {YELLOW}{model}{RESET}: {reason}')

    # Generate standalone HTML and open in browser
    generate_standalone_html()
    html_path = Path(__file__).parent / 'visualize.html'
    webbrowser.open(f'file://{html_path}')
