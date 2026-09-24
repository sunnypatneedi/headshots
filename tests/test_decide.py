"""Decide sits on top of a grade. Synthetic measurements, no photos, no models, no network."""
import json
import urllib.error

import pytest

from headshots import decide, events, polish
from headshots.cli import build_parser
from headshots.polish import Settings


def _photo(grade, reasons=(), metrics=None, output="a.jpg"):
    return {
        "source": "a.jpg",
        "output": output,
        "grade": grade,
        "reasons": list(reasons),
        "notes": [],
        "metrics": {} if metrics is None else dict(metrics),
    }


def _local(grade, reasons=(), metrics=None):
    entry = _photo(grade, reasons, metrics)
    decide.apply(entry, decide.choose("local"))
    return entry


def test_a_clean_pass_stays_a_sure_pass():
    entry = _local("PASS")
    assert entry["grade"] == "PASS"
    assert entry["decide"]["by"] == "local"
    assert entry["decide"]["grade"] == "PASS"
    assert entry["decide"]["confidence"] == 0.95
    assert "requested" not in entry["decide"]
    assert decide.remarks(entry) == ""


def test_one_soft_review_stays_a_review():
    entry = _local("REVIEW", ["eyes look soft"])
    assert entry["grade"] == "REVIEW"
    assert entry["decide"]["grade"] == "REVIEW"
    assert entry["decide"]["confidence"] == 0.8
    assert decide.remarks(entry) == "80% sure"


def test_more_reasons_raise_a_review_until_they_cap():
    entry = _local("REVIEW", ["a", "b", "c", "d", "e"])
    assert entry["decide"]["grade"] == "REVIEW"
    assert entry["decide"]["confidence"] == 0.95


def test_a_fail_stays_a_fail():
    entry = _local("FAIL", ["no face found in the output"])
    assert entry["grade"] == "FAIL"
    assert entry["decide"]["grade"] == "FAIL"
    assert entry["decide"]["confidence"] == 1.0
    assert decide.remarks(entry) == "100% sure"


def test_settle_never_clears_a_fail_or_a_review():
    assert decide.settle(0.0, "FAIL", by="local", basis="b").grade == "FAIL"
    assert decide.settle(0.99, "FAIL", by="local", basis="b").grade == "FAIL"
    assert decide.settle(0.0, "REVIEW", by="local", basis="b").grade == "REVIEW"
    passed = decide.settle(0.39, "PASS", by="local", basis="b")
    assert passed.grade == "PASS"
    assert passed.confidence == 0.61
    escalated = decide.settle(0.4, "PASS", by="local", basis="b")
    assert escalated.grade == "REVIEW"
    assert escalated.confidence == 0.4


def test_eyes_just_inside_the_line_escalate_a_pass():
    sharp = _local("PASS", metrics={"eye_sharpness": 0.61})
    assert sharp["grade"] == "PASS"
    assert sharp["decide"]["grade"] == "REVIEW"
    assert sharp["decide"]["confidence"] == 0.55
    assert sharp["decide"]["note"] == "close to the line: eye sharpness 0.61"
    assert decide.remarks(sharp) == "55% sure, close to the line: eye sharpness 0.61"
    assert _local("PASS", metrics={"eye_sharpness": 0.6})["decide"]["grade"] == "REVIEW"
    assert _local("PASS", metrics={"eye_sharpness": 0.65})["decide"]["grade"] == "PASS"
    assert _local("PASS", metrics={"eye_sharpness": 1.1})["decide"]["confidence"] == 0.95


def test_highlights_just_under_the_line_escalate_a_pass():
    hot = _local("PASS", metrics={"face_blown": 0.028})
    calm = _local("PASS", metrics={"face_blown": 0.01})
    assert hot["decide"]["grade"] == "REVIEW"
    assert calm["decide"]["grade"] == "PASS"


def test_a_stored_head_size_does_not_escalate_a_pass():
    """judge() bands head/planned_head when a plan exists. The stored head_size is not that ratio."""
    entry = _local("PASS", metrics={"head_size": 1.09, "planned_head_size": 1.0})
    assert entry["decide"]["grade"] == "PASS"
    assert entry["decide"]["confidence"] == 0.95


def test_a_skipped_photo_gets_no_decision():
    skipped = _photo("SKIPPED", ["no face found"], output=None)
    decide.apply(skipped, decide.choose("local"))
    assert "decide" not in skipped
    bare = _photo("PASS", output=None)
    decide.apply(bare, decide.choose("local"))
    assert "decide" not in bare


def test_the_shown_grade_follows_decide_and_still_bumps_for_the_set():
    assert polish.final_grade({"output": "a.jpg", "grade": "PASS", "decide": {"grade": "REVIEW"}}) == "REVIEW"
    assert polish.final_grade({"output": "a.jpg", "grade": "FAIL", "decide": {"grade": "FAIL"}}) == "FAIL"
    assert polish.final_grade({"output": "a.jpg", "grade": "PASS"}) == "PASS"
    flagged = {"output": "a.jpg", "grade": "PASS", "set_reasons": ["head 12% larger than the rest of the set"],
               "decide": {"grade": "PASS"}}
    assert polish.final_grade(flagged) == "REVIEW"
    assert polish.final_grade({"grade": "FAIL", "decide": {"grade": "FAIL"}}) == "SKIPPED"


