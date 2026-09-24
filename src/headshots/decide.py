"""Whether a person should look at a photo, after judge has already graded it.

A backend estimates `look`, the chance a person should look, as a number from 0 to 1.
`settle` is the only policy: FAIL stays FAIL, REVIEW stays REVIEW, and a PASS becomes
REVIEW when look is at least LOOK_AT. The judge's grade on the entry is left as it was.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

from . import __version__, entitlements, events

LOOK_AT = 0.4     # a PASS becomes REVIEW once a look is at least this likely
SURE = 0.9        # a PASS this sure is not mentioned on the line a person reads
NEAR_LOOK = 0.55  # a measurement sitting just inside its line
JEV_URL = "https://api.typesafe.ai/v1/systemone"
JEV_MODEL = "jev-latest"
_GRADES = ("PASS", "REVIEW", "FAIL")

# One-sided checks whose stored metric is the number judge() compared.
# (name, line, slack, above). `above` means the pass side is value >= line.
# head_size is absent on purpose: with a plan, judge bands head/planned_head, not head_size.
_NEAR = (
    ("eye_sharpness", 0.6, 0.05, True),
    ("face_blown", 0.03, 0.005, False),
    ("clipping_added", 0.005, 0.001, False),
    ("crushing_added", 0.005, 0.001, False),
    ("sharpen_gain", 1.6, 0.05, False),
    ("upscale", 1.5, 0.05, False),
)


class Unavailable(Exception):
    """Jev could not answer. The message is safe to print: it never contains the API key."""


@dataclass(frozen=True)
class Decision:
    by: str
    grade: str
    confidence: float
    note: str
    basis: str
    requested: str | None = None


Decider = Callable[[dict], Decision]


def local_look(grade: str, reasons: list, metrics: dict | None = None) -> float:
    """How likely it is that a person should look, from the grade, the reasons, and near-misses.

    With no margins, a clean PASS is nearly sure and a FAIL is sure. A REVIEW climbs a little
    with each reason. A value just inside a one-sided line raises a PASS enough to escalate.
    """
    metrics = metrics or {}
    if grade == "FAIL":
        look = 1.0
    elif grade == "REVIEW":
        look = min(0.95, 0.75 + 0.05 * min(len(reasons), 4))
    elif grade == "PASS":
        look = 0.05
    else:
        look = 1.0
    if _near_hits(metrics):
        look = max(look, NEAR_LOOK)
    return round(look, 2)


def settle(look: float, judge_grade: str, *, by: str, note: str = "", basis: str,
           requested: str | None = None) -> Decision:
    """Turn one look and the judge's grade into a decision. Never lowers FAIL or REVIEW."""
    if not math.isfinite(look):
        look = 1.0
    else:
        look = min(1.0, max(0.0, look))
    grade = "REVIEW" if judge_grade == "PASS" and look >= LOOK_AT else judge_grade
    confidence = round((1.0 - look) if grade == "PASS" else look, 2)
    return Decision(by=by, grade=grade, confidence=confidence, note=note, basis=basis, requested=requested)


def _near_hits(metrics: dict) -> list[tuple[str, float]]:
    hits = []
    for name, line, slack, above in _NEAR:
        value = metrics.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            continue
        number = float(value)
        close = line <= number < line + slack if above else line - slack < number <= line
        if close:
            hits.append((name, number))
    return hits


def _near_note(metrics: dict) -> str:
    hits = _near_hits(metrics)[:2]
    if not hits:
        return ""
    bits = [f"{name.replace('_', ' ')} {value:g}" for name, value in hits]
    return "close to the line: " + ", ".join(bits)


def _compact(metrics: dict) -> dict:
    """Numbers a remote model may see. Paths and pixel buffers are dropped."""
    kept = {}
    for key, value in metrics.items():
        if not isinstance(key, str) or "/" in key or "\\" in key:
            continue
        plain = _plain(value)
        if plain is not None:
            kept[key] = plain
    return kept


def _plain(value: object) -> object | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str) and len(value) <= 80 and "/" not in value and "\\" not in value:
        return value
    if isinstance(value, (list, tuple)) and len(value) <= 8:
        items = []
        for item in value:
            if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item):
                return None
            items.append(item)
        return items
    return None


