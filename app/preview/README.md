# UI preview

Static HTML mirror of the SwiftUI shell for visual QA on Linux (where `swiftc` cannot build the Mac app).

```console
$ python3 -m http.server 8765 --directory app/preview
# open http://127.0.0.1:8765/?screen=welcome&theme=light
```

Query params: `screen` = welcome|check|finish|processing|results|empty|error · `theme` = light|dark.

Tokens in `tokens.json` are shared with `Theme.swift` and checked by `tests/test_theme_contrast.py`.
