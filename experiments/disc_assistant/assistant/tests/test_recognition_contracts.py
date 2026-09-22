"""Deployment constraints for the inactive multi-STT architecture contracts."""
from dataclasses import FrozenInstanceError
import unittest

from experiments.disc_assistant.assistant.recognition import RecognitionPlan


class RecognitionPlanTests(unittest.TestCase):
    def test_explicit_primary_and_shadow_are_independent_of_scheduling(self):
        for mode in ('sequential', 'parallel'):
            plan = RecognitionPlan(('sherpa', 'whisper'), 2000, mode=mode,
                                   max_parallel=2 if mode == 'parallel' else 1)
            self.assertEqual(plan.instances[0], 'sherpa')
            self.assertTrue(plan.shadow)
            with self.assertRaises(FrozenInstanceError):
                plan.shadow = False

    def test_rejects_unbounded_duplicate_and_inconsistent_schedules(self):
        for settings in (
            {'instances': ()}, {'instances': ('sherpa', 'sherpa'), 'mode': 'parallel'},
            {'instances': ('sherpa', 'whisper')},
            {'mode': 'sequential', 'instances': ('sherpa', 'whisper'), 'max_parallel': 2},
            {'mode': 'parallel', 'max_parallel': 2}, {'mode': 'all'},
            {'budget_ms': 0}, {'budget_ms': float('inf')}, {'budget_ms': True},
            {'max_parallel': True}, {'shadow': 'yes'},
        ):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                RecognitionPlan(**({'instances': ('sherpa',), 'budget_ms': 2000} | settings))
