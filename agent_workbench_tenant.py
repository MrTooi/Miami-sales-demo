"""Synthetic evaluation task. Intentionally incorrect; not product code."""


def visible_records(records, tenant_id):
    """Return records visible to one tenant."""
    return list(records)


def replace_record(records, tenant_id, record_id, new_value):
    """Replace one record by id."""
    for record in records:
        if record["id"] == record_id:
            record["value"] = new_value
            return True
    return False
