import unittest

from agent_operator.claim import extract_allowed_paths
from agent_operator.core import build_dispatch_plan, is_candidate, select_next_issue


def issue(number, labels, title="Task", state="open", pull_request=False):
    payload = {
        "number": number,
        "title": title,
        "state": state,
        "labels": [{"name": label} for label in labels],
    }
    if pull_request:
        payload["pull_request"] = {"url": "https://example.invalid/pr"}
    return payload


class AgentOperatorTests(unittest.TestCase):
    def test_candidate_requires_ready_and_excludes_other_lifecycle_states_or_pr(self):
        self.assertTrue(is_candidate(issue(1, ["agent:ready"])))
        self.assertFalse(is_candidate(issue(2, [])))
        for index, state_label in enumerate(
            [
                "agent:paused",
                "agent:claimed",
                "agent:working",
                "agent:awaiting-review",
                "agent:blocked",
                "needs:human",
            ],
            start=3,
        ):
            with self.subTest(state=state_label):
                self.assertFalse(is_candidate(issue(index, ["agent:ready", state_label])))
        self.assertFalse(is_candidate(issue(20, ["agent:ready"], pull_request=True)))

    def test_select_next_issue_is_priority_then_issue_number(self):
        issues = [
            issue(20, ["agent:ready", "priority:p2"]),
            issue(30, ["agent:ready", "priority:p1"]),
            issue(10, ["agent:ready", "priority:p1"]),
            issue(1, ["agent:ready", "priority:p0", "agent:paused"]),
        ]
        self.assertEqual(10, select_next_issue(issues)["number"])

    def test_settlement_routes_to_integrations_with_independent_security_review(self):
        plan = build_dispatch_plan(
            issue(11, ["agent:ready", "area:settlement", "priority:p1"], "Reconcile payouts")
        )
        self.assertEqual("integrations", plan.owner)
        self.assertEqual("medium", plan.risk)
        self.assertEqual(("qa-critic", "security-integrity"), plan.reviewers)
        self.assertFalse(plan.requires_human_approval)
        self.assertEqual("branch-only", plan.execution_scope)

    def test_high_impact_external_action_is_blocked_and_requires_human(self):
        plan = build_dispatch_plan(
            issue(12, ["agent:ready", "owner:backend", "action:deploy"], "Deploy change")
        )
        self.assertEqual("backend", plan.owner)
        self.assertEqual("high", plan.risk)
        self.assertTrue(plan.blocked_external_action)
        self.assertTrue(plan.requires_human_approval)
        self.assertIn("external action blocked", plan.execution_scope)

    def test_low_risk_label_cannot_downgrade_high_impact_action(self):
        plan = build_dispatch_plan(
            issue(15, ["agent:ready", "risk:low", "data:credentials"], "Credential task")
        )
        self.assertEqual("high", plan.risk)
        self.assertTrue(plan.requires_human_approval)
        self.assertIn("security-integrity", plan.reviewers)

    def test_conflicting_owner_labels_fall_back_to_generalist_triage(self):
        plan = build_dispatch_plan(
            issue(13, ["agent:ready", "owner:backend", "owner:frontend"], "Mixed task")
        )
        self.assertEqual("generalist", plan.owner)
        self.assertIn("conflicting", plan.reason)

    def test_unclassified_task_fails_closed_to_medium_risk(self):
        plan = build_dispatch_plan(issue(14, ["agent:ready"], "Unknown task"))
        self.assertEqual("generalist", plan.owner)
        self.assertEqual("medium", plan.risk)
        self.assertEqual(("qa-critic", "security-integrity"), plan.reviewers)
        self.assertFalse(plan.requires_human_approval)

    def test_explicit_low_risk_remains_available_for_deliberately_classified_work(self):
        plan = build_dispatch_plan(issue(16, ["agent:ready", "risk:low"], "Known low risk task"))
        self.assertEqual("low", plan.risk)
        self.assertEqual(("qa-critic",), plan.reviewers)

    def test_allowed_files_section_becomes_exact_machine_scope(self):
        body = """## Outcome
Create a feature.

## Allowed files

Create only:
- `agent_workbench/trial.py`
- `tests/test_agent_workbench_trial.py`

Do not change anything else.

## Required behavior
Do the thing.
"""
        self.assertEqual(
            ("agent_workbench/trial.py", "tests/test_agent_workbench_trial.py"),
            extract_allowed_paths(body),
        )

    def test_allowed_files_parser_ignores_backticks_in_prose(self):
        body = """## Allowed files
Do not touch `app_ledger.py`.
- `agent_workbench/trial.py`

## Required behavior
"""
        self.assertEqual(("agent_workbench/trial.py",), extract_allowed_paths(body))

    def test_allowed_files_parser_rejects_multiple_paths_in_one_bullet(self):
        body = """## Allowed files
- `a.py` or `b.py`

## Required behavior
"""
        with self.assertRaises(ValueError):
            extract_allowed_paths(body)

    def test_allowed_files_parser_rejects_globs_and_parent_escape(self):
        for unsafe in ("`tests/*.py`", "`../outside.py`"):
            with self.subTest(path=unsafe):
                body = f"## Allowed files\n- {unsafe}\n\n## Next\n"
                with self.assertRaises(ValueError):
                    extract_allowed_paths(body)

    def test_missing_allowed_files_section_fails_closed_to_empty_scope(self):
        self.assertEqual((), extract_allowed_paths("## Outcome\nNo explicit file boundary."))


if __name__ == "__main__":
    unittest.main()