def test_decide_is_a_flag_on_polish_and_run_only():
    polish_args = build_parser().parse_args(["polish", "photos", "--decide", "local"])
    run_args = build_parser().parse_args(["run", "photos", "--decide", "jev"])
    assert polish_args.decide == "local"
    assert run_args.decide == "jev"
    assert "decide" not in Settings.__dataclass_fields__
    with pytest.raises(SystemExit):
        build_parser().parse_args(["group", "photos", "--decide", "local"])


class _Body:
    def __init__(self, raw: bytes):
        self._raw = raw

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _install(monkeypatch, handler):
    monkeypatch.setattr(decide.urllib.request, "urlopen", handler)


def test_free_jev_checks_locally_and_says_to_upgrade_once(monkeypatch, capsys):
    monkeypatch.setenv("HEADSHOTS_PLAN", "free")

    def boom(*args, **kwargs):
        raise AssertionError("free plan called Jev")

    _install(monkeypatch, boom)
    decider = decide.choose("jev")
    first = _photo("PASS", metrics={"eye_sharpness": 1.1})
    second = _photo("PASS", metrics={"eye_sharpness": 1.1})
    decide.apply(first, decider)
    decide.apply(second, decider)
    assert first["grade"] == "PASS"
    assert first["decide"]["by"] == "local"
    assert first["decide"]["requested"] == "jev"
    assert first["decide"]["grade"] == "PASS"
    assert second["decide"]["by"] == "local"
    out = capsys.readouterr().out
    assert out.count("headshots upgrade") == 1
    assert "Checking photos locally." in out


def test_premium_jev_uses_the_look_it_was_given(monkeypatch, capsys):
    monkeypatch.setenv("HEADSHOTS_PLAN", "premium")
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    seen = {}

    def fake(req, timeout=10):
        seen["url"] = req.full_url
        seen["auth"] = req.get_header("Authorization")
        seen["body"] = json.loads(req.data.decode())
        return _Body(b'{"look": 0.8}')

    _install(monkeypatch, fake)
    entry = _photo("PASS", metrics={"eye_sharpness": 1.1, "scratch": "/secret/pixels"})
    entry["source"] = "/secret/IMG_0418.JPG"
    decide.apply(entry, decide.choose("jev"))
    assert entry["grade"] == "PASS"
    assert entry["decide"]["by"] == "jev"
    assert entry["decide"]["grade"] == "REVIEW"
    assert entry["decide"]["confidence"] == 0.8
    assert "requested" not in entry["decide"]
    assert seen["url"] == "https://api.typesafe.ai/v1/systemone"
    assert seen["auth"] == "Bearer test-key"
    assert seen["body"]["model"] == "jev-latest"
    assert "question" in seen["body"]
    assert "person should look" in seen["body"]["question"]
    assert set(seen["body"]["state"]) == {"grade", "reasons", "metrics"}
    assert seen["body"]["state"]["grade"] == "PASS"
    assert seen["body"]["state"]["metrics"]["eye_sharpness"] == 1.1
    blob = json.dumps(seen["body"])
    assert "test-key" not in blob
    assert "/secret" not in blob
    assert "pixels" not in blob
    assert "test-key" not in capsys.readouterr().out


def test_a_photo_jev_already_answered_is_not_asked_again(monkeypatch):
    monkeypatch.setenv("HEADSHOTS_PLAN", "premium")
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    calls = {"n": 0}

    def fake(req, timeout=10):
        calls["n"] += 1
        return _Body(b'{"look": 0.2}')

    _install(monkeypatch, fake)
    entry = _photo("PASS", metrics={"eye_sharpness": 1.1})
    decider = decide.choose("jev")
    decide.apply(entry, decider)
    decide.apply(entry, decider)
    assert calls["n"] == 1
    assert entry["decide"]["grade"] == "PASS"
    assert entry["decide"]["confidence"] == 0.8
    entry["metrics"]["eye_sharpness"] = 0.9
    decide.apply(entry, decider)
    assert calls["n"] == 2


def test_jev_falls_back_locally_after_one_message(monkeypatch, capsys):
    monkeypatch.setenv("HEADSHOTS_PLAN", "premium")
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    calls = {"n": 0}

    def fake(req, timeout=10):
        calls["n"] += 1
        raise urllib.error.URLError("down")

    _install(monkeypatch, fake)
    decider = decide.choose("jev")
    first = _photo("FAIL", ["no face found in the output"])
    second = _photo("PASS", metrics={"eye_sharpness": 1.1})
    decide.apply(first, decider)
    decide.apply(second, decider)
    assert calls["n"] == 1
    assert first["decide"]["by"] == "local"
    assert first["decide"]["requested"] == "jev"
    assert first["decide"]["grade"] == "FAIL"
    assert second["decide"]["by"] == "local"
    assert second["decide"]["grade"] == "PASS"
    out = capsys.readouterr().out
    assert out.count("checked locally") == 1
    assert "test-key" not in out


