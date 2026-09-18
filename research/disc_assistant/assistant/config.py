"""Explicit prototype configuration; no environment or filesystem work at import."""
from dataclasses import dataclass, field
import os
from pathlib import Path
import sys
import tomllib

from research.disc_assistant.assistant.languages import DEFAULT_LANGUAGES, load_languages
from research.disc_assistant.assistant.responses import DEFAULT_LANGUAGE, validate_response_preferences


@dataclass(frozen=True)
class Config:
    device_key: str
    host: str
    tcp_port: int
    http_port: int
    data_dir: Path
    search_host: str
    search_port: int
    search_protocol: str
    api_key_env: str
    aliases: dict
    page_size: int = 200
    timeout: int = 8
    max_tracks: int = 100000
    max_requests: int = 10000
    languages: tuple[str, ...] = DEFAULT_LANGUAGES
    continuous_context: bool = False
    journal_enabled: bool = True
    journal_retention_days: int = 90
    journal_max_requests: int = 10000
    terminal: dict = field(default_factory=dict)
    response_language: str = DEFAULT_LANGUAGE
    response_mode: str = 'errors'
    dialogue_enabled: bool = False


def default_data_dir():
    if sys.platform == 'darwin':
        return Path.home() / 'Library/Application Support/disc-hub/prototype'
    if sys.platform == 'win32':
        return Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'disc-hub/prototype'
    return Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'disc-hub/prototype'


def text(value, label):
    if not isinstance(value, str) or not value.strip() or value != value.strip() or any(ord(c) < 32 for c in value):
        raise ValueError(f'{label} must be a nonempty, trimmed string without control characters')
    return value


def number(value, label, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{label} must be an integer in {low}..{high}')
    return value


def load(path):
    with Path(path).open('rb') as stream:
        raw = tomllib.load(stream)
    allowed = {'device': {'key', 'host', 'tcp_port', 'http_port'},
               'storage': {'data_dir'},
               'typesense': {'host', 'port', 'protocol', 'api_key_env'},
               'sync': {'page_size', 'timeout', 'max_tracks', 'max_requests'},
               'aliases': {'artists', 'titles'},
               'language': {'enabled'},
               'response': {'language', 'mode'},
               'dialogue': {'enabled'},
               'playback': {'continuous_context'},
               'journal': {'enabled', 'retention_days', 'max_requests'},
               'terminal': {'color', 'prompt', 'input', 'result', 'error', 'warning', 'suggestion'}}
    if set(raw) - set(allowed):
        raise ValueError('unknown configuration section')
    for section, keys in allowed.items():
        if not isinstance(raw.get(section, {}), dict) or set(raw.get(section, {})) - keys:
            raise ValueError(f'invalid or unknown options in [{section}]')
    device, storage, search, sync = (raw.get(k, {}) for k in ('device', 'storage', 'typesense', 'sync'))
    aliases = raw.get('aliases', {})
    languages = load_languages(raw.get('language', {}).get('enabled', DEFAULT_LANGUAGES)).enabled
    continuous = raw.get('playback', {}).get('continuous_context', False)
    if type(continuous) is not bool:
        raise ValueError('playback.continuous_context must be a boolean')
    journal = raw.get('journal', {})
    journal_enabled = journal.get('enabled', True)
    if type(journal_enabled) is not bool:
        raise ValueError('journal.enabled must be a boolean')
    response = raw.get('response', {})
    response = validate_response_preferences(response.get('language', DEFAULT_LANGUAGE), response.get('mode', 'errors'))
    dialogue = raw.get('dialogue', {}).get('enabled', False)
    if dialogue is not False:
        raise ValueError('dialogue.enabled must be false; dialogue is not implemented')
    terminal = raw.get('terminal', {})
    if type(terminal.get('color', True)) is not bool:
        raise ValueError('terminal.color must be a boolean')
    for key, value in terminal.items():
        if key != 'color':
            text(value, f'terminal.{key}')
    for field, mapping in aliases.items():
        if not isinstance(mapping, dict):
            raise ValueError(f'aliases.{field} must be a table')
        for canonical, alternatives in mapping.items():
            text(canonical, 'alias canonical name')
            if not isinstance(alternatives, list) or any(not isinstance(x, str) for x in alternatives):
                raise ValueError('alias alternatives must be a list of strings')
            for alternative in alternatives:
                text(alternative, 'alias')
    data_dir = Path(text(storage.get('data_dir', str(default_data_dir())), 'data_dir')).expanduser()
    if not data_dir.is_absolute():
        raise ValueError('data_dir must be absolute (or start with ~)')
    data_dir = data_dir.resolve()
    repo = Path(__file__).resolve().parents[3]
    if data_dir == repo or repo in data_dir.parents:
        raise ValueError('personal application data must live outside the repository')
    protocol = search.get('protocol', 'http')
    if protocol not in ('http', 'https'):
        raise ValueError('typesense.protocol must be http or https')
    return Config(
        text(device.get('key'), 'device.key'), text(device.get('host'), 'device.host'),
        number(device.get('tcp_port', 12100), 'tcp_port', 1, 65535),
        number(device.get('http_port', 12103), 'http_port', 1, 65535), data_dir,
        text(search.get('host', '127.0.0.1'), 'typesense.host'),
        number(search.get('port', 8108), 'typesense.port', 1, 65535), protocol,
        text(search.get('api_key_env', 'TYPESENSE_API_KEY'), 'api_key_env'), aliases,
        number(sync.get('page_size', 200), 'page_size', 1, 200),
        number(sync.get('timeout', 8), 'timeout', 1, 120),
        number(sync.get('max_tracks', 100000), 'max_tracks', 1, 1000000),
        number(sync.get('max_requests', 10000), 'max_requests', 2, 100000), languages, continuous,
        journal_enabled, number(journal.get('retention_days', 90), 'journal.retention_days', 1, 3650),
        number(journal.get('max_requests', 10000), 'journal.max_requests', 1, 1000000), terminal,
        response['language'], response['mode'], dialogue)
