"""Validated speech deployment profiles; no downloads or platform auto-selection."""
from pathlib import Path
import tomllib
from experiments.disc_assistant.assistant.voice.registry import AdapterSpec, Registry, BUILTINS, NAME


def validate(raw):
    if not isinstance(raw, dict) or set(raw) - {'profile', 'stt', 'web_stt', 'tts', 'providers', 'plugins', 'web_choices'}:
        raise ValueError('invalid voice configuration')
    if 'profile' in raw:
        path = raw['profile']
        if not isinstance(path, str) or not Path(path).expanduser().is_absolute():
            raise ValueError('voice.profile must be an absolute path (or start with ~)')
    for role in ('stt', 'web_stt', 'tts'):
        if role in raw and (not isinstance(raw[role], str) or not NAME.fullmatch(raw[role])):
            raise ValueError(f'invalid voice.{role}')
    if 'web_choices' in raw:
        choices = raw['web_choices']
        if (not isinstance(choices, list) or not 1 <= len(choices) <= 16
                or any(not isinstance(x, str) or not NAME.fullmatch(x) for x in choices)
                or len(set(choices)) != len(choices)):
            raise ValueError('voice.web_choices must list distinct provider instances')
    plugins = raw.get('plugins', {})
    if not isinstance(plugins, dict):
        raise ValueError('voice.plugins must be a factory mapping')
    Registry(plugins)  # Validates identifiers without importing user code.
    providers = raw.get('providers', {})
    if not isinstance(providers, dict):
        raise ValueError('voice.providers must be a table')
    for name, spec in providers.items():
        if (not NAME.fullmatch(name) or not isinstance(spec, dict)
                or set(spec) - {'kind', 'adapter', 'label', 'settings'}
                or spec.get('kind') not in ('stt', 'tts')
                or not isinstance(spec.get('adapter'), str) or not NAME.fullmatch(spec['adapter'])
                or not isinstance(spec.get('settings', {}), dict)
                or not isinstance(spec.get('label', name), str) or not 1 <= len(spec.get('label', name)) <= 100):
            raise ValueError('invalid voice provider specification')
        settings = spec.get('settings', {})
        if 'normalization' in settings:
            if spec['kind'] != 'tts':
                raise ValueError('normalization is only available for TTS')
            from experiments.disc_assistant.assistant.voice.text import validate as validate_normalization
            validate_normalization(settings['normalization'])
        if 'timeout' in settings and (type(settings['timeout']) not in (int, float) or not 0 < settings['timeout'] <= 600):
            raise ValueError('voice provider timeout must be in (0, 600] seconds')
    return raw


def load_profile(raw):
    validate(raw)
    if 'profile' not in raw:
        return raw
    path = Path(raw['profile']).expanduser()
    with path.open('rb') as stream:
        document = tomllib.load(stream)
    if set(document) != {'voice'} or 'profile' in document['voice']:
        raise ValueError('profile must contain only [voice], without nested profiles')
    base = validate(document['voice'])
    # Inline selectors win; a provider override replaces that whole specification.
    return validate({**base, **raw,
                     'providers': {**base.get('providers', {}), **raw.get('providers', {})},
                     'plugins': {**base.get('plugins', {}), **raw.get('plugins', {})}})


def resolve(config, *, registered=None):
    registered = registered or {}
    raw = config.voice
    speech = dict(config.speech)
    server = {**speech, 'server_url': speech.get('server_url', 'http://127.0.0.1:18119/inference')}
    specs = {
        'whisper_cli': AdapterSpec('stt', 'whisper_cpp', 'Whisper CLI', speech),
        'whisper': AdapterSpec('stt', 'whisper_server', 'Whisper Server', server),
        'sherpa': AdapterSpec('stt', 'sherpa_onnx', 'Sherpa · Russian', speech),
        'piper': AdapterSpec('tts', 'piper', 'Piper', dict(config.tts)),
        'macos_say': AdapterSpec('tts', 'macos_say', 'macOS Say', speech),
    }
    for name, spec in raw.get('providers', {}).items():
        specs[name] = AdapterSpec(spec['kind'], spec['adapter'], spec.get('label', name), spec.get('settings', {}))
    selected = {
        'stt': raw.get('stt', 'whisper' if speech.get('backend') == 'server' else 'whisper_cli'),
        'web_stt': raw.get('web_stt', raw.get('stt', speech.get('web_backend', 'whisper'))),
        'tts': raw.get('tts', 'piper' if config.tts.get('backend') == 'piper' else 'none'),
    }
    for role, name in selected.items():
        if role == 'tts' and name == 'none':
            continue
        if name not in specs or specs[name].kind != ('stt' if role in ('stt', 'web_stt') else 'tts'):
            raise ValueError(f'voice.{role} selects an unknown provider or wrong role')
    for spec in specs.values():
        if spec.adapter not in BUILTINS and spec.adapter not in raw.get('plugins', {}) and spec.adapter not in registered:
            raise ValueError('voice provider selects an unregistered adapter')
        if spec.adapter in BUILTINS and BUILTINS[spec.adapter][0] != spec.kind:
            raise ValueError('voice provider adapter has the wrong role')
    web = raw.get('web_choices', ['whisper', 'sherpa'] + [
        name for name in raw.get('providers', {}) if specs[name].kind == 'stt' and name not in ('whisper', 'sherpa')])
    if selected['web_stt'] not in web:
        web = [*web, selected['web_stt']]
    if any(name not in specs or specs[name].kind != 'stt' for name in web):
        raise ValueError('voice.web_choices must select configured STT instances')
    return specs, selected, web
