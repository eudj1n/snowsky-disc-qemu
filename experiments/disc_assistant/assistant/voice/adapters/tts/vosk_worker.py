"""Vosk Synth host with explicit local-only loading and bounded CPU threading."""
import base64
import importlib.metadata
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import wave

from experiments.disc_assistant.assistant.voice.json_worker import read_message
from experiments.disc_assistant.assistant.voice.text import checked_text
from experiments.disc_assistant.assistant.voice.vosk_model import ENGINE, ORT, SAMPLE_RATE, verify


def load_model(root, threads):
    """Build the pinned Synth model interface without Model's auto-download paths.

    Own the ONNX sessions so both networks use the requested CPU thread budget.
    No monkeypatching of global ONNX constructors or automatic GPU selection.
    """
    verify(root)
    if importlib.metadata.version('vosk-tts') != ENGINE or importlib.metadata.version('onnxruntime') != ORT:
        raise ValueError('install the pinned Vosk TTS environment')
    import onnxruntime as ort
    from tokenizers.implementations import BertWordPieceTokenizer
    options = ort.SessionOptions()
    options.intra_op_num_threads = threads
    options.inter_op_num_threads = 1
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    def session(path):
        return ort.InferenceSession(str(root / path), sess_options=options, providers=['CPUExecutionProvider'])
    # The dictionary includes alternate pronunciations with a probability column.
    best = {}
    with (root / 'dictionary').open(encoding='utf-8') as stream:
        for line in stream:
            word, score, phones = line.split(maxsplit=2)
            if float(score) > best.get(word, (float('-inf'), ''))[0]:
                best[word] = (float(score), phones)
    return SimpleNamespace(config=json.loads((root / 'config.json').read_text()),
        dic={word: entry[1] for word, entry in best.items()}, onnx=session('model.onnx'),
        tokenizer=BertWordPieceTokenizer(vocab=str(root / 'bert/vocab.txt'), unk_token='[UNK]', lowercase=True),
        bert_onnx=session('bert/model.onnx'))


def main():
    output = sys.stdout
    sys.stdout = sys.stderr
    def send(value):
        print(json.dumps(value), file=output, flush=True)
    settings = read_message(sys.stdin.buffer)
    model = load_model(Path(settings['model']), settings['threads'])
    import numpy as np
    from vosk_tts import Synth
    synth = Synth(model)
    send({'ready': True})
    while (request := read_message(sys.stdin.buffer)) is not None:
        text = checked_text(request['text'])
        speaker = request['speaker_id']
        if type(speaker) is not int or not 0 <= speaker <= 4:
            raise ValueError('invalid Vosk speaker')
        try:
            pcm = synth.synth_audio(text, speaker_id=speaker)
        except KeyError:
            # The pinned phoneme map can reject foreign words (e.g. Numb -> u).
            # Report a bounded domain error, without logging/repeating private text.
            send({'error': 'unsupported_text'})
            continue
        if pcm.ndim != 1 or pcm.dtype != np.int16 or not 0 < len(pcm) <= SAMPLE_RATE * 60:
            raise ValueError('invalid Vosk model audio')
        stream = io.BytesIO()
        with wave.open(stream, 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(SAMPLE_RATE)
            wav.writeframes(pcm.astype('<i2').tobytes())
        send({'audio': base64.b64encode(stream.getvalue()).decode()})


if __name__ == '__main__':
    main()
