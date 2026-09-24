"""The app and the command are two languages that have to agree about one thing: the event stream.

A field renamed in Python would not break any Python test, and the Swift would still compile - the
app would just quietly stop updating. So this reads both sides and checks they still line up. It
parses text rather than running either one, so it needs no photos, no models and no Swift.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SWIFT = ROOT / "app" / "Sources" / "Headshots" / "Events.swift"
PYTHON = sorted((ROOT / "src" / "headshots").glob("*.py"))

# Swift struct -> the event name it decodes. Kept here because the mapping lives in a switch
# statement that is not worth parsing.
STRUCTS = {"Photo": "photo", "Polished": "polished", "Grouped": "grouped",
           "Group": "grouped"}      # the nested one, for the entries inside `groups`


def swift_fields(struct: str) -> tuple[set[str], set[str]]:
    """(required, optional) stored-property names for one struct, renames applied.

    Only properties of the struct itself: a nested struct's own fields belong to that struct, and
    are checked under its own name.
    """
    src = SWIFT.read_text()
    start = re.search(rf"struct {struct}\b", src).start()
    depth, end = 0, start
    for i, ch in enumerate(src[start:], start):
        depth += (ch == "{") - (ch == "}")
        if depth == 0 and i > start and ch == "}":
            end = i + 1
            break
    body = src[start:end]

    renames = dict(re.findall(r"case\s+(\w+)\s*=\s*\"([^\"]+)\"", body))
    required, optional = set(), set()
    depth = 0
    for line in body.splitlines():
        stripped = line.strip()
        was = depth
        depth += line.count("{") - line.count("}")
        if was != 1:                                   # not directly inside this struct's braces
            continue
        m = re.match(r"let\s+(\w+)\s*:\s*([^\n=]+)$", stripped)
        if not m:
            continue
        name, kind = m.group(1), m.group(2).strip()
        (optional if kind.endswith("?") else required).add(renames.get(name, name))
    return required, optional


def _dict_keys(src: str, name: str, before: int) -> set[str]:
    """Every quoted key, at any depth, in the nearest `name = {...}` literal above `before`."""
    start = src.rindex(f"{name} = {{", 0, before)
    end, depth = src.index("{", start), 0     # start on the brace, or depth 0 ends it immediately
    while end < len(src):
        depth += (src[end] == "{") - (src[end] == "}")
        end += 1
        if depth == 0:
            break
    return set(re.findall(r'"(\w+)"\s*:', src[start:end]))


def emitted_fields(event: str) -> set[str]:
    """The keyword names passed to events.emit("<event>", ...) anywhere in the package."""
    found = set()
    for path in PYTHON:
        src = path.read_text()
        for m in re.finditer(r"events\.emit\(\s*['\"]" + event + r"['\"]\s*,", src):
            depth, i = 1, m.end()
            while depth and i < len(src):
                depth += (src[i] == "(") - (src[i] == ")")
                i += 1
            call = src[m.end():i - 1]
            found |= set(re.findall(r"(?:^|[,(\s])(\w+)\s*=(?!=)", call))
            spread = re.search(r"\*\*(\w+)", call)
            if spread:                                  # emit(**result): read the dict it spreads
                found |= _dict_keys(src, spread.group(1), before=m.start())
    return found


@pytest.mark.parametrize("struct,event", STRUCTS.items())
def test_the_app_can_decode_what_the_command_sends(struct, event):
    required, _ = swift_fields(struct)
    sent = emitted_fields(event)
    missing = required - sent
    assert not missing, (
        f"Events.swift decodes `{struct}` from the `{event}` event and needs {sorted(missing)}, "
        f"which nothing in src/headshots emits. Either the Swift or the Python was renamed "
        f"without the other."
    )


def test_the_swift_file_is_where_the_test_thinks_it_is():
    assert SWIFT.exists(), "app/Sources/Headshots/Events.swift moved; update this test"
    assert emitted_fields("photo"), "no events.emit(\"photo\", ...) found; the parser is broken"
