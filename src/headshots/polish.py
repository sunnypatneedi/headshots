"""Framing, finishing and judging one folder of portraits.

Polish, per photo: read it as Photos shows it (rotation applied, Display P3 -> sRGB), find the
face, frame every shot the same way (same head size, eyes on the same line, 4:5 at 1600x2000),
finish lightly (luminance levels and S-curve, a little light on the face, subtle vignette,
output sharpening; a color cast is fixed only when skin is clearly off; no smoothing or
reshaping), and save an sRGB JPEG with all metadata (GPS included) stripped.

Judge, per output file: re-detect the face in the saved JPEG and re-measure framing, clipping,
skin color, eye sharpness, stray faces, fidelity to the original and metadata, then grade it
PASS / REVIEW / FAIL. A set-level pass flags head sizes that don't match the rest.

Results land in <folder>/polished/ with _contact-sheet.jpg and _report.json. Originals are never
modified. Re-runs skip photos that haven't changed and never overwrite an output you edited.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import os
import plistlib
import re
import sys
import time
import zlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageCms, ImageDraw, ImageFont, ImageOps

from . import events, models
from .__init__ import __version__

try:
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)  # hide DNN backend chatter
except AttributeError:
    pass

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIC_OK = True
except ImportError:  # HEIC won't open; JPEG/PNG/TIFF still work
    HEIC_OK = False

IMAGE_EXTS = [".heic", ".heif", ".jpg", ".jpeg", ".png", ".tif", ".tiff"]  # preference order for same-name files


# Framing. Crop height = HEAD_TO_FRAME x face scale, where face scale = max(2 x eye distance,
# 1.8 x eyes-to-mouth): taking the max keeps head size steady when the head turns or tilts.
HEAD_TO_FRAME = 3.4
# When a photo can't give the standard framing (subject near an edge, head close to the top):
# slide the crop sideways (up to 12% of its width), zoom in (up to 12%), or move the eyes lower
# (up to 10%), whichever compromise is smallest. Room above the top of the head: at least 3%,
# ideally 6-12% of the frame.
MAX_SLIDE, MAX_ZOOM_IN, MAX_EYE_DRIFT = 0.12, 0.12, 0.10
MIN_HEADROOM, HEADROOM = 0.03, (0.06, 0.12)   # the upper value only sets the judge's expectation

SKIN_HUE, SKIN_CHROMA = (30.0, 75.0), 55.0      # outside these, skin reads as a color cast (CIELAB)
LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)  # Rec.709 luma weights
SRGB = ImageCms.createProfile("sRGB")
# Pillow stamps a profile with the moment it was built, so two runs that produce identical pixels
# would still write different bytes. Zeroing the date makes the output reproducible, which keeps
# re-runs from churning backups and makes "did anything actually change?" answerable with md5.
_icc = bytearray(ImageCms.ImageCmsProfile(SRGB).tobytes())
_icc[24:36] = b"\0" * 12                                  # ICC header: profile creation date/time
SRGB_ICC = bytes(_icc)

APPLE_EDIT_NAMES = {"DepthEffect": "Portrait blur", "PortraitEffect": "Portrait Lighting",
                    "Crop": "crop", "SmartTone": "light", "SmartColor": "color",
                    "Effect": "filter", "WhiteBalance": "white balance", "Retouch": "retouch"}

import hashlib  # noqa: E402  (kept next to what it is for)

try:  # any change to this file re-polishes cached photos
    CODE_KEY = hashlib.sha1(Path(__file__).read_bytes()).hexdigest()[:10]
except OSError:  # a frozen build: the version stands in
    CODE_KEY = hashlib.sha1(__version__.encode()).hexdigest()[:10]


@dataclass
class Settings:
    ratio: float = 4 / 5          # width / height
    width: int = 1600
    zoom: float = 1.0             # >1 = tighter
    eye_line: float = 0.42        # eyes this far down from the top
    finish: bool = True
    bw: bool = False

    @property
    def size(self) -> tuple[int, int]:
        return self.width, round(self.width / self.ratio)

    @property
    def key(self) -> str:
        return hashlib.sha1((json.dumps(asdict(self), sort_keys=True) + CODE_KEY).encode()).hexdigest()[:12]


@dataclass
class Face:
    box: np.ndarray               # x, y, w, h
    lm: np.ndarray                # 5x2: right eye, left eye, nose, mouth right, mouth left
    score: float

    @property
    def eyes(self) -> np.ndarray:
        return (self.lm[0] + self.lm[1]) / 2

    @property
    def iod(self) -> float:       # distance between the eyes
        return float(np.linalg.norm(self.lm[1] - self.lm[0]))

    @property
    def scale(self) -> float:
        eye_mouth = np.linalg.norm((self.lm[3] + self.lm[4]) / 2 - self.eyes)
        return float(max(2.0 * self.iod, 1.8 * eye_mouth))

    def moved(self, box, k: float) -> Face:
        """The same face in the coordinates of a crop starting at box[:2], scaled by k."""
        o = np.array(box[:2])
        return Face(np.r_[(self.box[:2] - o) * k, self.box[2:] * k], (self.lm - o) * k, self.score)


class Skip(Exception):
    """The photo can't become a headshot; the message says why."""


# ---------------------------------------------------------------- color

def load(path: Path) -> tuple[np.ndarray, bytes | None]:
    """Stored pixels with rotation applied (uint8 RGB), plus the embedded color profile."""
    im = ImageOps.exif_transpose(Image.open(path))
    return np.asarray(im.convert("RGB")), im.info.get("icc_profile")


def to_srgb8(rgb: np.ndarray, icc: bytes | None) -> np.ndarray:
    """uint8 pixels from their embedded profile to sRGB. The costliest step per pixel, so it only
    ever runs on the final crop or on thumbnails, never on the whole 12 MP photo."""
    if not icc:
        return rgb
    try:
        tf = ImageCms.buildTransform(ImageCms.ImageCmsProfile(io.BytesIO(icc)), SRGB, "RGB", "RGB")
        return np.asarray(ImageCms.applyTransform(Image.fromarray(rgb), tf))
    except (ImageCms.PyCMSError, OSError, ValueError):
        return rgb  # unreadable or non-RGB profile: treat the pixels as sRGB


