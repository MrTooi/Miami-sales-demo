import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


class AppSmokeTests(unittest.TestCase):
    def test_demo_app_runs_without_uncaught_exception(self):
        app = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
        self.assertEqual(list(app.exception), [])
        self.assertGreaterEqual(len(app.metric), 4)
        labels = [metric.label for metric in app.metric]
        self.assertIn("NET REVENUE", labels)
        self.assertIn("GROSS PROFIT", labels)
        self.assertIn("OPERATING PROFIT", labels)
        self.assertIn("REFUNDS", labels)


if __name__ == "__main__":
    unittest.main()
