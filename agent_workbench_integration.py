"""Synthetic evaluation task. Intentionally incorrect; not product code."""


def ingest_events(existing, incoming):
    """Return (canonical_events, conflicts) for synthetic provider events."""
    canonical = list(existing)
    canonical.extend(incoming)
    return canonical, []
