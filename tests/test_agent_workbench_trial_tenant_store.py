import inspect
import unittest

from agent_workbench.trial_tenant_store import TenantStore


class TenantStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = TenantStore()
        self.store.create(tenant_id="tenant-a", record_id="shared", record={"value": "A"})

    def test_same_record_id_is_independent_across_tenants(self):
        self.store.create(tenant_id="tenant-b", record_id="shared", record={"value": "B"})
        self.assertEqual(self.store.get(tenant_id="tenant-a", record_id="shared"), {"value": "A"})
        self.assertEqual(self.store.get(tenant_id="tenant-b", record_id="shared"), {"value": "B"})
        self.store.update(tenant_id="tenant-b", record_id="shared", record={"value": "B2"})
        self.assertEqual(self.store.get(tenant_id="tenant-b", record_id="shared"), {"value": "B2"})
        self.assertEqual(self.store.get(tenant_id="tenant-a", record_id="shared"), {"value": "A"})
        self.store.delete(tenant_id="tenant-b", record_id="shared")
        with self.assertRaises(KeyError):
            self.store.get(tenant_id="tenant-b", record_id="shared")
        self.assertEqual(self.store.get(tenant_id="tenant-a", record_id="shared"), {"value": "A"})

    def test_cross_tenant_reads_updates_and_deletes_fail_without_mutation(self):
        for operation in ("get", "update", "delete"):
            with self.subTest(operation=operation):
                kwargs = {"tenant_id": "tenant-b", "record_id": "shared"}
                if operation == "update":
                    kwargs["record"] = {"value": "intruder"}
                with self.assertRaisesRegex(KeyError, "Record not found in tenant"):
                    getattr(self.store, operation)(**kwargs)
                self.assertEqual(self.store.get(tenant_id="tenant-a", record_id="shared"), {"value": "A"})
                with self.assertRaises(KeyError):
                    self.store.get(tenant_id="tenant-b", record_id="shared")

    def test_missing_record_errors_do_not_reveal_other_tenants(self):
        for operation in ("get", "update", "delete"):
            errors = []
            for record_id in ("shared", "absent-everywhere"):
                kwargs = {"tenant_id": "tenant-b", "record_id": record_id}
                if operation == "update":
                    kwargs["record"] = {}
                with self.assertRaises(KeyError) as error:
                    getattr(self.store, operation)(**kwargs)
                errors.append(error.exception.args)
            with self.subTest(operation=operation):
                self.assertEqual(errors[0], errors[1])

    def test_duplicate_in_same_tenant_is_rejected_without_overwrite(self):
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.store.create(tenant_id="tenant-a", record_id="shared", record={"value": "replacement"})
        self.assertEqual(self.store.get(tenant_id="tenant-a", record_id="shared"), {"value": "A"})

    def test_all_operations_reject_blank_or_invalid_tenants(self):
        for operation in ("create", "get", "update", "delete"):
            for tenant_id in (None, "", " ", "\t\n", 0, False, [], {}):
                with self.subTest(operation=operation, tenant_id=tenant_id):
                    kwargs = {"tenant_id": tenant_id, "record_id": "shared"}
                    if operation in ("create", "update"):
                        kwargs["record"] = {"value": "invalid"}
                    with self.assertRaisesRegex(ValueError, "tenant_id"):
                        getattr(self.store, operation)(**kwargs)
        self.assertEqual(self.store.get(tenant_id="tenant-a", record_id="shared"), {"value": "A"})

    def test_all_operations_require_explicit_tenant_argument(self):
        for operation in ("create", "get", "update", "delete"):
            with self.subTest(operation=operation):
                kwargs = {"record_id": "shared"}
                if operation in ("create", "update"):
                    kwargs["record"] = {}
                with self.assertRaises(TypeError):
                    getattr(self.store, operation)(**kwargs)

    def test_all_operations_reject_invalid_record_ids(self):
        for operation in ("create", "get", "update", "delete"):
            for record_id in (None, "", "\t ", 0, False, [], {}):
                with self.subTest(operation=operation, record_id=record_id):
                    kwargs = {"tenant_id": "tenant-a", "record_id": record_id}
                    if operation in ("create", "update"):
                        kwargs["record"] = {}
                    with self.assertRaisesRegex(ValueError, "record_id"):
                        getattr(self.store, operation)(**kwargs)

    def test_tenant_identity_is_not_normalized_or_combined_with_record_id(self):
        for tenant_id, record_id in (("tenant-a ", "shared"), ("TENANT-A", "shared"),
                                     ("a:b", "c"), ("a", "b:c")):
            self.store.create(tenant_id=tenant_id, record_id=record_id, record={"owner": tenant_id})
        for tenant_id, record_id in (("tenant-a ", "shared"), ("TENANT-A", "shared"),
                                     ("a:b", "c"), ("a", "b:c")):
            self.assertEqual(self.store.get(tenant_id=tenant_id, record_id=record_id), {"owner": tenant_id})
        self.assertEqual(self.store.get(tenant_id="tenant-a", record_id="shared"), {"value": "A"})

    def test_nested_mutable_records_are_copied_on_create_update_and_get(self):
        shared_input = {"nested": {"labels": ["original"]}}
        for tenant_id in ("tenant-a", "tenant-b"):
            self.store.create(tenant_id=tenant_id, record_id="nested", record=shared_input)
        shared_input["nested"]["labels"].append("input mutation")
        fetched = self.store.get(tenant_id="tenant-a", record_id="nested")
        fetched["nested"]["labels"].append("output mutation")
        for tenant_id in ("tenant-a", "tenant-b"):
            self.assertEqual(self.store.get(tenant_id=tenant_id, record_id="nested"),
                             {"nested": {"labels": ["original"]}})
        replacement = {"nested": {"labels": ["updated"]}}
        self.store.update(tenant_id="tenant-a", record_id="nested", record=replacement)
        replacement["nested"]["labels"].append("later mutation")
        self.assertEqual(self.store.get(tenant_id="tenant-a", record_id="nested"),
                         {"nested": {"labels": ["updated"]}})
        self.assertEqual(self.store.get(tenant_id="tenant-b", record_id="nested"),
                         {"nested": {"labels": ["original"]}})

    def test_payload_tenant_field_cannot_override_explicit_scope(self):
        self.store.create(tenant_id="tenant-b", record_id="payload", record={"tenant_id": "tenant-a"})
        with self.assertRaises(KeyError):
            self.store.get(tenant_id="tenant-a", record_id="payload")
        self.assertEqual(self.store.get(tenant_id="tenant-b", record_id="payload"), {"tenant_id": "tenant-a"})

    def test_invalid_payload_does_not_insert_or_replace_records(self):
        for invalid in (None, "text", [], 1):
            with self.subTest(record=invalid):
                with self.assertRaises(ValueError):
                    self.store.create(tenant_id="tenant-a", record_id="new", record=invalid)
                with self.assertRaises(KeyError):
                    self.store.get(tenant_id="tenant-a", record_id="new")
                with self.assertRaises(ValueError):
                    self.store.update(tenant_id="tenant-a", record_id="shared", record=invalid)
                self.assertEqual(self.store.get(tenant_id="tenant-a", record_id="shared"), {"value": "A"})

    def test_store_instances_do_not_share_state(self):
        with self.assertRaises(KeyError):
            TenantStore().get(tenant_id="tenant-a", record_id="shared")

    def test_public_api_exposes_no_unscoped_access(self):
        methods = {name: method for name, method in inspect.getmembers(TenantStore, callable)
                   if not name.startswith("_")}
        self.assertEqual(set(methods), {"create", "get", "update", "delete"})
        for name, method in methods.items():
            with self.subTest(method=name):
                tenant = inspect.signature(method).parameters["tenant_id"]
                self.assertEqual(tenant.kind, inspect.Parameter.KEYWORD_ONLY)
                self.assertIs(tenant.default, inspect.Parameter.empty)


if __name__ == "__main__":
    unittest.main()
