import unittest

from agent_workbench_unknown_format import parse_oradar1


class SyntheticUnknownFormatTaskTests(unittest.TestCase):
    def test_valid_document_parses_and_preserves_fact_pipes(self):
        text = """# exported by partner tool
ORADAR1
r1|HVAC|quantified_interview|Owner spends 6 hours/week|during close
r2|Printing|software_review|Job costing export is manual
"""
        self.assertEqual(
            [
                {"evidence_id": "r1", "market": "HVAC", "kind": "quantified_interview", "observed_fact": "Owner spends 6 hours/week|during close"},
                {"evidence_id": "r2", "market": "Printing", "kind": "software_review", "observed_fact": "Job costing export is manual"},
            ],
            parse_oradar1(text),
        )

    def test_missing_magic_header_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_oradar1("r1|HVAC|software_review|Manual export")

    def test_malformed_row_is_rejected_not_silently_dropped(self):
        with self.assertRaises(ValueError):
            parse_oradar1("ORADAR1\nr1|HVAC|software_review")

    def test_blank_required_field_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_oradar1("ORADAR1\nr1||software_review|Manual export")

    def test_duplicate_evidence_id_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_oradar1("ORADAR1\nr1|HVAC|software_review|A\nr1|HVAC|software_review|B")


if __name__ == "__main__":
    unittest.main()
