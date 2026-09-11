"""CI must fail, not go green with missing optional test dependencies."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
suite = unittest.defaultTestLoader.discover('tools', pattern='test_*.py')
result = unittest.TextTestRunner(verbosity=2).run(suite)
if result.skipped:
    print('CI forbids skipped tests; install dependencies from docker/Dockerfile.', file=sys.stderr)
sys.exit(not result.wasSuccessful() or bool(result.skipped) or result.testsRun == 0)
