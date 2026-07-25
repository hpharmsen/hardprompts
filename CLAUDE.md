# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

hardprompts is an LLM benchmarking tool that runs test prompts against multiple AI models and compares their results. It supports text and visual prompts, caching of results, and concurrent execution.

## Commands

- **Run all tests**: `python main.py`
- **Run specific models**: `python main.py gpt-5 claude-sonnet-4-5`
- **Run specific prompts**: `python main.py STRAWBERRY APPLES`
- **Run concurrently**: `python main.py -c` or `python main.py --concurrent`
- **Include visual prompts**: `python main.py -v` or `python main.py --visual`
- **Multiple passes**: `python main.py -n=3`
- **Disable cache**: `python main.py --no-cache`

## Architecture

```
main.py          Entry point, argument parsing, loads prompts.toml and models.yaml
run.py           Job execution (sequential/concurrent), LLM API calls via justai
output.py        Results display with color-coded pass/fail
storage.py       JSONL-based result persistence in storage.jsonl
prompts.toml     Test case definitions with prompts, expected answers, images
models.yaml      List of model identifiers to test
input/           Images for visual prompts
```

### Data Flow

1. `main.py` parses args, loads test cases from `prompts.toml` and models from `models.yaml`
2. `get_jobs()` in `run.py` creates job list, skipping cached results based on `storage.jsonl`
3. `run_jobs()` executes jobs (sequential with SIGALRM timeout or concurrent with asyncio)
4. `run_prompt()` calls LLM via `justai.Model`, validates response against expected answer
5. Results stored via `Storage.add()`, displayed via `print_results()`

### Test Case Format (prompts.toml)

```toml
[TEST_NAME]
prompt = "..."              # Required
answer_contains = "..."     # Check if response contains string
answer = {...}              # Check exact match (for JSON responses)
json = true                 # Request JSON output
image = "input/file.png"    # Single image or list for visual prompts
system_prompt = "..."       # Optional system message
follow_up_prompt = "..."    # Post-process with reviewer model
```

### Result Codes

- `√` - Correct
- `X` - Wrong
- `T` - Timeout
- `R` - Rate limited
- `B` - Bad request
- `E` - Error (unhandled exception after retries)
- `G` - General error (justai `GeneralException`, non-quota)
- `N` - Not implemented
- `I` - Import/initialization error

## Key Dependencies

- `justai` - Unified LLM API wrapper (handles OpenAI, Anthropic, Google, etc.)
- Results cached in `storage.jsonl` to avoid re-running passed tests
