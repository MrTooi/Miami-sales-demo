import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class RoutingTests(unittest.TestCase):
    def test_provider_vs_internal(self):
        data = json.loads((ROOT / 'agent_evals/routing_regressions.json').read_text())
        cases = data['cases']
        self.assertEqual(cases[0]['expected_primary'], 'integrations')
        self.assertEqual(cases[1]['expected_primary'], 'backend')
