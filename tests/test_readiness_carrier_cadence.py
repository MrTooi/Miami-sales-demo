from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
CARRIER = ROOT / ".github" / "workflows" / "agent-operator.yml"


class ReadinessCarrierCadenceTests(unittest.TestCase):
    def test_schedule_offers_every_five_minute_slot_without_changing_event_type(self):
        text = CARRIER.read_text(encoding="utf-8")
        header = text.split("permissions:", 1)[0]
        expressions = re.findall(r"cron:\s*'([^']+)'", header)
        self.assertEqual(
            ["17,47 * * * *", "2,7,12,22,27,32,37,42,52,57 * * * *"],
            expressions,
        )
        minutes = set()
        for expression in expressions:
            minute_field, hour, day, month, weekday = expression.split()
            self.assertEqual((hour, day, month, weekday), ("*", "*", "*", "*"))
            minutes.update(int(value) for value in minute_field.split(","))
        self.assertEqual(set(range(2, 60, 5)), minutes)
        self.assertIn("schedule:", header)
        self.assertNotIn("repository_dispatch:", header)
        self.assertNotIn("pull_request:", header)

    def test_readiness_still_requires_genuine_schedule_event(self):
        text = CARRIER.read_text(encoding="utf-8")
        readiness = text.split("  final-readiness:\n", 1)[1]
        self.assertIn("if: github.event_name == 'schedule'", readiness)
        self.assertNotIn("workflow_dispatch", readiness)
        self.assertIn("uses: ./.github/workflows/agent-final-readiness-core.yml", readiness)


if __name__ == "__main__":
    unittest.main()
