import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


class AppSmokeTests(unittest.TestCase):
    def test_app_opens_the_margenx_page_without_errors(self):
        app = AppTest.from_file(str(APP_PATH), default_timeout=30).run()
        self.assertEqual(list(app.exception), [])
        page = " ".join(m.value for m in app.markdown)
        self.assertIn("Margen<b>X</b>", page)
        self.assertIn("Here's where your money was made", page)  # the demo shop's results


if __name__ == "__main__":
    unittest.main()