def test_a_bad_jev_answer_falls_back_locally(monkeypatch, capsys):
    monkeypatch.setenv("HEADSHOTS_PLAN", "premium")
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")

    def fake(req, timeout=10):
        return _Body(b'{"look": 2}')

    _install(monkeypatch, fake)
    entry = _photo("PASS", metrics={"eye_sharpness": 1.1})
    decide.apply(entry, decide.choose("jev"))
    assert entry["decide"]["by"] == "local"
    assert entry["decide"]["requested"] == "jev"
    assert entry["decide"]["confidence"] == 0.95
    assert "checked locally" in capsys.readouterr().out


def test_jev_without_a_key_does_not_call_the_network(monkeypatch, capsys):
    monkeypatch.setenv("HEADSHOTS_PLAN", "premium")
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)

    def boom(*args, **kwargs):
        raise AssertionError("missing key still called Jev")

    _install(monkeypatch, boom)
    entry = _photo("PASS", metrics={"eye_sharpness": 1.1})
    decide.apply(entry, decide.choose("jev"))
    assert entry["decide"]["by"] == "local"
    assert entry["decide"]["requested"] == "jev"
    out = capsys.readouterr().out
    assert "TYPESAFE_API_KEY" in out
    assert "checked locally" in out


def test_run_decides_an_unchanged_photo_without_polishing_it_again(tmp_path, monkeypatch):
    folder, out, st = _shoot(tmp_path)
    src, jpg = folder / "a.jpg", out / "a.jpg"
    src.write_bytes(b"original")
    jpg.write_bytes(b"polished")
    entry = _photo("PASS", metrics={"eye_sharpness": 0.61})
    entry.update(size=src.stat().st_size, mtime_ns=src.stat().st_mtime_ns, key=st.key,
                 out_mtime_ns=jpg.stat().st_mtime_ns)
    (out / "_report.json").write_text(json.dumps({
        "settings": {"ratio": st.ratio, "width": st.width, "zoom": st.zoom, "eye_line": st.eye_line,
                     "finish": st.finish, "bw": st.bw},
        "set_note": None,
        "photos": [entry],
    }))

    def boom(*args, **kwargs):
        raise AssertionError("polished again")

    monkeypatch.setattr(polish, "process", boom)
    monkeypatch.setattr(polish, "rejudge", boom)
    monkeypatch.setattr(polish, "contact_sheets", lambda *args, **kwargs: 1)
    entries = polish.run(folder, out, st, "unused-model")
    assert entries[0]["grade"] == "PASS"
    assert entries[0]["decide"]["grade"] == "REVIEW"
    saved = json.loads((out / "_report.json").read_text())
    assert saved["photos"][0]["grade"] == "PASS"
    assert saved["photos"][0]["decide"]["grade"] == "REVIEW"


def test_a_new_photo_is_decided_before_the_line_is_printed(tmp_path, monkeypatch, capsys):
    folder, out, st = _shoot(tmp_path)
    (folder / "a.jpg").write_bytes(b"x")
    entry = _photo("PASS", metrics={"eye_sharpness": 0.61})
    monkeypatch.setattr(polish, "process", lambda *args, **kwargs: dict(entry))
    monkeypatch.setattr(polish, "contact_sheets", lambda *args, **kwargs: 1)
    photos = []
    real_emit = events.emit

    def spy(kind, **fields):
        if kind == "photo":
            photos.append(fields)
        real_emit(kind, **fields)

    monkeypatch.setattr(polish.events, "emit", spy)
    entries = polish.run(folder, out, st, "unused-model")
    assert entries[0]["grade"] == "PASS"
    assert entries[0]["decide"]["grade"] == "REVIEW"
    assert photos[0]["grade"] == "REVIEW"
    assert photos[0]["confidence"] == 0.55
    assert photos[0]["decide"]["by"] == "local"
    assert "55% sure" in capsys.readouterr().out


def test_a_skipped_photo_is_printed_without_a_decision(tmp_path, monkeypatch):
    folder, out, st = _shoot(tmp_path)
    (folder / "a.jpg").write_bytes(b"x")
    entry = _photo("SKIPPED", ["no face found"], output=None)
    monkeypatch.setattr(polish, "process", lambda *args, **kwargs: dict(entry))
    monkeypatch.setattr(polish, "contact_sheets", lambda *args, **kwargs: 1)
    photos = []

    def spy(kind, **fields):
        if kind == "photo":
            photos.append(fields)

    monkeypatch.setattr(polish.events, "emit", spy)
    entries = polish.run(folder, out, st, "unused-model")
    assert "decide" not in entries[0]
    assert photos[0]["grade"] == "SKIPPED"
    assert photos[0]["decide"] is None
    assert photos[0]["confidence"] is None


def _shoot(tmp_path):
    folder, out = tmp_path / "in", tmp_path / "out"
    folder.mkdir()
    out.mkdir()
    return folder, out, Settings()
