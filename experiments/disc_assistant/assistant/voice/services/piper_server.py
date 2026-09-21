"""Private Piper worker. Explicit voices only; no downloads or arbitrary file API.

Piper is a separate GPL-3.0 component. This adapter source is covered by the
repository license; see docs/ASSISTANT_TTS.md for dependency/model notices.
"""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import io
import json
from pathlib import Path
import wave


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=18121)
    parser.add_argument('--voices', required=True, help='JSON mapping of locale to installed ONNX path')
    args = parser.parse_args()
    from piper import PiperVoice
    paths = json.loads(Path(args.voices).read_text())
    voices, evidence = {}, {}
    for locale, filename in paths.items():
        path = Path(filename)
        voices[locale] = PiperVoice.load(str(path), use_cuda=False)
        def digest(file):
            with file.open('rb') as stream:
                return hashlib.file_digest(stream, 'sha256').hexdigest()
        evidence[locale] = {'model_sha256': digest(path), 'config_sha256': digest(Path(str(path) + '.json'))}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Text, tokens and request bodies never enter access logs.

        def do_GET(self):
            if self.path != '/health':
                self.send_error(404)
                return
            data = json.dumps({'ok': True, 'voices': evidence}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            if self.path != '/synthesize':
                self.send_error(404)
                return
            self.connection.settimeout(10)
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 8192 or self.headers.get('Transfer-Encoding'):
                    raise ValueError('invalid length')
                request = json.loads(self.rfile.read(length))
                text, locale = request['text'], request['locale']
                if (set(request) != {'text', 'locale'} or not isinstance(text, str)
                        or not 1 <= len(text.strip()) <= 1000 or any(ord(c) < 32 or ord(c) == 127 for c in text)
                        or not isinstance(locale, str) or locale not in voices):
                    raise ValueError('invalid request')
                output = io.BytesIO()
                with wave.open(output, 'wb') as stream:
                    voice = voices[locale]
                    stream.setparams((1, 2, voice.config.sample_rate, 0, 'NONE', 'not compressed'))
                    frames = 0
                    for chunk in voice.synthesize(text):
                        if (chunk.sample_rate, chunk.sample_width, chunk.sample_channels) != (voice.config.sample_rate, 2, 1):
                            raise RuntimeError('unexpected Piper audio format')
                        frames += len(chunk.audio_int16_bytes) // 2
                        if frames > voice.config.sample_rate * 60:
                            raise ValueError('synthesis exceeds duration limit')
                        stream.writeframes(chunk.audio_int16_bytes)
                data = output.getvalue()
                self.send_response(200)
                self.send_header('Content-Type', 'audio/wav')
                self.send_header('Content-Length', str(len(data)))
                self.send_header('X-Model-SHA256', evidence[locale]['model_sha256'])
                self.send_header('X-Config-SHA256', evidence[locale]['config_sha256'])
                self.send_header('X-Voice-Locale', locale)
                self.end_headers()
                self.wfile.write(data)
            except (ValueError, KeyError, TypeError):
                self.send_error(400, 'Invalid synthesis request')
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                pass
            except Exception:
                self.send_error(503, 'Synthesis unavailable')

    HTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
