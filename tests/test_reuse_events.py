"""Cache-hit (full reuse) runs must still emit one `photo` event per reused entry.

The Mac gallery grids `photo` events. If every file is unchanged, `jobs` is empty and — without
this — zero photo events leave an empty gallery under a non-empty polished summary.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from PIL import Image

from headshots import events, polish
from headshots.polish import Settings


def _tiny_jpeg(path: Path, color: tuple[int, int, int] = (120, 130, 140)) -> None:
    buf = io.BytesIO()
    Image.new("RGB", (32, 40), color).save(buf, format="JPEG", quality=85)
    path.write_bytes(buf.getvalue())


def test_full_reuse_emits_one_photo_per_reused_entry(tmp_path, monkeypatch):
    folder = tmp_path / "shoot"
    out_dir = folder / "polished"
    folder.mkdir()
    out_dir.mkdir()

    st = Settings()
    names = ["person-a-01.jpg", "person-b-01.jpg"]
    photos = []
    for i, name in enumerate(names):
        src = folder / name
        _tiny_jpeg(src, color=(100 + i * 20, 110, 120))
        out = out_dir / name
        _tiny_jpeg(out, color=(90 + i * 20, 100, 110))
        s, o = src.stat(), out.stat()
        photos.append({
            "source": name,
            "size": s.st_size,
            "mtime_ns": s.st_mtime_ns,
            "key": st.key,
            "output": name,
            "out_mtime_ns": o.st_mtime_ns,
            "grade": "PASS" if i == 0 else "REVIEW",
            "reasons": [] if i == 0 else ["eyes a bit high"],
            "notes": [],
            "metrics": {"head_size": 0.42, "backdrop_luma": 150},
        })

    report = {"settings": {
        "ratio": st.ratio, "width": st.width, "zoom": st.zoom,
        "eye_line": st.eye_line, "finish": st.finish, "bw": st.bw,
    }, "set_note": None, "photos": photos}
    (out_dir / "_report.json").write_text(json.dumps(report, indent=1))
    _tiny_jpeg(out_dir / "_contact-sheet.jpg")  # present so reuse need not rebuild sheets

    captured: list[dict] = []

    def capture(kind, **fields):
        captured.append({"event": kind, **fields})

    monkeypatch.setattr(events, "emit", capture)
    monkeypatch.setattr(events, "say", lambda *a, **k: None)
    monkeypatch.setattr(polish, "contact_sheets", lambda *a, **k: 1)

    entries = polish.run(folder, out_dir, st, model="unused-on-full-reuse")

    assert len(entries) == 2
    photo_events = [e for e in captured if e["event"] == "photo"]
    assert {e["source"] for e in photo_events} == set(names)
    assert len(photo_events) == 2
    by_source = {e["source"]: e for e in photo_events}
    assert by_source["person-a-01.jpg"]["grade"] == "PASS"
    assert by_source["person-a-01.jpg"]["output"] == "person-a-01.jpg"
    assert by_source["person-b-01.jpg"]["grade"] == "REVIEW"

    starts = [e for e in captured if e["event"] == "start"]
    assert starts and starts[0]["total"] == 2 and starts[0]["unchanged"] == 2

    polished = [e for e in captured if e["event"] == "polished"]
    assert polished and polished[0]["processed"] == 0 and polished[0]["unchanged"] == 2
