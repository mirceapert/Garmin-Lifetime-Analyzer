"""Text clean-up for names that arrive from Garmin."""
from __future__ import annotations

import re

_MOJIBAKE = re.compile("[\u00c2-\u00f4][\u0080-\u00bf]{1,3}")


def fix_text(s: str | None) -> str | None:
    """Undo UTF-8 read as Latin-1 somewhere upstream ("ReprizÄ\x83" -> "Repriză"), piece by piece,
    so names that mix correct and garbled letters are fixed too."""
    if not s:
        return s

    def repl(m: re.Match) -> str:
        try:
            return m.group(0).encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return m.group(0)
    return _MOJIBAKE.sub(repl, s)
