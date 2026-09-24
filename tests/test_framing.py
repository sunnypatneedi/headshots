"""The framing and finishing maths, on made-up faces. No photos, no models, no network."""
import json

import numpy as np
import pytest

from headshots import polish
from headshots.polish import Face, Settings


def face_at(cx, cy, iod=100.0):
    """A face looking straight ahead: eyes iod apart, mouth below, nose between."""
    eye_r = np.array([cx - iod / 2, cy])
    eye_l = np.array([cx + iod / 2, cy])
    mouth_y = cy + iod * 0.9
    lm = np.array([eye_r, eye_l, [cx, cy + iod * 0.5],
                   [cx - iod * 0.35, mouth_y], [cx + iod * 0.35, mouth_y]])
    box = np.array([cx - iod, cy - iod * 0.9, iod * 2, iod * 2.6])
    return Face(box, lm, 0.99)


def eye_position(box, face, st):
    """Where the eyes land in the crop: (across, down), each 0-1."""
    left, top, right, bottom = box
    return ((face.eyes[0] - left) / (right - left), (face.eyes[1] - top) / (bottom - top))


# ---------------------------------------------------------------- framing

def test_eyes_land_on_the_requested_line():
    st = Settings()
    f = face_at(2000, 1400)
    box, _ = polish.plan_crop(f, 4032, 3024, st)
    assert eye_position(box, f, st)[1] == pytest.approx(st.eye_line, abs=0.02)


def test_the_face_is_centred_across():
    f = face_at(2000, 1400)
    box, _ = polish.plan_crop(f, 4032, 3024, Settings())
    assert eye_position(box, f, Settings())[0] == pytest.approx(0.5, abs=0.02)


def test_the_crop_keeps_the_requested_shape():
    for ratio in (4 / 5, 2 / 3, 1.0):
        st = Settings(ratio=ratio)
        box, _ = polish.plan_crop(face_at(2000, 1400), 4032, 3024, st)
        left, top, right, bottom = box
        assert (right - left) / (bottom - top) == pytest.approx(ratio, rel=0.01)


def test_the_crop_stays_inside_the_photo():
    for cx, cy in [(300, 300), (3700, 2700), (2000, 200), (100, 1500)]:
        box, _ = polish.plan_crop(face_at(cx, cy, iod=60), 4032, 3024, Settings())
        left, top, right, bottom = box
        assert left >= -0.5 and top >= -0.5
        assert right <= 4032.5 and bottom <= 3024.5


def test_two_faces_at_different_distances_come_out_the_same_size():
    """The whole point of the set: a head is the same fraction of the frame whoever it is."""
    st = Settings()
    sizes = []
    for iod in (70, 100, 140):
        f = face_at(2000, 1400, iod=iod)
        box, _ = polish.plan_crop(f, 4032, 3024, st)
        sizes.append(f.scale / (box[3] - box[1]))
    assert max(sizes) / min(sizes) == pytest.approx(1.0, abs=0.02)


def test_zoom_tightens_the_crop():
    f = face_at(2000, 1400)
    wide, _ = polish.plan_crop(f, 4032, 3024, Settings(zoom=0.85))
    tight, _ = polish.plan_crop(f, 4032, 3024, Settings(zoom=1.15))
    assert (tight[3] - tight[1]) < (wide[3] - wide[1])


def test_a_known_crown_is_never_cropped_into():
    """If the top of the head was found, the crop must sit above it."""
    f = face_at(2000, 1400)
    crown = f.box[1] - 120
    box, _ = polish.plan_crop(f, 4032, 3024, Settings(), crown=crown)
    assert box[1] <= crown


# ---------------------------------------------------------------- colour and tone

def test_srgb_decode_encode_round_trips():
    x = np.linspace(0, 1, 257, dtype=np.float32)
    assert np.allclose(polish.encode(polish.decode(x)), x, atol=1e-3)


def test_lab_round_trips():
    rng = np.random.default_rng(0)
    rgb = rng.random((16, 16, 3), dtype=np.float32)
    assert np.allclose(polish.lab_to_srgb(polish.srgb_to_lab(rgb)), rgb, atol=2e-3)


def test_grey_stays_grey_through_lab():
    grey = np.full((4, 4, 3), 0.5, dtype=np.float32)
    lab = polish.srgb_to_lab(grey)
    assert np.allclose(lab[..., 1:], 0, atol=1e-3)


def test_finishing_does_not_blow_out_a_normal_face():
    rng = np.random.default_rng(1)
    img = np.clip(rng.normal(150, 20, (600, 480, 3)), 0, 255).astype(np.uint8)
    out, _ = polish.finish(img, face_at(240, 250, iod=90), bw=False)
    assert out.dtype == np.uint8
    assert (out >= 250).mean() < 0.02


def test_black_and_white_really_is_neutral():
    rng = np.random.default_rng(2)
    img = np.clip(rng.normal(140, 25, (400, 320, 3)), 0, 255).astype(np.uint8)
    out, _ = polish.finish(img, face_at(160, 170, iod=70), bw=True)
    assert out[..., 0].astype(int).tolist() == out[..., 2].astype(int).tolist()


# ---------------------------------------------------------------- grading and settings

@pytest.mark.parametrize("x,grade", [(1.0, "PASS"), (0.95, "PASS"), (0.8, "REVIEW"), (0.5, "FAIL")])
def test_band_grades_where_you_would_expect(x, grade):
    assert polish.band(x, (0.9, 1.1), (0.75, 1.3)) == grade


def test_a_folder_remembers_how_it_was_polished(tmp_path):
    """Add photos to a finished set months later and they should match, not restart the look."""
    saved = Settings(ratio=2 / 3, width=1200, zoom=0.85)
    (tmp_path / "_report.json").write_text(json.dumps({"settings": {
        "ratio": saved.ratio, "width": saved.width, "zoom": saved.zoom,
        "eye_line": saved.eye_line, "finish": saved.finish, "bw": saved.bw}}))
    blank = type("A", (), {"ratio": None, "width": None, "zoom": None,
                           "eye_line": None, "finish": None, "bw": None})()
    assert polish.settings_for(tmp_path, blank) == saved


def test_a_flag_beats_the_saved_setting(tmp_path):
    blank = type("A", (), {"ratio": None, "width": 900, "zoom": None,
                           "eye_line": None, "finish": None, "bw": None})()
    assert polish.settings_for(tmp_path, blank).width == 900


def test_changing_the_code_invalidates_the_cache():
    """The cache key folds in a hash of the polishing code, so an upgrade re-polishes."""
    a = Settings().key
    old, polish.CODE_KEY = polish.CODE_KEY, "different"
    try:
        assert Settings().key != a
    finally:
        polish.CODE_KEY = old


def test_the_embedded_colour_profile_carries_no_timestamp():
    """Same photos in, same bytes out. Pillow would otherwise stamp the profile with the clock."""
    assert polish.SRGB_ICC[24:36] == b"\0" * 12
