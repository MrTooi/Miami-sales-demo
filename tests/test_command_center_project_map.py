import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "command_center" / "pages" / "1_Project_Map.py"


class CommandCenterProjectMapTests(unittest.TestCase):
    def test_project_map_source_is_valid_python(self):
        ast.parse(PAGE.read_text(encoding="utf-8"))

    def test_project_map_is_read_only(self):
        source = PAGE.read_text(encoding="utf-8")
        self.assertIn("urllib.request.Request", source)
        for method in ('method="POST"', 'method="PUT"', 'method="PATCH"', 'method="DELETE"'):
            self.assertNotIn(method, source)

    def test_project_map_tracks_live_gate_issues(self):
        source = PAGE.read_text(encoding="utf-8")
        for issue in (11, 69, 74, 75, 79, 81):
            self.assertIn(f"({issue},", source)
        self.assertIn('/repos/{REPO}/issues/{number}', source)
        self.assertIn('/repos/{REPO}/pulls?state=open', source)

    def test_scheduler_health_has_delivery_grace_and_never_triggers_runs(self):
        source = PAGE.read_text(encoding="utf-8")
        self.assertIn("SCHEDULE_GRACE_MINUTES = 20", source)
        self.assertIn("previous_operator_slot", source)
        self.assertIn("LATE / CHECK", source)
        self.assertNotIn("workflow_dispatch", source)
        self.assertNotIn("/dispatches", source)
        self.assertNotIn("/rerun", source)

    def test_readiness_requires_exact_schedule_evidence(self):
        source = PAGE.read_text(encoding="utf-8")
        self.assertIn('run.get("event") == "schedule"', source)
        self.assertIn('run.get("run_attempt") != 1', source)
        self.assertIn('run.get("conclusion") != "success"', source)
        self.assertIn("EVIDENCE_PREFIX", source)
        self.assertIn("len(exact) == 1", source)

    def test_project_map_does_not_import_product_finance_modules(self):
        source = PAGE.read_text(encoding="utf-8")
        for module in ("finance_engine", "ledger_store", "data_pipeline", "app_ledger"):
            self.assertNotIn(f"import {module}", source)
            self.assertNotIn(f"from {module}", source)


if __name__ == "__main__":
    unittest.main()
