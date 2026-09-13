"""Check viewer environment selection, including the empty Compose default."""
import os
from pathlib import Path
import subprocess
import sys
import unittest


class ViewerBootScriptTests(unittest.TestCase):
    def test_unset_empty_and_custom_boot_script(self):
        tools = Path(__file__).resolve().parent
        default = str(tools.parent / 'scripts/20_boot.sh')
        for value, expected in ((None, default), ('', default), ('/work/custom-boot.sh', '/work/custom-boot.sh')):
            with self.subTest(value=value):
                env = dict(os.environ, PYTHONPATH=str(tools))
                env.pop('DEVICE_BOOT_SCRIPT', None)
                if value is not None:
                    env['DEVICE_BOOT_SCRIPT'] = value
                selected = subprocess.check_output(
                    [sys.executable, '-B', '-c', 'import stream; print(stream.device.boot_script)'],
                    env=env, text=True)
                self.assertEqual(selected.strip(), expected)
