"""Contrast and motion budgets for the app theme tokens.

tokens.json is the shared source of truth with Theme.swift. These tests keep light and dark
readable (WCAG body 4.5:1, UI 3:1) and keep motion under 300ms.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOKENS = ROOT / "app" / "preview" / "tokens.json"
THEME_SWIFT = ROOT / "app" / "Sources" / "Headshots" / "Theme.swift"
PRESETS = ROOT / "app" / "preview" / "option_presets.json"


def _load():
    return json.loads(TOKENS.read_text())


def _rel_luminance(rgb: list[int]) -> float:
    def channel(c: int) -> float:
        x = c / 255.0
        return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: list[int], bg: list[int]) -> float:
    l1, l2 = _rel_luminance(fg), _rel_luminance(bg)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


@pytest.mark.parametrize("theme_name", ["light", "dark"])
def test_theme_contrast_pairs(theme_name: str):
    data = _load()
    theme = data["themes"][theme_name]
    mins = {"body": data["meta"]["contrast_min_body"], "ui": data["meta"]["contrast_min_ui"]}
    failures = []
    for pair in data["pairs"]:
        fg, bg = theme[pair["fg"]], theme[pair["bg"]]
        ratio = contrast_ratio(fg, bg)
        need = mins[pair["min"]]
        if ratio < need:
            failures.append(
                f"{theme_name}: {pair['fg']} on {pair['bg']} = {ratio:.2f}:1 (need {need}:1)"
            )
    assert not failures, "contrast failures:\n" + "\n".join(failures)


def test_motion_budget_under_300ms():
    data = _load()
    assert data["meta"]["motion_max_ms"] <= 300
    for name, ms in data["motion_ms"].items():
        assert ms <= data["meta"]["motion_max_ms"], f"{name}={ms}ms exceeds max"


def test_swift_theme_mentions_shared_tokens_file():
    src = THEME_SWIFT.read_text()
    assert "tokens.json" in src
    assert "HSTheme" in src
    assert "Motion" in src


def test_option_presets_match_expected_zooms():
    presets = json.loads(PRESETS.read_text())
    framing = presets["framing"]
    assert framing["headShoulders"]["zoom"] == pytest.approx(0.85)
    assert framing["closeUp"]["zoom"] == pytest.approx(1.15)
    assert framing["halfBody"]["zoom"] == pytest.approx(0.70)
    assert presets["defaults"]["framing"] == "headShoulders"
    assert presets["defaults"]["softStudio"] is True


def test_swift_options_use_preset_zooms():
    """Keep Options.Framing.zoom in Runner.swift aligned with option_presets.json."""
    src = (ROOT / "app" / "Sources" / "Headshots" / "Runner.swift").read_text()
    presets = json.loads(PRESETS.read_text())["framing"]
    for key, spec in presets.items():
        # zoom literals appear as 0.85 / 1.15 / 0.70
        zoom = spec["zoom"]
        rendered = f"{zoom:.2f}" if not float(zoom).is_integer() else f"{zoom:.1f}0"
        # accept either 0.70 or 0.7 forms by checking the two-decimal form used in Swift
        assert f"return {zoom:.2f}" in src or f"return {zoom}" in src, (
            f"Framing.{key} zoom {zoom} missing from Runner.swift"
        )
        assert rendered  # silence unused if above passes


def test_token_rgb_round_trip_stable():
    """Sanity: every theme colour is a 3-int sRGB triple in 0..255."""
    data = _load()
    for theme_name, theme in data["themes"].items():
        for role, rgb in theme.items():
            assert len(rgb) == 3, f"{theme_name}.{role}"
            assert all(isinstance(c, int) and 0 <= c <= 255 for c in rgb), f"{theme_name}.{role}"


def test_relative_luminance_known_black_white():
    assert _rel_luminance([0, 0, 0]) == pytest.approx(0.0)
    assert _rel_luminance([255, 255, 255]) == pytest.approx(1.0)
    assert contrast_ratio([0, 0, 0], [255, 255, 255]) == pytest.approx(21.0)
    assert math.isfinite(contrast_ratio([37, 99, 235], [255, 255, 255]))
