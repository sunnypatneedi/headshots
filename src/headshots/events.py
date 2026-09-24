"""Progress output.

By default the tool prints lines a person can read. With --json it writes one JSON object per
line to stdout instead, which is what the macOS app reads. Both carry the same information;
neither is ever sent anywhere.
"""
from __future__ import annotations

import json
import sys
import threading

_json = False
_lock = threading.Lock()


def use_json(on: bool = True) -> None:
    global _json
    _json = on


def emit(kind: str, **fields) -> None:
    """A structured event. Dropped entirely in human mode - use say() for anything a person reads."""
    if not _json:
        return
    with _lock:
        sys.stdout.write(json.dumps({"event": kind, **fields}, default=str) + "\n")
        sys.stdout.flush()


def say(text: str = "", **fields) -> None:
    """A line for a person, or the same line as a JSON event."""
    if _json:
        emit("log", text=text, **fields)
    else:
        with _lock:
            print(text, flush=True)
