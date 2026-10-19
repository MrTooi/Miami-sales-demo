from pathlib import Path
import unittest

from command_center.progress_logic import (
    UNIT_STEP_LABEL,
    ci_state,
    classify_review,
    latest_weekly_checklist,
    next_action,
    parse_build_steps,
    parse_checklist,
    progress,
    review_for_head,
    step_status,
)

ROOT = Path(__file__).resolve().parents[1]
HEAD = "a3905445ad07ffa1956c2b2345ab2dfb26e06ee6"
OLD = "4ae7bcea78a163c923cc32c9d46a54e672dabefa"

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


def automated(sha, status="qualifying automated review — PASS.", author="github-actions[bot]", at="2026-10-19T05:00:00Z"):
    body = (
        "## Automated ChatGPT review (D-004)\n\n"
        f"Model: `m` · Reviewed commit: `{sha}` · Diff truncated: no\n\n**Status: {status}** more text\n\n---\n\n**Verdict:** PASS"
    )
    return {"user": {"login": author}, "created_at": at, "html_url": "auto", "body": body}


def manual(sha, verdict="PASS WITH WARNINGS", at="2026-10-19T05:00:00Z"):
    body = f"## Independent manual ChatGPT re-review — PR #97 at `{sha}`\n\n**Verdict: {verdict} — notes.**"
    return {"user": {"login": "MrTooi"}, "created_at": at, "html_url": "manual", "body": body}


def run(name="unit-tests", status="completed", conclusion="success"):
    return {"name": name, "status": status, "conclusion": conclusion}


class ChecklistAndStepsTests(unittest.TestCase):
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
        steps = parse_build_steps((ROOT / "docs" / "MVP_SPEC.md").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(steps), 5)
        self.assertEqual(list(range(1, len(steps) + 1)), [s["number"] for s in steps])
        self.assertIn("CSV upload", steps[0]["title"])

    def test_merged_step_pr_is_never_reported_as_done(self):
        pulls = [
            # Merged but only touched a README: still only "merged, unverified".
            {"title": "MarginX step 1: README tweak", "state": "closed", "merged_at": "2026-10-20T00:00:00Z", "number": 1},
            {"title": "MarginX step 2: xlsx", "state": "open", "merged_at": None, "number": 2},
            {"title": "MarginX step 3: profit", "state": "closed", "merged_at": None, "number": 3},
            {"title": "docs: step 4 notes", "state": "closed", "merged_at": "2026-10-20T00:00:00Z", "number": 4},
        ]
        self.assertEqual(UNIT_STEP_LABEL, step_status(1, pulls)[0])
        self.assertIn("unverified", UNIT_STEP_LABEL)
        self.assertNotEqual("DONE", step_status(1, pulls)[0])
        self.assertEqual("IN PROGRESS", step_status(2, pulls)[0])
        self.assertEqual("NOT STARTED", step_status(3, pulls)[0])
        self.assertEqual("NOT STARTED", step_status(4, pulls)[0])

    def test_absent_step_is_unknown_when_pr_list_is_incomplete(self):
        pulls = [{"title": "MarginX step 2: xlsx", "state": "open", "merged_at": None, "number": 2}]
        self.assertEqual("UNKNOWN", step_status(1, pulls, complete=False)[0])
        # Evidence that is present still counts.
        self.assertEqual("IN PROGRESS", step_status(2, pulls, complete=False)[0])


