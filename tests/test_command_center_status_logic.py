from datetime import datetime, timedelta, timezone
import unittest

from command_center.status_logic import classify_schedule_slot


class CommandCenterStatusLogicTests(unittest.TestCase):
    def setUp(self):
        self.slot = datetime(2026, 10, 17, 1, 17, tzinfo=timezone.utc)
        self.now = self.slot + timedelta(minutes=5)

    def run_data(self, *, status="completed", conclusion="success", created_offset=1):
        created = self.slot + timedelta(minutes=created_offset)
        return {
            "created_at": created.isoformat().replace("+00:00", "Z"),
            "status": status,
            "conclusion": conclusion,
            "run_attempt": 1,
        }

    def test_successful_completed_current_slot_is_on_track(self):
        state, _ = classify_schedule_slot(
            now=self.now,
            expected_slot=self.slot,
            latest_run=self.run_data(),
            runs_error=False,
        )
        self.assertEqual("ON TRACK", state)

    def test_failed_or_cancelled_current_slot_is_check_not_green(self):
        for conclusion in ("failure", "cancelled"):
            state, _ = classify_schedule_slot(
                now=self.now,
                expected_slot=self.slot,
                latest_run=self.run_data(conclusion=conclusion),
                runs_error=False,
            )
            self.assertEqual("CHECK", state)

    def test_in_progress_current_slot_is_waiting(self):
        state, _ = classify_schedule_slot(
            now=self.now,
            expected_slot=self.slot,
            latest_run=self.run_data(status="in_progress", conclusion=""),
            runs_error=False,
        )
        self.assertEqual("WAITING", state)

    def test_actions_fetch_error_is_unknown(self):
        state, _ = classify_schedule_slot(
            now=self.now,
            expected_slot=self.slot,
            latest_run=None,
            runs_error=True,
        )
        self.assertEqual("UNKNOWN", state)

    def test_missing_cron_slot_is_unknown(self):
        state, _ = classify_schedule_slot(
            now=self.now,
            expected_slot=None,
            latest_run=None,
            runs_error=False,
        )
        self.assertEqual("UNKNOWN", state)

    def test_missing_current_event_waits_then_becomes_late(self):
        state, _ = classify_schedule_slot(
            now=self.slot + timedelta(minutes=10),
            expected_slot=self.slot,
            latest_run=None,
            runs_error=False,
            grace_minutes=20,
        )
        self.assertEqual("WAITING", state)
        state, _ = classify_schedule_slot(
            now=self.slot + timedelta(minutes=21),
            expected_slot=self.slot,
            latest_run=None,
            runs_error=False,
            grace_minutes=20,
        )
        self.assertEqual("LATE / CHECK", state)


if __name__ == "__main__":
    unittest.main()
