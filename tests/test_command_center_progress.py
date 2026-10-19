from pathlib import Path
import unittest

from command_center.progress_logic import (
    ci_state,
    latest_review,
    latest_weekly_checklist,
    next_action,
    parse_build_steps,
    parse_checklist,
    progress,
    step_status,
)

ROOT = Path(__file__).resolve().parents[1]

CHECKLIST = """## Goal this week
Text.

## Owner (Alex) + Claude Code: building
**Decisions (Alex)**
- [x] Approve the plan
- [ ] Confirm the first customer type

**Ledger MVP**
- [ ] Data import

## Partner: customers and marketing
- [X] Finish the website
- [ ] Talk to 5-10 owners
  - How do you know which jobs make money?
"""


class ProgressLogicTests(unittest.TestCase):
    def test_checklist_groups_by_section_and_subheading(self):
        groups = parse_checklist(CHECKLIST)
        self.assertEqual(
            ["Owner (Alex) + Claude Code: building — Decisions (Alex)",
             "Owner (Alex) + Claude Code: building — Ledger MVP",
             "Partner: customers and marketing"],
            [g["title"] for g in groups],
        )
        self.assertEqual((1, 2), progress(groups[0]["items"]))
        self.assertEqual((1, 2), progress(groups[2]["items"]))
        # Plain sub-bullets are not checklist items.
        self.assertNotIn("How do you know", str(groups))

    def test_empty_or_missing_checklist(self):
        self.assertEqual([], parse_checklist(None))
        self.assertEqual((0, 0), progress([]))

    def test_latest_weekly_checklist_ignores_prs_and_other_issues(self):
        issues = [
            {"title": "Weekly checklist — Oct 13", "created_at": "2026-10-13T00:00:00Z"},
            {"title": "Weekly checklist — Oct 19", "created_at": "2026-10-18T00:00:00Z"},
            {"title": "Weekly checklist — PR", "created_at": "2026-10-19T00:00:00Z", "pull_request": {}},
            {"title": "Run final suites", "created_at": "2026-10-20T00:00:00Z"},
        ]
        self.assertEqual("Weekly checklist — Oct 19", latest_weekly_checklist(issues)["title"])
        self.assertIsNone(latest_weekly_checklist([]))

    def test_build_steps_come_from_the_merged_spec(self):
        spec = (ROOT / "docs" / "MVP_SPEC.md").read_text(encoding="utf-8")
        steps = parse_build_steps(spec)
        self.assertGreaterEqual(len(steps), 5)
        self.assertEqual(list(range(1, len(steps) + 1)), [s["number"] for s in steps])
        self.assertIn("CSV upload", steps[0]["title"])

    def test_step_status_needs_a_merged_step_pr(self):
        pulls = [
            {"title": "MarginX step 1: CSV upload", "state": "closed", "merged_at": "2026-10-20T00:00:00Z", "number": 1},
            {"title": "MarginX step 2: xlsx", "state": "open", "merged_at": None, "number": 2},
            {"title": "MarginX step 3: profit", "state": "closed", "merged_at": None, "number": 3},
            {"title": "docs: step 4 notes", "state": "closed", "merged_at": "2026-10-20T00:00:00Z", "number": 4},
        ]
        self.assertEqual("DONE", step_status(1, pulls)[0])
        self.assertEqual("IN PROGRESS", step_status(2, pulls)[0])
        self.assertEqual("NOT STARTED", step_status(3, pulls)[0])  # closed without merging
        self.assertEqual("NOT STARTED", step_status(4, pulls)[0])  # title doesn't follow the convention
        self.assertEqual("NOT STARTED", step_status(12, pulls)[0])

    def test_latest_review_reads_manual_automated_and_incomplete(self):
        comments = [
            {"created_at": "2026-10-19T01:00:00Z", "body": "**Verdict:** **FAIL** — do not merge", "html_url": "a"},
            {"created_at": "2026-10-19T02:00:00Z", "body": "## Fixes\nno verdict here", "html_url": "b"},
            {"created_at": "2026-10-19T03:00:00Z", "body": "**Verdict:** PASS WITH WARNINGS", "html_url": "c"},
        ]
        self.assertEqual("PASS WITH WARNINGS", latest_review(comments)["verdict"])
        incomplete = comments + [{"created_at": "2026-10-19T04:00:00Z", "body": "**Status: REVIEW INCOMPLETE — x**\n**Verdict:** PASS", "html_url": "d"}]
        self.assertEqual("INCOMPLETE", latest_review(incomplete)["verdict"])
        self.assertIsNone(latest_review([]))

    def test_latest_review_uses_the_header_verdict_not_quoted_examples(self):
        comment = {
            "created_at": "2026-10-19T04:36:19Z",
            "html_url": "x",
            "body": "## Re-review\n\n**Verdict: FAIL — one remaining edge case.**\n\n"
                    "This response would wrongly qualify:\n```text\n**Verdict:** PASS\n```",
        }
        self.assertEqual("FAIL", latest_review([comment])["verdict"])
        # A fix note that only mentions the format has no verdict.
        note = {"created_at": "2026-10-19T05:00:00Z", "html_url": "y",
                "body": "the first line is the one valid `**Verdict:**` line; anything else is REVIEW INCOMPLETE"}
        self.assertEqual("FAIL", latest_review([comment, note])["verdict"])
        self.assertEqual("x", latest_review([comment, note])["url"])

    def test_ci_state(self):
        self.assertEqual("UNKNOWN", ci_state(None))
        self.assertEqual("NO CHECKS", ci_state([]))
        self.assertEqual("RUNNING", ci_state([{"status": "in_progress"}]))
        self.assertEqual("FAILING", ci_state([{"status": "completed", "conclusion": "failure"}]))
        self.assertEqual("PASSING", ci_state([{"status": "completed", "conclusion": "success"}, {"status": "completed", "conclusion": "skipped"}]))

    def test_next_action_never_says_ready_without_a_fresh_passing_review_and_tests(self):
        passed = {"verdict": "PASS"}
        self.assertEqual("Ready for your merge decision", next_action(passed, "PASSING", True))
        self.assertEqual("Needs ChatGPT review", next_action(passed, "PASSING", False))
        self.assertEqual("Needs ChatGPT review", next_action(None, "PASSING", False))
        self.assertEqual("Claude: fix review findings", next_action({"verdict": "FAIL"}, "PASSING", True))
        self.assertEqual("Claude: fix review findings", next_action({"verdict": "INCOMPLETE"}, "PASSING", True))
        self.assertEqual("Claude: fix failing tests", next_action(passed, "FAILING", True))
        self.assertEqual("Waiting for tests", next_action(passed, "RUNNING", True))


if __name__ == "__main__":
    unittest.main()
