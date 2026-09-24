"""Grouping a folder of polished headshots by who is in them, and picking the best frame each.

Runs entirely on this machine. Reads the polished JPEGs, turns each face into a 128-number
fingerprint (OpenCV SFace), and clusters the fingerprints. No image and no fingerprint leaves
the computer; the only thing that ever needs the network is the one-time model download.

Writes, next to the photos:
    _students.csv          one row per photo: student number, how well it fits, whether it is the pick
    _students.txt          the summary, including the threshold sweep and every flag worth a human look
    _students-sheet-NN.jpg one row per student, their frames in order, the pick outlined

Verify by eye: open the sheets. A row with two different people in it is a merge; the same face
in two rows is a split. Both are listed in _students.txt under FLAGS with the reason.
"""
import csv
import json
import re
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import events, models

try:
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
except Exception:
    pass

# SFace's published same-person cosine threshold is 0.363 for a single pair. We cluster on the
# average similarity between whole groups, so the sweep below decides the operating point and
# 0.363 is printed as a reference line, not used as the answer.
SFACE_PAIR_THRESHOLD = 0.363
SWEEP = (0.20, 0.90, 0.01)
PLATEAU_RANGE = (0.30, 0.78)   # where a stable cluster count is believable
NEAR_MISS = 0.04               # how close to the cut a pair has to be to get flagged


def shot_number(p):
    """Capture order. IMG_E3721 is an edited IMG_3721, so the digits are the order, not the name."""
    m = re.search(r"(\d+)", p.stem)
    return (int(m.group(1)) if m else 0, p.name)


# ---------------------------------------------------------------- fingerprints

DETECT_SIDE = 640   # YuNet is trained on faces that are small in frame; a polished headshot's
                    # head fills a third of it, so detect on a 640px view and scale the result
                    # back up. At native 1200x1800 it returns weak, doubled boxes or nothing.


def detect(det, img, thresholds=(0.8, 0.5, 0.3)):
    h, w = img.shape[:2]
    sc = DETECT_SIDE / max(h, w)
    small = cv2.resize(img, None, fx=sc, fy=sc, interpolation=cv2.INTER_AREA) if sc < 1 else img
    sh, sw = small.shape[:2]
    for t in thresholds:
        det.setScoreThreshold(t)
        det.setInputSize((sw, sh))
        _, faces = det.detect(small)
        if faces is not None and len(faces):
            # the polish step centres the subject, so the biggest face is the subject
            face = max(faces, key=lambda f: float(f[2]) * float(f[3])).copy()
            face[:14] /= sc            # box and the five landmarks, back to full resolution
            return face, t
    return None, None


def fingerprints(files):
    det = cv2.FaceDetectorYN.create(models.ensure("detect"), "", (320, 320), 0.8, 0.3, 5000)
    rec = cv2.FaceRecognizerSF.create(models.ensure("recognize"), "")
    kept, vecs, skipped, weak = [], [], [], []
    for p in files:
        img = cv2.imread(str(p), cv2.IMREAD_COLOR)
        if img is None:
            skipped.append((p.name, "unreadable"))
            continue
        face, t = detect(det, img)
        if face is None:
            skipped.append((p.name, "no face found"))
            continue
        if t < 0.8:
            weak.append((p.name, t))
        v = rec.feature(rec.alignCrop(img, face)).flatten().astype(np.float64)
        n = np.linalg.norm(v)
        if n == 0:
            skipped.append((p.name, "empty fingerprint"))
            continue
        kept.append(p)
        vecs.append(v / n)
    return kept, (np.vstack(vecs) if vecs else np.zeros((0, 128))), skipped, weak


# ---------------------------------------------------------------- clustering

def cluster(sim, thresh):
    """Average-linkage agglomerative clustering on a cosine-similarity matrix.

    Merges the two groups with the highest average between-group similarity until the best
    remaining merge falls below `thresh`. Average linkage (rather than single linkage) is what
    stops one ambiguous photo from chaining two students into one group.
    """
    n = len(sim)
    if n == 0:
        return [], []
    sums = sim.astype(np.float64).copy()
    cnt = np.ones(n)
    alive = np.ones(n, dtype=bool)
    members = {i: [i] for i in range(n)}
    idx = np.arange(n)
    while alive.sum() > 1:
        live = idx[alive]
        avg = sums[np.ix_(live, live)] / np.outer(cnt[live], cnt[live])
        np.fill_diagonal(avg, -np.inf)
        a, b = np.unravel_index(np.argmax(avg), avg.shape)
        if avg[a, b] < thresh:
            break
        i, j = int(live[a]), int(live[b])
        ij = sums[i, j]
        sums[i, :] += sums[j, :]
        sums[i, i] += sums[j, j] + ij
        sums[:, i] = sums[i, :]
        cnt[i] += cnt[j]
        members[i] = members[i] + members[j]
        alive[j] = False
    groups = [sorted(members[i]) for i in idx[alive]]
    groups.sort(key=lambda g: g[0])                      # keep capture order
    return groups, [np.array(g) for g in groups]


