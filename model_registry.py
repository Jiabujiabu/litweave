"""Auditable presets; remote discovery never edits these or the current selection."""
import copy
import json
from pathlib import Path

CATALOG_PATH = Path(__file__).parent / 'config/model_presets.json'
IMPLEMENTED_PROVIDERS = ('openai', 'anthropic', 'deepseek')
CUSTOM_MODEL = '__custom__'


def catalog():
    data = json.loads(CATALOG_PATH.read_text(encoding='utf-8'))
    providers = data['providers']
    for name, cfg in providers.items():
        if name not in IMPLEMENTED_PROVIDERS or not cfg.get('official_sources') or not cfg.get('checked_on'):
            raise ValueError('Invalid or unimplemented provider in model presets')
        ids = [m['api_id'] for m in cfg['models']]
        if len(ids) != len(set(ids)):
            raise ValueError('Duplicate model preset IDs')
    return data


def provider_config(provider):
    if provider not in IMPLEMENTED_PROVIDERS:
        raise ValueError('Provider adapter not implemented')
    return copy.deepcopy(catalog()['providers'][provider])


def model_preset(provider, model_id):
    return next((m for m in provider_config(provider)['models'] if m['api_id'] == model_id), None)


def capabilities(provider, model_id):
    cfg = provider_config(provider)
    preset = next((m for m in cfg['models'] if m['api_id'] == model_id), None)
    return copy.deepcopy(preset['capabilities'] if preset else cfg['custom_capabilities'])


def model_options(provider, remote_models=None, selected_id=None):
    choices = {m['api_id']:m['display_name'] for m in provider_config(provider)['models']}
    for model in remote_models or []:
        choices.setdefault(model['api_id'], model.get('display_name') or model['api_id'])
    if selected_id and selected_id != CUSTOM_MODEL:
        choices.setdefault(selected_id, selected_id)
    choices[CUSTOM_MODEL] = 'Custom model ID / 自定义模型 ID'
    return choices
