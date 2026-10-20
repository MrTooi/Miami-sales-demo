"""The public demo link (D-006): the made-up demo shop only, with no way to upload a file."""
import os
from pathlib import Path
import unittest
from unittest import mock

from streamlit.testing.v1 import AppTest

import pilot_safety as ps

ROOT = Path(__file__).resolve().parents[1]


def run(entry: str, environ=None):
    with mock.patch.dict("os.environ", environ or {}), \
            mock.patch("pilot_safety.request_is_local", return_value=True):
        at = AppTest.from_file(str(ROOT / entry), default_timeout=60)
        at.run()
    return at


class DemoLinkTests(unittest.TestCase):
    def test_demo_link_shows_only_the_demo_shop_and_no_upload_box(self):
        at = run("margenx_demo.py")
        self.assertFalse(at.exception, at.exception)
        page = " ".join(m.value for m in at.markdown)
        self.assertIn("Margen<b>X</b>", page)
        self.assertIn("$11,000", page)  # the demo sign shop's sales
        self.assertTrue(any("Online demo with a made-up sign shop" in i.value for i in at.info))
        self.assertEqual(0, len(at.get("file_uploader")))
        self.assertEqual([], [t for t in at.toggle])  # no "use sample files" switch
        self.assertEqual([], [c for c in at.checkbox])  # no consent box that could lead to uploads
        self.assertFalse(any(r.label == "Which made-up files?" for r in at.radio))
        self.assertFalse(any("End session" in b.label for b in at.button))

    def test_pilot_mode_can_never_switch_on_in_the_demo(self):
        # Even with the pilot switch set and a local-looking request, the demo entry point wins.
        at = run("margenx_demo.py", {ps.PILOT_ENV: "1"})
        self.assertFalse(at.exception, at.exception)
        page = " ".join(m.value for m in at.markdown)
        self.assertNotIn("Pilot session", page)
        self.assertFalse(any("Pilot session" in w.value for w in at.warning))  # the pilot banner is a warning
        self.assertEqual(0, len(at.get("file_uploader")))
        self.assertEqual([], [c for c in at.checkbox])

    def test_demo_fails_closed_when_the_entry_file_cant_be_confirmed(self):
        # Streamlit gives no context, or looking it up fails: the demo shows nothing at all, so the
        # normal app's upload box and pilot mode can never appear on the link.
        for patch in (mock.patch("pilot_safety._script_ctx", return_value=None),
                      mock.patch("pilot_safety._script_ctx", side_effect=RuntimeError("no context"))):
            with self.subTest(patch=patch), patch:
                at = run("margenx_demo.py", {ps.PILOT_ENV: "1"})
            self.assertFalse(at.exception, at.exception)
            self.assertTrue(any("This demo can't start right now" in e.value for e in at.error))
            self.assertEqual(0, len(at.get("file_uploader")))
            self.assertEqual([], [c for c in at.checkbox])
            self.assertEqual([], [t for t in at.toggle])
            self.assertFalse(any("Pilot session" in w.value for w in at.warning))
            self.assertEqual([], [m.value for m in at.markdown if "Margen" in m.value])  # the page never ran

    def test_running_main_script_never_raises(self):
        with mock.patch("pilot_safety._script_ctx", side_effect=RuntimeError("boom")):
            self.assertIsNone(ps.running_main_script())
        with mock.patch("pilot_safety._script_ctx", return_value=None):
            self.assertIsNone(ps.running_main_script())

    def test_the_demo_changes_nothing_process_wide(self):
        # No cleanup between runs: the demo must not leave any switch behind for other entry points.
        before = dict(os.environ)
        demo = AppTest.from_file(str(ROOT / "margenx_demo.py"), default_timeout=60)
        demo.run()
        self.assertEqual(before, dict(os.environ))
        normal = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
        normal.run()
        self.assertFalse(normal.exception, normal.exception)
        self.assertTrue(any(t.label == "Try it with the made-up sample files" for t in normal.toggle))
        self.assertFalse(any("Online demo" in i.value for i in normal.info))

    def test_demo_only_is_decided_by_the_entry_file_alone(self):
        self.assertTrue(ps.demo_only(str(ROOT / "margenx_demo.py")))
        self.assertTrue(ps.demo_only("/mount/src/miami-sales-demo/margenx_demo.py"))
        for path in (str(ROOT / "app.py"), str(ROOT / "marginx_pilot.py"), "margenx_demo.py.bak", "", None):
            self.assertFalse(ps.demo_only(path), path)

    def test_demo_entry_point_opens_only_the_margenx_page_and_sets_nothing(self):
        source = (ROOT / "margenx_demo.py").read_text(encoding="utf-8")
        self.assertEqual(1, source.count("st.Page("))
        self.assertIn('"pages/1_MargenX_Import.py"', source)
        self.assertNotIn("os.environ", source)
        # The fail-closed check comes before the page is opened.
        self.assertLess(source.index("st.stop()"), source.index("st.navigation("))


if __name__ == "__main__":
    unittest.main()
