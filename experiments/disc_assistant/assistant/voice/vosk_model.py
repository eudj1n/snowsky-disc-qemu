"""Reviewed Vosk TTS 0.9 RU model identity; no inference imports."""
import hashlib
from pathlib import Path

MODEL = 'vosk-model-tts-ru-0.9-multi'
ENGINE = '0.3.61'
ORT = '1.23.2'
SAMPLE_RATE = 22050
ARCHIVE_SHA256 = '0aa332451ce46bfdbd620e74765fc16a4087988067c299969121ed0f8ed5bdf2'
FILES = {
    'model.onnx': '0fa5a36b22a8bf7fe7179a3882c6371d2c01e5317019e717516f892d329c24b9',
    'dictionary': '2939e72c170bb41ac8e256828cca1c5fac4db1e36717f9f53fde843b00a220ba',
    'bert/model.onnx': '2e2f1740eaae5e29c2b4844625cbb01ff644b2b5fb0560bd34374c35d8a092c1',
    'bert/vocab.txt': 'bbe5063cc3d7a314effd90e9c5099cf493b81f2b9552c155264e16eeab074237',
    'bert/README.md': 'd9fc3039e005e2b5a6a1b07661d53ecf0b63414482520656e61de03c7c164537',
    'config.json': 'e155fb266a730e1858a2420442b465acf08a3236dffad7d1a507bf155b213d50',
    'README.md': 'e9db06085c65064c6f8e5220a85070f14fdf47bb8018d0b5c07cc0218cbb5a41',
}


def verify(root):
    root = Path(root)
    if not FILES:
        raise ValueError('missing reviewed Vosk file manifest')
    for name, expected in FILES.items():
        with (root / name).open('rb') as source:
            if hashlib.file_digest(source, 'sha256').hexdigest() != expected:
                raise ValueError(f'Vosk model digest mismatch: {name}')
