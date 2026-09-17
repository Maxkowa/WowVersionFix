#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARCHS="${ARCHS-$(uname -m)}"

die() { echo "build.sh: $*" >&2; exit 1; }

command -v swiftc >/dev/null 2>&1 || die "swiftc not found - install the Xcode command line tools (xcode-select --install)"
command -v codesign >/dev/null 2>&1 || die "codesign not found - install the Xcode command line tools (xcode-select --install)"
command -v lipo >/dev/null 2>&1 || die "lipo not found - install the Xcode command line tools (xcode-select --install)"
[ -f "$ROOT/wowbuildapp/main.swift" ] || die "missing $ROOT/wowbuildapp/main.swift"
[ -f "$ROOT/Info.plist" ] || die "missing $ROOT/Info.plist"
[ -f "$ROOT/wowbuild.py" ] || die "missing $ROOT/wowbuild.py"

set -- $ARCHS
[ "$#" -gt 0 ] || die "ARCHS is empty - set it to one or more architectures, e.g. ARCHS=\"arm64 x86_64\""

plist() { /usr/libexec/PlistBuddy -c "Print :$1" "$ROOT/Info.plist" 2>/dev/null || echo ""; }

NAME="$(plist CFBundleExecutable)"
[ -n "$NAME" ] || die "Info.plist has no CFBundleExecutable"
APP="$ROOT/build/$NAME.app"

PLIST_MIN="$(plist LSMinimumSystemVersion)"
[ -n "$PLIST_MIN" ] || die "Info.plist has no LSMinimumSystemVersion"
MIN="${MACOS_MIN:-$PLIST_MIN}"
[ "$MIN" = "$PLIST_MIN" ] || \
  die "MACOS_MIN=$MIN does not match LSMinimumSystemVersion $PLIST_MIN in Info.plist"

ICON=""
for c in "$ROOT/AppIcon.icns" "$ROOT/Resources/AppIcon.icns"; do
  if [ -f "$c" ]; then ICON="$c"; break; fi
done
[ -n "$ICON" ] || echo "build.sh: warning: no AppIcon.icns in the repo - building without an icon" >&2

STAGE="$(mktemp -d "${TMPDIR:-/tmp}/wowbuildapp.XXXXXX")"
trap 'rm -rf "$STAGE"' EXIT
NEW="$STAGE/$NAME.app"
BIN="$NEW/Contents/MacOS/$NAME"
mkdir -p "$NEW/Contents/MacOS" "$NEW/Contents/Resources" "$STAGE/slices"

cd "$ROOT"
SLICES=()
for arch in "$@"; do
  swiftc -O -module-name wowbuildapp -target "$arch-apple-macos$MIN" \
    -o "$STAGE/slices/$arch" \
    wowbuildapp/main.swift
  SLICES+=("$STAGE/slices/$arch")
done

if [ "${#SLICES[@]}" -eq 1 ]; then
  mv "${SLICES[0]}" "$BIN"
else
  lipo -create "${SLICES[@]}" -output "$BIN"
fi

cp "$ROOT/Info.plist"  "$NEW/Contents/Info.plist"
cp "$ROOT/wowbuild.py" "$NEW/Contents/Resources/wowbuild.py"
if [ -n "$ICON" ]; then cp "$ICON" "$NEW/Contents/Resources/AppIcon.icns"; fi

# Stamped before signing, so the release carries the tag's version while a plain
# local build keeps whatever the committed Info.plist says.
if [ -n "${BUNDLE_VERSION:-}" ]; then
  /usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $BUNDLE_VERSION" "$NEW/Contents/Info.plist"
  /usr/libexec/PlistBuddy -c "Set :CFBundleVersion ${BUNDLE_BUILD:-$BUNDLE_VERSION}" "$NEW/Contents/Info.plist"
fi

codesign --force --sign - "$NEW"
codesign -dv "$NEW" 2>&1 | grep -E 'Signature|Identifier'

mkdir -p "$ROOT/build"
rm -rf "$APP"
mv "$NEW" "$APP"

VERSION="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$APP/Contents/Info.plist")"
echo "built: $APP (version $VERSION, deployment target macOS $MIN, architectures: $(lipo -archs "$APP/Contents/MacOS/$NAME"))"
