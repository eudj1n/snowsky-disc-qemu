"""Loopback-only native GigaAM worker. Explicit model installation; no DISC access."""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import distribution
import json
from pathlib import Path
import resource
import shutil
import sys
import tempfile
import threading

from experiments.disc_assistant.assistant.speech import InvalidSpeech
from experiments.disc_assistant.assistant.voice.files import wav_audio, audio_details
from experiments.disc_assistant.assistant.voice.adapters.stt.gigaam_contract import MODELS, UPSTREAM_REVISION


def make_server(port, recognize, evidence):
    busy = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send_json(self, value, status=200):
            data = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(data)

        def permitted(self):
            return (self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'
                    and not self.headers.get('Origin')
                    and self.headers.get('Sec-Fetch-Site') in (None, 'none'))

        def do_GET(self):
            if not self.permitted() or self.path != '/health':
                self.send_error(404)
                return
            self.send_json({'ok': True, 'model': evidence})

        def do_POST(self):
            if not self.permitted() or self.path != '/inference':
                self.send_error(403)
                return
            if not busy.acquire(blocking=False):
                self.send_error(409, 'Worker busy; no request was queued')
                return
            self.connection.settimeout(10)
            try:
                length = int(self.headers.get('Content-Length', '0'))
                locale = self.headers.get('X-Locale')
                if (not 0 < length <= 1024 * 1024 or self.headers.get('Transfer-Encoding')
                        or self.headers.get('Content-Type') != 'audio/wav'
                        or locale not in MODELS[evidence['model']]
                        or self.headers.get('X-Model-SHA256') != evidence['model_sha256']):
                    raise ValueError('invalid request')
                data = self.rfile.read(length)
                if len(data) != length:
                    raise ValueError('incomplete body')
                audio = wav_audio(data, max_seconds=25)
                # Avoid invented transcripts on digital silence; this is not a VAD.
                text = '' if audio_details(audio)['digital_silence'] else recognize(data)
                if (not isinstance(text, str) or len(text) > 1000
                        or any(ord(c) < 32 or ord(c) == 127 for c in text)):
                    raise RuntimeError('invalid model result')
                rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                observed = {**evidence, 'peak_rss_bytes': int(rss if sys.platform == 'darwin' else rss * 1024)}
                self.send_json({'text': text.strip(), 'locale': locale, 'no_speech': not text.strip(), 'model': observed})
            except (ValueError, InvalidSpeech):
                self.send_error(400, 'Invalid audio, locale or model identity')
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                pass
            except Exception:
                self.send_error(503, 'Transcription unavailable')
            finally:
                busy.release()

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', choices=MODELS, default='v3_ctc')
    parser.add_argument('--model-dir', required=True, type=Path)
    parser.add_argument('--download', action='store_true', help='allow explicit initial model download at startup')
    parser.add_argument('--threads', type=int, default=4)
    parser.add_argument('--port', type=int, default=18123)
    args = parser.parse_args()
    if not 1 <= args.threads <= 64 or not 1 <= args.port <= 65535:
        parser.error('invalid thread count or port')
    if shutil.which('ffmpeg') is None:
        parser.error('ffmpeg is required on PATH before starting the GigaAM worker')
    installed = json.loads(distribution('gigaam').read_text('direct_url.json') or '{}')
    if installed.get('vcs_info', {}).get('commit_id') != UPSTREAM_REVISION:
        parser.error('install the pinned voice/requirements/gigaam.txt')
    root = args.model_dir.expanduser().resolve()
    checkpoint = root / (args.model + '.ckpt')
    if not checkpoint.is_file() and not args.download:
        parser.error('model missing: use --download explicitly for initial installation')
    import torch
    import gigaam
    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    model = gigaam.load_model(args.model, device='cpu', fp16_encoder=False, use_flash=False, download_root=str(root))
    with checkpoint.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    evidence = {'model': args.model, 'model_sha256': digest, 'upstream_revision': UPSTREAM_REVISION,
                'torch_version': torch.__version__, 'device': 'cpu', 'threads': torch.get_num_threads()}

    def recognize(data):
        with tempfile.TemporaryDirectory(prefix='disc-gigaam-') as temporary:
            path = Path(temporary) / 'input.wav'
            path.write_bytes(data)
            return model.transcribe(str(path)).text

    with make_server(args.port, recognize, evidence) as server:
        print(json.dumps({'ready': True, 'url': f'http://127.0.0.1:{args.port}/inference', 'model': evidence}), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
