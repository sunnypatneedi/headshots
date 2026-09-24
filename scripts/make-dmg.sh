#!/usr/bin/env bash
# Wrap dist/Headshots.app in a .dmg with a drag-to-Applications shortcut.
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' src/headshots/__init__.py)
ARCH=$(uname -m)
STAGE=$(mktemp -d)
cp -R dist/Headshots.app "$STAGE/"
ln -s /Applications "$STAGE/Applications"
DMG="dist/Headshots-$VERSION-$ARCH.dmg"
rm -f "$DMG"
hdiutil create -volname "Headshots $VERSION" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null
rm -rf "$STAGE"
shasum -a 256 "$DMG"
