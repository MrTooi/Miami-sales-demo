"""Synthetic in-memory tenant-isolation trial; not a product persistence layer.

Tenant IDs are explicit namespaces supplied by a trusted caller, not authentication.
Records are dictionaries of trusted, deepcopy-compatible Python data. The store
is single-threaded and provides no persistence or unscoped enumeration API.
"""

from copy import deepcopy


class TenantStore:
    """Store independent records by the exact (tenant_id, record_id) pair.

Missing records raise KeyError identically whether absent everywhere or present
in another tenant. Updates replace existing records; they never create records.
Input and output copies prevent nested mutable data from aliasing stored data.
"""

    def __init__(self):
        self._records: dict[tuple[str, str], dict] = {}

    @staticmethod
    def _key(tenant_id: str, record_id: str) -> tuple[str, str]:
        for name, value in (("tenant_id", tenant_id), ("record_id", record_id)):
            if type(value) is not str or not value.strip():
                raise ValueError(f"{name} must be a nonblank string")
        # Validate whitespace without normalizing distinct tenant identities.
        return tenant_id, record_id

    @staticmethod
    def _copy_record(record: dict) -> dict:
        if not isinstance(record, dict):
            raise ValueError("record must be a dictionary")
        return deepcopy(record)

    def create(self, *, tenant_id: str, record_id: str, record: dict) -> None:
        """Create a record, rejecting duplicate IDs within the same tenant."""
        key = self._key(tenant_id, record_id)
        if key in self._records:
            raise ValueError("Record already exists in tenant")
        self._records[key] = self._copy_record(record)

    def get(self, *, tenant_id: str, record_id: str) -> dict:
        """Return a detached copy of a record belonging to this tenant."""
        key = self._key(tenant_id, record_id)
        if key not in self._records:
            raise KeyError("Record not found in tenant")
        return deepcopy(self._records[key])

    def update(self, *, tenant_id: str, record_id: str, record: dict) -> None:
        """Replace an existing record belonging to this tenant."""
        key = self._key(tenant_id, record_id)
        if key not in self._records:
            raise KeyError("Record not found in tenant")
        self._records[key] = self._copy_record(record)

    def delete(self, *, tenant_id: str, record_id: str) -> None:
        """Delete an existing record belonging to this tenant."""
        key = self._key(tenant_id, record_id)
        if key not in self._records:
            raise KeyError("Record not found in tenant")
        del self._records[key]
