#!/usr/bin/env bash
# Render every layout at exact panel size with headless Chrome, for use by
# scripts/make-images.py. Needs a local checkout plus `trmnlp build`.
#
# Usage: scripts/screenshot-layouts.sh [build-dir] [out-dir]
set -euo pipefail

BUILD_DIR="${1:-_build}"
OUT_DIR="${2:-/tmp/trmnl-wallet-renders}"
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"

[ -x "$CHROME" ] || { echo "Chrome not found at $CHROME (set \$CHROME)" >&2; exit 1; }
mkdir -p "$OUT_DIR"

# layout:width:height — the four panel geometries TRMNL renders
for pair in "full:800:480" "half_horizontal:800:240" "half_vertical:400:480" "quadrant:400:240"; do
  name="${pair%%:*}"
  rest="${pair#*:}"
  width="${rest%%:*}"
  height="${rest##*:}"
  src="$BUILD_DIR/$name.html"
  [ -f "$src" ] || { echo "missing $src (run: trmnlp build)" >&2; exit 1; }
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=1 \
    --window-size="$width,$height" --virtual-time-budget=5000 \
    --screenshot="$OUT_DIR/$name.png" "file://$PWD/$src" >/dev/null 2>&1
  echo "rendered $name ${width}x${height} -> $OUT_DIR/$name.png"
done