def _basis(grade: str, reasons: list, metrics: dict, by: str) -> str:
    payload = {
        "by": by,
        "grade": grade,
        "metrics": _compact(metrics),
        "model": JEV_MODEL if by == "jev" else "local",
        "reasons": list(reasons),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _fields(entry: dict) -> tuple[str, list, dict]:
    grade = entry.get("grade") if isinstance(entry.get("grade"), str) else ""
    reasons = list(entry.get("reasons") or [])
    metrics = entry.get("metrics") if isinstance(entry.get("metrics"), dict) else {}
    return grade, reasons, metrics


def _decide_local(entry: dict, requested: str | None) -> Decision:
    grade, reasons, metrics = _fields(entry)
    look = local_look(grade, reasons, metrics)
    note = _near_note(metrics) if grade == "PASS" and look >= LOOK_AT else ""
    asked = requested if requested and requested != "local" else None
    return settle(look, grade, by="local", note=note, basis=_basis(grade, reasons, metrics, "local"),
                  requested=asked)


def _public(decision: Decision) -> dict:
    out = {
        "by": decision.by,
        "grade": decision.grade,
        "confidence": decision.confidence,
        "note": decision.note,
        "basis": decision.basis,
    }
    if decision.requested:
        out["requested"] = decision.requested
    return out


def _from_saved(old: dict, basis: str) -> Decision | None:
    if old.get("by") != "jev" or old.get("basis") != basis or old.get("grade") not in _GRADES:
        return None
    try:
        confidence = float(old.get("confidence"))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(confidence):
        return None
    requested = old.get("requested") if isinstance(old.get("requested"), str) else None
    note = old.get("note") if isinstance(old.get("note"), str) else ""
    return Decision(by="jev", grade=old["grade"], confidence=confidence, note=note, basis=basis,
                    requested=requested)


def _ask_jev(grade: str, reasons: list, metrics: dict) -> float:
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if not key:
        raise Unavailable("needs TYPESAFE_API_KEY")
    state = {"grade": grade, "reasons": list(reasons), "metrics": _compact(metrics)}
    body = json.dumps({"model": JEV_MODEL, "state": state}, separators=(",", ":")).encode()
    req = urllib.request.Request(
        JEV_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": f"headshots/{__version__}",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        payload = json.loads(resp.read().decode())
    return _probability(payload)


def _probability(payload: object) -> float:
    value = _find_look(payload)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise Unavailable("answer was not a probability")
    look = float(value)
    if not math.isfinite(look) or look < 0.0 or look > 1.0:
        raise Unavailable("answer was not a probability")
    return look


def _find_look(payload: object) -> object:
    if isinstance(payload, (int, float)) and not isinstance(payload, bool):
        return payload
    if not isinstance(payload, dict):
        raise Unavailable("answer was not a probability")
    if "look" in payload and not isinstance(payload["look"], dict):
        return payload["look"]
    if "noul" in payload and not isinstance(payload["noul"], dict):
        return payload["noul"]
    answers = payload.get("answers")
    if isinstance(answers, dict):
        look = answers.get("look")
        if isinstance(look, dict) and "noul" in look:
            return look["noul"]
        if isinstance(look, (int, float)) and not isinstance(look, bool):
            return look
    raise Unavailable("answer was not a probability")


def _open_local(_name: str) -> Decider:
    def decider(entry: dict) -> Decision:
        return _decide_local(entry, None)
    return decider


def _open_jev(name: str) -> Decider:
    # apply() runs on the thread that writes the report, so this flag needs no lock.
    gave_up = False

    def give_up(entry: dict, text: str) -> Decision:
        nonlocal gave_up
        if not gave_up:
            events.say(text)
        gave_up = True
        return _decide_local(entry, name)

    def decider(entry: dict) -> Decision:
        grade, reasons, metrics = _fields(entry)
        basis = _basis(grade, reasons, metrics, "jev")
        old = entry.get("decide")
        if isinstance(old, dict):
            saved = _from_saved(old, basis)
            if saved is not None:
                return saved
        if gave_up:
            return _decide_local(entry, name)
        try:
            look = _ask_jev(grade, reasons, metrics)
        except Unavailable as err:
            return give_up(entry, f"Jev didn't answer ({err}); the rest are checked locally.")
        except urllib.error.HTTPError as err:
            why = "Jev refused TYPESAFE_API_KEY" if err.code == 401 else "Jev didn't answer"
            return give_up(entry, f"{why}; the rest are checked locally.")
        except (OSError, ValueError, TimeoutError, TypeError):
            return give_up(entry, "Jev didn't answer; the rest are checked locally.")
        return settle(look, grade, by="jev", basis=basis)

    return decider


@dataclass(frozen=True)
class Backend:
    feature: str | None
    open: Callable[[str], Decider]


BACKENDS: dict[str, Backend] = {
    "local": Backend(None, _open_local),
    "jev": Backend("decide.jev", _open_jev),
}


def choose(name: str) -> Decider:
    """The decider for this command. Says at most one line. Never exits the process."""
    backend = BACKENDS.get(name)
    if backend is None:
        return _open_local("local")
    if backend.feature and not entitlements.allows(backend.feature):
        what = entitlements.FEATURES.get(backend.feature, backend.feature)
        events.say(f"{what} need Premium. Run `headshots upgrade`. Checking photos locally.")
        return _local_with(name)
    return backend.open(name)


def _local_with(requested: str) -> Decider:
    def decider(entry: dict) -> Decision:
        return _decide_local(entry, requested)
    return decider


def apply(entry: dict, decider: Decider) -> None:
    """Write entry['decide']. A SKIPPED photo, or one with no output, is left untouched."""
    if entry.get("grade") == "SKIPPED" or not entry.get("output"):
        return
    entry["decide"] = _public(decider(entry))


def remarks(entry: dict) -> str:
    """A short confidence clause, or '' when the decision is a sure PASS."""
    decided = entry.get("decide")
    if not isinstance(decided, dict):
        return ""
    try:
        confidence = float(decided.get("confidence"))
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(confidence):
        return ""
    if decided.get("grade") == "PASS" and confidence >= SURE:
        return ""
    text = f"{confidence:.0%} sure"
    note = decided.get("note")
    if isinstance(note, str) and note:
        text = f"{text}, {note}"
    return text
