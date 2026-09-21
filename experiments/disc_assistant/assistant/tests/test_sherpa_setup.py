"""Firmware/model-free checks for the optional evaluation installer."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments.disc_assistant.evaluation import sherpa_setup as setup
from experiments.disc_assistant.assistant.voice import sherpa_model


class SherpaSetupTests(unittest.TestCase):
    def test_rejects_checkout_storage(self):
        with self.assertRaises(ValueError):
            setup.outside_repo(setup.REPO / 'models')

    def test_rejects_symlink_into_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            link = Path(directory) / 'link'
            link.symlink_to(setup.REPO, target_is_directory=True)
            with self.assertRaises(ValueError):
                setup.outside_repo(link / 'models')

    def test_corruption_is_preserved_and_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'weights').write_bytes(b'original')
            expected = setup.digest(path / 'weights')
            with patch.object(sherpa_model, 'FILES', {'weights': expected}):
                setup.verify_models(path)
                (path / 'weights').write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                    setup.verify_models(path)
                self.assertEqual((path / 'weights').read_bytes(), b'changed')


if __name__ == '__main__':
    unittest.main()