def save_jpeg(rgb: np.ndarray, path: Path) -> None:
    """sRGB-tagged JPEG, full-resolution color (4:4:4), no EXIF/GPS carried over. Baseline
    encoding: the same pixels as progressive/optimized, 4x faster to write, ~3% larger."""
    Image.fromarray(rgb).save(path, "JPEG", quality=92, subsampling=0, icc_profile=SRGB_ICC)


def _to_linear(x):
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def _to_srgb(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * x ** (1 / 2.4) - 0.055)


# The sRGB curve via 64k-entry lookup tables: ~10x faster than pow() on millions of pixels,
# and accurate to well under 1/100 of an 8-bit level.
_N = 65535
_DECODE = _to_linear(np.linspace(0, 1, _N + 1)).astype(np.float32)
_ENCODE = _to_srgb(np.linspace(0, 1, _N + 1)).astype(np.float32)


def decode(x: np.ndarray) -> np.ndarray:
    """sRGB 0..1 -> linear light."""
    return _DECODE[(np.clip(x, 0, 1) * _N + 0.5).astype(np.uint16)]


def encode(lin: np.ndarray) -> np.ndarray:
    """Linear light -> sRGB 0..1 (clipping at white)."""
    return _ENCODE[(np.clip(lin, 0, 1) * _N + 0.5).astype(np.uint16)]


XYZ = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
D65 = np.array([0.9505, 1.0, 1.089])


def srgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    xyz = _to_linear(np.asarray(rgb, np.float64)) @ XYZ.T / D65
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]),
                     200 * (f[..., 1] - f[..., 2])], axis=-1)


def lab_to_srgb(lab: np.ndarray) -> np.ndarray:
    fy = (lab[..., 0] + 16) / 116
    f = np.stack([fy + lab[..., 1] / 500, fy, fy - lab[..., 2] / 200], axis=-1)
    xyz = np.where(f > 0.206893, f ** 3, (f - 16 / 116) / 7.787) * D65
    return _to_srgb(xyz @ np.linalg.inv(XYZ).T)


def gray8(rgb8: np.ndarray) -> np.ndarray:
    return np.repeat(cv2.cvtColor(rgb8, cv2.COLOR_RGB2GRAY)[..., None], 3, axis=2)


# ---------------------------------------------------------------- faces

def ensure_model() -> str:
    return models.ensure("detect")


def detect_faces(rgb: np.ndarray, model: str, first: int = 1280) -> list[Face]:
    """All faces, largest first. The largest is re-detected up close for precise landmarks."""
    faces = _detect(rgb, model, first) or _detect(rgb, model, 2 * first)   # retry larger for small faces
    if faces:
        faces[0] = _refine(rgb, faces[0], model)
    return faces


