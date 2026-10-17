import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "command_center" / "pages" / "1_Project_Map.py"


class CommandCenterProjectMapTests(unittest.TestCase):
    def setUp(self):
        self.source = PAGE.read_text(encoding="utf-8")
        self.tree = ast.parse(self.source)

    def test_project_map_source_is_valid_python(self):
        ast.parse(self.source)

    def test_project_map_http_requests_are_read_only(self):
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            is_request = isinstance(func, ast.Attribute) and func.attr == "Request"
            is_urlopen = isinstance(func, ast.Attribute) and func.attr == "urlopen"
            if is_request:
                names = {kw.arg for kw in node.keywords if kw.arg}
                self.assertNotIn("data", names)
                self.assertNotIn("method", names)
            if is_urlopen:
                names = {kw.arg for kw in node.keywords if kw.arg}
                self.assertNotIn("data", names)
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            self.assertNotIn(method, self.source)

    def test_project_map_tracks_live_gate_issues(self):
        for issue in (11, 69, 74, 75, 79, 81):
            self.assertIn(f"({issue},", self.source)
        self.assertIn('/repos/{REPO}/issues/{number}', self.source)
        self.assertIn('/repos/{REPO}/pulls?state=open', self.source)

    def test_scheduler_health_has_delivery_grace_and_no_invented_fallback(self):
        self.assertIn("SCHEDULE_GRACE_MINUTES = 20", self.source)
        self.assertIn("previous_operator_slot", self.source)
        self.assertIn("LATE / CHECK", self.source)
        self.assertIn("no fallback schedule is invented", self.source)
        self.assertNotIn("workflow_dispatch", self.source)
        self.assertNotIn("/dispatches", self.source)
        self.assertNotIn("/rerun", self.source)

    def test_readiness_artifact_is_only_unverified_telemetry(self):
        self.assertIn('run.get("event") == "schedule"', self.source)
        self.assertIn('run.get("run_attempt") != 1', self.source)
        self.assertIn('run.get("conclusion") != "success"', self.source)
        self.assertIn("EVIDENCE_PREFIX", self.source)
        self.assertIn("len(exact) == 1", self.source)
        self.assertIn("EVIDENCE PRESENT — UNVERIFIED HERE", self.source)
        self.assertIn("does not assign Suite A/B/C or claim a pass", self.source)
        self.assertNotIn("VERIFIED EVIDENCE", self.source)

    def test_evidence_fetch_errors_are_visible(self):
        self.assertIn("evidence_errors", self.source)
        self.assertIn("Evidence telemetry is UNKNOWN", self.source)

    def test_project_map_does_not_import_product_finance_modules(self):
        for module in ("finance_engine", "ledger_store", "data_pipeline", "app_ledger"):
            self.assertNotIn(f"import {module}", self.source)
            self.assertNotIn(f"from {module}", self.source)


if __name__ == "__main__":
    unittest.main()
