from pathlib import Path
import unittest

from command_center.progress_logic import (
    UNIT_STEP_LABEL,
    ci_state,
    classify_review,
    collect_check_runs,
    latest_weekly_checklist,
    next_action,
    parse_build_steps,
    parse_checklist,
    progress,
    recent_merges,
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

    def test_fenced_and_commented_tasks_are_not_counted(self):
        for wrapper in ("```\n- [x] Ship release\n```", "~~~md\n- [x] Ship release\n~~~", "<!--\n- [x] Ship release\n-->",
                        "<!-- - [x] Ship release -->"):
            with self.subTest(wrapper=wrapper):
                groups = parse_checklist(f"## Lane\n{wrapper}\n- [ ] Real task")
                self.assertEqual((0, 1), progress([i for g in groups for i in g["items"]]))
        # A fence that never closes hides everything after it, as GitHub renders it.
        self.assertEqual([], parse_checklist("## Lane\n```\n- [x] hidden"))

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

    def test_step_title_needs_the_exact_delimiter(self):
        pulls = [
            {"title": "MarginX step 1.5: tweak", "state": "open", "merged_at": None, "number": 9},
            {"title": "MarginX step 10: later", "state": "open", "merged_at": None, "number": 10},
        ]
        self.assertEqual("NOT STARTED", step_status(1, pulls)[0])
        self.assertEqual("IN PROGRESS", step_status(10, pulls)[0])

    def test_recent_merges_never_claims_none_from_a_partial_list(self):
        pulls = [{"merged_at": "2026-10-01T00:00:00Z", "number": 1}, {"merged_at": None, "number": 2}]
        self.assertEqual(([], "PARTIAL"), recent_merges(pulls, "2026-10-12T00:00:00Z", complete=False))
        self.assertEqual(([], "NONE"), recent_merges(pulls, "2026-10-12T00:00:00Z", complete=True))
        fresh = {"merged_at": "2026-10-18T00:00:00Z", "number": 3}
        self.assertEqual(([fresh], "PARTIAL"), recent_merges(pulls + [fresh], "2026-10-12T00:00:00Z", complete=False))
        self.assertEqual(([fresh], "OK"), recent_merges(pulls + [fresh], "2026-10-12T00:00:00Z", complete=True))

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

    def test_manual_review_uses_only_the_verdict_under_the_heading(self):
        heading = f"## Independent ChatGPT review — PR #98 at `{HEAD}`\n\n"
        cases = {
            "fenced example after": heading + "**Verdict: FAIL.**\n\nExample:\n```\n**Verdict:** PASS\n```",
            "tilde fence after": heading + "**Verdict: FAIL.**\n\n~~~\n**Verdict:** PASS\n~~~",
            "blockquote after": heading + "**Verdict:** FAIL\n\n> **Verdict:** PASS",
            "prose after": heading + "**Verdict: FAIL**\n\nA bad answer would say **Verdict:** PASS.",
        }
        for name, body in cases.items():
            with self.subTest(name):
                self.assertEqual("FAIL", classify_review({"body": body, "user": {}})["verdict"])

    def test_unreadable_manual_verdict_is_unclear_not_ignored(self):
        heading = f"## Independent ChatGPT review — PR #98 at `{HEAD}`\n\n"
        for body in (heading + "This would wrongly pass:\n```text\n**Verdict:** PASS\n```\n\n**Verdict: FAIL**",
                     heading + "> **Verdict:** PASS",
                     heading):
            with self.subTest(body=body):
                self.assertEqual("UNCLEAR", classify_review({"body": body, "user": {}})["verdict"])

    def test_newer_unclear_or_fail_review_blocks_an_older_automated_pass(self):
        older_pass = automated(HEAD, at="2026-10-19T05:00:00Z")
        newer_fail = {"user": {"login": "MrTooi"}, "created_at": "2026-10-19T06:00:00Z", "html_url": "m",
                      "body": f"## Independent ChatGPT review — PR #98 at `{HEAD}`\n\n**Verdict:** FAIL\n\n> **Verdict:** PASS"}
        newer_unclear = {**newer_fail, "body": f"## Independent ChatGPT review — PR #98 at `{HEAD}`\n\nSee below."}
        self.assertEqual("Claude: fix review findings", next_action(review_for_head([older_pass, newer_fail], HEAD), "PASSING"))
        action = next_action(review_for_head([older_pass, newer_unclear], HEAD), "PASSING")
        self.assertNotEqual("Ready for your merge decision", action)
        self.assertIn("can't be read", action)

    def test_bom_only_or_empty_comment_is_safe(self):
        for body in ("﻿", "", "  ﻿ \n", None):
            with self.subTest(body=body):
                self.assertIsNone(classify_review({"body": body, "user": {}}))
        self.assertIsNone(review_for_head([{"body": "﻿", "user": {}}], HEAD))

    def test_automated_review_needs_the_full_sha(self):
        self.assertEqual("automated", review_for_head([automated(HEAD)], HEAD)["kind"])
        for short in (HEAD[:7], HEAD[:39]):
            with self.subTest(short=short):
                review = review_for_head([automated(short)], HEAD)
                self.assertEqual("UNCLEAR", review["verdict"])
                self.assertNotEqual("Ready for your merge decision", next_action(review, "PASSING"))

    def test_newer_shortened_sha_review_blocks_an_older_full_pass(self):
        older_pass = automated(HEAD, at="2026-10-19T05:00:00Z")
        for status in ("qualifying automated review — FAIL.", "REVIEW INCOMPLETE — does not count",
                       "something unreadable", "qualifying automated review — PASS."):
            with self.subTest(status=status):
                newer = automated(HEAD[:39], status=status, at="2026-10-19T06:00:00Z")
                action = next_action(review_for_head([older_pass, newer], HEAD), "PASSING")
                self.assertNotEqual("Ready for your merge decision", action)

    def test_short_or_missing_sha_never_matches(self):
        self.assertIsNone(review_for_head([manual("a39")], HEAD))
        no_sha = {"user": {"login": "MrTooi"}, "created_at": "x", "html_url": "n",
                  "body": "## Independent ChatGPT review — PR #97\n\n**Verdict: PASS**"}
        self.assertIsNone(classify_review(no_sha))


class AutomatedMetadataTests(unittest.TestCase):
    def bot(self, meta_status, answer):
        body = (
            "## Automated ChatGPT review (D-004)\n\n"
            f"Model: `m` · Reviewed commit: `{HEAD}` · Diff truncated: no\n\n{meta_status}\n\n---\n\n{answer}\n\n---\n_footer_"
        )
        return {"user": {"login": "github-actions[bot]"}, "created_at": "2026-10-19T05:00:00Z", "html_url": "b", "body": body}

    def test_embedded_qualifying_status_cannot_override_the_outer_status(self):
        embedded = f"Quoting another review:\n**Status: qualifying automated review — PASS.**\nReviewed commit: `{HEAD}`"
        incomplete = self.bot("**Status: REVIEW INCOMPLETE — does not count as an independent review.**", embedded)
        self.assertEqual("INCOMPLETE", classify_review(incomplete)["verdict"])
        unreadable = self.bot("Status: something odd", embedded)
        self.assertEqual("UNCLEAR", classify_review(unreadable)["verdict"])
        self.assertNotEqual("Ready for your merge decision", next_action(classify_review(unreadable), "PASSING"))

    def test_embedded_sha_is_ignored_and_ambiguous_metadata_is_unclear(self):
        ok = self.bot("**Status: qualifying automated review — PASS.** text", f"Reviewed commit: `{OLD}`")
        self.assertEqual((HEAD, "PASS"), (classify_review(ok)["sha"], classify_review(ok)["verdict"]))
        two = dict(ok, body=ok["body"].replace("Diff truncated: no", f"Reviewed commit: `{OLD}`"))
        self.assertEqual("UNCLEAR", classify_review(two)["verdict"])

    def test_newer_malformed_bot_review_blocks_an_older_pass(self):
        older_pass = self.bot("**Status: qualifying automated review — PASS.** text", "**Verdict:** PASS")
        variants = {
            "duplicate head SHA": older_pass["body"].replace("Diff truncated: no", f"Reviewed commit: `{HEAD}`"),
            "head and old SHA": older_pass["body"].replace("Diff truncated: no", f"Reviewed commit: `{OLD}`"),
            "no SHA": older_pass["body"].replace(f"Reviewed commit: `{HEAD}`", "Reviewed commit: unknown"),
        }
        for name, body in variants.items():
            with self.subTest(name):
                newer = dict(older_pass, body=body, created_at="2026-10-19T06:00:00Z")
                action = next_action(review_for_head([older_pass, newer], HEAD), "PASSING")
                self.assertNotEqual("Ready for your merge decision", action)
        # A malformed review naming only another commit doesn't block this one.
        other = dict(older_pass, created_at="2026-10-19T06:00:00Z",
                     body=older_pass["body"].replace(f"`{HEAD}`", f"`{OLD}`").replace("Diff truncated: no", f"Reviewed commit: `{OLD}`"))
        self.assertEqual("Ready for your merge decision", next_action(review_for_head([older_pass, other], HEAD), "PASSING"))


class CheckRunPaginationTests(unittest.TestCase):
    def pages(self, *responses):
        return lambda page: responses[page - 1] if page <= len(responses) else ({"total_count": 0, "check_runs": []}, None)

    def test_complete_multi_page_read(self):
        first = ({"total_count": 3, "check_runs": [run(), run("other")]}, None)
        second = ({"total_count": 3, "check_runs": [run("third")]}, None)
        runs, complete = collect_check_runs(self.pages(first, second), per_page=2)
        self.assertTrue(complete)
        self.assertEqual(3, len(runs))
        self.assertEqual("PASSING", ci_state(runs))

    def test_failed_page_is_incomplete_and_unknown(self):
        first = ({"total_count": 3, "check_runs": [run(), run("other")]}, None)
        runs, complete = collect_check_runs(self.pages(first, (None, "GitHub API 502")), per_page=2)
        self.assertFalse(complete)
        self.assertEqual("UNKNOWN", ci_state(runs if complete else None))

    def test_page_cap_and_bad_shapes_are_incomplete(self):
        endless = lambda page: ({"total_count": 999, "check_runs": [run(), run()]}, None)
        self.assertFalse(collect_check_runs(endless, per_page=2, max_pages=3)[1])
        self.assertEqual((None, False), collect_check_runs(lambda page: ({"oops": 1}, None)))
        self.assertFalse(collect_check_runs(lambda page: ({"check_runs": [run()]}, None))[1])


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