def _detect(rgb: np.ndarray, model: str, max_side: int, enlarge: bool = False) -> list[Face]:
    h, w = rgb.shape[:2]
    s = max_side / max(h, w) if enlarge else min(1.0, max_side / max(h, w))
    if s != 1:
        rgb = cv2.resize(rgb, (round(w * s), round(h * s)),
                         interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
    det = cv2.FaceDetectorYN.create(model, "", (rgb.shape[1], rgb.shape[0]), 0.7, 0.3, 50)
    _, found = det.detect(np.ascontiguousarray(rgb[..., ::-1]))      # the detector wants BGR
    faces = [Face(r[:4] / s, (r[4:14] / s).reshape(5, 2), float(r[14]))
             for r in (found if found is not None else [])]
    return sorted(faces, key=lambda f: f.scale, reverse=True)


def _refine(rgb: np.ndarray, face: Face, model: str) -> Face:
    """Re-detect on a close crop (face ~250 px wide): steadier landmarks, steadier framing."""
    x, y, fw, fh = face.box
    half = 1.25 * max(fw, fh)
    l, t = int(max(0, x + fw / 2 - half)), int(max(0, y + fh / 2 - half))
    r, b = int(min(rgb.shape[1], x + fw / 2 + half)), int(min(rgb.shape[0], y + fh / 2 + half))
    found = _detect(rgb[t:b, l:r], model, 640, enlarge=True)
    if not found:
        return face
    near = min(found, key=lambda f: np.linalg.norm(f.eyes + (l, t) - face.eyes))
    return Face(np.r_[near.box[:2] + (l, t), near.box[2:]], near.lm + (l, t), near.score)


def eye_sharpness(rgb: np.ndarray, face: Face) -> float:
    """Detail around the eyes, normalized for face size and contrast. Sharp phone shots
    score about 1.0-1.2; a visible focus miss or motion blur drops it below 0.6."""
    iod = face.iod
    (x0, y0), (x1, y1) = face.lm[0], face.lm[1]
    t, b = int(max(0, min(y0, y1) - 0.3 * iod)), int(max(y0, y1) + 0.3 * iod)
    l, r = int(max(0, min(x0, x1) - 0.5 * iod)), int(max(x0, x1) + 0.5 * iod)
    patch = cv2.cvtColor(np.ascontiguousarray(rgb[t:b, l:r]), cv2.COLOR_RGB2GRAY)
    k = min(1.0, 100 / iod)                        # compare every face at eye distance = 100 px
    patch = cv2.resize(patch, None, fx=k, fy=k, interpolation=cv2.INTER_AREA).astype(np.float32)
    return float(cv2.Laplacian(patch, cv2.CV_32F, ksize=3).std() / (patch.std() + 1e-6))


def find_crown(rgb: np.ndarray, face: Face) -> float | None:
    """Row of the top of the head (hair, bows, hats) above this face: the first rows, walking up
    from the brow, where a band over the head matches the backdrop beside it. 0 if the head
    runs off the top of the photo; None if the backdrop is too busy to tell."""
    q = min(1.0, 100 / face.scale)                       # work where the face scale is ~100 px
    lab = cv2.cvtColor(cv2.resize(rgb, None, fx=q, fy=q, interpolation=cv2.INTER_AREA).astype(np.float32) / 255,
                       cv2.COLOR_RGB2Lab)
    w = lab.shape[1]
    ex, s, brow = face.eyes[0] * q, face.scale * q, int(face.box[1] * q)
    top = int(max(0, brow - 3 * s))
    cols = lambda a, b: lab[top:brow, int(np.clip(ex + a * s, 0, w)):int(np.clip(ex + b * s, 0, w))]  # noqa: E731
    band = cols(-0.8, 0.8)
    sides = [x for x in (cols(-2.2, -1.2), cols(1.2, 2.2)) if x.shape[1] >= 3]
    if brow - top < 5 or band.shape[1] < 5 or not sides:
        return None
    side = np.concatenate(sides, axis=1)
    ref = cv2.blur(np.median(side, axis=1)[:, None, :], (1, 9))    # backdrop color, row by row
    spread = float(np.percentile(np.linalg.norm(side - ref, axis=2), 95))
    if spread > 25:
        return None                                      # busy background: can't tell hair from it
    head = (np.linalg.norm(band - ref, axis=2) > max(10.0, 1.5 * spread)).mean(axis=1) >= 0.06
    crown, gap = None, 0
    for r in range(len(head) - 1, -1, -1):               # walk up from the brow
        if head[r]:
            crown, gap = r, 0
        elif (gap := gap + 1) > max(3, int(0.06 * s)):
            break
    if crown is None or (crown == 0 and top > 0):        # nothing found, or "head" 3 face-heights tall
        return None
    return (top + crown) / q


def skin_lab(img: np.ndarray, face: Face) -> np.ndarray | None:
    """Median CIELAB (L, a, b) of both mid-cheeks, skipping shadows and shine."""
    iod, r = face.iod, max(2, int(0.1 * face.iod))
    samples = []
    for eye, mouth, side in ((face.lm[0], face.lm[3], -1), (face.lm[1], face.lm[4], 1)):
        x, y = ((eye + mouth) / 2 + [side * 0.12 * iod, 0]).astype(int)
        samples.append(img[max(0, y - r):y + r, max(0, x - r):x + r].reshape(-1, 3))
    lab = srgb_to_lab(np.concatenate(samples))
    lab = lab[(lab[:, 0] > 20) & (lab[:, 0] < 92)]
    return np.median(lab, axis=0) if len(lab) >= 20 else None


def inner_face(shape, face: Face) -> np.ndarray:
    """Boolean mask of the face from brows to below the mouth, cheek to cheek (little hair)."""
    iod, (e0, e1, m0, m1) = face.iod, face.lm[[0, 1, 3, 4]]
    pts = np.array([e0 + (-.35 * iod, -.45 * iod), e1 + (.35 * iod, -.45 * iod),
                    m1 + (.2 * iod, .3 * iod), m0 + (-.2 * iod, .3 * iod)], np.int32)
    mask = np.zeros(shape[:2], np.uint8)
    cv2.fillConvexPoly(mask, pts, 1)
    return mask.astype(bool)


# ---------------------------------------------------------------- framing

def plan_crop(face: Face, w: int, h: int, st: Settings,
              crown: float | None = None) -> tuple[tuple[float, ...], list[str]]:
    """Crop box (left, top, right, bottom) that puts this face in the standard position: head
    size and eye line as in every other shot, and, when the top of the head (`crown`) is known,
    the whole head in the frame with some room above it. When the photo doesn't allow all of
    that, pick the smallest compromise: slide sideways, zoom in a little, move the eyes a little."""
    fx, fy, fw, fh = face.box
    pts = np.vstack([face.lm, [[fx, fy], [fx + fw, fy + fh]]])
    tol = 0.03 * fw
    for side, cut in (("left", pts[:, 0].min() < -tol), ("right", pts[:, 0].max() > w + tol),
                      ("top", pts[:, 1].min() < -tol), ("bottom", pts[:, 1].max() > h + tol)):
        if cut:
            raise Skip(f"face is cut off at the {side} edge of the photo")

    cx, ey = face.eyes
    ideal = HEAD_TO_FRAME * face.scale / st.zoom
    crown = None if crown is None else crown - 0.03 * face.scale    # margin for stray hairs and bow tips
    best = None
    heights = {min(ideal * (1 - z), h, w / st.ratio) for z in np.arange(0, 0.35 + 1e-9, 0.01)}
    for H in sorted(heights, reverse=True):
        W = H * st.ratio
        left = float(np.clip(cx - W / 2, 0, w - W))
        dx = abs(left - (cx - W / 2)) / W
        if dx > MAX_SLIDE + 1e-6:
            continue
        zoom_in = 1 - H / ideal
        for drift in np.arange(-0.08, 0.25 + 1e-9, 0.005):   # + = eyes lower in the frame
            top = ey - (st.eye_line + drift) * H
            if top < -0.5 or top + H > h + 0.5:
                continue
            room = None if crown is None else (crown - top) / H
            if room is not None and room < MIN_HEADROOM:
                continue
            # Small compromises are cheap; past the usual limits they get expensive fast. Extra
            # room above the head is never "fixed" by raising the eyes: a misread head top could
            # then cut off hair, and a wider frame naturally has more space up there.
            cost = (3 * zoom_in + 10 * max(0, zoom_in - MAX_ZOOM_IN) + 4 * abs(drift)
                    + 20 * max(0, drift - MAX_EYE_DRIFT) + dx
                    + (0 if room is None else 3 * max(0, HEADROOM[0] - room)))
            if best is None or cost < best[0]:
                best = (cost, H, W, left, max(0.0, top), zoom_in, drift, dx)
    notes = []
    if best is None:                                     # no crop keeps the head in: fit as well as we can
        H = min(ideal * (1 - MAX_ZOOM_IN), h, w / st.ratio)
        W = H * st.ratio
        left = float(np.clip(cx - W / 2, 0, w - W))
        top = float(np.clip(ey - st.eye_line * H, 0, h - H))
        best = (0, H, W, left, top, 1 - H / ideal, (ey - top) / H - st.eye_line, abs(left - (cx - W / 2)) / W)
        notes.append("the photo doesn't leave room for the standard framing")
    _, H, W, left, top, zoom_in, drift, dx = best
    if zoom_in > 0.01:
        notes.append(f"framed {zoom_in:.0%} tighter to fit the photo")
    if drift > 0.01:
        notes.append(f"eyes {drift:.0%} lower than standard, to keep the whole head in")
    elif drift < -0.01:
        notes.append(f"eyes {-drift:.0%} higher than standard (subject sits high in the photo)")
    if dx > 0.05:
        notes.append(f"{dx:.0%} off-center (subject near the edge)")
    return (left, top, left + W, top + H), notes


def render(rgb: np.ndarray, icc: bytes | None, box, size: tuple[int, int]) -> np.ndarray:
    """Crop, resize and convert to sRGB (uint8), color-converting whichever image is smaller."""
    l, t, r, b = (int(round(v)) for v in box)
    crop = np.ascontiguousarray(rgb[t:b, l:r])
    if crop.shape[1] > size[0]:
        return to_srgb8(cv2.resize(crop, size, interpolation=cv2.INTER_AREA), icc)
    return cv2.resize(to_srgb8(crop, icc), size, interpolation=cv2.INTER_LANCZOS4)


# ---------------------------------------------------------------- finishing

def fix_skin_cast(img: np.ndarray, face: Face) -> tuple[np.ndarray, str | None]:
    """Neutralize a clear color cast, judged by skin hue and chroma (never by lightness).

    Across skin tones, skin under neutral light sits in a hue band (about 35-70 deg in CIELAB)
    with moderate chroma. The band here is deliberately wide, so that natural skin of any tone
    is never "corrected": only a clear cast outside it triggers a white-balance gain that brings
    the cheeks back inside, keeping brightness. Otherwise do nothing.
    """
    lab = skin_lab(img, face)
    if lab is None:
        return img, None
    L, a, b = lab
    hue, chroma = math.degrees(math.atan2(b, a)), math.hypot(a, b)
    hue_off, too_strong = not SKIN_HUE[0] <= hue <= SKIN_HUE[1], chroma > SKIN_CHROMA
    if chroma < 6 or not (hue_off or too_strong):
        return img, None
    new_hue = math.radians((SKIN_HUE[0] + 4 if hue < SKIN_HUE[0] else SKIN_HUE[1] - 4) if hue_off else hue)
    new_chroma = SKIN_CHROMA - 6 if too_strong else chroma
    target = lab_to_srgb(np.array([L, new_chroma * math.cos(new_hue), new_chroma * math.sin(new_hue)]))
    gain = _to_linear(target) / np.maximum(_to_linear(lab_to_srgb(np.array([L, a, b]))), 1e-4)
    gain = np.clip(gain / (gain @ LUMA), 0.75, 1.3).astype(np.float32)   # keep brightness
    cast = "warm/orange" if not hue_off else ("magenta/blue" if hue < SKIN_HUE[0] else "yellow-green")
    return encode(decode(img) * gain), f"fixed a {cast} color cast"


def light_maps(shape: tuple[int, int], face: Face) -> tuple[np.ndarray, np.ndarray]:
    """Two smooth full-size maps, computed at 1/8 size: where the face is (0-1), and a vignette
    gain (-12% of light toward the corners, expressed for gamma-encoded values)."""
    hgt, wid = shape
    gh, gw = -(-hgt // 8), -(-wid // 8)
    yy, xx = np.meshgrid((np.arange(gh, dtype=np.float32) + 0.5) * (hgt / gh) - 0.5,
                         (np.arange(gw, dtype=np.float32) + 0.5) * (wid / gw) - 0.5, indexing="ij")
    cx, cy = (float(v) for v in (face.eyes + (face.lm[3] + face.lm[4]) / 2) / 2)
    on_face = np.exp(-(((xx - cx) / (0.55 * face.scale)) ** 2 + ((yy - cy) / (0.75 * face.scale)) ** 2) / 2)
    corner = np.hypot((xx - wid / 2) / (wid / 2), (yy - 0.45 * hgt) / (0.55 * hgt)) / math.sqrt(2)
    vignette = (1 - 0.12 * np.clip((corner - 0.35) / 0.65, 0, 1) ** 2) ** (1 / 2.4)
    up = lambda m: cv2.resize(m.astype(np.float32), (wid, hgt), interpolation=cv2.INTER_LINEAR)  # noqa: E731
    return up(on_face), up(vignette)


def finish(img8: np.ndarray, face: Face, bw: bool) -> tuple[np.ndarray, list[str]]:
    """Gentle finishing on the framed image. `face` is in its coordinates. All float32."""
    notes = []
    img, note = fix_skin_cast(img8.astype(np.float32) / 255, face)
    if note:
        notes.append(note)

    # One tone pass on luminance, so colors keep their hue. Levels: pull a lifted black point
    # down (by up to 5%) and stretch a dull white point (by up to 8%). Then a soft S-curve
    # (+10% midtone contrast), a little light on the face's midtones, and a subtle vignette
    # (an exact exposure change in linear light, done in gamma space).
    y = img @ LUMA
    peak = np.maximum(np.maximum(img[..., 0], img[..., 1]), img[..., 2])
    bp = min(float(np.percentile(y, 0.05)), 0.05)
    wp = max(float(np.percentile(peak, 99.95)), 0.92)
    t0 = np.clip((y - bp) / (wp - bp), 0, 1)
    t = t0 + 0.2 * t0 * (1 - t0) * (2 * t0 - 1)
    on_face, vignette = light_maps(t.shape, face)
    t += 0.12 * on_face * t * (1 - t)
    t = np.maximum(vignette * (t + 0.055) - 0.055, 0)

    # Apply as a per-pixel RGB scale. The creative brightening (curve + light) fades out as a
    # pixel's brightest channel nears white, so highlights keep their detail instead of clipping.
    levels = t0 / np.maximum(y, 1e-4)
    creative = t / np.maximum(t0, 1e-4)
    s = np.clip((0.97 - peak * levels) / 0.17, 0, 1)
    creative = np.where(creative > 1, 1 + (creative - 1) * s * s * (3 - 2 * s), creative)
    img *= (levels * creative)[..., None]

    if bw:
        img = np.repeat((img @ LUMA)[..., None], 3, axis=2)

    # Output sharpening on luminance only (no color fringes), ignoring fine noise, and never
    # pushing a pixel more than halfway toward pure white or black.
    y = img @ LUMA
    detail = y - cv2.GaussianBlur(y, (0, 0), 1.0)
    detail *= np.clip((np.abs(detail) - 0.004) / 0.008, 0, 1)
    hi_room = 1 - np.maximum(np.maximum(img[..., 0], img[..., 1]), img[..., 2])
    lo_room = np.minimum(np.minimum(img[..., 0], img[..., 1]), img[..., 2])
    img += (0.6 * np.clip(detail, -0.5 * lo_room, 0.5 * hi_room))[..., None]
    return (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8), notes


# ---------------------------------------------------------------- judge

GRADES = ["PASS", "REVIEW", "FAIL"]


@dataclass
class Verdict:
    grade: str = "PASS"
    reasons: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def record(self, name: str, value, grade: str, why: str) -> None:
        self.metrics[name] = value
        if grade != "PASS":
            self.reasons.append(why)
            self.grade = max(self.grade, grade, key=GRADES.index)


def band(x: float, ok: tuple[float, float], review: tuple[float, float]) -> str:
    return "PASS" if ok[0] <= x <= ok[1] else "REVIEW" if review[0] <= x <= review[1] else "FAIL"


def judge(path: Path, st: Settings, model: str, plain: np.ndarray | None = None,
          upscale: float | None = None, planned_head: float | None = None) -> Verdict:
    """Grade an output file from what's actually in it. `plain` is the same crop of the original
    without finishing; with it, the judge also checks the edit stayed faithful. `planned_head`
    is the head size the crop was planned at (above 1.0 when the photo had no room for the
    requested framing; its notes say so), and the output is checked against that plan."""
    v = Verdict()
    im = Image.open(path)
    W, H = im.size
    v.record("size", [W, H], "PASS" if (W, H) == st.size else "FAIL", f"size {W}x{H}, expected {st.size[0]}x{st.size[1]}")
    icc = im.info.get("icc_profile")
    srgb = bool(icc) and "sRGB" in ImageCms.getProfileDescription(ImageCms.ImageCmsProfile(io.BytesIO(icc)))
    v.record("srgb", srgb, "PASS" if srgb else "FAIL", "no sRGB color profile")
    tags = len(im.getexif())
    v.record("metadata_tags", tags, "PASS" if not tags else "FAIL", "metadata (EXIF/GPS) not stripped")

    out = np.asarray(im.convert("RGB"))
    faces = detect_faces(out, model, first=640)
    if not faces:
        v.record("face", 0, "FAIL", "no face found in the output")
        return v
    f = faces[0]
    ex, ey = f.eyes
    v.record("eye_line", round(ey / H, 3), band(ey / H - st.eye_line, (-.03, MAX_EYE_DRIFT + .01), (-.10, .16)),
             f"eyes at {ey / H:.0%} from the top, not {st.eye_line:.0%}")
    crown = find_crown(out, f)
    if crown is not None:
        room = crown / H
        roomy = 0.2 + 0.4 * max(0.0, 1 - st.zoom)                # a wider zoom leaves more space up top
        v.record("headroom", round(room, 3), "PASS" if .02 <= room <= roomy else "REVIEW",
                 "top of the head is cut off" if room < .005 else
                 "top of the head is tight to the edge" if room < .02 else "a lot of empty space above the head")
    v.record("center", round(ex / W, 3), band(ex / W - .5, (-.04, .04), (-.15, .15)),
             f"face {abs(ex / W - .5):.0%} off-center")
    head = f.scale * HEAD_TO_FRAME / st.zoom / H             # 1.0 = the requested head size
    if planned_head is None:
        v.record("head_size", round(head, 3), band(head, (.9, 1.1), (.75, 1.3)), f"head {head:.2f}x the standard size")
    else:
        v.metrics["planned_head_size"] = round(planned_head, 3)
        v.record("head_size", round(head, 3), band(head / planned_head, (.92, 1.08), (.8, 1.25)),
                 f"head {head:.2f}x the requested size, but the crop planned {planned_head:.2f}x")
    others = sum(g.scale > 0.4 * f.scale for g in faces[1:])
    v.record("other_faces", others, "PASS" if not others else "REVIEW", "someone else's face is in the frame")

    region = inner_face(out.shape, f)
    face_px = out[region]
    blown = float((face_px.astype(np.float32) @ LUMA >= 250).mean())   # near white: detail gone
    v.record("face_blown", round(blown, 4), "PASS" if blown <= .03 else "REVIEW",
             f"{blown:.0%} of the face is blown out (harsh light or shine)")
    lab = None if st.bw else skin_lab(out.astype(np.float32) / 255, f)
    if lab is not None:
        hue, chroma = math.degrees(math.atan2(lab[2], lab[1])), math.hypot(lab[1], lab[2])
        ok = chroma < 6 or (SKIN_HUE[0] - 2 <= hue <= SKIN_HUE[1] + 2 and chroma <= SKIN_CHROMA + 2)
        v.record("skin_hue", round(hue, 1), "PASS" if ok else "REVIEW", f"skin color looks off (hue {hue:.0f}, chroma {chroma:.0f})")
        v.metrics["skin_chroma"] = round(chroma, 1)
    sharp = eye_sharpness(out, f)
    v.record("eye_sharpness", round(sharp, 2), "PASS" if sharp >= .6 else "REVIEW", "eyes look soft (focus miss or motion?)")
    top = cv2.cvtColor(np.ascontiguousarray(out[: H // 12]), cv2.COLOR_RGB2GRAY)
    v.metrics["backdrop_luma"] = round(float(np.median(np.r_[top[:, : W // 5].ravel(), top[:, -W // 5:].ravel()])), 1)

    if plain is not None and plain.shape == out.shape:
        ssim = luma_ssim(out, plain)
        v.record("fidelity_ssim", round(ssim, 3), band(ssim, (.9, 1), (.8, 1)), f"edit changed the photo a lot (SSIM {ssim:.2f})")
        ref = plain[region]
        added = float(((face_px.max(axis=1) >= 254) & (ref.max(axis=1) < 250)).mean())
        v.record("clipping_added", round(added, 4), "PASS" if added <= .005 else "REVIEW", f"the edit blew out {added:.1%} of the face")
        lum_o, lum_r = face_px.astype(np.float32) @ LUMA, ref.astype(np.float32) @ LUMA
        crushed = float(((lum_o <= 3) & (lum_r > 10)).mean())
        v.record("crushing_added", round(crushed, 4), "PASS" if crushed <= .005 else "REVIEW", f"the edit crushed {crushed:.1%} of the face to black")
        d_l = float((srgb_to_lab(face_px[::5] / 255)[:, 0] - srgb_to_lab(ref[::5] / 255)[:, 0]).mean())
        v.record("face_lightness_change", round(d_l, 1), band(abs(d_l), (0, 8), (0, 20)), f"the edit changed face brightness a lot ({d_l:+.0f} L*)")
        boost = sharp / max(eye_sharpness(plain, f), 1e-6)
        v.record("sharpen_gain", round(boost, 2), "PASS" if boost <= 1.6 else "REVIEW", "looks over-sharpened")
    if upscale is not None:
        v.record("upscale", round(upscale, 2), "PASS" if upscale <= 1.5 else "REVIEW", f"low resolution: enlarged {upscale:.1f}x (face small in the photo)")
    return v


def luma_ssim(a8: np.ndarray, b8: np.ndarray) -> float:
    """Structural similarity of two images' luminance (at half size; 1.0 = identical)."""
    a, b = (cv2.resize(cv2.cvtColor(np.ascontiguousarray(z), cv2.COLOR_RGB2GRAY).astype(np.float32), None,
                       fx=.5, fy=.5, interpolation=cv2.INTER_AREA) for z in (a8, b8))
    blur = lambda z: cv2.GaussianBlur(z, (0, 0), 1.5)  # noqa: E731
    ma, mb = blur(a), blur(b)
    va, vb, cov = blur(a * a) - ma * ma, blur(b * b) - mb * mb, blur(a * b) - ma * mb
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    return float((((2 * ma * mb + c1) * (2 * cov + c2)) / ((ma * ma + mb * mb + c1) * (va + vb + c2))).mean())


def judge_set(entries: list[dict]) -> str | None:
    """Across the set: flag head sizes that stray from the rest; report how much backdrops vary."""
    graded = [e for e in entries if e.get("output") and "head_size" in e["metrics"]]
    for e in entries:
        e["set_reasons"] = []
    if len(graded) >= 3:
        median = float(np.median([e["metrics"]["head_size"] for e in graded]))
        for e in graded:
            off = e["metrics"]["head_size"] / median - 1
            if abs(off) > 0.08:
                e["set_reasons"].append(f"head {abs(off):.0%} {'larger' if off > 0 else 'smaller'} than the rest of the set")
    lum = [e["metrics"]["backdrop_luma"] for e in graded if "backdrop_luma" in e["metrics"]]
    if len(lum) >= 2 and max(lum) - min(lum) > 40:
        return f"backdrop brightness varies a lot across the set ({min(lum):.0f}-{max(lum):.0f} of 255): shoot everyone in one spot"
    return None


def final_grade(e: dict) -> str:
    if not e.get("output"):
        return "SKIPPED"
    return max(e["grade"], "REVIEW" if e.get("set_reasons") else "PASS", key=GRADES.index)


# ---------------------------------------------------------------- Apple Photos exports

def pick_sources(folder: Path) -> tuple[list[Path], dict[Path, list[str]]]:
    """Top-level photos. Prefers Photos' edited export (IMG_E1234) over its original (IMG_1234)
    and notes when an original was exported without the edits saved in its .AAE sidecar."""
    files = [p for p in folder.iterdir()
             if p.is_file() and not p.name.startswith(".") and p.suffix.lower() in IMAGE_EXTS]
    by_stem: dict[str, Path] = {}
    for p in sorted(files, key=lambda p: IMAGE_EXTS.index(p.suffix.lower())):
        by_stem.setdefault(p.stem.upper(), p)       # IMG_1.HEIC wins over IMG_1.JPG
    chosen, notes = [], {}
    for stem, p in sorted(by_stem.items()):
        if re.fullmatch(r"[A-Z]+_\d+", stem):
            if re.sub(r"_(\d+)$", r"_E\1", stem) in by_stem:
                continue                             # use the edited export instead
            edits = photos_edits(p.with_suffix(".AAE")) or photos_edits(p.with_suffix(".aae"))
            if edits:
                notes[p] = [f"exported without its Photos edits ({', '.join(edits)}); "
                            "export the edited version to keep them"]
        chosen.append(p)
    return chosen, notes


def photos_edits(aae: Path) -> list[str]:
    """Names of the edits stored in a Photos .AAE sidecar."""
    if not aae.exists():
        return []
    try:
        blob = zlib.decompress(plistlib.loads(aae.read_bytes())["adjustmentData"], -15)
        try:
            doc = json.loads(blob)
        except ValueError:
            doc = plistlib.loads(blob)
        return [APPLE_EDIT_NAMES.get(a.get("identifier"), a.get("identifier", "edit"))
                for a in doc.get("adjustments", []) if a.get("enabled", True)]
    except Exception:
        return ["unknown edits"]


# ---------------------------------------------------------------- pipeline

def process(src: Path, out_dir: Path, model: str, st: Settings, notes: list[str]) -> dict:
    """Polish one photo and judge the result. Returns its _report.json entry."""
    s = src.stat()
    rgb = icc = img = None
    e = {"source": src.name, "size": s.st_size, "mtime_ns": s.st_mtime_ns, "key": st.key,
         "output": None, "grade": "SKIPPED", "reasons": [], "notes": list(notes), "metrics": {}}
    try:
        rgb, icc = load(src)
        e["src_wh"] = [rgb.shape[1], rgb.shape[0]]
        faces = detect_faces(rgb, model)
        if not faces:
            raise Skip("no face found")
        face = faces[0]
        x, y, w, h = (float(v) for v in face.box)
        e["face_box"] = [round(x), round(y), round(x + w), round(y + h)]
        if len(faces) > 1 and faces[1].scale > 0.6 * face.scale:
            e["notes"].append(f"{len(faces)} people, framed the largest face")
        crown = find_crown(rgb, face)
        box, crop_notes = plan_crop(face, rgb.shape[1], rgb.shape[0], st, crown)
        e["notes"] += crop_notes
        e["box"] = [round(v, 1) for v in box]
        e["planned_head"] = round(HEAD_TO_FRAME * face.scale / st.zoom / (box[3] - box[1]), 3)
        k = st.size[0] / (box[2] - box[0])
        plain = render(rgb, icc, box, st.size)
        if st.finish:
            img, finish_notes = finish(plain, face.moved(box, k), st.bw)
            e["notes"] += finish_notes
        else:
            img = gray8(plain) if st.bw else plain
        out = out_dir / f"{src.stem}.jpg"
        save_jpeg(img, out)
        v = judge(out, st, model, plain, upscale=k, planned_head=e["planned_head"])
        e.update(output=out.name, out_mtime_ns=out.stat().st_mtime_ns, grade=v.grade,
                 reasons=v.reasons, metrics=v.metrics)
    except Skip as err:
        e["reasons"] = [str(err)]
    except Exception as err:  # keep the batch going; report the file
        why = ("HEIC needs pillow-heif: pip install pillow-heif"
               if src.suffix.lower() in (".heic", ".heif") and not HEIC_OK else f"{type(err).__name__}: {err}")
        e["reasons"] = [f"couldn't process ({why})"]
    if rgb is not None:
        card_thumbs(e, src.parent, out_dir, rgb, icc, img if e["output"] else None)
    return e


def rejudge(e: dict, folder: Path, out_dir: Path, model: str, st: Settings) -> dict:
    """An output you edited by hand: keep it, and grade what's there now."""
    out = out_dir / e["output"]
    plain = None
    if e.get("box") and (folder / e["source"]).exists():
        rgb, icc = load(folder / e["source"])
        plain = render(rgb, icc, e["box"], st.size)
    v = judge(out, st, model, plain, planned_head=e.get("planned_head"))
    notes = [n for n in e["notes"] if n != "edited by hand; kept your version"] + ["edited by hand; kept your version"]
    return {**e, "out_mtime_ns": out.stat().st_mtime_ns, "hand_edited": True, "grade": v.grade,
            "reasons": v.reasons, "metrics": v.metrics, "notes": notes}


def run(folder: Path, out_dir: Path, st: Settings, model: str, force: bool = False) -> list[dict]:
    """Polish and judge whatever is new or changed; reuse everything else from _report.json."""
    report_path, sheet = out_dir / "_report.json", out_dir / "_contact-sheet.jpg"   # sheet = page 1
    try:
        old_text = report_path.read_text()
        old = {e["source"]: e for e in json.loads(old_text)["photos"]}
    except (OSError, ValueError, KeyError):
        old_text, old = "", {}
    sources, notes = pick_sources(folder)
    reuse, todo, hand_edited = [], [], []
    for p in sources:
        e, s = old.get(p.name), p.stat()
        out = out_dir / e["output"] if e and e.get("output") else None
        if out and out.exists() and out.stat().st_mtime_ns != e.get("out_mtime_ns"):
            hand_edited.append(e)                   # you edited it: re-judge, never overwrite
        elif out and out.exists() and e.get("hand_edited"):
            reuse.append(e)
        elif (e and not force and e["key"] == st.key and e["size"] == s.st_size
              and e["mtime_ns"] == s.st_mtime_ns and (out is None or out.exists())):
            reuse.append(e)
        else:
            todo.append(p)

    t0, threads = time.perf_counter(), cv2.getNumThreads()
    if len(todo) + len(hand_edited) > 1:
        cv2.setNumThreads(1)                        # parallelize across photos, not inside each
    jobs = [lambda p=p: process(p, out_dir, model, st, notes.get(p, [])) for p in todo]
    jobs += [lambda e=e: rejudge(e, folder, out_dir, model, st) for e in hand_edited]
    events.emit("start", total=len(jobs), unchanged=len(reuse), folder=str(folder), out=str(out_dir))
    marks = {"PASS": "✓", "REVIEW": "!", "FAIL": "✗", "SKIPPED": "✗"}
    fresh: list[dict] = []
    with ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 2)) as pool:
        for i in range(0, len(jobs), 24):           # in chunks, saving progress: big sets can resume
            chunk = list(pool.map(lambda job: job(), jobs[i:i + 24]))
            fresh += chunk
            for e in sorted(chunk, key=lambda e: e["source"]):
                why = "; ".join(e["reasons"] + e["notes"])
                events.emit('photo', source=e['source'], grade=final_grade(e), reasons=e['reasons'], notes=e['notes'], output=e.get('output'))
                events.say(f"{marks[final_grade(e)]} {final_grade(e):<7} {e['source']:<16} {why}")
            if i + 24 < len(jobs):
                report_path.write_text(json.dumps({"settings": asdict(st), "set_note": None,
                                                   "photos": sorted(reuse + fresh, key=lambda e: e["source"])}))
        entries = sorted(reuse + fresh, key=lambda e: e["source"])
        set_note = judge_set(entries)
        text = json.dumps({"settings": asdict(st), "set_note": set_note, "photos": entries}, indent=1)
        pages = 1
        if text != old_text or not sheet.exists():
            report_path.write_text(text)
            pages = contact_sheets(entries, folder, out_dir, pool)
    cv2.setNumThreads(threads)

    counts = {g: sum(final_grade(e) == g for e in entries) for g in marks}
    took = f" in {time.perf_counter() - t0:.1f}s" if fresh else ""
    flagged = sum(bool(e.get("set_reasons")) for e in entries)
    events.say(f"\n{len(fresh)} processed{took}, {len(reuse)} unchanged. Set: "
          + ", ".join(f"{n} {g}" for g, n in counts.items() if n)
          + (f" ({flagged} flagged for not matching the rest of the set)" if flagged else ""))
    if set_note:
        events.say(f"Note: {set_note}")
    events.say(f"Review: {sheet}" + (f" (+{pages - 1} more pages)" if pages > 1 else ""))
    events.emit("polished", processed=len(fresh), unchanged=len(reuse), counts=counts, flagged=flagged,
                set_note=set_note, sheet=str(sheet), pages=pages, out=str(out_dir))
    return entries


def watch(folder: Path, out_dir: Path, st: Settings, model: str, every: float = 2.0) -> None:
    """Re-run whenever the folder's photos change, once files have finished copying."""
    def snapshot():
        return {p.name: (p.stat().st_size, p.stat().st_mtime_ns) for p in pick_sources(folder)[0]}
    events.say(f"\nWatching {folder} for new photos. Ctrl-C to stop.")
    last = snapshot()
    try:
        while True:
            time.sleep(every)
            now = snapshot()
            if now != last:
                time.sleep(every)                    # let copies/exports finish
                if snapshot() == now:
                    events.say()
                    run(folder, out_dir, st, model)
                    now = snapshot()
                last = now
    except KeyboardInterrupt:
        events.say("\nStopped watching.")


# ---------------------------------------------------------------- review sheet

THUMB_H = 320
CROP_COLOR, SKIP_COLOR = (255, 204, 0), (220, 40, 40)
_thumbs: dict = {}


def thumb(path: Path, box=None, full_wh=None, color=CROP_COLOR, pixels=None, icc=None) -> Image.Image:
    """Small sRGB preview of a file, optionally with a box drawn on it. Uses pixels already in
    memory when given; otherwise decodes at 1/4 size inside the JPEG decoder (fast)."""
    key = (path, path.stat().st_mtime_ns, tuple(box or ()), color)
    if key not in _thumbs:
        if pixels is None:
            im = Image.open(path)
            if im.format == "JPEG":
                im.draft("RGB", (im.width // 4, im.height // 4))
            icc = im.info.get("icc_profile")
            pixels = np.asarray(ImageOps.exif_transpose(im).convert("RGB"))
        k = THUMB_H / pixels.shape[0]
        small = cv2.resize(pixels, (max(1, round(pixels.shape[1] * k)), THUMB_H), interpolation=cv2.INTER_AREA)
        t = Image.fromarray(to_srgb8(small, icc))
        if box and full_wh:
            ImageDraw.Draw(t).rectangle([v * THUMB_H / full_wh[1] for v in box], outline=color, width=3)
        _thumbs[key] = t
    return _thumbs[key]


def card_thumbs(e: dict, folder: Path, out_dir: Path, rgb=None, icc=None, out8=None):
    """The (before, after) previews for one report entry."""
    src, out = folder / e["source"], out_dir / e["output"] if e.get("output") else None
    after = thumb(out, pixels=out8) if out and out.exists() else None
    box, color = (e.get("box"), CROP_COLOR) if after else (e.get("face_box"), SKIP_COLOR)
    before = thumb(src, box, e.get("src_wh"), color, pixels=rgb, icc=icc) if src.exists() else None
    return before, after


PAGE = 30                                           # photos per contact-sheet page


def contact_sheets(entries: list[dict], folder: Path, out_dir: Path, pool) -> int:
    """_contact-sheet.jpg, plus _contact-sheet-02.jpg, -03... when there are more than PAGE photos."""
    pages = [entries[i:i + PAGE] for i in range(0, len(entries), PAGE)] or [[]]
    for n, page in enumerate(pages, 1):
        list(pool.map(lambda e: card_thumbs(e, folder, out_dir), page))   # decode previews in parallel
        contact_sheet(page, folder, out_dir, out_dir / ("_contact-sheet.jpg" if n == 1 else f"_contact-sheet-{n:02d}.jpg"))
        done = {folder / e["source"] for e in page} | {out_dir / e["output"] for e in page if e.get("output")}
        for key in [k for k in _thumbs if k[0] in done]:
            del _thumbs[key]                            # keep memory flat on big sets
    return len(pages)


def contact_sheet(entries: list[dict], folder: Path, out_dir: Path, path: Path) -> None:
    """Before (crop drawn on it) and after, side by side, with the judge's grade and notes."""
    font, small = ImageFont.load_default(size=18), ImageFont.load_default(size=15)
    pad, gap, card_w, text_h = 20, 12, 700, 104
    cols = 1 if len(entries) == 1 else 2
    rows = max(1, math.ceil(len(entries) / cols))
    sheet = Image.new("RGB", (cols * card_w + (cols + 1) * pad,
                              rows * (THUMB_H + text_h) + (rows + 1) * pad), (246, 245, 242))
    draw = ImageDraw.Draw(sheet)
    colors = {"PASS": (40, 150, 70), "REVIEW": (225, 150, 20), "FAIL": (210, 50, 50), "SKIPPED": (210, 50, 50)}
    for i, e in enumerate(entries):
        x = pad + (i % cols) * (card_w + pad)
        y = pad + (i // cols) * (THUMB_H + text_h + pad)
        before, after = card_thumbs(e, folder, out_dir)
        after_w = after.width if after else round(THUMB_H * 0.8)
        if before:
            before = before.copy()
            before.thumbnail((card_w - after_w - gap, THUMB_H))
            sheet.paste(before, (x, y + (THUMB_H - before.height) // 2))
        if after:
            sheet.paste(after, (x + card_w - after_w, y))
        else:
            draw.rectangle([x + card_w - after_w, y, x + card_w, y + THUMB_H], fill=(228, 226, 222))
            draw.text((x + card_w - after_w / 2, y + THUMB_H / 2), "skipped", font=font, fill=(150, 40, 40), anchor="mm")
        grade = final_grade(e)
        draw.ellipse([x, y + THUMB_H + 12, x + 12, y + THUMB_H + 24], fill=colors[grade])
        draw.text((x + 20, y + THUMB_H + 8), f"{grade}  {e['source']}", font=font, fill=(25, 25, 25))
        line, ty = "", y + THUMB_H + 34
        for word in "; ".join(e["reasons"] + e.get("set_reasons", []) + e["notes"]).split(" "):
            if line and draw.textlength(f"{line} {word}", font=small) > card_w:
                draw.text((x, ty), line, font=small, fill=(95, 95, 95))
                line, ty = word, ty + 19
            else:
                line = f"{line} {word}".strip()
        draw.text((x, ty), line, font=small, fill=(95, 95, 95))
    sheet.save(path, quality=88)


def settings_for(out_dir: Path, a: argparse.Namespace) -> Settings:
    """Flags you pass, else the settings saved with this output folder, else the defaults. So once
    a set is polished a certain way, later runs (new photos, --watch) keep that look."""
    try:
        saved = Settings(**json.loads((out_dir / "_report.json").read_text())["settings"])
    except (OSError, ValueError, KeyError, TypeError):
        saved = None
    base = saved or Settings()
    ratio = base.ratio
    if a.ratio:
        try:
            rw, rh = (float(v) for v in a.ratio.split(":"))
            ratio = rw / rh
        except ValueError:
            sys.exit("--ratio looks like 4:5 or 1:1")
    pick = lambda flag, saved_value: saved_value if flag is None else flag  # noqa: E731
    st = Settings(ratio=ratio, width=pick(a.width, base.width), zoom=pick(a.zoom, base.zoom),
                  eye_line=pick(a.eye_line, base.eye_line), finish=pick(a.finish, base.finish),
                  bw=pick(a.bw, base.bw))
    if not (0.2 <= st.eye_line <= 0.6 and 0.3 <= st.zoom <= 3 and 200 <= st.width <= 8000):
        sys.exit("--eye-line must be 0.2-0.6, --zoom 0.3-3, --width 200-8000")
    source = "saved with this folder" if saved == st else "new: re-polishing to match" if saved else "defaults"
    events.say(f"Framing {st.size[0]}x{st.size[1]}, zoom {st.zoom:g}, eyes at {st.eye_line:.0%}, "
          f"{'black and white' if st.bw else 'color'}{'' if st.finish else ', no finishing'} ({source})")
    return st

