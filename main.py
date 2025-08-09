import sys
import tomllib
import yaml

from run import run_all
from output import print_results


def process_arguments() -> tuple[list[str], dict[str, dict[str, str]], int, bool]:
    with open("prompts.toml", "rb") as f:
        ALL_PROMPTS = tomllib.load(f)

    with open("models.yaml") as f:
        ALL_MODELS = yaml.safe_load(f)["models"]

    models = []
    prompts = {}
    include_visual_prompts = False
    use_cache = True
    passes = 1
    for arg in sys.argv[1:]:
        if arg == "--no-cache":
            use_cache = False
        elif arg == "--visual" or arg == "-v":
            include_visual_prompts = True
        elif arg.startswith("-n="):
            passes = int(arg[3:])
        elif arg in ALL_MODELS:
            models.append(arg)
        elif arg in ALL_PROMPTS:
            prompts[arg] = ALL_PROMPTS[arg]
        else:
            print("Unknown argument:", arg)
            sys.exit(1)

    if not models:
        models = ALL_MODELS

    if not prompts:
        if include_visual_prompts:
            prompts = ALL_PROMPTS
        else:
            prompts = {k: v for k, v in ALL_PROMPTS.items() if not v.get("image")}

    return models, prompts, passes, use_cache


if __name__ == "__main__":
    models, prompts, passes, use_cache = process_arguments()
    results = run_all(models, prompts, passes, use_cache)
    print_results(models, results, passes)
