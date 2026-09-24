# headshots

Turn a folder of phone photos into a matched set of portraits — same head size, same eye line,
same finish — then check every one of them and tell you which ones a person should look at.
Optionally, work out who is in them and pick each person's best frame.

It runs on your machine. No account, no upload, no telemetry.

```console
$ headshots run ~/Photos/cast-shoot
Framing 1600x2000, zoom 1, eyes at 42%, color (defaults)
✓ PASS    IMG_0418.JPG
✓ PASS    IMG_0419.JPG
! REVIEW  IMG_0420.JPG    eyes at 51% from the top, not 42%; framed 12% tighter to fit the photo
✓ PASS    IMG_0421.JPG

84 processed in 14.1s, 0 unchanged. Set: 71 PASS, 13 REVIEW (9 flagged for not matching the rest of the set)
Note: backdrop brightness varies a lot across the set (131-204 of 255): shoot everyone in one spot
Review: ~/Photos/cast-shoot/polished/_contact-sheet.jpg (+2 more pages)

12 people across 84 photos
grouped at cosine 0.55 (most stable: 12 people holds from 0.49 to 0.63)
```

## Why it exists

Shooting 200 portraits in an afternoon is easy. Making them look like one set is not: every
subject stands at a slightly different distance, so every head lands at a different size, and
cropping them by hand is a day of work that you will still get subtly wrong.

This finds the face, works out how big the head is from the eye and mouth positions rather than
the detector's box, and crops so that a head is the same fraction of the frame in every photo —
then it re-opens what it saved and measures whether it actually did that.

## Install

