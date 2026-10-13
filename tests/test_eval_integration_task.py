import unittest

from agent_workbench_integration import ingest_events


class SyntheticIntegrationTaskTests(unittest.TestCase):
    def test_exact_replay_is_idempotent(self):
        event = {"source": "square", "external_id": "evt-1", "kind": "sale", "amount": "100.00"}
        canonical, conflicts = ingest_events([event], [dict(event)])
        self.assertEqual([event], canonical)
        self.assertEqual([], conflicts)

    def test_conflicting_revision_is_flagged_without_overwrite(self):
        original = {"source": "square", "external_id": "evt-1", "kind": "sale", "amount": "100.00"}
        revised = {"source": "square", "external_id": "evt-1", "kind": "sale", "amount": "120.00"}
        canonical, conflicts = ingest_events([original], [revised])
        self.assertEqual([original], canonical)
        self.assertEqual(1, len(conflicts))
        self.assertEqual(original, conflicts[0]["existing"])
        self.assertEqual(revised, conflicts[0]["incoming"])

    def test_same_external_id_from_different_source_is_distinct(self):
        square = {"source": "square", "external_id": "42", "kind": "sale", "amount": "50.00"}
        bank = {"source": "bank", "external_id": "42", "kind": "bank_deposit", "amount": "50.00"}
        canonical, conflicts = ingest_events([square], [bank])
        self.assertEqual([square, bank], canonical)
        self.assertEqual([], conflicts)

    def test_duplicate_in_single_incoming_batch_is_not_counted_twice(self):
        event = {"source": "square", "external_id": "evt-2", "kind": "refund", "amount": "5.00"}
        canonical, conflicts = ingest_events([], [event, dict(event)])
        self.assertEqual([event], canonical)
        self.assertEqual([], conflicts)


if __name__ == "__main__":
    unittest.main()
