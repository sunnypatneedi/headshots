# Absolute import: PyInstaller freezes this file as a top-level script, so a package-relative
# cli import fails with "attempted relative import with no known parent package".
import sys

from headshots.cli import main

sys.exit(main())