**The app** — download the `.dmg` from
[Releases](https://github.com/sunnypatneedi/headshots/releases), drag it to Applications, drop a
folder on the window.

If macOS says the app is damaged or from an unidentified developer, the build was not notarised.
Clear the quarantine flag once:

```console
$ xattr -rd com.apple.quarantine /Applications/Headshots.app
```

That is not a bug and not a workaround for a broken signature — notarising requires a paid Apple
Developer account, and this project does not assume one. A notarised build needs no such step;
if the release you downloaded has one, this section does not apply to it.

**The command** — same tool, no Gatekeeper step:

```console
$ pipx install headshots     # or: uv tool install headshots
```

Python 3.10 or newer. The app carries its own Python, so you do not need both.

## Systems design

Interactive architecture map (Archify) for both audiences — open the HTML and use the view chips:

- **Plain story** — drop a folder, frame/check the set, group people
- **Technical stack** — SwiftUI shell → Python CLI → polish / group → YuNet + SFace
- **Stays on device** — local disk only; network is a one-time SHA-256-pinned model fetch

[Open the diagram](./docs/architecture/headshots.html) · source: [`headshots.architecture.json`](./docs/architecture/headshots.architecture.json)

## Demo shoot (synthetic)

Fictional phone portraits live in [`examples/synthetic/`](./examples/synthetic/) — not anyone’s private photos.

```console
$ cp -R examples/synthetic/shoot /tmp/headshots-demo
$ headshots run /tmp/headshots-demo
$ open /tmp/headshots-demo/polished/_contact-sheet.jpg   # macOS
```

See [`examples/synthetic/README.md`](./examples/synthetic/README.md).

## Use

```console
$ headshots polish ~/Photos/shoot          # frame, finish and check
$ headshots group  ~/Photos/shoot/polished # work out who is in them
$ headshots run    ~/Photos/shoot          # both
$ headshots models                         # fetch the models now, then work offline
```

Useful flags:

| | |
|---|---|
| `--ratio 2:3` | crop shape. Default `4:5` |
| `--width 1200` | output width in pixels. Default `1600` |
| `--zoom 0.85` | looser than standard — head and shoulders. `1.15` is tighter |
| `--bw` | black and white |
| `--no-finish` | crop only, no tone or colour work |
| `--watch` | keep running, polish photos as they land |
| `--json` | one JSON object per line, for scripting. The app uses this |

Results go to `<folder>/polished/`. **Originals are never modified.** A second run skips photos
that have not changed, and never overwrites an output you have edited by hand — it re-checks it
instead. Settings are remembered per output folder, so photos you add in November match the ones
you shot in September without you having to remember what you passed.

## How it frames

Head size comes from the face landmarks, not the detector's bounding box, which moves around too
much between shots to build a set on:

```
scale = max(2.0 × distance between the eyes,
            1.8 × distance from the eye line to the mouth)
```

The crop is then `3.4 × scale` tall, with the eyes 42% down. When that ideal crop would run off
the edge of the photo, it searches nearby framings and picks the one that costs least — a little
zoom, a little eye drift, a slide sideways — rather than either failing or silently cropping
someone's head off. It also tries to find the top of the head by looking for where the backdrop
starts, and refuses to crop into it.

Everything is done in sRGB with the source profile honoured, so a Display P3 photo out of an
iPhone does not lose its colour on the way through. Tone work is luminance-only.

## What the check catches

Every saved file is re-opened and measured as if someone else had made it: the face is detected
again, and the framing, clipping, skin colour, eye sharpness, stray faces, fidelity to the
original and remaining metadata are compared against what was planned. Each photo comes back
`PASS`, `REVIEW` or `FAIL` with the reason in words — *"eyes at 51% from the top, not 42%"* —
and a set-level pass flags photos whose head size does not match the rest of the set.

This is the part that makes a 200-photo set trustworthy: you are not eyeballing 200 photos, you
are reading the 13 the tool is unsure about.

It is not a substitute for looking. The head-top check uses the same detector as the cropping
step, so it cannot catch a mistake they both make. Open the contact sheet.

## Grouping by person

`headshots group` turns each face into a 128-number fingerprint and clusters them, so a shoot
becomes people rather than files. It will not tell you a number and leave you to trust it:

- **A sweep, not a threshold.** It reports how many people it finds at every cut from 0.20 to
  0.90. A count that holds steady across a wide range is a real answer; one that moves at every
  step is the model guessing. It groups at the widest stable range and says which one it used.
- **A check it cannot cheat.** People are photographed one at a time, so each group should be a
  single unbroken run of shots. The clustering never sees filenames, so when the groups agree
  with the shoot order anyway, that is independent evidence.
- **Named doubts.** Which two groups came closest to being one person, which group is held
  together by its weakest link and by which two shots, and which shots match nothing else well —
  with each one's grade, because a shot that also grades badly is a face that did not read, while
  a clean sharp shot that matches nobody is someone photographed only once.

Output lands beside the photos: `_students.csv`, `_students.txt`, and contact sheets with one row
per person and the suggested pick outlined.

## What this is for, and what it is not

This groups photos *you took*, of people who stood in front of your camera and knew it. A cast
list, a class, a team, a conference. That is the whole design: a closed set of willing subjects,
sorted so nobody has to do it by hand.

It is not built for identifying people against a database, and it cannot do it — there is no
enrolment, no stored gallery, no names anywhere in it. Fingerprints exist for the length of one
run and are never written to disk; what lands in `_students.csv` is filenames and similarity
numbers. If you want to point face recognition at strangers, this is the wrong tool and you
should think harder about the question.

Claims you can check rather than take on faith:

| Claim | How to check |
|---|---|
| It only ever talks to one host, for two files | `grep -rn "http" src/` — all of it is in `models.py` |
| Models are pinned, not trusted | SHA-256 in `models.py`; a mismatch is discarded, not used |
| It works with the network off | `headshots models`, then pull the plug |
| Fingerprints are never stored | `grep -rn "csv\|write" src/headshots/group.py` |
| Output carries no GPS or metadata | `exiftool polished/*.jpg` |
| The same photos give the same bytes | run it twice, compare checksums |

No analytics, no crash reporting, no update check.

## Speed

227 photos, polished, checked and contact-sheeted in **37 s**; grouping the same 227 took
**7 s**. Measured end to end, including writing the contact sheets, on 4 cores of an
Apple-silicon laptop — it uses up to 8, so a whole machine is faster than this. Re-running an
unchanged folder is near-instant: it reads the manifest and does nothing.

## Models

Two, from the [OpenCV Model Zoo](https://github.com/opencv/opencv_zoo), downloaded on first use
into `~/.cache/headshots` and pinned by checksum:

| | | |
|---|---|---|
| YuNet | face detection | MIT, 230 KB |
| SFace | face matching, `group` only | Apache-2.0, 37 MB |

See [NOTICE](NOTICE) for attribution and a caveat about SFace's training data.

## Development

```console
$ make dev     # install with the test tools
$ make test    # 34 tests: no photos, no models, no network
$ make lint
$ make app     # build Headshots.app into dist/  (macOS)
$ make dmg
```

The tests use made-up faces and made-up fingerprints, so they run anywhere in under a second.
The properties worth knowing are tested: two faces at different distances come out the same size,
a known head-top is never cropped into, average linkage does not chain two people together
through one ambiguous photo, and the embedded colour profile carries no timestamp.

The app is a window over the command. Same code, same output; it runs `headshots --json` and
reads the event stream. If the two ever disagree, the command is right.

## Licence

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
