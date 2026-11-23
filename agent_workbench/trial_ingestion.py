"""Synthetic, single-threaded ingestion trial; no product or provider integration.

Identity strings are preserved exactly. Payloads must be JSON objects with
string keys and finite JSON values. Object key order is ignored for replay;
array order and scalar types remain significant. Include provenance in the
payload: it is preserved and participates in conflict detection.
"""

from dataclasses import dataclass
import json


class IngestionConflict(ValueError):
    """An existing source identity was replayed with different content."""


def _validate_json(value):
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise ValueError("Payload object keys must be strings")
            _validate_json(item)
    elif type(value) is list:
        for item in value:
            _validate_json(item)
    elif value is not None and type(value) not in (str, int, float, bool):
        raise ValueError("Payload must contain only JSON values")


def _canonical_payload(payload):
    if type(payload) is not dict:
        raise ValueError("Payload must be a JSON object")
    try:
        _validate_json(payload)
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError("Payload must be a finite, acyclic JSON object") from exc


@dataclass(frozen=True)
class IngestedRecord:
    """Immutable identity and canonical snapshot, including supplied provenance."""

    source: str
    external_id: str
    canonical_payload: str

    @property
    def payload(self):
        """Return a fresh copy so caller mutations cannot alter stored evidence."""
        return json.loads(self.canonical_payload)


class IngestionStore:
    """In-memory trial store, scoped to one caller; no persistence or tenant auth."""

    def __init__(self):
        self._records = {}

    def __len__(self):
        return len(self._records)

    def ingest(self, source, external_id, payload):
        """Insert once, return the existing record on replay, or raise a conflict.

        Invalid input and conflicting replays leave the store unchanged.
        Nonblank identities are not trimmed, case-folded, or otherwise merged.
        """
        for field, value in (("source", source), ("external_id", external_id)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Missing or invalid {field}")

        canonical = _canonical_payload(payload)
        key = (source, external_id)
        existing = self._records.get(key)
        if existing is not None:
            if existing.canonical_payload != canonical:
                raise IngestionConflict("Conflicting content for existing source identity")
            return existing

        record = IngestedRecord(source, external_id, canonical)
        self._records[key] = record
        return record
