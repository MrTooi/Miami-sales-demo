import copy
import unittest

from agent_workbench_tenant import replace_record, visible_records


class SyntheticTenantTaskTests(unittest.TestCase):
    def setUp(self):
        self.records = [
            {"tenant_id": "alpha", "id": "a1", "value": 10},
            {"tenant_id": "beta", "id": "b1", "value": 20},
            {"tenant_id": "alpha", "id": "a2", "value": 30},
        ]

    def test_reads_are_tenant_scoped(self):
        visible = visible_records(self.records, "alpha")
        self.assertEqual(["a1", "a2"], [row["id"] for row in visible])
        self.assertTrue(all(row["tenant_id"] == "alpha" for row in visible))

    def test_write_cannot_cross_tenant_boundary(self):
        records = copy.deepcopy(self.records)
        changed = replace_record(records, "alpha", "b1", 999)
        self.assertFalse(changed)
        beta = next(row for row in records if row["id"] == "b1")
        self.assertEqual(20, beta["value"])

    def test_write_succeeds_within_tenant(self):
        records = copy.deepcopy(self.records)
        changed = replace_record(records, "alpha", "a1", 77)
        self.assertTrue(changed)
        alpha = next(row for row in records if row["id"] == "a1")
        self.assertEqual(77, alpha["value"])


if __name__ == "__main__":
    unittest.main()
