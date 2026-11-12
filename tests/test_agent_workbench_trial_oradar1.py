import unittest

from agent_workbench.trial_oradar1 import Record, parse_records


class TrialOradar1Tests(unittest.TestCase):
    def test_valid_records_preserve_all_fields_and_both_directions(self):
        self.assertEqual(
            parse_records("e1|support|synthetic A|Fact A\ne2|contradict|synthetic B|Fact B"),
            [
                Record("e1", "support", "synthetic A", "Fact A"),
                Record("e2", "contradict", "synthetic B", "Fact B"),
            ],
        )

    def test_embedded_and_trailing_pipes_are_preserved(self):
        for fact in ("Fact | with || pipes|", "|", "||"):
            with self.subTest(fact=fact):
                self.assertEqual(
                    parse_records(f"e1|support|synthetic|{fact}")[0].observed_fact,
                    fact,
                )

    def test_field_whitespace_is_preserved(self):
        self.assertEqual(
            parse_records(" e1 |support| synthetic |  Fact | more  "),
            [Record(" e1 ", "support", " synthetic ", "  Fact | more  ")],
        )

    def test_empty_and_blank_only_input(self):
        for text in ("", "\n", " \t\n\r\n \t"):
            with self.subTest(text=text):
                self.assertEqual(parse_records(text), [])

    def test_blank_lines_and_crlf_are_supported(self):
        self.assertEqual(
            parse_records("\r\n \t\r\ne1|support|synthetic|Fact\r\n\r\n"),
            [Record("e1", "support", "synthetic", "Fact")],
        )

    def test_malformed_lines_raise_instead_of_being_dropped(self):
        for malformed in ("bad", "e1|support", "e1|support|synthetic", "# comment"):
            for position in (0, 1, 2):
                with self.subTest(malformed=malformed, position=position):
                    lines = ["e2|support|synthetic|Fact", "e3|contradict|synthetic|Fact"]
                    lines.insert(position, malformed)
                    with self.assertRaisesRegex(
                        ValueError, rf"^Line {position + 1}: expected four fields$"
                    ):
                        parse_records("\n".join(lines))

    def test_blank_required_fields_are_rejected(self):
        names = ("record_id", "direction", "source", "observed_fact")
        for index, name in enumerate(names):
            for blank in ("", " ", "\t"):
                with self.subTest(field=name, blank=blank):
                    fields = ["e1", "support", "synthetic", "Fact"]
                    fields[index] = blank
                    with self.assertRaisesRegex(ValueError, rf"^Line 1: blank {name}$"):
                        parse_records("|".join(fields))

    def test_unsupported_directions_are_rejected_exactly(self):
        for direction in ("unknown", "Support", "SUPPORT", "Contradict", "support ", " contradict"):
            with self.subTest(direction=direction):
                with self.assertRaisesRegex(ValueError, "^Line 1: unsupported direction$"):
                    parse_records(f"e1|{direction}|synthetic|Fact")

    def test_duplicate_ids_fail_even_when_other_fields_differ(self):
        with self.assertRaisesRegex(ValueError, "^Line 4: duplicate record_id$"):
            parse_records(
                "e1|support|synthetic A|Fact A\n\n"
                "e2|support|synthetic B|Fact B\n"
                "e1|contradict|synthetic C|Different fact"
            )

    def test_ids_use_exact_equality(self):
        self.assertEqual(
            [record.record_id for record in parse_records(
                "e1|support|synthetic|Fact\nE1|support|synthetic|Fact\n e1 |support|synthetic|Fact"
            )],
            ["e1", "E1", " e1 "],
        )

    def test_first_seen_order_is_preserved_deterministically(self):
        text = "z|contradict|synthetic|Last letter\na|support|synthetic|First letter\nm|support|synthetic|Middle"
        for _ in range(3):
            self.assertEqual(
                [record.record_id for record in parse_records(text)], ["z", "a", "m"]
            )

    def test_line_numbers_include_blank_lines(self):
        with self.assertRaisesRegex(ValueError, "^Line 4: expected four fields$"):
            parse_records("\n \t\ne1|support|synthetic|Fact\nbroken")

    def test_parser_calls_do_not_share_duplicate_state(self):
        text = "e1|support|synthetic|Fact"
        self.assertEqual(parse_records(text), parse_records(text))

    def test_errors_do_not_echo_input_contents(self):
        with self.assertRaises(ValueError) as error:
            parse_records("synthetic-private-marker|invalid|synthetic|Fact")
        self.assertNotIn("synthetic-private-marker", str(error.exception))


if __name__ == "__main__":
    unittest.main()
