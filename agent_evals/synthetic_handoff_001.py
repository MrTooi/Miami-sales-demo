"""Synthetic helper used only to validate the multi-model review pipeline."""


def stable_unique(values: list[str]) -> list[str]:
    """Return unique strings from *values*."""
    return list(set(values))
