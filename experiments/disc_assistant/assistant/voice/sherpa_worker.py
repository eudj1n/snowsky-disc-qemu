"""Owned resident Sherpa subprocess with a bounded JSON line protocol."""
import argparse
import asyncio
import base64
import importlib.metadata
import json
from pathlib import Path
import sys

from experiments.disc_assistant.assistant.speech import SpeechContext
from experiments.disc_assistant.assistant.voice.files import wav_audio
from experiments.disc_assistant.assistant.voice.sherpa_model import SherpaRussian, ENGINE_VERSION
from experiments.disc_assistant.assistant.voice.sherpa_model import MODEL_ID, verify_models


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--threads', type=int, required=True)
    args = parser.parse_args()
    directory = Path(args.root).expanduser().resolve() / MODEL_ID
    if importlib.metadata.version('sherpa-onnx') != ENGINE_VERSION:
        raise ValueError('install the reviewed sherpa-onnx version')
    verify_models(directory)
    provider = SherpaRussian(directory, args.threads)
    print(json.dumps({'ready': True}), flush=True)
    while line := sys.stdin.buffer.readline(12 * 1024 * 1024):
        if not line.endswith(b'\n'):
            raise ValueError('oversized worker request')
        request = json.loads(line)
        audio = wav_audio(base64.b64decode(request['audio'], validate=True), max_seconds=120)
        result = asyncio.run(provider.transcribe(audio, SpeechContext('ru', 'sherpa-worker')))
        print(json.dumps({'text': result.text, 'no_speech': result.no_speech}), flush=True)


if __name__ == '__main__':
    main()
