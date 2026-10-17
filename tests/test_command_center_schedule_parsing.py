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


class RerunIsNotScheduleHealthTests(unittest.TestCase):
    def test_successful_rerun_in_current_slot_is_check_not_on_track(self):
        from command_center.status_logic import classify_schedule_slot

        slot = datetime(2026, 10, 17, 1, 17, tzinfo=timezone.utc)
        base = {"created_at": "2026-10-17T01:18:00Z", "status": "completed", "conclusion": "success"}
        state, _ = classify_schedule_slot(now=slot, expected_slot=slot, latest_run=dict(base, run_attempt=1),
                                          runs_error=False)
        self.assertEqual(state, "ON TRACK")
        state, note = classify_schedule_slot(now=slot, expected_slot=slot, latest_run=dict(base, run_attempt=2),
                                             runs_error=False)
        self.assertEqual(state, "CHECK")
        self.assertIn("rerun", note)


class LatestRunDisplayTests(unittest.TestCase):
    SLOT = datetime(2026, 10, 17, 1, 17, tzinfo=timezone.utc)
    CURRENT = {"created_at": "2026-10-17T01:18:00Z", "status": "completed", "conclusion": "success"}
    OLD = {"created_at": "2026-10-16T20:02:00Z", "status": "completed", "conclusion": "success"}

    def test_rerun_or_unknown_attempt_never_displays_success(self):
        from command_center.status_logic import latest_run_display

        for attempt in (2, 3, None, "1", 0):
            with self.subTest(attempt=attempt):
                value, tone, note = latest_run_display(dict(self.CURRENT, run_attempt=attempt), self.SLOT)
                self.assertEqual(value, "RERUN / CHECK")
                self.assertEqual(tone, "warn")
                self.assertIn(repr(attempt), note)
        value, tone, _ = latest_run_display(dict(self.CURRENT, run_attempt=1), self.SLOT)
        self.assertEqual((value, tone), ("SUCCESS", "info"))
        value, tone, _ = latest_run_display(dict(self.CURRENT, conclusion="failure", run_attempt=1), self.SLOT)
        self.assertEqual((value, tone), ("FAILURE", "warn"))
        self.assertEqual(latest_run_display(None, self.SLOT)[:2], ("UNKNOWN", "warn"))

    def test_old_attempt1_success_is_not_current_and_matches_late_scheduler(self):
        # ChatGPT round 2: Project Map must not show "LATE / CHECK" beside plain SUCCESS.
        from command_center.status_logic import classify_schedule_slot, latest_run_display

        old = dict(self.OLD, run_attempt=1)
        now = self.SLOT.replace(minute=50)
        state, _ = classify_schedule_slot(now=now, expected_slot=self.SLOT, latest_run=old, runs_error=False)
        self.assertEqual(state, "LATE / CHECK")
        value, tone, note = latest_run_display(old, self.SLOT)
        self.assertEqual((value, tone), ("NOT CURRENT", "warn"))
        self.assertIn("success", note)
        for slot in (None,):
            self.assertEqual(latest_run_display(dict(self.CURRENT, run_attempt=1), slot)[0], "NOT CURRENT")
        undated = {"status": "completed", "conclusion": "success", "run_attempt": 1}
        self.assertEqual(latest_run_display(undated, self.SLOT)[0], "NOT CURRENT")

    def test_display_tone_is_never_green(self):
        from command_center.status_logic import latest_run_display

        for run in (None, dict(self.CURRENT, run_attempt=1), dict(self.CURRENT, run_attempt=2), dict(self.OLD, run_attempt=1)):
            for slot in (self.SLOT, None):
                self.assertNotEqual(latest_run_display(run, slot)[1], "ok")

    def test_activity_list_always_discloses_reruns(self):
        from command_center.status_logic import activity_state_label

        self.assertEqual(activity_state_label({"conclusion": "success", "run_attempt": 1}), "success")
        self.assertEqual(activity_state_label({"conclusion": "success", "run_attempt": 2}), "success (rerun, attempt 2)")
        self.assertEqual(activity_state_label({"status": "in_progress"}), "in_progress (attempt unknown)")

    def test_missing_attempt_in_current_slot_is_check(self):
        from command_center.status_logic import classify_schedule_slot

        self.assertEqual(classify_schedule_slot(now=self.SLOT, expected_slot=self.SLOT, latest_run=self.CURRENT,
                                                runs_error=False)[0], "CHECK")

    def test_every_visible_run_status_goes_through_shared_helpers(self):
        app = (ROOT / "command_center/app.py").read_text(encoding="utf-8")
        page = (ROOT / "command_center/pages/1_Project_Map.py").read_text(encoding="utf-8")
        self.assertIn("latest_run_display(\n        latest_operator, previous_slot(fetched_at, operator_minutes())\n    )", app.replace("\r\n", "\n"))
        self.assertIn('card("Latest Scheduled Run", run_value, run_note, run_tone)', app)
        self.assertIn("latest_run_display(latest_operator, expected_slot)", page)
        self.assertIn('c4.metric("Latest schedule", latest_value', page)
        self.assertIn("state = html.escape(activity_state_label(run))", app)
        for source in (app, page):
            self.assertNotIn('latest_operator.get("conclusion")', source)
            self.assertNotIn('(latest_operator or {}).get("conclusion")', source)
            self.assertNotIn('str(run.get("conclusion") or run.get("status")', source)

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
