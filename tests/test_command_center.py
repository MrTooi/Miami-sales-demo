import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "command_center" / "app.py"
README = ROOT / "command_center" / "README.md"


class CommandCenterTests(unittest.TestCase):
    def test_dashboard_source_is_valid_python(self):
        source = APP.read_text(encoding="utf-8")
        ast.parse(source)

    def test_dashboard_is_read_only_by_construction(self):
        source = APP.read_text(encoding="utf-8")
        self.assertIn('urllib.request.Request', source)
        self.assertNotIn('method="POST"', source)
        self.assertNotIn('method="PUT"', source)
        self.assertNotIn('method="PATCH"', source)
        self.assertNotIn('method="DELETE"', source)
        self.assertNotIn('requests.post(', source)
        self.assertNotIn('requests.put(', source)
        self.assertNotIn('requests.patch(', source)
        self.assertNotIn('requests.delete(', source)

    def test_dashboard_does_not_import_product_finance_modules(self):
        source = APP.read_text(encoding="utf-8")
        for module in ("finance_engine", "ledger_store", "data_pipeline", "app_ledger"):
            self.assertNotIn(f"import {module}", source)
            self.assertNotIn(f"from {module}", source)

    def test_dashboard_live_refresh_is_enabled(self):
        source = APP.read_text(encoding="utf-8")
        self.assertIn("AUTO_REFRESH_SECONDS = 30", source)
        self.assertIn("window.parent.location.reload()", source)
        self.assertIn("@st.cache_data(ttl=20", source)

    def test_live_state_comes_from_github_not_hardcoded_progress(self):
        source = APP.read_text(encoding="utf-8")
        self.assertIn('/repos/{REPO}/branches/main', source)
        self.assertIn('/repos/{REPO}/actions/runs?branch=main', source)
        self.assertIn('/repos/{REPO}/pulls?state=open', source)
        self.assertIn('/repos/{REPO}/issues?state=open', source)
        self.assertIn("EVIDENCE_PREFIX", source)
        self.assertIn("run_attempt", source)

    def test_readme_states_private_hosting_and_unknown_semantics(self):
        text = README.read_text(encoding="utf-8")
        self.assertIn("authentication", text.lower())
        self.assertIn("UNKNOWN", text)
        self.assertIn("never guesses", text)


if __name__ == "__main__":
    unittest.main()
