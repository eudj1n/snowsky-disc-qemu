"""Selection and review boundaries independent of any installed firmware."""
import copy
import json
import os
import shutil
import sys
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from firmware import profile
from tests.integration.profile import require_acceptance


class SelectionTests(unittest.TestCase):
    def test_env_override_and_empty_default(self):
        for override, expected in [(None, profile.DEFAULT_VERSION), ('', profile.DEFAULT_VERSION), ('2.40', '2.40')]:
            with self.subTest(override=override), patch.dict(os.environ, {}, clear=True):
                if override is not None:
                    os.environ['FW_VERSION'] = override
                self.assertEqual(profile.selected_profile()['version'], expected)

    def test_unknown_version_never_falls_back(self):
        with patch.dict(os.environ, {'FW_VERSION': '9.99'}):
            with self.assertRaisesRegex(ValueError, 'Unknown'):
                profile.selected_profile()
        with self.assertRaises(ValueError):
            profile.load_profile('../2.57')

    def test_inventory_is_not_runtime_enablement(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(profile, 'PROFILES', Path(directory)):
            inventory = Path(directory) / 'inventory'
            inventory.mkdir()
            (inventory / 'v9.99.json').write_text('{}')
            self.assertEqual(profile.available_versions(), [])
            with self.assertRaises(ValueError):
                profile.load_profile('9.99')

    def test_new_profile_requires_explicit_capabilities_and_acceptance(self):
        candidate = copy.deepcopy(profile.load_profile())
        candidate.update(version='9.99', main_os_version=999, capabilities=[], acceptance=[], full_scenarios=[])
        with tempfile.TemporaryDirectory() as directory, patch.object(profile, 'PROFILES', Path(directory)):
            path = Path(directory) / 'v9.99.json'
            path.write_text(json.dumps(candidate))
            loaded = profile.load_profile('9.99')
            self.assertEqual(profile.available_versions(), ['9.99'])
            self.assertFalse(profile.supports(loaded, 'usb_power'))
            with self.assertRaises(ValueError):
                profile.require_scenario(loaded, 'idle')
            candidate['acceptance'] = ['idle']
            path.write_text(json.dumps(candidate))
            profile.require_scenario(profile.load_profile('9.99'), 'idle')
            candidate['version'] = '2.57'
            path.write_text(json.dumps(candidate))
            with self.assertRaisesRegex(ValueError, 'identity'):
                profile.load_profile('9.99')

    def test_disposable_scenario_is_checked_before_execution(self):
        for env in ({}, {'CI_DISPOSABLE': '1', 'FW_VERSION': '2.40'},
                    {'CI_DISPOSABLE': '1', 'FW_VERSION': '9.99'}):
            with self.subTest(env=env), patch.dict(os.environ, env, clear=True):
                with self.assertRaises(RuntimeError):
                    require_acceptance('idle')
        with patch.dict(os.environ, {'CI_DISPOSABLE': '1', 'FW_VERSION': '2.57'}, clear=True):
            require_acceptance('idle')

    def test_shell_and_python_select_same_profile(self):
        repo = Path(__file__).resolve().parents[2]
        for override in ('', '2.40', '2.57'):
            env = {**os.environ, 'REPO': str(repo), 'FW_VERSION': override}
            output = subprocess.check_output(['bash', '-c',
                'source "$REPO/emulator/scripts/lib.sh"; printf "%s" "$FW_VERSION"'], env=env, text=True)
            with patch.dict(os.environ, env):
                self.assertEqual(output, profile.selected_version())

    def test_moved_diagnostics_are_build_specific(self):
        current = profile.load_profile('2.57')
        legacy = profile.load_profile('2.40')
        self.assertEqual(current['diagnostics']['ui']['storage']['sd'], [0x83a720, 4])
        self.assertEqual(current['diagnostics']['power']['usb_detected'], ['83a768', 1])
        self.assertNotIn('ui', legacy['diagnostics'])
        self.assertFalse(profile.supports(legacy, 'usb_power'))
        self.assertNotEqual(current['diagnostics']['network']['expected_callbacks'],
                            legacy['diagnostics']['network']['expected_callbacks'])

    def test_promoting_active_file_needs_no_script_edits(self):
        source = Path(__file__).resolve().parents[2]
        candidate = copy.deepcopy(profile.load_profile())
        candidate.update(version='9.99', main_os_version=999, capabilities=[], acceptance=[], full_scenarios=[])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / 'firmware'
            package.mkdir()
            for name in ('__init__.py', 'profile.py'):
                shutil.copyfile(source / 'firmware' / name, package / name)
            (package / 'active-version').write_text('9.99\n')
            (package / 'v9.99.json').write_text(json.dumps(candidate))
            env = {**os.environ, 'REPO': directory, 'PYTHONPATH': directory, 'FW_VERSION': ''}
            selected = subprocess.check_output([sys.executable, '-m', 'firmware.profile', 'get', 'version'],
                                               env=env, cwd=root, text=True).strip()
            shell = subprocess.check_output(['bash', '-c', 'source "$1"; printf "%s" "$FW_VERSION"',
                                             'test', str(source / 'emulator/scripts/lib.sh')], env=env, text=True)
            self.assertEqual((selected, shell), ('9.99', '9.99'))
            denied = subprocess.run([sys.executable, '-m', 'firmware.profile', 'supports', 'usb_power'],
                                    env=env, cwd=root, capture_output=True)
            self.assertEqual(denied.returncode, 1)

    def test_full_suite_never_silently_omits_an_unimplemented_scenario(self):
        candidate = copy.deepcopy(profile.load_profile())
        candidate.update(version='9.99', acceptance=['new-scenario'], full_scenarios=['new-scenario'])
        with tempfile.TemporaryDirectory() as directory, patch.object(profile, 'PROFILES', Path(directory)):
            (Path(directory) / 'v9.99.json').write_text(json.dumps(candidate))
            with self.assertRaisesRegex(ValueError, 'without a runner'):
                profile.load_profile('9.99')
        import re
        runner = (Path(__file__).resolve().parents[2] / 'ci/integration.sh').read_text()
        dispatch = set(re.findall(r'^if full_scenario ([\w-]+); then$', runner, re.MULTILINE))
        self.assertEqual(dispatch, profile.FULL_SCENARIOS)