def sweep(sim):
    lo, hi, step = SWEEP
    out = []
    t = lo
    while t <= hi + 1e-9:
        out.append((round(t, 3), len(cluster(sim, t)[0])))
        t += step
    return out


def plateau(counts):
    """Longest run of an unchanging cluster count inside the believable range."""
    runs, cur = [], None
    for t, k in counts:
        if not (PLATEAU_RANGE[0] - 1e-9 <= t <= PLATEAU_RANGE[1] + 1e-9):
            cur = None
            continue
        if cur and cur[0] == k:
            cur[2].append(t)
        else:
            cur = [k, t, [t]]
            runs.append(cur)
    if not runs:
        return None
    best = max(runs, key=lambda r: (len(r[2]), r[1]))
    return best[0], best[2][0], best[2][-1], best[2][len(best[2]) // 2]


# ---------------------------------------------------------------- reporting

def student_sheets(groups, files, picks, folder, per_sheet=12, per_row=12):
    TH, TW, GAP, LAB = 174, 116, 6, 86
    sheets = []
    for s in range(0, len(groups), per_sheet):
        chunk = groups[s:s + per_sheet]
        wide = max(min(len(g), per_row) for g in chunk)
        W = LAB + wide * (TW + GAP) + GAP
        H = GAP + len(chunk) * (TH + GAP)
        sheet = Image.new("RGB", (W, H), (250, 250, 250))
        draw = ImageDraw.Draw(sheet)
        try:
            font = ImageFont.load_default(size=15)
            small = ImageFont.load_default(size=11)
        except TypeError:
            font = small = ImageFont.load_default()
        for r, g in enumerate(chunk):
            y = GAP + r * (TH + GAP)
            n = s + r + 1
            draw.text((8, y + 4), f"S{n:02d}", fill=(20, 20, 20), font=font)
            draw.text((8, y + 24), f"{len(g)} shot{'s' if len(g) != 1 else ''}", fill=(120, 120, 120), font=small)
            for c, i in enumerate(g[:per_row]):
                x = LAB + c * (TW + GAP)
                im = Image.open(files[i]).convert("RGB")
                im.thumbnail((TW, TH), Image.LANCZOS)
                sheet.paste(im, (x, y))
                if i == picks[s + r]:
                    draw.rectangle([x - 2, y - 2, x + im.width + 1, y + im.height + 1],
                                   outline=(0, 140, 255), width=3)
            if len(g) > per_row:
                draw.text((LAB + per_row * (TW + GAP) - 2, y + TH - 16),
                          f"+{len(g) - per_row}", fill=(120, 120, 120), font=small)
        path = folder / f"_students-sheet-{s // per_sheet + 1:02d}.jpg"
        sheet.save(path, "JPEG", quality=88, optimize=True)
        sheets.append(path)
    return sheets


def analyze(folder, threshold=None, expect=None, sheets=True) -> dict:
    """Group one folder of polished headshots.

    Writes _students.csv, _students.txt and the per-student sheets beside the photos, and returns
    the same findings as a dict. Face fingerprints are held in memory only - they are never
    written to disk, and nothing here touches the network beyond the one-time model download.
    """
    folder = Path(folder).expanduser()
    files = sorted((p for p in folder.glob("*.jpg") if not p.name.startswith("_")), key=shot_number)
    if not files:
        sys.exit(f"no polished photos in {folder}")

    report = {}
    rpath = folder / "_report.json"
    if rpath.exists():
        for e in json.loads(rpath.read_text()).get("photos", []):
            if e.get("output"):
                report[e["output"]] = e

    events.say(f"Fingerprinting {len(files)} photos ...")
    files, F, skipped, weak = fingerprints(files)
    sim = F @ F.T
    np.clip(sim, -1, 1, out=sim)

    counts = sweep(sim)
    pl = plateau(counts)
    if threshold is not None:
        thresh, why = threshold, "you asked for it"
    elif pl:
        thresh, why = pl[3], f"most stable: {pl[0]} students holds from {pl[1]:.2f} to {pl[2]:.2f}"
    else:
        thresh, why = SFACE_PAIR_THRESHOLD, "no stable plateau; falling back to SFace's pair threshold"

    groups, _ = cluster(sim, thresh)

    # the pick per student: own grade first, then the sharpest eyes
    picks = []
    for g in groups:
        def rank(i):
            e = report.get(files[i].name, {})
            own = 0 if not e.get("reasons") else (1 if e.get("grade") != "FAIL" else 2)
            m = e.get("metrics", {})
            return (own, -float(m.get("eye_sharpness", 0)), abs(float(m.get("head_size", 1)) - 1))
        picks.append(min(g, key=rank))

    # ---- verification signals
    #
    # None of these use the filenames or the shoot order, so agreement between them and the
    # grouping is real evidence rather than a restatement of it.
    order_breaks = []
    for n, g in enumerate(groups, 1):
        if g[-1] - g[0] + 1 != len(g):
            gap = [files[i].name for i in range(g[0], g[-1] + 1) if i not in set(g)]
            order_breaks.append((n, files[g[0]].name, files[g[-1]].name, gap))

    gidx = [np.array(g) for g in groups]
    span = {n: f"{files[min(g)].name}..{files[max(g)].name}" for n, g in enumerate(groups, 1)}
    cross = []
    for i in range(len(groups)):
        for j in range(i + 1, len(groups)):
            cross.append((float(sim[np.ix_(gidx[i], gidx[j])].mean()), i + 1, j + 1))
    cross.sort(reverse=True)

    within = []
    for n, g in enumerate(groups, 1):
        if len(g) < 2:
            continue
        s_ = sim[np.ix_(gidx[n - 1], gidx[n - 1])]
        off = ~np.eye(len(g), dtype=bool)
        k = np.unravel_index(np.argmin(np.where(off, s_, 9)), s_.shape)
        within.append((float(s_[off].min()), n, files[g[k[0]]].name, files[g[k[1]]].name))
    within.sort()

    best_other = (sim - np.eye(len(sim)) * 9).max(axis=1)
    order = np.argsort(best_other)
    lonely = []
    for i in order[:6]:
        e = report.get(files[i].name, {})
        lonely.append((float(best_other[i]), files[i].name,
                       next(n for n, g in enumerate(groups, 1) if i in g),
                       e.get("grade", "?"), float(e.get("metrics", {}).get("eye_sharpness", 0))))

    sizes = {}
    for g in groups:
        sizes[len(g)] = sizes.get(len(g), 0) + 1

    # ---- write it out
    with (folder / "_students.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["student", "photo", "source", "frame_of", "fit_to_group", "grade", "pick"])
        for n, g in enumerate(groups, 1):
            c = F[gidx[n - 1]].mean(axis=0)
            c /= np.linalg.norm(c) or 1
            for k, i in enumerate(g, 1):
                e = report.get(files[i].name, {})
                w.writerow([f"S{n:02d}", files[i].name, e.get("source", ""), f"{k}/{len(g)}",
                            round(float(F[i] @ c), 3), e.get("grade", ""),
                            "pick" if i == picks[n - 1] else ""])

    L = []
    L.append(f"{len(groups)} students across {len(files)} photos")
    L.append(f"grouped at cosine {thresh:.2f} ({why})")
    L.append("")
    L.append("HOW MANY STUDENTS, BY HOW STRICT THE CUT IS")
    L.append("  a count that holds over a wide range of cuts is a real answer; one that moves at")
    L.append("  every step is the model guessing. Only the cuts where the count changes are shown.")
    prev = None
    for t, k in counts:
        mark = "   <- SFace's published same-person threshold" if abs(t - SFACE_PAIR_THRESHOLD) < 0.005 else ""
        if k != prev or mark:
            L.append(f"    {t:.2f} -> {k:>3} students{mark}")
            prev = k
    L.append("")
    L.append("HOW CLEANLY THE GROUPS SEPARATE")
    if within and cross:
        L.append(f"    within a group, the weakest pair:   {within[0][0]:.3f}  (median {np.median([w_[0] for w_ in within]):.3f})")
        L.append(f"    between groups, the closest pair:   {cross[0][0]:.3f}  (median {np.median([c[0] for c in cross]):.3f} over {len(cross)} pairs)")
        gap = within[0][0] - cross[0][0]
        L.append(f"    gap between those two: {gap:+.3f}" +
                 ("  - clean separation, no overlap" if gap > 0 else
                  "  - they overlap, so the pairs listed below decide the count"))
    L.append("")
    L.append("GROUP SIZES")
    for k in sorted(sizes):
        L.append(f"    {sizes[k]:>3} students with {k} shot{'s' if k != 1 else ''}")
    if expect:
        L.append("")
        L.append(f"    you expected {expect}: " +
                 ("matches" if expect == len(groups) else f"off by {len(groups) - expect:+d}"))
    L.append("")
    L.append("WHAT TO CHECK ON THE SHEETS")
    if skipped:
        L.append(f"  no fingerprint, left out of the grouping ({len(skipped)}):")
        for n_, r in skipped:
            L.append(f"    {n_}  {r}")
    if weak:
        L.append(f"  face found only at a lowered confidence ({len(weak)}):")
        for n_, t in weak:
            L.append(f"    {n_}  at {t:.1f}")
    L.append(f"  groups that are not one unbroken run of shots ({len(order_breaks)} of {len(groups)}):")
    L.append("    students get photographed one at a time, so a group should be a single run.")
    L.append("    A group that jumps around the shoot is a student who came back - or two people")
    L.append("    merged into one group. The grouping never saw the filenames, so agreement here")
    L.append("    is independent evidence that it is right.")
    for n, first, last, gapf in order_breaks[:20]:
        L.append(f"    S{n:02d}  {first} .. {last}, skipping {', '.join(gapf[:6])}{' ...' if len(gapf) > 6 else ''}")
    L.append("  the two groups that came closest to being one student:")
    for s_, i, j in cross[:4]:
        L.append(f"    S{i:02d} + S{j:02d}  {s_:.3f}   ({span[i]}  and  {span[j]})")
    L.append("  groups held together by their weakest link:")
    L.append("    if the two shots named are different people, that group is a bad merge.")
    for m, n, x, y in within[:4]:
        L.append(f"    S{n:02d}  {x} vs {y}  {m:.3f}")
    L.append("  shots that match nothing else well:")
    L.append("    two different things look like this, and the grade tells them apart. A shot that")
    L.append("    also grades badly or has soft eyes is a face that did not read - turned away, eyes")
    L.append("    shut, something across it - and is not a new student. A shot that grades clean with")
    L.append("    sharp eyes and still matches nobody is someone who was photographed only once.")
    for m, n_, gid, grade, sharp in lonely:
        L.append(f"    {n_}  best match anywhere {m:.3f}  (in S{gid:02d}, graded {grade}, eye sharpness {sharp:.2f})")
    L.append("")
    L.append("PICK PER STUDENT  (best own grade, then sharpest eyes)")
    for n, g in enumerate(groups, 1):
        e = report.get(files[picks[n - 1]].name, {})
        L.append(f"    S{n:02d}  {files[picks[n-1]].name}  {e.get('grade','')}  ({len(g)} to choose from)")
    text = "\n".join(L)
    (folder / "_students.txt").write_text(text + "\n")

    sheet_paths = student_sheets(groups, files, picks, folder) if sheets else []
    events.say(text)
    events.say()
    events.say("wrote _students.csv, _students.txt"
               + (f", {len(sheet_paths)} sheet(s)" if sheet_paths else ""))
    result = {
        "students": len(groups),
        "photos": len(files),
        "threshold": round(thresh, 3),
        "why": why,
        "sweep": [{"cut": t, "students": k} for t, k in counts],
        "groups": [{"id": f"S{n:02d}", "photos": [files[i].name for i in g],
                    "pick": files[picks[n - 1]].name} for n, g in enumerate(groups, 1)],
        "flags": {
            "not_one_run": [f"S{n:02d}" for n, *_ in order_breaks],
            "closest_pair": [f"S{cross[0][1]:02d}", f"S{cross[0][2]:02d}",
                             round(cross[0][0], 3)] if cross else None,
            "matches_nothing": [[nm, round(m, 3)] for m, nm, *_ in lonely[:3]],
        },
        "report": str(folder / "_students.txt"),
        "csv": str(folder / "_students.csv"),
        "sheets": [str(p) for p in sheet_paths],
    }
    events.emit("grouped", **result)
    return result

