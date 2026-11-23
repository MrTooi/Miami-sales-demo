"""The website trial's control channel between MargenX and its launcher (issue #131, uploads plan v7).

One MargenX process holds at most one consent. Any ending (End session, Log out, the consented tab's
connection closing, a file taking too long) ends the whole process: the launcher (deploy/trial/launch.py),
a separate process, kills MargenX's process group and starts a fresh, empty one. This module is the only
thing the two share: the messages MargenX writes on a pipe the launcher gives it, and the launcher's
reader for them. **The messages carry no data**: no file, no email, no setting, only these words and,
for a logout, a time in whole seconds.

The rules (plan v7, sections 2 and 11):
- Each MargenX process gets a fresh pipe. Every message is one line of at most MAX_LINE bytes, written in
  one `write` call. On Linux a pipe write of at most 4,096 bytes is all-or-nothing, so a message arrives
  whole or not at all; a reader can still receive it split across reads, or several in one read, so the
  reader keeps a partial line between reads.
- The first bad line (unknown word, too long, malformed time) makes the whole stream invalid.
- When MargenX dies, the launcher reads the old pipe to its end first. The death is **explained** only if
  a complete `recycle` arrived, nothing was invalid, the end of the pipe was reached within the limits, and
  nothing was left over (a line without its newline). Any other death is unexplained, and the launcher
  then advances the logout cutoff (`unexplained_cutoff`) before starting a replacement.
- A cutoff is a time: logins issued at or before it are refused. Cutoffs only ever grow.
"""
from __future__ import annotations

import math
import re

ALIVE, ARM, DISARM, RECYCLE, LOGOUT = "alive", "arm", "disarm", "recycle", "logout"
WORDS = (ALIVE, ARM, DISARM, RECYCLE)
MAX_LINE = 64  # bytes, the newline included
# The launcher reads at most this much of a dead process's pipe, for at most DRAIN_SECONDS.
DRAIN_BYTES = 64 * 1024
DRAIN_SECONDS = 2.0
# Added to every cutoff: a conservative allowance for a clock difference between Cloudflare (which sets a
# login's issue time) and this copy, not a proven maximum. A login made within it is refused too.
CUTOFF_MARGIN_SECONDS = 30
_LOGOUT_LINE = re.compile(rb"logout ([0-9]{1,12})")

# The settings the launcher gives each MargenX process (names only; never secret).
SUPERVISOR_FD_ENV = "MARGINX_SUPERVISOR_FD"
CUTOFF_ENV = "MARGINX_TRIAL_LOGGED_OUT_AT"


def encode(word: str, when: float | None = None) -> bytes:
    """One message, as written: a fixed word, or `logout <whole seconds>` (rounded up, so never earlier)."""
    if word == LOGOUT:
        if when is None or when < 0:
            raise ValueError("a logout needs its time")
        line = f"{LOGOUT} {math.ceil(when)}\n".encode()
    elif word in WORDS:
        line = f"{word}\n".encode()
    else:
        raise ValueError("not a control word")
    if len(line) > MAX_LINE:
        raise ValueError("message too long")
    return line


def later_cutoff(current: float | None, new: float | None) -> float | None:
    """The larger of two cutoffs: a cutoff never goes back."""
    if new is None:
        return current
    return new if current is None else max(current, new)


def unexplained_cutoff(current: float | None, now: float) -> float:
    """The cutoff after a death the launcher can't fully explain: every login issued up to now, plus the
    margin, is refused from then on."""
    return later_cutoff(current, now + CUTOFF_MARGIN_SECONDS)


class Reader:
    """The launcher's reader for one MargenX process's pipe: a stream of lines, checked one by one."""

    def __init__(self):
        self._partial = b""
        self.invalid = False
        self.recycle = False
        self.cutoff: float | None = None  # the latest logout time seen on this pipe
        self.alive = 0
        self.armed = False

    def feed(self, data: bytes) -> list[str]:
        """Take newly read bytes; returns the complete, valid words (logout included) in order. After the
        first bad line, nothing more is accepted."""
        if self.invalid:
            return []
        self._partial += data
        words = []
        while not self.invalid:
            end = self._partial.find(b"\n")
            if end < 0:
                if len(self._partial) >= MAX_LINE:  # can't be a valid line any more
                    self.invalid = True
                break
            line, self._partial = self._partial[:end], self._partial[end + 1:]
            if len(line) + 1 > MAX_LINE:
                self.invalid = True
                break
            word = self._word(line)
            if word is None:
                self.invalid = True
                break
            words.append(word)
        return words

    def _word(self, line: bytes) -> str | None:
        found = _LOGOUT_LINE.fullmatch(line)
        if found:
            self.cutoff = later_cutoff(self.cutoff, float(found.group(1)))
            return LOGOUT
        text = line.decode("ascii", "replace")
        if text not in WORDS:
            return None
        if text == ALIVE:
            self.alive += 1
        elif text == ARM:
            self.armed = True
        elif text == DISARM:
            self.armed = False
        elif text == RECYCLE:
            self.recycle = True
        return text

    @property
    def leftover(self) -> bool:
        """Bytes after the last newline: a message cut off."""
        return bool(self._partial)

    def explained(self, reached_end: bool) -> bool:
        """Whether a death is fully explained by what this pipe said (see the module notes)."""
        return self.recycle and not self.invalid and reached_end and not self.leftover
