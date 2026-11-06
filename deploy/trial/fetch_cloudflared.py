"""Downloads Cloudflare's tunnel program (cloudflared) at one pinned version, during the image build only,
and refuses it unless its SHA-256 matches. PR A2 of issue #131.

The version and checksum are pinned here and nowhere else. The checksum was checked three ways when it
was pinned: the downloaded file, the release notes of that version, and GitHub's own record of the file.
Changing the version means changing both lines below and re-running the release checks it could affect.
"""
from __future__ import annotations

import hashlib
import os
import platform
import sys
import tempfile
import urllib.request

VERSION = "2026.10.7"
SHA256 = "1f99fb518b83dec2ba8d870a7cc991d82a77e6196295a3d2754ba17ab9f91872"
URL = f"https://github.com/cloudflare/cloudflared/releases/download/{VERSION}/cloudflared-linux-amd64"
DESTINATION = "/usr/local/bin/cloudflared"


def fetch(url: str = URL, sha256: str = SHA256, destination: str = DESTINATION, timeout: float = 120) -> None:
    """Download to a temporary file next to the destination; only a file with the right checksum is moved
    into place (executable). Anything else is deleted and the build fails."""
    folder = os.path.dirname(destination) or "."
    handle, temporary = tempfile.mkstemp(dir=folder)
    digest = hashlib.sha256()
    try:
        with os.fdopen(handle, "wb") as out, urllib.request.urlopen(url, timeout=timeout) as response:
            while chunk := response.read(1 << 20):
                digest.update(chunk)
                out.write(chunk)
        if digest.hexdigest() != sha256:
            raise SystemExit(f"cloudflared checksum mismatch: expected {sha256}, got {digest.hexdigest()}")
        os.chmod(temporary, 0o755)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


def check_machine(machine: str | None = None) -> None:
    """The pinned file is cloudflared for linux/amd64. Building on any other machine type fails here, rather
    than producing an image whose tunnel can't run (build with --platform linux/amd64)."""
    machine = platform.machine() if machine is None else machine
    if machine.lower() not in ("x86_64", "amd64"):
        raise SystemExit(f"this image is for linux/amd64, not {machine}: build with --platform linux/amd64")


if __name__ == "__main__":
    check_machine()
    fetch()
    print(f"cloudflared {VERSION} installed, checksum verified", file=sys.stderr)
