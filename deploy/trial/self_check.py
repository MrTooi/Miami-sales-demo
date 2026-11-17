"""MargenX's own refusals, checked from inside one running trial copy (issue #131, lean v1.2; PR B).

Run it in the host's shell on the running copy (Render: the service's Shell tab):

    python /app/deploy/trial/self_check.py

It talks to MargenX directly on the container (127.0.0.1:8501), around Cloudflare: none of its requests
carry a real login. So it shows that MargenX itself refuses them, whatever Cloudflare does (release
check 1, "around the gate"). Every probe must be refused by MargenX's gate, which marks each refusal
with the X-MargenX-Gate header: "refused", or "closed" when the copy runs in closed mode.

The probes: no login; a forged login for the invited email (signed with a made-up key); another host
name; the upload address; another request that sends data; Log out by GET and from another site; media;
and the live connection, which must get the same marked 403. Every probe must run: if one can't (for
example the forged login, without PyJWT), the check fails as incomplete. The probes carry no valid
login, so they show the gate refuses requests that skip Cloudflare; they don't test the cross-site
checks for a person who IS logged in (those are unit tests, and release check 1). It prints only each probe's name and result: never a setting's value, a token
or an email. It sends nothing anywhere but the copy itself, except that the forged login makes MargenX
fetch Cloudflare's public signing keys, which is expected (release check 6).
"""
from __future__ import annotations

import argparse
import base64
import http.client
import os
import socket
import sys
import time

PORT = 8501
GATE_HEADER = "x-margenx-gate"
TOKEN_HEADER = "Cf-Access-Jwt-Assertion"


def forged_token(email: str, audience: str, issuer: str) -> str:
    """A login token in Cloudflare's form for the invited email, signed with a key made up on the spot,
    so no real key could ever accept it."""
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = int(time.time())
    return jwt.encode({"email": email, "aud": [audience], "iss": issuer, "iat": now - 5, "exp": now + 300},
                      key, algorithm="RS256", headers={"kid": "margenx-self-check"})


def http_probe(port: int, method: str, path: str, headers: dict[str, str], body: bytes | None = None,
               timeout: float = 20) -> tuple[int, str, str]:
    """(status, the gate's mark, Cache-Control) for one request to the copy."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        response.read()
        return response.status, response.getheader(GATE_HEADER, ""), response.getheader("Cache-Control", "")
    finally:
        conn.close()


def live_probe(port: int, host: str, timeout: float = 20) -> tuple[int, str]:
    """(HTTP status, the gate's mark) for a live-connection (WebSocket) handshake with no login: 101 would mean
    it opened; MargenX's gate answers 403 with its mark."""
    key = base64.b64encode(os.urandom(16)).decode()
    request = (f"GET /_stcore/stream HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\nOrigin: https://{host}\r\n"
               "Sec-WebSocket-Protocol: streamlit\r\n\r\n")
    head = b""
    with socket.create_connection(("127.0.0.1", port), timeout=timeout) as s:
        s.sendall(request.encode())
        while b"\r\n\r\n" not in head and len(head) < 65536:
            chunk = s.recv(4096)
            if not chunk:
                break
            head += chunk
    lines = head.split(b"\r\n\r\n", 1)[0].decode("latin-1").split("\r\n")
    parts = lines[0].split()
    status = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 0
    mark = ""
    for line in lines[1:]:
        name, _, value = line.partition(":")
        if name.strip().lower() == GATE_HEADER:
            mark = value.strip()
    return status, mark


def probes(host: str, token: str | None) -> list[tuple[str, str, str, dict[str, str], bytes | None]]:
    """(name, method, path, headers, body) for every HTTP probe."""
    base = {"Host": host}
    forged = {**base, TOKEN_HEADER: token} if token else None
    found = [
        ("page, no login", "GET", "/", base, None),
        ("health address, no login", "GET", "/_stcore/health", base, None),
        ("media, no login", "GET", "/media/self-check.png", base, None),
        ("page, another host name", "GET", "/", {"Host": "other.invalid"}, None),
        ("upload address, no login", "PUT", "/_stcore/upload_file/self-check/self-check", base, b"self-check"),
        ("data sent to the page, no login", "POST", "/", base, b"self-check"),
        ("Log out by GET", "GET", "/_trial/logout", base, None),
        ("Log out from another site, no login", "POST", "/_trial/logout",
         {**base, "Origin": "https://other.invalid", "Sec-Fetch-Site": "cross-site"}, b""),
    ]
    if forged:
        found += [
            ("page, forged login for the invited email", "GET", "/", forged, None),
            ("upload address, forged login", "PUT", "/_stcore/upload_file/self-check/self-check", forged,
             b"self-check"),
        ]
    return found


def main(argv: list[str] | None = None, environ=os.environ) -> int:
    parser = argparse.ArgumentParser(description="MargenX's own refusals, from inside the copy.")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--host", default=environ.get("MARGINX_TRIAL_HOST", "").strip(),
                        help="the trial's address (default: MARGINX_TRIAL_HOST)")
    args = parser.parse_args(argv)
    if not args.host:
        print("self-check: the trial's address isn't known; run it with --host app.margenx.org")
        return 2
    team = environ.get("MARGINX_TRIAL_TEAM_DOMAIN", "").strip().rstrip("/") or "https://margenx.cloudflareaccess.com"
    token = None
    failures = 0
    try:
        token = forged_token(environ.get("MARGINX_TRIAL_INVITED_EMAIL", "").strip().lower() or "nobody@example.com",
                             environ.get("MARGINX_TRIAL_AUDIENCE", "").strip() or "self-check", team)
    except ImportError:
        print("FAIL  forged-login probes: couldn't run here (no PyJWT), so this check is incomplete")
        failures += 1
    marks = set()
    for name, method, path, headers, body in probes(args.host, token):
        try:
            status, mark, cache = http_probe(args.port, method, path, headers, body)
        except OSError as problem:
            print(f"FAIL  {name}: no answer from MargenX ({problem.__class__.__name__})")
            failures += 1
            continue
        ok = status == 403 and mark in ("refused", "closed") and cache == "no-store"
        marks.add(mark)
        failures += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {name}: {status}, gate {mark or 'not seen'}, Cache-Control {cache or 'none'}")
    try:
        status, mark = live_probe(args.port, args.host)
        ok = status == 403 and mark in ("refused", "closed")
        marks.add(mark)
        shown = "opened" if status == 101 else f"{status or 'no valid answer'}, gate {mark or 'not seen'}"
        print(f"{'PASS' if ok else 'FAIL'}  live connection, no login: {shown}")
    except OSError as problem:
        ok = False
        print(f"FAIL  live connection, no login: no answer from MargenX ({problem.__class__.__name__})")
    failures += not ok
    mode = "closed mode" if marks == {"closed"} else "open (invited person only)" if marks == {"refused"} else "mixed"
    print(f"self-check: {'all refused by MargenX itself' if not failures else f'{failures} FAILED'}; the copy is in "
          f"{mode}. Time: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
