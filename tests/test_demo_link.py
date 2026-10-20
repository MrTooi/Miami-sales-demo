"""The public demo link (D-006): the made-up demo shop only, with no way to upload a file."""
from pathlib import Path
import unittest
from unittest import mock

from streamlit.testing.v1 import AppTest

import pilot_safety as ps

ROOT = Path(__file__).resolve().parents[1]


def run_demo(environ=None):
    # patch.dict restores os.environ afterwards, so the entry point's switch never leaks into other tests.
    with mock.patch.dict("os.environ", environ or {}), \
            mock.patch("pilot_safety.request_is_local", return_value=True):
        at = AppTest.from_file(str(ROOT / "margenx_demo.py"), default_timeout=60)
        at.run()
    return at


class DemoLinkTests(unittest.TestCase):
    def test_demo_link_shows_only_the_demo_shop_and_no_upload_box(self):
        at = run_demo()
        self.assertFalse(at.exception, at.exception)
        page = " ".join(m.value for m in at.markdown)
        self.assertIn("Margen<b>X</b>", page)
        self.assertIn("Here&#x27;s where your money was made", page.replace("'", "&#x27;"))
        self.assertIn("$11,000", page)  # the demo sign shop's sales
        self.assertTrue(any("Online demo with a made-up sign shop" in i.value for i in at.info))
        self.assertEqual(0, len(at.get("file_uploader")))
        self.assertEqual([], [t for t in at.toggle])  # no "use sample files" switch
        self.assertEqual([], [c for c in at.checkbox])  # no consent box that could lead to uploads
        self.assertFalse(any(r.label == "Which made-up files?" for r in at.radio))
        self.assertFalse(any("End session" in b.label for b in at.button))

    def test_pilot_mode_can_never_switch_on_in_the_demo(self):
        # Even with the pilot switch set and a local-looking request, demo-only wins.
        at = run_demo({ps.PILOT_ENV: "1"})
        self.assertFalse(at.exception, at.exception)
        page = " ".join(m.value for m in at.markdown)
        self.assertNotIn("Pilot session", page)
        self.assertEqual(0, len(at.get("file_uploader")))
        self.assertFalse(ps.pilot_mode({ps.PILOT_ENV: "1", ps.DEMO_ENV: "1"}, "localhost", {"host": "localhost:8501"}))

    def test_the_demo_switch_does_not_leak_into_the_normal_app(self):
        run_demo()
        self.assertFalse(ps.demo_only(__import__("os").environ))
        with mock.patch.dict("os.environ", {ps.PILOT_ENV: "0"}):
            at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
            at.run()
        self.assertFalse(at.exception, at.exception)
        self.assertTrue(any(t.label == "Try it with the made-up sample files" for t in at.toggle))

    def test_demo_only_needs_exactly_1(self):
        self.assertTrue(ps.demo_only({ps.DEMO_ENV: "1"}))
        for value in ("", "0", "true", "yes"):
            self.assertFalse(ps.demo_only({ps.DEMO_ENV: value}))
        self.assertFalse(ps.demo_only({}))

    def test_demo_entry_point_opens_only_the_margenx_page(self):
        source = (ROOT / "margenx_demo.py").read_text(encoding="utf-8")
        self.assertEqual(1, source.count("st.Page("))
        self.assertIn('"pages/1_MargenX_Import.py"', source)
        self.assertIn("os.environ[DEMO_ENV] = \"1\"", source)


if __name__ == "__main__":
    unittest.main()
