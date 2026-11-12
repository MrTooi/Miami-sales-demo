from dataclasses import FrozenInstanceError
import unittest

from agent_workbench.trial_ingestion import IngestionConflict, IngestionStore


class TrialIngestionTests(unittest.TestCase):
    def setUp(self):
        self.store = IngestionStore()
        self.payload = {
            "kind": "synthetic-event",
            "details": {"labels": ["first", "second"], "active": True},
            "provenance": {"fixture": "fictional-export", "row": 1},
        }

    def test_exact_replay_returns_existing_record_without_duplication(self):
        first = self.store.ingest("source-a", "event-1", self.payload)
        for _ in range(3):
            self.assertIs(self.store.ingest("source-a", "event-1", self.payload), first)
        self.assertEqual(len(self.store), 1)

    def test_nested_object_key_order_does_not_cause_conflict(self):
        first = self.store.ingest("source-a", "event-1", self.payload)
        reordered = {
            "provenance": {"row": 1, "fixture": "fictional-export"},
            "details": {"active": True, "labels": ["first", "second"]},
            "kind": "synthetic-event",
        }
        self.assertIs(self.store.ingest("source-a", "event-1", reordered), first)
        self.assertEqual(len(self.store), 1)

    def test_conflicting_payload_or_provenance_never_overwrites_original(self):
        first = self.store.ingest("source-a", "event-1", self.payload)
        changes = [
            {**self.payload, "kind": "changed"},
            {**self.payload, "provenance": {"fixture": "other-export", "row": 1}},
            {**self.payload, "details": {"active": True, "labels": ["second", "first"]}},
        ]
        for changed in changes:
            with self.subTest(changed=changed), self.assertRaises(IngestionConflict):
                self.store.ingest("source-a", "event-1", changed)
            self.assertIs(self.store.ingest("source-a", "event-1", self.payload), first)
            self.assertEqual(first.payload, self.payload)
            self.assertEqual(len(self.store), 1)

    def test_same_external_id_from_different_sources_remains_distinct(self):
        first = self.store.ingest("source-a", "same-id", self.payload)
        second = self.store.ingest("source-b", "same-id", self.payload)
        self.assertIsNot(first, second)
        self.assertEqual((first.source, second.source), ("source-a", "source-b"))
        self.assertEqual(first.external_id, second.external_id)
        self.assertIs(self.store.ingest("source-a", "same-id", self.payload), first)
        self.assertIs(self.store.ingest("source-b", "same-id", self.payload), second)
        self.assertEqual(len(self.store), 2)

    def test_different_external_ids_in_one_source_remain_distinct(self):
        first = self.store.ingest("source-a", "event-1", self.payload)
        second = self.store.ingest("source-a", "event-2", self.payload)
        self.assertIsNot(first, second)
        self.assertEqual(len(self.store), 2)

    def test_identity_is_preserved_without_normalization(self):
        first = self.store.ingest(" Source-A ", " event-1 ", self.payload)
        second = self.store.ingest("source-a", "event-1", self.payload)
        self.assertEqual((first.source, first.external_id), (" Source-A ", " event-1 "))
        self.assertIsNot(first, second)
        self.assertEqual(len(self.store), 2)

    def test_snapshot_preserves_payload_and_provenance_despite_caller_mutation(self):
        first = self.store.ingest("source-a", "event-1", self.payload)
        original = first.payload
        self.assertEqual(original, self.payload)
        self.payload["details"]["labels"].append("changed")
        self.payload["provenance"]["row"] = 99
        returned = first.payload
        returned["details"]["labels"].clear()
        returned["provenance"]["fixture"] = "changed"
        self.assertEqual(first.payload, original)
        self.assertIs(self.store.ingest("source-a", "event-1", original), first)
        with self.assertRaises(IngestionConflict):
            self.store.ingest("source-a", "event-1", self.payload)

    def test_returned_record_cannot_be_reassigned(self):
        record = self.store.ingest("source-a", "event-1", self.payload)
        for field in ("source", "external_id", "canonical_payload"):
            with self.subTest(field=field), self.assertRaises(FrozenInstanceError):
                setattr(record, field, "changed")
        self.assertIs(self.store.ingest("source-a", "event-1", self.payload), record)

    def test_missing_blank_or_non_string_identity_is_rejected(self):
        for field in ("source", "external_id"):
            for invalid in (None, "", " \t\n", 0, False, [], {}):
                arguments = {"source": "source-a", "external_id": "event-1"}
                arguments[field] = invalid
                with self.subTest(field=field, invalid=invalid):
                    with self.assertRaisesRegex(ValueError, field):
                        self.store.ingest(**arguments, payload=self.payload)
                    self.assertEqual(len(self.store), 0)

    def test_omitted_identity_argument_is_rejected(self):
        for arguments in ({"external_id": "event-1"}, {"source": "source-a"}):
            with self.subTest(arguments=arguments), self.assertRaises(TypeError):
                self.store.ingest(**arguments, payload=self.payload)
        self.assertEqual(len(self.store), 0)

    def test_malformed_payloads_do_not_write_or_replace_records(self):
        cyclic = {}
        cyclic["self"] = cyclic
        malformed = [
            None, [], "text", 1, {"nested": {1: "non-string-key"}},
            {"nested": (1, 2)}, {"nested": {1, 2}}, {"nested": object()},
            {"nested": float("nan")}, {"nested": float("inf")},
            {"nested": float("-inf")}, cyclic,
        ]
        first = self.store.ingest("source-a", "existing", self.payload)
        for payload in malformed:
            for external_id in ("new", "existing"):
                with self.subTest(payload=payload, external_id=external_id):
                    with self.assertRaises(ValueError):
                        self.store.ingest("source-a", external_id, payload)
                    self.assertEqual(len(self.store), 1)
                    self.assertIs(self.store.ingest("source-a", "existing", self.payload), first)

    def test_json_scalar_types_are_not_silently_merged(self):
        first = self.store.ingest("source-a", "event-1", {"value": 1})
        for changed in (True, 1.0, "1", None):
            with self.subTest(changed=changed), self.assertRaises(IngestionConflict):
                self.store.ingest("source-a", "event-1", {"value": changed})
        self.assertIs(self.store.ingest("source-a", "event-1", {"value": 1}), first)
        self.assertEqual(len(self.store), 1)

    def test_empty_and_nested_json_payload_round_trip(self):
        for index, payload in enumerate(({}, {"unicode": "café", "values": [None, False, 2]})):
            with self.subTest(payload=payload):
                first = self.store.ingest("source-a", str(index), payload)
                self.assertEqual(first.payload, payload)
                self.assertIs(self.store.ingest("source-a", str(index), payload), first)

    def test_store_instances_do_not_share_state(self):
        self.store.ingest("source-a", "event-1", self.payload)
        other = IngestionStore()
        record = other.ingest("source-a", "event-1", {"different": True})
        self.assertEqual(record.payload, {"different": True})
        self.assertEqual((len(self.store), len(other)), (1, 1))


if __name__ == "__main__":
    unittest.main()
