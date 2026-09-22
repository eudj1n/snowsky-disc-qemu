"""Reviewed Russian Zipformer model identity and isolated inference implementation."""
import hashlib
import io
from pathlib import Path
import wave

from experiments.disc_assistant.assistant.speech import Transcription

ENGINE_VERSION = '1.13.8'
MODEL_ID = 'sherpa-onnx-streaming-zipformer-small-ru-vosk-int8-2025-08-16'
REVISION = '31fa603e4f31279c6e1f7600fed13dc4312663ab'
BASE_URL = f'https://huggingface.co/csukuangfj/{MODEL_ID}/resolve/{REVISION}'
# LFS SHA-256 from the publisher API; tokens digest observed at this fixed revision.
FILES = {
    'encoder.int8.onnx': 'e0db705e94ec35d803b1df4f40cda23d064e1142977c80ab288430b109777a9d',
    'decoder.onnx': '89b3088a9e20e1ef7f2e85ce1a3478afe6a9c4ac57369cabcc4beb8e95328ea0',
    'joiner.int8.onnx': 'b55784b071ab7512eab4c7c44e4f5478284ef33c83562cc6a249b972515a31e5',
    'tokens.txt': '93bbbc0bae6b78c0bbb743d4aa9fded3bb5ff3aac5f0200e3a769a5a05e0fdf6',
    'test_wavs/0.wav': 'f3ac4f6e5b818ec89bdd884f60637daa32ef0ed19a11981b7e02e3e7799dfd79',
    'test_wavs/1.wav': 'd6e768803b3bc3afcb08326677f3bb872c9beeed29af40d3579bcc14e74484f8',
}


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_models(directory):
    for name, expected in FILES.items():
        if digest(directory / name) != expected:
            raise ValueError(f'checksum mismatch: {name}; existing files are not replaced')


class SherpaRussian:
    """Inference implementation used only inside an isolated worker or offline evaluation."""

    def __init__(self, directory, threads):
        import sherpa_onnx
        self.recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
            tokens=str(directory / 'tokens.txt'),
            encoder=str(directory / 'encoder.int8.onnx'),
            decoder=str(directory / 'decoder.onnx'),
            joiner=str(directory / 'joiner.int8.onnx'),
            num_threads=threads, sample_rate=16000, feature_dim=80,
            decoding_method='greedy_search', provider='cpu', enable_endpoint_detection=False,
        )

    async def transcribe(self, audio, context):
        import numpy as np
        if context.locale != 'ru' or context.vocabulary:
            raise ValueError('this experiment supports Russian without vocabulary hints only')
        with wave.open(io.BytesIO(audio.data), 'rb') as source:
            samples = np.frombuffer(source.readframes(source.getnframes()), dtype='<i2').astype(np.float32) / 32768
        stream = self.recognizer.create_stream()
        stream.accept_waveform(16000, samples)
        # Flush the transducer's right context; included in measured processing time.
        stream.accept_waveform(16000, np.zeros(4800, dtype=np.float32))
        stream.input_finished()
        while self.recognizer.is_ready(stream):
            self.recognizer.decode_stream(stream)
        text = self.recognizer.get_result(stream)
        return Transcription(text=text, locale='ru', no_speech=not text.strip())
