"""The physical-device controller works without the emulator/research checkout."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


class ControllerIsolationTests(unittest.TestCase):
    def test_imports_with_only_controller_present(self):
        source = Path(__file__).resolve().parents[1]
        modules = ['controller.' + str(p.relative_to(source).with_suffix('')).replace('/', '.')
                   for p in source.rglob('*.py')
                   if 'tests' not in p.relative_to(source).parts and p.name != '__init__.py']
        self.assertTrue(modules)
        with tempfile.TemporaryDirectory() as directory:
            shutil.copytree(source, Path(directory) / 'controller',
                            ignore=shutil.ignore_patterns('tests', '__pycache__'))
            subprocess.run([sys.executable, '-B', '-c',
                            'import importlib, json, sys; '
                            '[importlib.import_module(name) for name in json.loads(sys.argv[1])]',
                            json.dumps(modules)], cwd=directory,
                           env={**os.environ, 'PYTHONPATH': directory}, check=True,
                           capture_output=True, text=True)
