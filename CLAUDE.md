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

### Effort Variants

A model identifier may carry an effort suffix: `claude-fable-5@max`. `split_effort()` in
`modelspecs.py` splits it, `run_prompt()` passes the level to justai as `effort=`, and every
variant is a separate row in `results.jsonl` with its own cache and score. Only add levels the
provider supports natively (justai's README lists them per provider); the rest are silently
downmapped and cost a full run to reproduce a result you already have. High levels also get a
longer job timeout via `JOB_TIMEOUTS` in `run.py`.

`run_prompt()` sets `max_tokens` explicitly via `max_tokens_for()` (the model's own `max_output`,
capped at 32768). Do not remove this: justai defaults Anthropic to 800 tokens, which a thinking
model such as Fable 5 spends entirely on reasoning, returning no text block. The benchmark then
scored that as a `B`, so those prompts looked failed while they were only cut off.

Each result record stores `tokens_in` / `tokens_out` whenever tokens were billed, including on
failures: a call that spent its whole budget on reasoning and returned no answer is charged all
the same, and `spent_tokens()` reads it from justai's counters after the exception. The "Score vs
Kosten" chart multiplies these by the prices in `models.jsonl` to plot what one full benchmark
run costs, following the vision toggle. Models with a prompt that lacks a token count are left
out of that chart rather than priced on partial data.

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
