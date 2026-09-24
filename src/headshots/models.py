"""The two face models, fetched once and cached.

Both are pinned by SHA-256: a download that does not match the pin is discarded rather than used.
This is the only part of the tool that touches the network, and only the first time it runs.

    face detection    YuNet   (MIT, OpenCV Model Zoo)      230 KB
    face recognition  SFace   (Apache-2.0, OpenCV Model Zoo) 37 MB, only needed for `group`
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
import urllib.request
from pathlib import Path

ZOO = "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models"

MODELS = {
    "detect": (
        f"{ZOO}/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
        "face model (230 KB)",
    ),
    "recognize": (
        f"{ZOO}/face_recognition_sface/face_recognition_sface_2021dec.onnx",
        "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
        "face-matching model (37 MB)",
    ),
}

CACHE = Path.home() / ".cache" / "headshots"


def path_for(which: str) -> Path:
    return CACHE / Path(MODELS[which][0]).name


def ensure(which: str) -> str:
    """Return a local path to the model, downloading it once if it is not already cached."""
    url, sha, label = MODELS[which]
    path = path_for(which)
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == sha:
        return str(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading the {label} to {path} ...", file=sys.stderr, flush=True)
    try:
        data = urllib.request.urlopen(url, timeout=120).read()
    except Exception:  # e.g. a Python without CA certificates: let curl use the system's
        try:
            data = subprocess.run(["curl", "-fsSL", url], capture_output=True,
                                  check=True, timeout=300).stdout
        except Exception as e:
            sys.exit(f"Couldn't download the {label} ({e}).\n"
                     f"Get it manually:  curl -L --create-dirs -o '{path}' '{url}'")
    if hashlib.sha256(data).hexdigest() != sha:
        sys.exit(f"The downloaded {label} failed its checksum; not using it.")
    path.write_bytes(data)
    return str(path)


def cached(which: str) -> bool:
    return path_for(which).exists()
