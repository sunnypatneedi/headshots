# Contributing

## Getting set up

```console
$ make dev
$ make test
```

The tests need no photos, no models and no network — they run on made-up faces and made-up
fingerprints. If a change you make requires real photos to test, that is worth a conversation in
the issue before the pull request: it usually means a piece of maths wants pulling out of a
function that also does I/O.

## What this project is trying to be

A tool a photographer can point at a folder and trust the output of. Two things follow from that:

**Say why, in words, in the output.** "eyes at 51% from the top, not 42%" beats a score. If you
add a check, it reports what it measured, what it expected, and what to do.

**Never assert what you can measure.** The polisher does not claim a photo is framed correctly;
it re-opens the file it wrote and checks. New features are held to the same standard — if a
change cannot be verified after the fact, say so in the output rather than hiding the gap.

## House style

- Comments explain *why*, never *what*. If a line needs a comment to say what it does, rename
  something instead.
- Long lines are fine when they are a sentence the tool prints; keeping each on one line means a
  user can quote a message at you and you can grep for it.
- No new runtime dependencies without a good reason. The install is four packages and it should
  stay small enough to freeze into an app.

## Things that would genuinely help

- **Intel and universal builds.** The release currently ships for the architecture the runner
  builds on.
- **Expression and eye checks.** The judge grades sharpness but not whether someone blinked,
  which is the most common reason a technically perfect frame is unusable.
- **A better head-top finder.** It looks for where the backdrop starts and gives up on busy
  backgrounds, which is honest but leaves framing on the table. It also shares a detector with
  the cropping step, so it cannot catch a mistake they both make.
- **Other kinds of set.** The framing maths assumes a head-and-shoulders portrait. Full-length or
  group shots would need a different plan, not a different constant.

## Pull requests

Keep them one idea wide. Include what you measured, on how many photos, and on what hardware — a
change that makes framing "better" needs a before and after, since the tool's whole claim is that
it checks its own work.
