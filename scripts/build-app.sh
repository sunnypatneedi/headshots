#!/usr/bin/env bash
# Build Headshots.app: the command frozen with PyInstaller, inside a SwiftUI window.
#
#   ./scripts/build-app.sh            build for this Mac's architecture
#   SIGN_ID="Developer ID Application: You (TEAMID)" ./scripts/build-app.sh
#
# Without SIGN_ID the app is ad-hoc signed. That is enough to run on Apple Silicon, but macOS
# will still refuse it on another Mac until the person clears the quarantine flag - see the
# README. Notarisation is what removes that step, and it needs a paid Apple Developer account.
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' src/headshots/__init__.py)
ARCH=$(uname -m)
APP="dist/Headshots.app"
RES="$APP/Contents/Resources"

command -v swiftc >/dev/null || { echo "swiftc not found - install Xcode Command Line Tools: xcode-select --install"; exit 1; }

echo "==> freezing the command"
python3 -m venv build/venv
build/venv/bin/pip install --quiet --upgrade pip pyinstaller
build/venv/bin/pip install --quiet .
build/venv/bin/pyinstaller --noconfirm --clean --log-level WARN \
    --name headshots --distpath build/dist --workpath build/work --specpath build \
    --collect-all cv2 --collect-all pillow_heif \
    --exclude-module tkinter --exclude-module matplotlib \
    src/headshots/__main__.py

echo "==> assembling $APP"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$RES/bin"
cp -R build/dist/headshots/. "$RES/bin/"
sed "s/__VERSION__/$VERSION/g" app/Info.plist > "$APP/Contents/Info.plist"

echo "==> building the window"
swiftc -O -parse-as-library -target "${ARCH}-apple-macos13.0" \
    -o "$APP/Contents/MacOS/Headshots" app/Sources/Headshots/*.swift

echo "==> signing"
if [ -n "${SIGN_ID:-}" ]; then
    codesign --force --deep --options runtime --timestamp --sign "$SIGN_ID" "$APP"
    echo "    signed with $SIGN_ID"
else
    codesign --force --deep --sign - "$APP"
    echo "    ad-hoc signed (not notarised)"
fi
codesign --verify --verbose=2 "$APP" 2>&1 | tail -2

echo "==> checking it starts"
"$RES/bin/headshots" --version

echo "==> probing frozen binary (imports + empty polish)"
# Absolute import + OpenCV/NumPy/Pillow must load. Empty folder → "No photos found" (non-zero exit).
PROBE_DIR=$(mktemp -d)
PROBE_OUT=$("$RES/bin/headshots" polish "$PROBE_DIR" 2>&1 || true)
rm -rf "$PROBE_DIR"
echo "$PROBE_OUT" | grep -q "No photos found" || {
    echo "frozen binary probe failed — expected 'No photos found' from empty polish:"
    echo "$PROBE_OUT"
    exit 1
}
echo "    ok — empty polish reported No photos found"

echo
echo "Built $APP  ($VERSION, $ARCH)"
