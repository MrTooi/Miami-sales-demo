"""Parser for the issue #28 synthetic format; independent of product code."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Record:
    record_id: str
    direction: str
    source: str
    observed_fact: str


def parse_records(text: str) -> list[Record]:
    """Parse nonblank lines in order, raising ValueError on any invalid line.

    Only the first three pipes separate fields. Field contents are preserved
    verbatim; whitespace-only fields are blank, directions match exactly, and
    record IDs must be unique by exact string equality within this input.
    Errors identify the physical line without echoing input contents.
    """
    records = []
    seen_ids = set()
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        fields = line.split("|", 3)
        if len(fields) != 4:
            raise ValueError(f"Line {line_number}: expected four fields")
        for name, value in zip(
            ("record_id", "direction", "source", "observed_fact"), fields
        ):
            if not value.strip():
                raise ValueError(f"Line {line_number}: blank {name}")
        record_id, direction, source, observed_fact = fields
        if direction not in ("support", "contradict"):
            raise ValueError(f"Line {line_number}: unsupported direction")
        if record_id in seen_ids:
            raise ValueError(f"Line {line_number}: duplicate record_id")
        seen_ids.add(record_id)
        records.append(Record(record_id, direction, source, observed_fact))
    return records
