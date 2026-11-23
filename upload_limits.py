"""Checks every uploaded file before any reader sees it (issue #131, uploads plan v7, section 5).

A broken, oversized or highly compressed file ("zip bomb") gets one plain refusal, never a crash. An Excel
file (.xlsx) is a zip archive: its parts are listed with their declared sizes, which Python's zip reader
enforces while reading (a part can't unpack to more than it declares), so these limits hold for every
reader after this one. Nothing is opened beyond that list here, and the refusal never quotes the file.
"""
from __future__ import annotations

import io
import zipfile

MAX_FILE_BYTES = 5_000_000  # the same as job_intake's own limit and the trial gate's file limit
MAX_PARTS = 100
MAX_UNPACKED_BYTES = 25_000_000
MAX_RATIO = 100  # no part may unpack to more than 100 times its packed size

TOO_BIG = "This file is larger than 5 MB. Export a shorter date range."
BROKEN = "This file can't be opened as an Excel file (.xlsx). Export it again from QuickBooks as Excel."
TOO_MUCH = "This Excel file is too large inside to read safely. Export a shorter date range."


def refusal(name: str, data: bytes) -> str | None:
    """A plain reason to refuse this file before any reader sees it, or None."""
    if len(data) > MAX_FILE_BYTES:
        return TOO_BIG
    if not name.lower().endswith(".xlsx"):
        return None  # other kinds are refused (or read) by the page's own rules
    if not data.startswith(b"PK"):
        return BROKEN
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            parts = archive.infolist()
    except (zipfile.BadZipFile, zipfile.LargeZipFile, ValueError, OSError, EOFError, RuntimeError):
        return BROKEN
    if not parts:
        return BROKEN
    if len(parts) > MAX_PARTS:
        return TOO_MUCH
    if sum(part.file_size for part in parts) > MAX_UNPACKED_BYTES:
        return TOO_MUCH
    for part in parts:
        if part.file_size > MAX_RATIO * max(part.compress_size, 1) and part.file_size > 1_000_000:
            return TOO_MUCH
    return None
