from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from streamlit.testing.v1 import AppTest

import job_intake as ji
import pilot_safety as ps
from finance_engine import money

ROOT = Path(__file__).resolve().parents[1]
PAGE = str(ROOT / "pages" / "1_MargenX_Import.py")
CONFIG = Path(__file__).resolve().parents[1] / ".streamlit" / "config.toml"


class PilotModeTests(unittest.TestCase):
    LOCAL = {"Host": "localhost:8501"}

    def test_pilot_mode_needs_the_switch_a_loopback_address_and_a_local_request(self):
        on = {"MARGINX_PILOT": "1"}
        for address in ("localhost", "127.0.0.1", "::1", "LOCALHOST"):
            self.assertTrue(ps.pilot_mode(on, address, self.LOCAL), address)
        # Listening on every address (Streamlit's default), or on a network address, is never pilot mode.
        for address in (None, "", "0.0.0.0", "192.168.1.20", "example.com"):
            self.assertFalse(ps.pilot_mode(on, address, self.LOCAL), address)
        for environ in ({}, {"MARGINX_PILOT": "0"}, {"MARGINX_PILOT": "yes"}, {"MARGINX_PILOT": "true"}):
            self.assertFalse(ps.pilot_mode(environ, "localhost", self.LOCAL), environ)
        self.assertFalse(ps.pilot_mode(on, "localhost", None))  # unknown request: never pilot mode

    def test_requests_through_a_proxy_or_tunnel_are_not_local(self):
        for host in ("localhost:8501", "127.0.0.1:8501", "[::1]:8501", "localhost"):
            self.assertTrue(ps.request_is_local({"Host": host}), host)
        for headers in ({"Host": "marginx.example.com"}, {"Host": "abcd.ngrok-free.app"}, {},
                        {"Host": "localhost:8501", "X-Forwarded-For": "203.0.113.5"},
                        {"Host": "localhost:8501", "Cf-Connecting-Ip": "203.0.113.5"},
                        {"Host": "127.0.0.1:8501", "Forwarded": "for=203.0.113.5"},
                        {"Host": "localhost:8501", "Via": "1.1 proxy"},
                        {"host": "localhost:8501", "x-real-ip": "203.0.113.5"}):
            self.assertFalse(ps.request_is_local(headers), headers)

    def test_own_files_need_their_box_ticked(self):
        self.assertTrue(ps.upload_allowed(True, False, False))
        self.assertFalse(ps.upload_allowed(False, True, False))
        self.assertTrue(ps.upload_allowed(False, True, True))


class UploadReleaseTests(unittest.TestCase):
    """End session deletes uploads from Streamlit's real in-memory upload storage (pinned 1.65.0)."""

    def manager_with_files(self):
        from streamlit.runtime.memory_uploaded_file_manager import MemoryUploadedFileManager
        from streamlit.runtime.uploaded_file_manager import UploadedFileRec

        manager = MemoryUploadedFileManager("/_stcore/upload_file")
        for session, file_id in (("visit", "f1"), ("visit", "f2"), ("other", "f3")):
            manager.add_file(session, UploadedFileRec(file_id, f"{file_id}.csv", "text/csv",
                                                      b"Date,Vendor,Amount\n10/31/2026,Shop A (fictional),12.00\n"))
        return manager

    def test_end_session_deletes_only_this_sessions_uploads_and_confirms_it(self):
        manager = self.manager_with_files()
        self.assertEqual(2, len(manager.get_files("visit", ["f1", "f2"])))
        self.assertTrue(ps.release_uploads(manager, "visit"))
        self.assertEqual([], manager.get_files("visit", ["f1", "f2"]))  # a later session can't get them
        self.assertNotIn("visit", manager.file_storage)
        self.assertEqual(1, len(manager.get_files("other", ["f3"])))  # another browser session is untouched

    def test_a_deletion_that_cant_be_checked_is_never_claimed(self):
        self.assertFalse(ps.release_uploads(None, "visit"))
        self.assertFalse(ps.release_uploads(self.manager_with_files(), None))

        class NoStorage:
            def remove_session_files(self, session_id):
                pass
        self.assertFalse(ps.release_uploads(NoStorage(), "visit"))

        class Failing:
            file_storage = {}
            def remove_session_files(self, session_id):
                raise RuntimeError("boom")
        self.assertFalse(ps.release_uploads(Failing(), "visit"))

    def test_the_streamlit_internals_relied_on_are_present(self):
        # If an upgrade removes these, this test fails and End session falls back to "couldn't confirm".
        from streamlit.runtime import Runtime
        from streamlit.runtime.memory_uploaded_file_manager import MemoryUploadedFileManager
        from streamlit.runtime.scriptrunner_utils.script_run_context import get_script_run_ctx  # noqa: F401
        self.assertTrue(hasattr(Runtime, "uploaded_file_mgr"))
        self.assertTrue(callable(getattr(MemoryUploadedFileManager, "remove_session_files", None)))
        self.assertIn("file_storage", MemoryUploadedFileManager("/x").__dict__)
        self.assertIn("streamlit==1.65.0", (ROOT / "requirements.txt").read_text(encoding="utf-8"))


