"""Free and premium.

Everything the tool does on your machine is free. Premium adds remote decide backends
(see decide.py). The plan is HEADSHOTS_PLAN if that is set, otherwise the receipt at
~/.config/headshots/receipt.json, otherwise free. Nothing here is checked online, and
this module never reads a Stripe secret key.
"""
from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path

# decide.remote is a row with no backend yet, so the next remote check is a table entry.
FEATURES: dict[str, str] = {
    "decide.jev": "Jev decisions (--decide jev)",
    "decide.remote": "remote decisions",
}
PLANS: dict[str, frozenset[str]] = {
    "free": frozenset(),
    "premium": frozenset(FEATURES),
}
RECEIPT_VERSION = 1
# A Stripe Payment Link, once premium is on sale.
# HEADSHOTS_CHECKOUT_URL overrides this. There is no secret key beside it.
BUY: str | None = None


def receipt_file(environ: Mapping[str, str] | None = None) -> Path:
    """$XDG_CONFIG_HOME/headshots/receipt.json, else ~/.config/headshots/receipt.json."""
    env = os.environ if environ is None else environ
    base = env.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "headshots" / "receipt.json"


def _known_plan(value: object) -> str | None:
    if isinstance(value, str) and value in PLANS:
        return value
    return None


def plan(environ: Mapping[str, str] | None = None, receipt_path: Path | None = None) -> str:
    """HEADSHOTS_PLAN wins when it is set. Otherwise a versioned receipt. Otherwise free.

    An unknown name, a bad version, or a receipt that cannot be read is free.
    """
    env = os.environ if environ is None else environ
    raw = env.get("HEADSHOTS_PLAN")
    if raw is not None:
        return _known_plan(raw.strip().lower()) or "free"
    path = receipt_file(env) if receipt_path is None else receipt_path
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return "free"
    if not isinstance(data, dict) or data.get("version") != RECEIPT_VERSION:
        return "free"
    return _known_plan(data.get("plan")) or "free"


def allows(feature: str, environ: Mapping[str, str] | None = None,
           receipt_path: Path | None = None) -> bool:
    return feature in PLANS[plan(environ, receipt_path)]


def save_receipt(path: Path | None = None, *, plan_name: str = "premium") -> Path:
    """Write {version, plan}. The caller picks the path; the default is receipt_file()."""
    if plan_name not in PLANS:
        raise ValueError(f"unknown plan {plan_name}")
    dest = receipt_file() if path is None else path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({"version": RECEIPT_VERSION, "plan": plan_name}, indent=1) + "\n")
    return dest


def checkout_url(environ: Mapping[str, str] | None = None) -> str | None:
    env = os.environ if environ is None else environ
    return env.get("HEADSHOTS_CHECKOUT_URL") or BUY or None


def upgrade(receipt_path: Path | None = None, environ: Mapping[str, str] | None = None) -> str:
    """Save a premium receipt and return the checkout link, when one is configured.

    `headshots upgrade` prints this. Payment is not verified: the receipt is a local
    file until a webhook exists (see docs/PREMIUM.md).
    """
    saved = save_receipt(receipt_file(environ) if receipt_path is None else receipt_path)
    url = checkout_url(environ)
    if url:
        return f"Premium checkout: {url}\nSaved a premium receipt to {saved}"
    return f"No payment link is set yet (HEADSHOTS_CHECKOUT_URL). Saved a premium receipt to {saved}"
