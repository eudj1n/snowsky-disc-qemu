"""Explicit, repeatable installation of the optional resident speech stack."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import ssl
import subprocess
import urllib.error
import urllib.request

from experiments.disc_assistant.assistant.config import load

SERVICES = Path(__file__).parent / 'assistant/voice/services'
VOICES = {'ru': 'ru_RU-irina-medium', 'en': 'en_GB-alba-medium'}


def download_context():
    """Keep platform trust and add explicit public roots for standalone Python builds."""
    import certifi
    context = ssl.create_default_context()
    context.load_verify_locations(cafile=certifi.where())
    extra = os.environ.get('DISC_ASSISTANT_CA_BUNDLE')
    if extra:
        try:
            context.load_verify_locations(cafile=str(Path(extra).expanduser()))
        except (OSError, ssl.SSLError) as exc:
            raise ValueError('DISC_ASSISTANT_CA_BUNDLE must name a readable, trusted PEM CA bundle') from exc
    return context


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def download(entry, root):
    target = root / entry['file']
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if sha256(target) != entry['sha256']:
            raise ValueError(f'Existing model asset differs from the pinned checksum: {target}; move it aside explicitly')
        return
    temporary = target.with_name(target.name + '.part-' + secrets.token_hex(6))
    print(f'Downloading {entry["file"]}', flush=True)
    try:
        total = 0
        with urllib.request.urlopen(entry['url'], timeout=60, context=download_context()) as source, temporary.open('xb') as output:
            while chunk := source.read(1024 * 1024):
                total += len(chunk)
                if total > 1024 * 1024 * 1024:
                    raise ValueError('Model download exceeds 1 GiB')
                output.write(chunk)
        if sha256(temporary) != entry['sha256']:
            raise ValueError('Downloaded model checksum mismatch')
        temporary.chmod(0o644)
        temporary.replace(target)
    except (urllib.error.URLError, ssl.SSLCertVerificationError) as exc:
        reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
        if isinstance(reason, ssl.SSLCertVerificationError):
            raise RuntimeError('Model download TLS certificate verification failed. '
                               'If a trusted proxy inspects HTTPS, set DISC_ASSISTANT_CA_BUNDLE '
                               'to its administrator-provided PEM CA bundle and rerun setup --all. '
                               'Certificate verification remains enabled.') from exc
        raise
    finally:
        temporary.unlink(missing_ok=True)


def compose(*args):
    return ['docker', 'compose', '--env-file', '/dev/null', '-p', 'disc-assistant-speech',
            '-f', str(SERVICES / 'compose.yaml'), *args]


def environment(config):
    root = config.data_dir / 'speech'
    voices = root / 'piper/voices.json'
    return {**os.environ, 'DISC_WHISPER_MODEL': str(Path(config.speech.get('model', root / 'ggml-base.bin')).expanduser()),
            'DISC_PIPER_DIR': str(root / 'piper'),
            'DISC_PIPER_VOICES_SHA256': sha256(voices) if voices.is_file() else 'unconfigured'}


def selected_whisper(config, model):
    """An omitted model option preserves an installed model, including custom builds."""
    if model is None and config.speech.get('model'):
        installed = Path(config.speech['model']).expanduser()
        if installed.is_file():
            return installed, None
        known = {'ggml-base.bin': 'base', 'ggml-small.bin': 'small'}
        model = known.get(installed.name)
        if model is None:
            raise ValueError('Configured Whisper model is missing; restore it or explicitly choose --whisper-model base|small')
    model = model or 'base'
    if model not in ('base', 'small'):
        raise ValueError('choose multilingual base or small')
    return config.data_dir / 'speech' / f'ggml-{model}.bin', f'ggml-{model}.bin'


def install(config_path, *, model=None):
    import tomlkit
    config = load(config_path)
    whisper_path, whisper_download = selected_whisper(config, model)
    subprocess.run(['docker', 'info'], check=True, stdout=subprocess.DEVNULL, timeout=30)
    root = config.data_dir / 'speech'
    root.mkdir(parents=True, exist_ok=True)
    for entry in json.loads((SERVICES / 'models.json').read_text()):
        if entry['file'].startswith('piper/') or entry['file'] == whisper_download:
            download(entry, root)
    voices = {locale: '/models/' + name + '.onnx' for locale, name in VOICES.items()}
    # Build before updating the user's configuration. No service/device is started here.
    env = {**os.environ, 'DISC_WHISPER_MODEL': str(whisper_path), 'DISC_PIPER_DIR': str(root / 'piper')}
    subprocess.run(compose('build'), check=True, env=env)
    from experiments.disc_assistant.launcher import compose_command, environment as search_environment
    subprocess.run(compose_command('build' if config.typesense_io_compat else 'pull', 'typesense', config=config),
                   check=True, env=search_environment(config))
    original = config_path.read_text()
    document = tomlkit.parse(original)
    for section in ('speech', 'tts', 'services'):
        if section not in document:
            document[section] = tomlkit.table()
    document['speech'].update(backend='server', server_url='http://127.0.0.1:18119/inference',
                              model=str(whisper_path))
    document['tts'].update(backend='piper', server_url='http://127.0.0.1:18121/synthesize', timeout=30)
    document['tts']['models'] = {locale: str(root / 'piper' / (voice + '.onnx')) for locale, voice in VOICES.items()}
    document['services']['speech'] = True
    updated = tomlkit.dumps(document)
    if original != updated:
        suffix = secrets.token_hex(6)
        backup = config_path.with_name(config_path.name + '.before-speech-' + suffix)
        temporary = config_path.with_name(config_path.name + '.speech-' + suffix)
        try:
            for path, data in ((backup, original), (temporary, updated)):
                with open(path, 'x', encoding='utf-8', opener=lambda p, flags: os.open(p, flags, 0o600)) as output:
                    output.write(data)
            load(temporary)  # Validate the complete file before atomic replacement.
            temporary.replace(config_path)
        finally:
            temporary.unlink(missing_ok=True)
        print(f'Original config preserved: {backup}')
    voice_path = root / 'piper/voices.json'
    temporary = voice_path.with_name('voices.json.part-' + secrets.token_hex(6))
    try:
        temporary.write_text(json.dumps(voices, indent=2) + '\n')
        temporary.replace(voice_path)
    finally:
        temporary.unlink(missing_ok=True)
    print(f'Whisper model: {whisper_path}')
    print('Speech installed: Whisper Server + Piper (RU Irina / EN Alba).')
    print('Start everything: run.sh web --bootstrap. Models and licenses stay outside Git.')


def manage(config, command):
    if command == 'down':
        # Stopping our named stack must remain possible when a model was moved.
        return subprocess.run(compose('down'), check=True, env=environment(config)).returncode
    if not config.services.get('speech'):
        raise ValueError('managed speech is not configured; run setup --all or start external services explicitly')
    root = config.data_dir / 'speech'
    if (config.speech.get('server_url') != 'http://127.0.0.1:18119/inference'
            or config.tts.get('server_url') != 'http://127.0.0.1:18121/synthesize'
            or config.tts.get('models') != {locale: str(root / 'piper' / (voice + '.onnx')) for locale, voice in VOICES.items()}):
        raise ValueError('managed speech configuration changed; use services.speech=false for external services')
    return subprocess.run(compose('up', '-d', '--wait', '--wait-timeout', '120'),
                          check=True, env=environment(config), timeout=180).returncode
