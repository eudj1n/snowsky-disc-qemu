from pathlib import Path
import re
import unittest


class ActionPinTests(unittest.TestCase):
    def test_external_actions_are_pinned_to_full_commit_sha(self):
        directory = Path(__file__).resolve().parents[2] / '.github/workflows'
        references = []
        for path in directory.glob('*.y*ml'):
            for reference in re.findall(r'^\s*-?\s*uses:\s*([^\s#]+)', path.read_text(), re.MULTILINE):
                if reference.startswith('./'):  # Local reusable code is pinned by checkout.
                    continue
                references.append(reference)
                with self.subTest(workflow=path.name, reference=reference):
                    self.assertRegex(reference, r'^[\w.-]+/[\w./-]+@[0-9a-f]{40}$')
        self.assertTrue(references, 'No external action references found')


class FirmwareWorkflowPolicyTests(unittest.TestCase):
    def setUp(self):
        self.workflow = (Path(__file__).resolve().parents[2] /
                         '.github/workflows/firmware.yml').read_text()

    def test_only_active_profile_and_its_secret_are_used(self):
        self.assertIn('cat firmware/active-version', self.workflow)
        self.assertIn('python3 -m firmware.profile get url_secret', self.workflow)
        self.assertIn('FIRMWARE_URL: ${{ secrets[steps.firmware.outputs.url_secret] }}', self.workflow)
        self.assertNotRegex(self.workflow, r'FIRMWARE_V\d+_URL')
        self.assertNotRegex(self.workflow, r"FW_VERSION: ['\"]\d+\.\d+")
        self.assertNotIn('toJSON(secrets)', self.workflow)
        self.assertNotIn('inputs.version', self.workflow)
        self.assertNotRegex(self.workflow, re.compile(r'^\s+inputs:', re.MULTILINE))

    def test_firmware_execution_is_manual_on_trusted_branch_only(self):
        triggers = self.workflow.split('on:\n', 1)[1].split('permissions:', 1)[0]
        self.assertEqual(triggers.strip(), 'workflow_dispatch:')
        self.assertIn("if: github.ref == 'refs/heads/2.x'", self.workflow)
        self.assertIn('permissions:\n  contents: read\n', self.workflow)
        self.assertNotIn('pull_request_target', self.workflow)

    def test_integration_still_runs_firmware_free_checks_and_full_suite(self):
        self.assertIn('bash /repo/ci/test.sh', self.workflow)
        self.assertIn('bash ci/integration.sh "$RUNNER_TEMP/snowsky-disc-ota"', self.workflow)
        self.assertNotIn('CI_SCENARIO=', self.workflow)
        self.assertIn('group: firmware-active', self.workflow)
