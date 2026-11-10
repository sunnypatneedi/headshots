"""Guard the frozen-app entry point.

PyInstaller runs `src/headshots/__main__.py` as a top-level script. A package-relative import
there fails at app launch with ImportError; this test locks the absolute form.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAIN = ROOT / "src" / "headshots" / "__main__.py"


def test_entry_point_uses_absolute_cli_import():
    src = MAIN.read_text()
    imports = re.findall(r"^(?:from|import)\s+.+$", src, flags=re.M)
    assert any(line == "from headshots.cli import main" for line in imports), (
        "__main__.py must absolute-import headshots.cli so the PyInstaller freeze can start"
    )
    assert not any(re.match(r"from\s+\.cli\s+import\s+main\b", line) for line in imports), (
        "package-relative cli import in __main__.py breaks the frozen Headshots.app binary"
    )
