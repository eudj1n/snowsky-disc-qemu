from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from research.browser import bundle


class BrowserUITests(unittest.TestCase):
    def test_refresh_invalidates_module_graph_without_touching_vm_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            (work / 'www').mkdir()
            disk = work / 'www/kernel.bin'
            disk.write_bytes(b'untouched VM artifact')
            with patch.object(bundle, 'WORK', work):
                bundle.refresh_ui()
            html = (work / 'www/index.html').read_text()
            revision = re.search(r'app.js\?v=([a-f0-9]+)', html)[1]
            self.assertIn(f'power.mjs?v={revision}', (work / 'www/app.js').read_text())
            self.assertIn(f'worker.js?v={revision}', (work / 'www/app.js').read_text())
            self.assertIn(f'device.css?v={revision}', html)
            self.assertEqual((work / 'www/device.css').read_bytes(),
                             (bundle.REPO / 'viewer/static/device.css').read_bytes())
            self.assertEqual(disk.read_bytes(), b'untouched VM artifact')
