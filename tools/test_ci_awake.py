"""Safety/fixture coverage without firmware or guest processes."""
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ci'))
import awake_check


class AwakeFixtureTests(unittest.TestCase):
    def test_refuses_non_disposable_or_unreviewed_firmware(self):
        for env in ({}, {'CI_DISPOSABLE': '1', 'FW_VERSION': '2.40'},
                    {'FW_VERSION': '2.57'}):
            with patch.dict(os.environ, env, clear=True), patch.object(awake_check, 'validate') as validate:
                with self.assertRaises(RuntimeError):
                    awake_check.run(True)
                validate.assert_not_called()

    def test_refuses_running_guest(self):
        with patch.dict(os.environ, {'CI_DISPOSABLE': '1', 'FW_VERSION': '2.57'}), \
                patch.object(awake_check, 'validate'), patch.object(awake_check, 'Device') as device:
            device.return_value.processes.return_value = [123]
            with self.assertRaises(RuntimeError):
                awake_check.run(True)

    def test_configures_only_display_and_checks_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / 'usr/data/fiio/db/sysconfig.db'
            database.parent.mkdir(parents=True)
            with sqlite3.connect(database) as db:
                db.execute('CREATE TABLE SYSCONFIG (ID INTEGER, LIGTH_ON_TIME INTEGER, POWER_SAVE INTEGER)')
                db.execute('INSERT INTO SYSCONFIG VALUES (1,3,300)')
            with patch.dict(os.environ, {'CI_DISPOSABLE': '1', 'FW_VERSION': '2.57'}), \
                    patch.object(awake_check, 'ROOT', root), patch.object(awake_check, 'validate'), \
                    patch.object(awake_check, 'Device') as device, patch.object(awake_check, 'ui') as ui:
                device.return_value.processes.return_value = []
                awake_check.run(True)
                with sqlite3.connect(database) as db:
                    self.assertEqual(db.execute('SELECT * FROM SYSCONFIG').fetchall(), [(1, 7, 300)])
                ui.return_value = {'display_index': 7, 'display_seconds': 65535}
                awake_check.run(False)
                ui.assert_called_once()

    def test_unexpected_database_is_not_modified(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / 'usr/data/fiio/db/sysconfig.db'
            database.parent.mkdir(parents=True)
            with sqlite3.connect(database) as db:
                db.execute('CREATE TABLE SYSCONFIG (ID INTEGER, LIGTH_ON_TIME INTEGER)')
                db.execute('INSERT INTO SYSCONFIG VALUES (2,3)')
            with patch.dict(os.environ, {'CI_DISPOSABLE': '1', 'FW_VERSION': '2.57'}), \
                    patch.object(awake_check, 'ROOT', root), patch.object(awake_check, 'validate'), \
                    patch.object(awake_check, 'Device') as device:
                device.return_value.processes.return_value = []
                with self.assertRaises(RuntimeError):
                    awake_check.run(True)
            with sqlite3.connect(database) as db:
                self.assertEqual(db.execute('SELECT * FROM SYSCONFIG').fetchall(), [(2, 3)])
