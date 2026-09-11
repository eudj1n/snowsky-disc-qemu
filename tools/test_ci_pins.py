from pathlib import Path
import re
import unittest


class ActionPinTests(unittest.TestCase):
    def test_external_actions_are_pinned_to_full_commit_sha(self):
        directory = Path(__file__).resolve().parents[1] / '.github/workflows'
        references = []
        for path in directory.glob('*.y*ml'):
            for reference in re.findall(r'^\s*-?\s*uses:\s*([^\s#]+)', path.read_text(), re.MULTILINE):
                if reference.startswith('./'):  # Local reusable code is pinned by checkout.
                    continue
                references.append(reference)
                with self.subTest(workflow=path.name, reference=reference):
                    self.assertRegex(reference, r'^[\w.-]+/[\w./-]+@[0-9a-f]{40}$')
        self.assertTrue(references, 'No external action references found')
