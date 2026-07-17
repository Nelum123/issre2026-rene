#!/usr/bin/env bash
set -euo pipefail

# Minimal GCC dump builder for C projects in the current directory.
# Usage:
#   ./build_modified.sh main

ENTRY="${1:-main}"
OUT_DIR="mrd_dumps"
BIN_NAME="mrd_test_bin"

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"
rm -f ./*.cfg ./*.cfg.dot ./*.cgraph ./*.ipa-cgraph ./*.o "$BIN_NAME"

gcc -O0 -g0 \
  -fdump-tree-cfg-graph \
  -fdump-ipa-cgraph \
  ./*.c \
  -o "$BIN_NAME"

# Move generated dump files into OUT_DIR instead of copying them.
# This keeps the project root clean after the build.
find . -maxdepth 1 -type f \
  \( -name "*.cfg" -o -name "*.cfg.dot" -o -name "*.cgraph" -o -name "*.ipa-cgraph" \) \
  -exec mv {} "$OUT_DIR"/ \;

echo "Done."
echo "Entry function: $ENTRY"
echo "Dump folder: $OUT_DIR"
echo "CFG files:     $(find "$OUT_DIR" -name "*.cfg" | wc -l)"
echo "CFG DOT files: $(find "$OUT_DIR" -name "*.cfg.dot" | wc -l)"
echo "CGRAPH files:  $(find "$OUT_DIR" \( -name "*.cgraph" -o -name "*.ipa-cgraph" \) | wc -l)"
echo
echo "Next run:"
echo "  python3 calculate_mrd.py --dump-dir $OUT_DIR --entry $ENTRY --output mrd_output.json"
