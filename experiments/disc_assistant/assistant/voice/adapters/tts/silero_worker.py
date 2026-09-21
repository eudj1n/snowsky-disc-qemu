"""Silero model host. Only this optional subprocess imports PyTorch."""
import base64
import hashlib
import io
import json
from pathlib import Path
import sys
import wave

from experiments.disc_assistant.assistant.voice.json_worker import read_message
from experiments.disc_assistant.assistant.voice.adapters.tts.silero import TORCH, VOICES


def main():
    output = sys.stdout
    sys.stdout = sys.stderr  # Model logging must never corrupt the wire protocol.
    def send(value):
        print(json.dumps(value), file=output, flush=True)
    settings = read_message(sys.stdin.buffer)
    model_path = Path(settings['model'])
    with model_path.open('rb') as source:
        if hashlib.file_digest(source, 'sha256').hexdigest() != settings['sha256']:
            raise ValueError('Silero model digest mismatch')
    import torch
    if torch.__version__.split('+')[0] != TORCH:
        raise ValueError('install the pinned torch version')
    torch.set_num_threads(settings['threads'])
    torch.set_grad_enabled(False)
    model = torch.package.PackageImporter(str(model_path)).load_pickle('tts_models', 'model')
    model.to(torch.device('cpu'))
    send({'ready': True})
    while (request := read_message(sys.stdin.buffer)) is not None:
        text, voice, rate = request['text'], request['voice'], request['rate']
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 4000 or voice not in VOICES or rate not in (8000, 24000, 48000):
            raise ValueError('invalid synthesis request')
        with torch.inference_mode():
            audio = model.apply_tts(text=text, speaker=voice, sample_rate=rate,
                                    put_accent=request['put_accent'], put_yo=request['put_yo'])
        if audio.ndim != 1 or not 0 < audio.numel() <= rate * 60 or not torch.isfinite(audio).all():
            raise ValueError('invalid model audio')
        pcm = (audio.cpu().clamp(-1, 1) * 32767).to(torch.int16).numpy().astype('<i2').tobytes()
        stream = io.BytesIO()
        with wave.open(stream, 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            wav.writeframes(pcm)
        send({'audio': base64.b64encode(stream.getvalue()).decode()})


if __name__ == '__main__':
    main()
