import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import urllib.error
import urllib.request

import check_ota


class OTACheckTests(unittest.TestCase):
    def record(self, source=257, target=257, recovery=18):
        return dict(last_version=source, new_version=target, recovery=recovery,
                    patch_url='https://private.invalid/package?signature=hidden')

    def catalog(self, *rows):
        return check_ota.parse_catalog(json.dumps(list(rows)).encode())

    def test_vendor_trailing_comma_and_strict_json(self):
        row = self.record()
        expected = self.catalog(row)
        self.assertEqual(check_ota.parse_catalog(
            ('[\n' + json.dumps(row) + ',\n \n]\n').encode()), expected)
        self.assertNotIn('patch_url', expected[0])

    def test_rejects_malformed_or_ambiguous_catalog(self):
        row = json.dumps(self.record()).encode()
        invalid = [b'[]', b'[', b'null', b'<html>error</html>',
                   b'[' + row + b',,]', b'[' + row + b'] garbage',
                   b'[' + row + row + b']', b'[' + row + b',' + row + b']',
                   b'[' + row[:-1] + b',}]',
                   b'[' + row[:-1] + b',"new_version":258}]',
                   b' ' * (check_ota.MAX_CATALOG + 1)]
        for data in invalid:
            with self.subTest(data=data[:30]), self.assertRaises(ValueError):
                check_ota.parse_catalog(data)

    def test_validates_types_versions_and_urls(self):
        for key, value in [('new_version', True), ('new_version', '258'),
                           ('new_version', 256), ('recovery', 0),
                           ('last_version', -1), ('new_version', 1000000),
                           ('patch_url', None), ('patch_url', 'http://example.com'),
                           ('patch_url', 'https://user:pass@example.com'),
                           ('patch_url', 'https://example.com/\nsecret')]:
            row = self.record()
            row[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.catalog(row)

    def test_does_not_rewrite_url_contents(self):
        row = self.record()
        row['patch_url'] = 'https://example.com/a,]'
        self.assertEqual(len(self.catalog(row)), 1)

    def test_source_selection_and_new_release_on_other_route(self):
        rows = self.catalog(self.record(240, 258), self.record())
        result = check_ota.evaluate(rows, {'main_os_version': 257, 'recovery_os_version': 18})
        self.assertEqual(result['target_version'], 257)
        self.assertFalse(result['update_available'])
        self.assertTrue(result['newer_release_available'])
        self.assertEqual(result['latest_version'], 258)

    def test_current_update_recovery_update_and_missing_route(self):
        profile = {'main_os_version': 257, 'recovery_os_version': 18}
        for target, recovery, available in [(257, 18, False), (258, 18, True), (257, 19, True)]:
            result = check_ota.evaluate(self.catalog(self.record(257, target, recovery)), profile)
            self.assertEqual(result['update_available'], available)
        with self.assertRaises(ValueError):
            check_ota.evaluate(self.catalog(self.record(240, 257)), profile)

    def test_network_failure_retries_then_fails(self):
        opener = MagicMock()
        opener.open.side_effect = urllib.error.URLError('private URL')
        with patch('check_ota.urllib.request.build_opener', return_value=opener), \
             patch('check_ota.time.sleep') as sleep, self.assertRaises(urllib.error.URLError):
            check_ota.fetch_catalog()
        self.assertEqual(opener.open.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_download_is_bounded_and_parsed(self):
        opener = MagicMock()
        response = opener.open.return_value.__enter__.return_value
        response.status = 200
        response.read.return_value = json.dumps([self.record()]).encode()
        with patch('check_ota.urllib.request.build_opener', return_value=opener):
            self.assertEqual(len(check_ota.fetch_catalog()), 1)
        response.read.assert_called_once_with(check_ota.MAX_CATALOG + 1)

    def test_redirect_cannot_downgrade_to_http(self):
        with self.assertRaises(ValueError):
            check_ota.HTTPSRedirect().redirect_request(
                urllib.request.Request(check_ota.CATALOG), None, 302, '', {}, 'http://example.com')

    def test_output_contains_only_sanitized_metadata(self):
        result = check_ota.evaluate(self.catalog(self.record(257, 258)),
                                    {'main_os_version': 257, 'recovery_os_version': 18})
        with tempfile.TemporaryDirectory() as temp:
            output, summary = Path(temp) / 'output', Path(temp) / 'summary'
            stdout = io.StringIO()
            with patch.dict(os.environ, {'GITHUB_OUTPUT': str(output),
                            'GITHUB_STEP_SUMMARY': str(summary), 'GITHUB_ACTIONS': 'true'}), \
                 contextlib.redirect_stdout(stdout):
                check_ota.report(result)
            all_text = stdout.getvalue() + output.read_text() + summary.read_text()
            self.assertIn('update_available=true', output.read_text())
            self.assertIn('::warning title=New SNOWSKY DISC firmware', stdout.getvalue())
            self.assertIn('| Offered to this profile | 258 | 18 |', summary.read_text())
            self.assertNotIn('private.invalid', all_text)
            self.assertNotIn('signature', all_text)

    def test_cli_suppresses_error_details(self):
        stderr = io.StringIO()
        with patch('sys.argv', ['check_ota.py']), \
             patch('check_ota.fetch_catalog', side_effect=ValueError('https://private.invalid/secret')), \
             contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as caught:
            check_ota.main()
        self.assertEqual(caught.exception.code, 1)
        self.assertNotIn('private.invalid', stderr.getvalue())
        self.assertIn('OTA check failed', stderr.getvalue())


if __name__ == '__main__':
    unittest.main()
