"""The `headshots` command.

    headshots polish ~/Photos/shoot              frame, finish and judge a folder
    headshots group  ~/Photos/shoot/polished     group the polished photos by who is in them
    headshots run    ~/Photos/shoot              both, in order
    headshots models                             fetch the face models now, then you can go offline
    headshots upgrade                            print the premium checkout link and save a receipt

Add --json to any of them to get one JSON object per line instead of prose. That is what the
macOS app reads; the two carry the same information.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, decide, entitlements, events


def _decide_flag(p: argparse.ArgumentParser) -> None:
    p.add_argument("--decide", choices=tuple(decide.BACKENDS), default="local",
                   help="who should look: local (default) or jev (premium)")


def _framing_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("--out", type=Path, help="output folder (default: <folder>/polished)")
    p.add_argument("--ratio", help="crop shape, width:height (default 4:5)")
    p.add_argument("--width", type=int, help="output width in px (default 1600)")
    p.add_argument("--zoom", type=float,
                   help="tighter >1, looser <1: 0.85 is a wider head-and-shoulders crop (default 1.0)")
    p.add_argument("--eye-line", type=float, help="eye height from the top, 0-1 (default 0.42)")
    p.add_argument("--bw", action=argparse.BooleanOptionalAction, help="black and white (--no-bw: color)")
    p.add_argument("--finish", action=argparse.BooleanOptionalAction,
                   help="tone, color and sharpening (--no-finish: frame only)")
    p.add_argument("--force", action="store_true",
                   help="re-polish everything except outputs you edited (delete one to redo it)")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="headshots", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"headshots {__version__}")
    ap.add_argument("--json", action="store_true", help="one JSON object per line instead of prose")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("polish", help="frame, finish and judge a folder of photos")
    p.add_argument("folder", type=Path, help="folder of photos (only top-level files are read)")
    p.add_argument("--watch", action="store_true", help="keep running; polish photos as they're added")
    _framing_flags(p)
    _decide_flag(p)

    g = sub.add_parser("group", help="group polished photos by who is in them")
    g.add_argument("folder", type=Path, help="a folder of polished photos")
    g.add_argument("--threshold", type=float,
                   help="cosine cut to group at (default: the most stable value in the sweep)")
    g.add_argument("--expect", type=int, help="how many people you expect, as a cross-check")
    g.add_argument("--sheets", action=argparse.BooleanOptionalAction, default=True,
                   help="write the per-person contact sheets (--no-sheets to skip)")

    r = sub.add_parser("run", help="polish, then group the result")
    r.add_argument("folder", type=Path, help="folder of photos")
    r.add_argument("--threshold", type=float, help="see `headshots group --help`")
    r.add_argument("--expect", type=int, help="how many people you expect, as a cross-check")
    _framing_flags(r)
    _decide_flag(r)

    sub.add_parser("models", help="download the face models now (they are cached after that)")
    u = sub.add_parser("upgrade", help="print the premium checkout link and save a receipt")
    u.add_argument("--receipt", type=Path,
                   help="where to write the receipt (default: ~/.config/headshots/receipt.json)")
    return ap


def _polish(a) -> tuple[Path, int]:
    from . import polish

    folder = a.folder.expanduser().resolve()
    if not folder.is_dir():
        sys.exit(f"Not a folder: {folder}")
    out_dir = (a.out.expanduser() if a.out else folder / "polished").resolve()
    if out_dir == folder:
        sys.exit("--out must be a different folder than the originals")
    st = polish.settings_for(out_dir, a)
    if not polish.pick_sources(folder)[0] and not getattr(a, "watch", False):
        sys.exit(f"No photos found in {folder}")
    decider = decide.choose(a.decide)
    model = polish.ensure_model()
    out_dir.mkdir(parents=True, exist_ok=True)
    entries = polish.run(folder, out_dir, st, model, force=a.force, decider=decider)
    if getattr(a, "watch", False):
        polish.watch(folder, out_dir, st, model, decider=decider)
    return out_dir, sum(polish.final_grade(e) == "FAIL" for e in entries)


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    if a.json:
        events.use_json()

    if a.cmd == "upgrade":
        events.say(entitlements.upgrade(receipt_path=a.receipt))
        return 0

    if a.cmd == "models":
        from . import models

        for which in models.MODELS:
            events.say(models.ensure(which))
        return 0

    if a.cmd == "polish":
        return 1 if _polish(a)[1] else 0

    if a.cmd == "group":
        from . import group

        group.analyze(a.folder, threshold=a.threshold, expect=a.expect, sheets=a.sheets)
        return 0

    if a.cmd == "run":
        from . import group

        out_dir, failed = _polish(a)
        events.say()
        group.analyze(out_dir, threshold=a.threshold, expect=a.expect)
        return 1 if failed else 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
