"""Behavior tests for Command Center cron parsing and slot math (PR #80 review blocker)."""
import unittest
from datetime import datetime, timezone
from pathlib import Path

from command_center.status_logic import next_slot, parse_cron_minutes, previous_slot

ROOT = Path(__file__).resolve().parents[1]
FIVE_MINUTE = [2, 7, 12, 17, 22, 27, 32, 37, 42, 47, 52, 57]


class CronParsingTests(unittest.TestCase):
    def test_current_two_line_operator_schedule_is_fully_parsed(self):
        text = (
            "on:\n  workflow_dispatch:\n  schedule:\n"
            "    - cron: '17,47 * * * *'\n"
            "    - cron: '2,7,12,22,27,32,37,42,52,57 * * * *'\n"
        )
        self.assertEqual(parse_cron_minutes(text), FIVE_MINUTE)

    def test_live_operator_workflow_parses_to_every_five_minutes(self):
        text = (ROOT / ".github/workflows/agent-operator.yml").read_text(encoding="utf-8")
        self.assertEqual(parse_cron_minutes(text), FIVE_MINUTE)

    def test_quoting_variants_and_single_line(self):
        self.assertEqual(parse_cron_minutes('- cron: "5 * * * *"'), [5])
        self.assertEqual(parse_cron_minutes("- cron: 5,35 * * * *"), [5, 35])

    def test_any_unrecognised_cron_line_makes_schedule_unknown(self):
        for bad in (
            "*/5 * * * *",
            "2-57/5 * * * *",
            "17 3 * * *",
            "17 * * * 1-5",
            "60 * * * *",
            "17,x * * * *",
            "",
        ):
            with self.subTest(bad=bad):
                text = f"    - cron: '17,47 * * * *'\n    - cron: '{bad}'\n"
                self.assertIsNone(parse_cron_minutes(text))

    def test_missing_text_or_no_cron_is_unknown(self):
        self.assertIsNone(parse_cron_minutes(None))
        self.assertIsNone(parse_cron_minutes(""))
        self.assertIsNone(parse_cron_minutes("on:\n  workflow_dispatch:\n"))


class SlotTests(unittest.TestCase):
    def at(self, hour, minute, second=0):
        return datetime(2026, 10, 17, hour, minute, second, tzinfo=timezone.utc)

    def test_previous_slot_uses_full_five_minute_schedule(self):
        self.assertEqual(previous_slot(self.at(1, 25), FIVE_MINUTE), self.at(1, 22))
        self.assertEqual(previous_slot(self.at(1, 22), FIVE_MINUTE), self.at(1, 22))
        self.assertEqual(previous_slot(self.at(1, 1), FIVE_MINUTE), self.at(0, 57))

    def test_next_slot_uses_full_five_minute_schedule(self):
        self.assertEqual(next_slot(self.at(1, 25), FIVE_MINUTE), self.at(1, 27))
        self.assertEqual(next_slot(self.at(1, 27), FIVE_MINUTE), self.at(1, 32))
        self.assertEqual(next_slot(self.at(1, 58), FIVE_MINUTE), self.at(2, 2))

    def test_first_line_only_parsing_would_have_reported_a_stale_slot(self):
        # Regression for the PR #80 BLOCK: reading only '17,47' made the expected
        # slot up to 30 minutes stale and delayed LATE detection.
        self.assertEqual(previous_slot(self.at(1, 45), [17, 47]), self.at(1, 17))
        self.assertEqual(previous_slot(self.at(1, 45), FIVE_MINUTE), self.at(1, 42))

    def test_unknown_schedule_yields_no_slot(self):
        self.assertIsNone(previous_slot(self.at(1, 25), None))
        self.assertIsNone(next_slot(self.at(1, 25), []))


class PagesUseSharedParserTests(unittest.TestCase):
    def test_no_page_keeps_a_private_first_match_cron_parser(self):
        for rel in ("command_center/app.py", "command_center/pages/1_Project_Map.py"):
            source = (ROOT / rel).read_text(encoding="utf-8")
            with self.subTest(page=rel):
                self.assertIn("parse_cron_minutes(", source)
                self.assertNotIn("re.search(", source)
                self.assertIn("sys.path.insert(0, _REPO_ROOT)", source)


if __name__ == "__main__":
    unittest.main()
