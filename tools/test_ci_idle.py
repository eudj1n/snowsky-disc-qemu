"""Firmware-free guards for the opt-in destructive-lifecycle CI fixture."""
import asyncio
import copy
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ci'))
import idle_check


class IdleFixtureTests(unittest.TestCase):
    def test_control_setup_gates_usb_abi_and_preserves_cable(self):
        script = Path(__file__).resolve().parents[1] / 'scripts/15_controls.sh'
        for version in ('2.57', '2.40'):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / 'rootfs'
                (root / 'dev').mkdir(parents=True)
                (root / 'emu').mkdir()
                battery = root / 'sys/class/power_supply/cw221X-bat'
                battery.mkdir(parents=True)
                (root / 'emu/usb-connected').write_text('1')
                for _ in range(2):
                    subprocess.run(['bash', str(script)], check=True,
                                   env={**os.environ, 'ROOTFS': str(root), 'FW_VERSION': version})
                    self.assertEqual((root / 'emu/usb-connected').read_text(), '1')
                    self.assertEqual((battery / 'status').read_text(), 'Charging\n')
                    self.assertEqual((root / 'emu/usb-power-supported').read_text(),
                                     '1' if version == '2.57' else '0')
                    for name in ('aw35615', 'sgm41513', 'jz_adc_aux_0', 'jz_adc_aux_1',
                                 'jz_adc_aux_2', 'jz_adc_aux_3'):
                        self.assertEqual((root / 'dev' / name).is_file(), version == '2.57')

    def test_scope_guard_precedes_firmware_access(self):
        for env in ({}, {'CI_DISPOSABLE': '1', 'FW_VERSION': '2.40'},
                    {'FW_VERSION': '2.57'}):
            with patch.dict(os.environ, env, clear=True), patch.object(idle_check, 'validate') as validate:
                with self.assertRaises(RuntimeError):
                    idle_check.configure(300)
                validate.assert_not_called()

    def test_refuses_running_guest_and_unreviewed_values(self):
        with patch.object(idle_check, 'require_disposable'), patch.object(idle_check, 'Device') as device:
            device.return_value.processes.return_value = [123]
            with self.assertRaises(RuntimeError):
                idle_check.configure(0)
            for value in (True, -1, 5, 301, '300'):
                with self.assertRaises(ValueError):
                    idle_check.configure(value)

    def test_fixture_only_changes_reviewed_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / 'usr/data/fiio/db/sysconfig.db'
            database.parent.mkdir(parents=True)
            with sqlite3.connect(database) as db:
                db.execute('CREATE TABLE SYSCONFIG (ID, LIGTH_ON_TIME, POWER_SAVE, VOLUME)')
                db.execute('INSERT INTO SYSCONFIG VALUES (1,7,300,42)')
            with patch.object(idle_check, 'require_disposable'), patch.object(idle_check, 'ROOT', root), \
                    patch.object(idle_check, 'Device') as device:
                device.return_value.processes.return_value = []
                for value in (0, 300):
                    idle_check.configure(value)
                    with sqlite3.connect(database) as db:
                        self.assertEqual(db.execute('SELECT * FROM SYSCONFIG').fetchall(),
                                         [(1, 3, value, 42)])
                with sqlite3.connect(database) as db:
                    db.execute('UPDATE SYSCONFIG SET ID=2')
                with self.assertRaises(RuntimeError):
                    idle_check.configure(0)
                with sqlite3.connect(database) as db:
                    self.assertEqual(db.execute('SELECT * FROM SYSCONFIG').fetchall(), [(2,3,300,42)])

    def test_quiet_trace_requires_elapsed_time_screen_off_and_live_paused_state(self):
        value = dict(screen=1, marker=0, state=2, connected=1, idle_limit=0,
                     idle_counter=0, sleep_limit=0, power_request='0')
        trace = [(0, value), (134.5, {**value, 'screen': 0, 'marker': 1})]
        idle_check.quiet_trace(trace)
        for key, bad in (('screen', 1), ('marker', 0), ('state', 1), ('connected', 0),
                         ('idle_counter', 1), ('power_request', '1')):
            changed = copy.deepcopy(trace)
            changed[-1][1][key] = bad
            with self.assertRaises(AssertionError):
                idle_check.quiet_trace(changed)
        with self.assertRaises(AssertionError):
            idle_check.quiet_trace([(0,value), (120,trace[-1][1])])

    def test_stopped_read_never_retries_or_accepts_success(self):
        with self.assertRaises(AssertionError):
            asyncio.run(idle_check.refused(lambda: {'soc_version': 257}))
        for error in (ConnectionError('closed'), TimeoutError('unavailable')):
            calls = []
            def fail():
                calls.append(1)
                raise error
            asyncio.run(idle_check.refused(fail))
            self.assertEqual(calls, [1])


if __name__ == '__main__':
    unittest.main()
