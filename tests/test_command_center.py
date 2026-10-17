import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "command_center" / "app.py"
README = ROOT / "command_center" / "README.md"


class CommandCenterTests(unittest.TestCase):
    def setUp(self):
        self.source = APP.read_text(encoding="utf-8")
        self.tree = ast.parse(self.source)

    def test_dashboard_source_is_valid_python(self):
        ast.parse(self.source)

    def test_dashboard_http_requests_are_read_only(self):
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else None
            keyword_names = {kw.arg for kw in node.keywords if kw.arg}
            if name == "Request":
                # Request(url, data, ...) or data=/method= would make a write request.
                self.assertLessEqual(len(node.args), 1, "Request() must not receive a positional body")
                self.assertNotIn("data", keyword_names)
                self.assertNotIn("method", keyword_names)
            if name == "urlopen":
                self.assertLessEqual(len(node.args), 1, "urlopen() must not receive a positional body")
                self.assertNotIn("data", keyword_names)
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            self.assertNotIn(method, self.source)

    def test_dashboard_only_uses_expected_http_hosts(self):
        self.assertIn("https://api.github.com", self.source)
        self.assertIn("https://raw.githubusercontent.com", self.source)
        self.assertNotIn("requests.", self.source)

    def test_dashboard_does_not_import_product_finance_modules(self):
        for module in ("finance_engine", "ledger_store", "data_pipeline", "app_ledger"):
            self.assertNotIn(f"import {module}", self.source)
            self.assertNotIn(f"from {module}", self.source)

    def test_dashboard_live_refresh_is_enabled(self):
        self.assertIn("AUTO_REFRESH_SECONDS = 30", self.source)
        self.assertIn("window.parent.location.reload()", self.source)
        self.assertIn("@st.cache_data(ttl=20", self.source)
        self.assertIn("data fetched", self.source)

    def test_live_state_comes_from_github(self):
        self.assertIn('/repos/{REPO}/branches/main', self.source)
        self.assertIn('/repos/{REPO}/actions/runs?branch=main', self.source)
        self.assertIn('/repos/{REPO}/pulls?state=open', self.source)
        self.assertIn('/repos/{REPO}/issues?state=open', self.source)

    def test_ci_health_is_bound_to_exact_main_sha(self):
        self.assertIn('run.get("head_sha") == main_sha', self.source)
        self.assertIn("CI success on this exact SHA", self.source)

    def test_artifact_presence_is_not_claimed_as_verified_readiness(self):
        self.assertIn("EVIDENCE PRESENT — UNVERIFIED HERE", self.source)
        self.assertIn("VALIDATION PENDING", self.source)
        self.assertIn("authoritative readiness validation", self.source)
        self.assertNotIn('card("Readiness", "TECHNICAL GATE"', self.source)
        self.assertNotIn("VERIFIED PASS", self.source)

    def test_evidence_fetch_failure_becomes_unknown(self):
        self.assertIn("evidence_fetch_errors", self.source)
        self.assertIn("Evidence retrieval is incomplete; no pass count inferred", self.source)
        self.assertIn("Candidate evidence count is UNKNOWN", self.source)

    def test_stale_scheduled_run_success_cannot_render_green(self):
        # The card's tone comes only from the shared helper, whose tones are never "ok"
        # (behavior-tested in tests/test_command_center_schedule_parsing.py).
        self.assertIn('card("Latest Scheduled Run", run_value, run_note, run_tone)', self.source)
        self.assertIn("run_value, run_tone, run_note = latest_run_display(latest_operator)", self.source)
        from command_center.status_logic import latest_run_display

        stale_success = {"run_attempt": 1, "status": "completed", "conclusion": "success"}
        self.assertNotEqual(latest_run_display(stale_success)[1], "ok")

    def test_schedule_has_no_invented_fallback_minutes(self):
        self.assertIn("return None", self.source)
        self.assertIn("no fallback time is invented", self.source)

    def test_readme_states_private_hosting_and_unknown_semantics(self):
        text = README.read_text(encoding="utf-8")
        self.assertIn("authentication", text.lower())
        self.assertIn("UNKNOWN", text)
        self.assertIn("never guesses", text)
        self.assertIn("LATE / CHECK", text)


if __name__ == "__main__":
    unittest.main()
