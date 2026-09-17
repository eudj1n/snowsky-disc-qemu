import contextlib
import io
import os
import subprocess
import unittest
from unittest.mock import patch

from firmware.tools import notify_ota


class OTANotificationTests(unittest.TestCase):
    def test_no_api_calls_when_no_new_release(self):
        with patch('firmware.tools.notify_ota.api') as api:
            self.assertEqual(notify_ota.ensure_issue('owner/repo', (257, 18), (257, 18)), (None, False))
            self.assertEqual(notify_ota.ensure_issue('owner/repo', (257, 18), (240, 17)), (None, False))
        api.assert_not_called()

    def test_create_with_manual_process_and_stable_marker(self):
        with patch('firmware.tools.notify_ota.api', side_effect=[[[]], {'number': 5}]) as api:
            self.assertEqual(notify_ota.ensure_issue('owner/repo', (257, 18), (258, 19)), (5, True))
        args, body = api.call_args.args
        self.assertIn('POST', args)
        self.assertIn('V2.58 / recovery 19', body['title'])
        self.assertIn('<!-- snowsky-disc-ota:258:19 -->', body['body'])
        self.assertIn('Close this issue manually', body['body'])
        self.assertIn('Refs #<issue>', body['body'])
        self.assertIn('single-active-firmware policy', body['body'])
        self.assertIn('final validated release before promoting', body['body'])
        self.assertIn('OTA detection alone does not replace', body['body'])
        self.assertNotIn('FIFO', body['body'])
        self.assertNotIn('fourth supported', body['body'])
        self.assertNotIn('patch_url', body['body'])

    def test_open_and_closed_issues_on_later_pages_prevent_duplicates(self):
        for state in ('open', 'closed'):
            pages = [[{'number': 2, 'body': None}], [
                {'number': 5, 'state': state, 'body': '<!-- snowsky-disc-ota:258:19 -->'}]]
            with self.subTest(state=state), patch('firmware.tools.notify_ota.api', return_value=pages) as api:
                self.assertEqual(notify_ota.ensure_issue('owner/repo', (257, 18), (258, 19)), (5, False))
                self.assertEqual(api.call_count, 1)
                self.assertIn('state=all', api.call_args.args[0][0])

    def test_recovery_only_release_and_pr_marker(self):
        pages = [[{'number': 2, 'body': '<!-- snowsky-disc-ota:257:19 -->', 'pull_request': {}}]]
        with patch('firmware.tools.notify_ota.api', side_effect=[pages, {'number': 6}]) as api:
            self.assertEqual(notify_ota.ensure_issue('owner/repo', (257, 18), (257, 19)), (6, True))
        self.assertIn('<!-- snowsky-disc-ota:257:19 -->', api.call_args.args[1]['body'])

    def test_failed_listing_never_creates_issue(self):
        with patch('firmware.tools.notify_ota.api', side_effect=RuntimeError('API error')) as api, \
             self.assertRaises(RuntimeError):
            notify_ota.ensure_issue('owner/repo', (257, 18), (258, 19))
        self.assertEqual(api.call_count, 1)

    def test_invalid_metadata_cannot_become_issue_content(self):
        with patch('firmware.tools.notify_ota.api') as api:
            for repo, latest in [('owner/repo/other', (258, 19)), ('owner/repo', ('258\ntext', 19)),
                                 ('owner/repo', (True, 19)), ('owner/repo', (258, 0))]:
                with self.subTest(repo=repo, latest=latest), self.assertRaises(ValueError):
                    notify_ota.ensure_issue(repo, (257, 18), latest)
        api.assert_not_called()

    def test_api_uses_structured_stdin_and_fixed_github_host(self):
        result = subprocess.CompletedProcess([], 0, '{"number":7}', '')
        with patch('firmware.tools.notify_ota.subprocess.run', return_value=result) as run:
            self.assertEqual(notify_ota.api(['repos/owner/repo/issues', '--input', '-'],
                                          {'body': 'literal `text`\nnext line'}), {'number': 7})
        self.assertEqual(run.call_args.args[0][:4], ['gh', 'api', '--hostname', 'github.com'])
        self.assertNotIn('shell', run.call_args.kwargs)

    def test_cli_error_is_sanitized(self):
        env = {'GH_REPO': 'owner/repo', 'OTA_CURRENT_VERSION': '257', 'OTA_CURRENT_RECOVERY': '18',
               'OTA_LATEST_VERSION': '258', 'OTA_LATEST_RECOVERY': '19'}
        stderr = io.StringIO()
        with patch.dict(os.environ, env), patch('firmware.tools.notify_ota.ensure_issue', side_effect=RuntimeError('secret')), \
             contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit):
            notify_ota.main()
        self.assertNotIn('secret', stderr.getvalue())


if __name__ == '__main__':
    unittest.main()