class ReviewBindingTests(unittest.TestCase):
    def test_verified_automated_pass_on_exact_head_is_ready(self):
        review = review_for_head([automated(HEAD)], HEAD)
        self.assertEqual(("automated", "PASS"), (review["kind"], review["verdict"]))
        self.assertEqual("Ready for your merge decision", next_action(review, "PASSING"))

    def test_quoted_or_fix_note_pass_is_not_a_review(self):
        quoted = {"user": {"login": "MrTooi"}, "created_at": "2026-10-19T06:00:00Z", "html_url": "q",
                  "body": f"## Fix notes for `{HEAD}`\n\nThis would wrongly qualify:\n```\n**Verdict:** PASS\n```"}
        self.assertIsNone(classify_review(quoted))
        self.assertIsNone(review_for_head([quoted], HEAD))
        self.assertEqual("Needs ChatGPT review of the current commit", next_action(None, "PASSING"))

    def test_spoofed_automated_comment_from_another_author_is_ignored(self):
        self.assertIsNone(review_for_head([automated(HEAD, author="MrTooi")], HEAD))

    def test_pass_on_an_older_commit_does_not_cover_a_new_head(self):
        comments = [automated(OLD, at="2026-10-19T09:00:00Z"), manual(OLD, "PASS", at="2026-10-19T09:00:00Z")]
        self.assertIsNone(review_for_head(comments, HEAD))

    def test_newer_fail_on_head_overrides_older_pass_on_head(self):
        comments = [automated(HEAD, at="2026-10-19T05:00:00Z"), manual(HEAD, "FAIL", at="2026-10-19T06:00:00Z")]
        self.assertEqual("Claude: fix review findings", next_action(review_for_head(comments, HEAD), "PASSING"))

    def test_review_incomplete_is_never_ready(self):
        review = review_for_head([automated(HEAD, status="REVIEW INCOMPLETE — does not count")], HEAD)
        self.assertEqual("INCOMPLETE", review["verdict"])
        self.assertEqual("Claude: fix review findings", next_action(review, "PASSING"))

    def test_manual_pass_on_head_is_not_green_ready(self):
        review = review_for_head([manual(HEAD, "PASS WITH WARNINGS")], HEAD)
        self.assertEqual("manual", review["kind"])
        action = next_action(review, "PASSING")
        self.assertNotEqual("Ready for your merge decision", action)
        self.assertIn("confirm", action)

    def test_manual_header_variants_are_recognised(self):
        for heading in (
            f"## Independent ChatGPT manual re-review — PR #97 at `{HEAD}`",
            f"## Independent manual ChatGPT re-review — PR #97 at `{HEAD}`",
            f"## Independent ChatGPT review — PR #97 (`{HEAD[:7]}`)",
        ):
            with self.subTest(heading):
                comment = {"user": {"login": "MrTooi"}, "created_at": "x", "html_url": "h",
                           "body": heading + "\n\n**Verdict: PASS WITH WARNINGS. Resolved.**"}
                self.assertEqual(("manual", "PASS WITH WARNINGS"),
                                 (classify_review(comment)["kind"], classify_review(comment)["verdict"]))
        fix_note = {"user": {"login": "MrTooi"}, "created_at": "x", "html_url": "f",
                    "body": f"## Fix for the second ChatGPT re-review FAIL, now at `{HEAD[:7]}` (Claude Code)\n\nPASS"}
        self.assertIsNone(classify_review(fix_note))

    def test_manual_review_uses_header_verdict_not_quoted_examples(self):
        heading = f"## Independent ChatGPT review — PR #98 at `{HEAD}`\n\n"
        quoted_first = heading + "This would wrongly pass:\n```text\n**Verdict:** PASS\n```\n\n**Verdict: FAIL**"
        # The verdict must come before any fenced block; a quoted PASS first leaves no header verdict.
        self.assertIsNone(classify_review({"body": quoted_first, "user": {}}))
        fail_then_quote = heading + "**Verdict: FAIL.**\n\nExample:\n```\n**Verdict:** PASS\n```"
        self.assertEqual("FAIL", classify_review({"body": fail_then_quote, "user": {}})["verdict"])

    def test_conflicting_manual_verdicts_are_ignored(self):
        body = f"## Independent ChatGPT review — PR #98 at `{HEAD}`\n\n**Verdict: PASS**\n\n**Verdict: FAIL**"
        self.assertIsNone(classify_review({"body": body, "user": {}}))

    def test_bom_only_or_empty_comment_is_safe(self):
        for body in ("﻿", "", "  ﻿ \n", None):
            with self.subTest(body=body):
                self.assertIsNone(classify_review({"body": body, "user": {}}))
        self.assertIsNone(review_for_head([{"body": "﻿", "user": {}}], HEAD))

    def test_automated_review_needs_the_full_sha(self):
        self.assertIsNone(review_for_head([automated(HEAD[:7])], HEAD))
        self.assertIsNone(review_for_head([automated(HEAD[:39])], HEAD))
        self.assertEqual("automated", review_for_head([automated(HEAD)], HEAD)["kind"])

    def test_short_or_missing_sha_never_matches(self):
        self.assertIsNone(review_for_head([manual("a39")], HEAD))
        no_sha = {"user": {"login": "MrTooi"}, "created_at": "x", "html_url": "n",
                  "body": "## Independent ChatGPT review — PR #97\n\n**Verdict: PASS**"}
        self.assertIsNone(classify_review(no_sha))


class CiStateTests(unittest.TestCase):
    def test_passing_needs_a_successful_required_check(self):
        self.assertEqual("PASSING", ci_state([run(), run(), run("ChatGPT review", conclusion="skipped")]))

    def test_no_successful_test_is_never_passing(self):
        self.assertEqual("UNKNOWN", ci_state([run(conclusion="skipped")]))
        self.assertEqual("UNKNOWN", ci_state([run(conclusion="neutral"), run(conclusion="neutral")]))
        self.assertEqual("UNKNOWN", ci_state([run(conclusion=None)]))
        self.assertEqual("UNKNOWN", ci_state([run(), run(conclusion="skipped")]))
        self.assertEqual("UNKNOWN", ci_state([run("lint")]))  # required check missing
        self.assertEqual("UNKNOWN", ci_state([]))
        self.assertEqual("UNKNOWN", ci_state(None))

    def test_incomplete_check_list_is_unknown(self):
        self.assertEqual("UNKNOWN", ci_state([run()], total_count=150))

    def test_failures_and_running(self):
        self.assertEqual("FAILING", ci_state([run(), run(conclusion="failure")]))
        self.assertEqual("RUNNING", ci_state([run(status="in_progress", conclusion=None)]))
        # A failing non-required job does not mark the tests as failing.
        self.assertEqual("PASSING", ci_state([run(), run("ChatGPT PR review", conclusion="failure")]))

    def test_unknown_tests_never_say_ready(self):
        review = review_for_head([automated(HEAD)], HEAD)
        self.assertNotEqual("Ready for your merge decision", next_action(review, "UNKNOWN"))
        self.assertEqual("Claude: fix failing tests", next_action(review, "FAILING"))


if __name__ == "__main__":
    unittest.main()
