from decimal import Decimal
from pathlib import Path
import unittest
from unittest import mock

from streamlit.testing.v1 import AppTest

import job_intake as ji
import pilot_safety as ps
from finance_engine import money

PAGE = str(Path(__file__).resolve().parents[1] / "pages" / "1_MarginX_Import.py")
CONFIG = Path(__file__).resolve().parents[1] / ".streamlit" / "config.toml"


class PilotModeTests(unittest.TestCase):
    def test_pilot_mode_needs_the_switch_and_a_local_only_address(self):
        on = {"MARGINX_PILOT": "1"}
        for address in ("localhost", "127.0.0.1", "::1", "LOCALHOST"):
            self.assertTrue(ps.pilot_mode(on, address), address)
        # Listening on every address (Streamlit's default), or on a network address, is never pilot mode.
        for address in (None, "", "0.0.0.0", "192.168.1.20", "example.com"):
            self.assertFalse(ps.pilot_mode(on, address), address)
        for environ in ({}, {"MARGINX_PILOT": "0"}, {"MARGINX_PILOT": "yes"}, {"MARGINX_PILOT": "true"}):
            self.assertFalse(ps.pilot_mode(environ, "localhost"), environ)

    def test_own_files_need_their_box_ticked(self):
        self.assertTrue(ps.upload_allowed(True, False, False))
        self.assertFalse(ps.upload_allowed(False, True, False))
        self.assertTrue(ps.upload_allowed(False, True, True))


class StrictMoneyTests(unittest.TestCase):
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
        for name in ("job_intake.py", "job_profit.py", "pilot_safety.py", "pages/1_MarginX_Import.py"):
            source = (root / name).read_text(encoding="utf-8")
            for forbidden in ("open(", "write_text", "write_bytes", "to_csv", "sqlite", "logging", "print("):
                self.assertNotIn(forbidden, source, f"{name} uses {forbidden}")


class PilotPageTests(unittest.TestCase):
    def run_page(self, environ, address):
        """Run the page with these environment variables and this server address."""
        with mock.patch.dict("os.environ", environ), \
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

    def test_pilot_mode_asks_for_the_owners_consent(self):
        at = self.run_page({"MARGINX_PILOT": "1"}, "localhost")
        self.assertIn("Pilot session on this laptop", at.warning[0].value)
        self.assertFalse(at.toggle[0].value)  # starts on the shop's own files, not the samples
        self.assertEqual([ps.CONSENT_TEXT], [c.label for c in at.checkbox])

    def test_end_session_clears_everything(self):
        at = AppTest.from_file(PAGE, default_timeout=30)
        at.run()
        at.toggle[0].set_value(False).run()
        at.checkbox[0].check().run()
        self.assertTrue(at.checkbox[0].value)
        next(b for b in at.button if b.label == "End session and clear everything").click().run()
        self.assertFalse(at.exception, at.exception)
        self.assertTrue(any("Session ended" in s.value for s in at.success))
        self.assertTrue(at.toggle[0].value)  # back to the samples: the previous answers are gone
        self.assertEqual(1, at.session_state["session_number"])


if __name__ == "__main__":
    unittest.main()
