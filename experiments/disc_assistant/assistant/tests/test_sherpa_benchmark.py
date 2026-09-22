"""Runner boundary/report tests without optional model dependencies or devices."""
import argparse
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave

from experiments.disc_assistant.assistant.speech import Transcription
from experiments.disc_assistant.evaluation import sherpa_benchmark as runner


class SherpaBenchmarkTests(unittest.IsolatedAsyncioTestCase):
    async def test_freezes_audio_preserves_errors_and_warmup(self):
        contexts = []

        class FakeProvider:
            def __init__(self, directory, threads):
                self.calls = 0

            async def transcribe(self, audio, context):
                contexts.append(context)
                self.calls += 1
                if self.calls == 2:
                    raise RuntimeError('test inference failure')
                return Transcription('пауза', 'ru')

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = root / 'input.wav'
            with wave.open(str(audio), 'wb') as stream:
                stream.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
                stream.writeframes(b'\x01\x00' * 3200)
            args = argparse.Namespace(root=root, audio=[audio], samples=None,
                                      output=root / 'result', threads=[2], repeats=2, warmup=1)
            with (patch.object(runner, 'verify_models'), patch.object(runner, 'SherpaRussian', FakeProvider),
                  patch.dict('sys.modules', {'sherpa_onnx': SimpleNamespace(__version__='test')}),
                  redirect_stdout(io.StringIO())):
                self.assertEqual(await runner.benchmark(args), 1)
                with self.assertRaises(FileExistsError):
                    await runner.benchmark(args)
            report = json.loads((args.output / 'report.json').read_text())
            self.assertEqual(report['status'], 'completed_with_errors')
            self.assertEqual([r['warmup'] for r in report['rows']], [True, False, False])
            self.assertEqual(report['summary'][0]['errors'], 1)
            self.assertEqual(report['summary'][0]['warm_successes'], 1)
            self.assertIsNone(report['summary'][0]['text_correct'])
            self.assertTrue(all(c.locale == 'ru' and not c.vocabulary for c in contexts))
            self.assertEqual((args.output / '000.wav').read_bytes(), audio.read_bytes())

    async def test_rejects_english_before_creating_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'result'
            args = argparse.Namespace(root=directory, audio=[], samples=None, output=output)
            with (patch.object(runner, 'verify_models'),
                  patch.object(runner, 'cases_from_inputs', return_value=[{'locale': 'en'}]),
                  patch.dict('sys.modules', {'sherpa_onnx': SimpleNamespace(__version__='test')})):
                with self.assertRaisesRegex(ValueError, 'Russian-only'):
                    await runner.benchmark(args)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
