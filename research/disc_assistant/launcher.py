"""Local development commands behind run.sh; no shell evaluation of .env values."""
import argparse
import json
import os
from pathlib import Path
import secrets
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request

from research.disc_assistant.assistant.config import load

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = Path(__file__).resolve().parent
ENV_FILE = PACKAGE / 'assistant/.env'


def read_env(path):
    result = {}
    if not path.exists():
        return result
    for line_number, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, sep, raw = line.removeprefix('export ').partition('=')
        key = key.strip()
        if not sep or key not in ('TYPESENSE_API_KEY', 'TYPESENSE_PORT') or key in result:
            raise ValueError(f'invalid or duplicate .env setting at line {line_number}')
        try:
            tokens = shlex.split(raw, comments=True)
        except ValueError as exc:
            raise ValueError(f'invalid .env quoting at line {line_number}') from exc
        if len(tokens) > 1:
            raise ValueError(f'quote .env values containing spaces at line {line_number}')
        result[key] = tokens[0] if tokens else ''
    return result


def initialize(config_path):
    # Validate existing environment before changing anything; preserve private keys.
    values = read_env(ENV_FILE)
    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'x', encoding='utf-8', opener=lambda path, flags: os.open(path, flags, 0o600)) as output:
            output.write((PACKAGE / 'assistant/config.example.toml').read_text())
    if not values.get('TYPESENSE_API_KEY'):
        key = secrets.token_hex(32)
        old = ENV_FILE.read_text() if ENV_FILE.exists() else ''
        lines = old.splitlines()
        replaced = False
        for index, line in enumerate(lines):
            if line.strip().removeprefix('export ').partition('=')[0].strip() == 'TYPESENSE_API_KEY':
                lines[index] = 'TYPESENSE_API_KEY=' + key
                replaced = True
        if not replaced:
            lines.append('TYPESENSE_API_KEY=' + key)
        # Atomic replace; only a missing/empty key is initialized. Never print it.
        temporary = ENV_FILE.with_name('.env.setup-' + secrets.token_hex(6))
        try:
            with open(temporary, 'x', encoding='utf-8', opener=lambda path, flags: os.open(path, flags, 0o600)) as output:
                output.write('\n'.join(lines) + '\n')
            temporary.replace(ENV_FILE)
        finally:
            temporary.unlink(missing_ok=True)
    print(f'Config: {config_path}\nSearch credentials: {ENV_FILE} (value hidden)')
    print('Edit device.host/key and ports before sync. Physical DISC: TCP 12100, HTTP 12103.')


def environment(config):
    result = dict(os.environ)
    local = read_env(ENV_FILE)
    # The config selects the secret variable. Default local .env takes precedence
    # over a stale exported key, consistently for Compose and the application.
    if config.api_key_env == 'TYPESENSE_API_KEY' and local.get('TYPESENSE_API_KEY'):
        result[config.api_key_env] = local['TYPESENSE_API_KEY']
    key = result.get(config.api_key_env, '')
    if not key.strip():
        raise ValueError('search key missing; run setup or set the configured api_key_env variable')
    result['TYPESENSE_API_KEY'] = key
    # One source for the port with this launcher. Legacy .env port is for manual Compose only.
    result['TYPESENSE_PORT'] = str(config.search_port)
    return result


def compose_command(*args):
    return ['docker', 'compose', '--env-file', '/dev/null', '-p', 'disc-assistant',
            '-f', str(PACKAGE / 'assistant/compose.yaml'), *args]


def wait_ready(config, timeout=45):
    url = f'{config.search_protocol}://{config.search_host}:{config.search_port}/health'
    deadline = time.monotonic() + timeout
    while True:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200 and json.load(response).get('ok') is True:
                    print(f'Typesense ready: {url}')
                    return
        except (OSError, ValueError, urllib.error.URLError):
            pass
        if time.monotonic() >= deadline:
            raise RuntimeError('Typesense readiness timed out; inspect the disc-assistant container logs')
        time.sleep(0.5)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default=os.environ.get('DISC_ASSISTANT_CONFIG', '~/disc-assistant.toml'))
    parser.add_argument('command', choices=('setup', 'up', 'down', 'sync', 'status', 'index', 'search', 'rank', 'ask', 'test', 'check'))
    parser.add_argument('arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    config_path = Path(args.config).expanduser()
    if not config_path.is_absolute():
        config_path = Path(os.environ.get('DISC_ASSISTANT_CALLER_DIR', os.getcwd())) / config_path
    config_path = config_path.resolve()
    try:
        if args.command not in ('search', 'rank', 'ask') and args.arguments:
            raise ValueError('unexpected arguments; see run.sh help')
        if args.command == 'setup':
            subprocess.run([sys.executable, '-m', 'pip', 'install', '-r',
                            str(PACKAGE / 'assistant/requirements.txt')], check=True, cwd=ROOT)
            initialize(config_path)
            return 0
        if args.command in ('test', 'check'):
            module = (['unittest', 'discover', '-s', 'research/disc_assistant', '-t', '.', '-v']
                      if args.command == 'test' else ['research.disc_assistant.check'])
            return subprocess.run([sys.executable, '-B', '-m', *module], cwd=ROOT).returncode
        if args.command == 'down':
            # Compose validates interpolation even for down. Stopping this named
            # stack must also work after a config/key has been moved or lost.
            env = {**os.environ, 'TYPESENSE_API_KEY': 'unused-for-stop', 'TYPESENSE_PORT': '8108'}
            return subprocess.run(compose_command('down'), env=env, cwd=ROOT).returncode
        if not config_path.is_file():
            raise ValueError(f'config missing: {config_path}; run setup or pass --config PATH')
        config = load(config_path)
        env = environment(config) if args.command in ('up', 'index', 'search', 'rank', 'ask') else dict(os.environ)
        if args.command == 'up':
            if config.search_host not in ('localhost', '127.0.0.1') or config.search_protocol != 'http':
                raise ValueError('up/down manage local HTTP Typesense only; remote search is externally managed')
            subprocess.run(compose_command('up', '-d'), check=True, env=env, cwd=ROOT)
            wait_ready(config)
            return 0
        return subprocess.run([sys.executable, '-m', 'research.disc_assistant.assistant',
                               '--config', str(config_path), args.command, *args.arguments],
                              cwd=ROOT, env=env).returncode
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'Assistant launcher: {exc}', file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        print(f'Assistant launcher: command failed (exit {exc.returncode})', file=sys.stderr)
        return exc.returncode


if __name__ == '__main__':
    sys.exit(main())