class MainEntryPointTests(unittest.TestCase):
    """app.py opens only the MargenX page; the older Ledger screen (uploads kept in SQLite) is retired."""

    def run_app(self, environ):
        with mock.patch.dict("os.environ", environ):
            at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
            at.run()
        return at

    def ledger_dbs(self):
        return {p.name for p in Path(tempfile.gettempdir()).glob("ledger-*.db")}

    def test_app_opens_only_margenx_and_creates_no_database(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertEqual(1, source.count("st.Page("))
        self.assertIn('"pages/1_MargenX_Import.py"', source)
        for pilot in ("0", "1"):
            before = self.ledger_dbs()
            at = self.run_app({"MARGINX_PILOT": pilot})
            self.assertFalse(at.exception, at.exception)
            page = " ".join(m.value for m in at.markdown)
            self.assertIn("Margen<b>X</b>", page)
            self.assertNotIn("ledger", page.lower())
            self.assertEqual(before, self.ledger_dbs())

    def test_the_old_ledger_screen_is_gone(self):
        self.assertFalse((ROOT / "ui_theme.py").exists())
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        for old in ("LedgerStore", "file_uploader", "sqlite", "ui_theme"):
            self.assertNotIn(old, source)


class PilotEntryPointTests(unittest.TestCase):
    def test_the_pilot_entry_point_opens_only_marginx(self):
        source = (ROOT / "marginx_pilot.py").read_text(encoding="utf-8")
        self.assertEqual(1, source.count("st.Page("))
        self.assertIn('"pages/1_MargenX_Import.py"', source)
        with mock.patch.dict("os.environ", {"MARGINX_PILOT": "0"}):
            at = AppTest.from_file(str(ROOT / "marginx_pilot.py"), default_timeout=30)
            at.run()
        self.assertFalse(at.exception, at.exception)
        page = " ".join(m.value for m in at.markdown)
        # The MargenX header (product name and tagline), not the Ledger demo, in any capitalisation.
        import marginx_ui as ui
        self.assertEqual("MargenX", ui.BRAND)  # the owner's spelling (2026-10-20)
        self.assertIn("Margen<b>X</b>", page)
        self.assertNotIn("marginx", page.lower())
        self.assertIn(ui.TAGLINE, page)
        self.assertNotIn("ledger", page.lower())
        self.assertEqual([], [t.value for t in at.title])


class StrictMoneyTests(unittest.TestCase):
    def test_floats_are_never_turned_into_money(self):
        for value in (0.1, 12.5, 1e3, float("nan")):
            with self.assertRaises(ValueError, msg=value):
                money(value)
        self.assertEqual(Decimal("12"), money(12))
        self.assertEqual(Decimal("0.30"), money(Decimal("0.10")) + money("0.20"))

    def test_us_amounts_are_read_exactly(self):
        for text, amount in (("1234.56", "1234.56"), ("1,234.56", "1234.56"), ("$1,250.00", "1250.00"),
                             ("-$45.00", "-45.00"), ("1,234,567.89", "1234567.89"), ("0.10", "0.10"), (" 7 ", "7")):
            self.assertEqual(Decimal(amount), money(text), text)

    def test_ambiguous_comma_amounts_are_refused_not_misread(self):
        for text in ("12,50", "1,5", "1.234,56", "1,23", "1,2345.00", "12.345", "1 234.56", "(45.00)"):
            with self.assertRaises(ValueError, msg=text):
                money(text)

    def test_a_european_style_amount_is_listed_as_a_rejected_row(self):
        headers, rows = ji.read_csv(b"Date,Vendor,Amount\n10/31/2026,Paper Co,\"12,50\"\n10/31/2026,Ink Co,30.00\n")
        result = ji.intake(headers, rows, ji.suggest_mapping(headers, "costs"), "costs", "MM/DD/YYYY")
        self.assertEqual([Decimal("30.00")], [r["amount"] for r in result.accepted])
        self.assertIn("'12,50' isn't read as 12.50 or 1,250", " ".join(result.rejected[0]["reasons"]))


class SafeSettingsTests(unittest.TestCase):
    def test_streamlit_settings_send_nothing_and_show_no_error_details(self):
        text = CONFIG.read_text(encoding="utf-8")
        self.assertIn("gatherUsageStats = false", text)
        self.assertIn('showErrorDetails = "none"', text)
        self.assertIn("maxUploadSize = 5", text)
        self.assertEqual(5_000_000, ji.MAX_FILE_BYTES)

    def test_marginx_code_never_writes_files_or_logs_contents(self):
        root = Path(__file__).resolve().parents[1]
        for name in ("job_intake.py", "job_profit.py", "pilot_safety.py", "pages/1_MargenX_Import.py", "marginx_pilot.py",
                     "app.py"):
            source = (root / name).read_text(encoding="utf-8")
            # A guard against obvious regressions, not proof.
            for forbidden in ("open(", "write_text", "write_bytes", "to_csv", "sqlite", "logging", "print("):
                self.assertNotIn(forbidden, source, f"{name} uses {forbidden}")


class PilotPageTests(unittest.TestCase):
    def run_page(self, environ, address, local_request=True):
        """Run the page with these environment variables, server address and request locality."""
        with mock.patch.dict("os.environ", environ), \
                mock.patch("pilot_safety.request_is_local", return_value=local_request), \
                mock.patch("streamlit.get_option", side_effect=lambda key: address if key == "server.address" else None):
            at = AppTest.from_file(PAGE, default_timeout=30)
            at.run()
        self.assertFalse(at.exception, at.exception)
        return at

    def test_outside_pilot_mode_only_made_up_files_are_allowed(self):
        at = self.run_page({"MARGINX_PILOT": "1"}, None)  # switch on, but not a local-only address
        self.assertIn("made-up data only", at.warning[0].value)
        at.toggle[0].set_value(False).run()
        self.assertEqual([ps.MADE_UP_TEXT], [c.label for c in at.checkbox])
        self.assertEqual(0, len(at.get("file_uploader")))  # upload area only after the box is ticked
        at.checkbox[0].check().run()
        self.assertEqual(1, len(at.get("file_uploader")))

    def test_pilot_mode_asks_for_the_owners_consent_before_any_upload(self):
        at = self.run_page({"MARGINX_PILOT": "1"}, "localhost")
        self.assertIn("Pilot session on this laptop", at.warning[0].value)
        self.assertFalse(at.toggle[0].value)  # starts on the shop's own files, not the samples
        self.assertEqual([ps.CONSENT_TEXT], [c.label for c in at.checkbox])
        self.assertEqual(0, len(at.get("file_uploader")))  # no upload area until the owner agrees

    def test_pilot_start_screen_shows_the_check_up_frame_with_the_upload_locked(self):
        at = self.run_page({"MARGINX_PILOT": "1"}, "localhost")
        html = " ".join(m.value for m in at.markdown)
        self.assertIn('<span class="mx-live"><i></i>Pilot session · this laptop only</span>', html)
        self.assertIn("<h1>Add your reports</h1>", html)  # step 1 heading, before any file
        self.assertIn('<div class="mx-nav on"><div class="n">1</div>', html)  # step 1 is the current step
        self.assertIn("Tick the box above to choose files.", html)  # a locked drop area, not an upload
        self.assertEqual(0, len(at.get("file_uploader")))
        self.assertIn("<b>Sales report</b> · waiting", html)
        self.assertIn("<b>Cost report</b> · waiting", html)
        self.assertIn("Stays on this laptop, never sent online", html)  # a verified local pilot session
        self.assertIn("End session clears the app&#x27;s data", html)
        # The consent is shown in full: AppTest can't render, so this checks the style rule that undoes
        # Streamlit's one-line cut-off for checkbox labels in columns (checked by eye in the browser).
        self.assertIn('.st-key-mx-consent [data-testid="stCheckbox"] p{white-space:normal!important;'
                      "overflow:visible!important;text-overflow:clip!important", html)
        self.assertEqual([ps.CONSENT_TEXT], [c.label for c in at.checkbox])  # the whole consent, unchanged

    def test_outside_a_verified_pilot_the_privacy_points_never_claim_this_laptop(self):
        # Pilot switched on but not a local-only address, or a proxied request: the app may not be on this
        # laptop, so the start screen never says the files stay on it.
        for address, local in ((None, True), ("localhost", False)):
            with self.subTest(address=address, local=local):
                at = self.run_page({"MARGINX_PILOT": "1"}, address, local_request=local)
                at.toggle[0].set_value(False).run()
                html = " ".join(m.value for m in at.markdown)
                self.assertIn("Made-up files only", html)
                self.assertNotIn("this laptop, never sent online", html)
                self.assertNotIn("Pilot session · this laptop only", html)

    def test_a_proxied_or_tunneled_request_is_never_pilot_mode(self):
        at = self.run_page({"MARGINX_PILOT": "1"}, "localhost", local_request=False)
        self.assertIn("made-up data only", at.warning[0].value)

    def test_end_session_clears_everything(self):
        at = AppTest.from_file(PAGE, default_timeout=30)
        at.run()
        at.toggle[0].set_value(False).run()
        at.checkbox[0].check().run()
        self.assertTrue(at.checkbox[0].value)
        next(b for b in at.button if b.label == "End session and clear everything").click().run()
        self.assertFalse(at.exception, at.exception)
        # AppTest has no real upload storage, so the deletion can't be confirmed here: the page must
        # then say so instead of claiming it (the confirmed path is tested in UploadReleaseTests).
        self.assertTrue(any("couldn't confirm the uploaded files were deleted" in w.value for w in at.warning))
        self.assertFalse(any("removed from MargenX's upload storage" in s.value for s in at.success))
        self.assertTrue(at.toggle[0].value)  # back to the samples: the previous answers are gone
        self.assertEqual(1, at.session_state["session_number"])

    def test_end_session_removes_shown_results_and_answers(self):
        # Results from files (here the samples; AppTest can't upload) and every answer are gone after
        # End session: nothing is left in the session but its counter.
        at = AppTest.from_file(PAGE, default_timeout=30)
        at.run()
        next(r for r in at.radio if r.label == "Which made-up files?").set_value("test").run()
        next(r for r in at.radio if "on each line?" in r.label).set_value("line").run()
        self.assertTrue(len(at.radio) > 0 and len(at.text) > 0)
        next(b for b in at.button if b.label == "End session and clear everything").click().run()
        self.assertFalse(at.exception, at.exception)
        # Every choice and answer is forgotten: back to the default demo set, with no question answered.
        self.assertEqual("demo", next(r for r in at.radio if r.label == "Which made-up files?").value)
        self.assertFalse(any("on each line?" in r.label and r.value for r in at.radio))
        # The earlier session's results (test-file job J-501) are gone; only the fresh default demo remains.
        tables = [d.value for d in at.dataframe if "Job" in d.value.columns]
        self.assertFalse(any("J-501" in list(table["Job"]) for table in tables))
        self.assertEqual(1, at.session_state["session_number"])


if __name__ == "__main__":
    unittest.main()
