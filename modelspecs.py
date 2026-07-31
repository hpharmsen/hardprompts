'''Fetch model specifications and pricing from OpenRouter API.'''

import json
import yaml
import httpx
from pathlib import Path

MODELS_FILE = Path('data/models.yaml')
OUTPUT_FILE = Path('data/models.jsonl')
OPENROUTER_API = 'https://openrouter.ai/api/v1/models'

# Map our model keys to OpenRouter prefixes
LAB_PREFIXES = {
    'gpt': ('OpenAI', 'openai'),
    'o3': ('OpenAI', 'openai'),
    'o1': ('OpenAI', 'openai'),
    'claude': ('Anthropic', 'anthropic'),
    'gemini': ('Google', 'google'),
    'deepseek': ('Deepseek', 'deepseek'),
    'sonar': ('Perplexity', 'perplexity'),
    'grok': ('xAI', 'x-ai'),
    'kimi': ('Moonshot', 'moonshotai'),
    'moonshot': ('Moonshot', 'moonshotai'),
    'minimax': ('MiniMax', 'minimax'),
}

# OpenRouter is not always the price we actually pay. Fields here win over the fetched spec;
# prices are the provider's own list price per million tokens. Recheck when a promo ends.
SPEC_OVERRIDES = {
    # OpenRouter has no highspeed variant, so the fuzzy match lands on plain M2.7: the context
    # window is right, but the name and the price (M2.7 is $0.3/$1.2) are not.
    'MiniMax-M2.7-highspeed': {'name': 'MiniMax: MiniMax M2.7 highspeed',
                               'input_price': 0.6, 'output_price': 2.4},
    # OpenRouter runs a temporary 50% off promo on these two and so reports exactly half of
    # OpenAI's list price. Sol, nano and mini carry no promo and match, so they need no entry.
    'gpt-5.6-terra': {'input_price': 2.0, 'output_price': 12.0},
    'gpt-5.6-luna': {'input_price': 0.2, 'output_price': 1.2},
}


def load_models() -> list[str]:
    '''Load model keys from yaml.'''
    with open(MODELS_FILE) as f:
        return yaml.safe_load(f)['models']


def get_lab_for_model(model_key: str) -> tuple[str, str]:
    '''Map model key to (lab name, openrouter prefix).'''
    for prefix, (lab, or_prefix) in LAB_PREFIXES.items():
        if model_key.lower().startswith(prefix):  # MiniMax's model ids are mixed case
            return lab, or_prefix
    return 'Unknown', ''


def fetch_openrouter_models() -> dict[str, dict]:
    '''Fetch all models from OpenRouter API.'''
    response = httpx.get(OPENROUTER_API, timeout=30)
    response.raise_for_status()
    data = response.json()
    return {m['id']: m for m in data.get('data', [])}


def normalize_key(key: str) -> str:
    '''Normalize model key for matching.'''
    return key.lower().replace('-', '').replace('_', '').replace('.', '')


def find_openrouter_model(model_key: str, or_prefix: str, or_models: dict) -> dict | None:
    '''Find matching OpenRouter model for our model key.'''
    # Try exact match first
    exact_id = f'{or_prefix}/{model_key}'
    if exact_id in or_models:
        return or_models[exact_id]

    # Try common variations
    for suffix in ['', '-chat']:
        var = f'{or_prefix}/{model_key}{suffix}'
        if var in or_models:
            return or_models[var]

    # Fuzzy match
    norm_key = normalize_key(model_key)
    for or_id, or_model in or_models.items():
        if not or_id.startswith(or_prefix + '/'):
            continue
        or_model_part = or_id.split('/', 1)[1]
        norm_or = normalize_key(or_model_part)
        if norm_or == norm_key or norm_key in norm_or or norm_or in norm_key:
            return or_model

    return None


def price_per_million(price_per_token: str | float | None) -> float | None:
    '''Convert price per token to price per million tokens.'''
    if price_per_token is None:
        return None
    try:
        price = float(price_per_token)
        return round(price * 1_000_000, 4) if price > 0 else None
    except (ValueError, TypeError):
        return None


def build_model_spec(model_key: str, or_model: dict, lab: str) -> dict:
    '''Build model spec from OpenRouter data.'''
    pricing = or_model.get('pricing', {})
    arch = or_model.get('architecture', {})
    top_provider = or_model.get('top_provider', {})

    return {
        'key': model_key,
        'name': or_model.get('name', model_key),
        'lab': lab,
        'context_length': or_model.get('context_length'),
        'max_output': top_provider.get('max_completion_tokens'),
        'input_price': price_per_million(pricing.get('prompt')),
        'output_price': price_per_million(pricing.get('completion')),
        'modality': arch.get('modality'),
        'supports_images': 'image' in arch.get('input_modalities', []),
    } | SPEC_OVERRIDES.get(model_key, {})


def main():
    models = load_models()

    print('Fetching OpenRouter models...')
    or_models = fetch_openrouter_models()
    print(f'  Found {len(or_models)} models')

    results = []
    not_found = []

    for model_key in models:
        lab, or_prefix = get_lab_for_model(model_key)
        or_model = find_openrouter_model(model_key, or_prefix, or_models)

        if or_model:
            spec = build_model_spec(model_key, or_model, lab)
            results.append(spec)
            print(f'  {model_key}: ${spec["input_price"]}/{spec["output_price"]}')
        else:
            not_found.append(model_key)
            print(f'  {model_key}: NOT FOUND')

    # Write results
    with open(OUTPUT_FILE, 'w') as f:
        for spec in results:
            f.write(json.dumps(spec, ensure_ascii=False) + '\n')

    print(f'\nWrote {len(results)} models to {OUTPUT_FILE}')
    if not_found:
        print(f'Not found: {", ".join(not_found)}')


if __name__ == '__main__':
    main()
