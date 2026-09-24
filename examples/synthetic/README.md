# Synthetic demo shoot

Phone-sized **fictional** portraits for docs, manual demos, and smoke tests.

## What this is

- Eight JPEGs under `shoot/` — four fictional adults × two frames each
- Portraits are **AI-generated** studio headshots of people who do not exist
- **Not** photos of the maintainers, contributors, kids, or anyone affiliated with this project
- **Not** a real cast shoot

`manifest.json` records fictional ids. Every frame was checked with YuNet (the same detector `headshots` uses) before commit.

## Quick demo

```bash
cp -R examples/synthetic/shoot /tmp/headshots-demo
headshots run /tmp/headshots-demo
open /tmp/headshots-demo/polished/_contact-sheet.jpg   # macOS
```

Do not run polish inside the git tree if you want a clean `git status` — copy out first (outputs create a `polished/` folder next to the inputs).

## Licensing note

These fixtures are synthetic demo assets for this repository. Do not replace them with private album photos before pushing.
