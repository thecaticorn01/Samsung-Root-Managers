#!/usr/bin/env bash
#
# collect_assets.sh PREFIX DL_DIR OUT_DIR
#
# Flattens the artifacts downloaded from a backend build (all named PREFIX-*)
# into OUT_DIR as clean, uploadable release assets, EXCLUDING any run/CI logs or
# gradle mapping files. Writes OUT_DIR/SHA256SUMS and prints the asset basenames
# (one per line) to stdout for the state file.
#
#   PREFIX = ksun | baka
#   DL_DIR = directory holding the downloaded artifact folders
#   OUT_DIR= where to assemble the final assets
set -euo pipefail
PREFIX="$1"; DL="$2"; OUT="$3"
mkdir -p "$OUT"

# 1) Manager APK(s)
find "$DL/${PREFIX}-manager-apk" -name '*.apk' -exec cp -f {} "$OUT/" \; 2>/dev/null || true

# 2) ksud binaries, one per target triple -> ksud-<triple>
for d in "$DL/${PREFIX}-ksud-"*; do
  [ -d "$d" ] || continue
  triple="$(basename "$d" | sed "s/^${PREFIX}-ksud-//")"
  f="$(find "$d" -type f -name 'ksud' | head -1 || true)"
  [ -n "$f" ] && cp -f "$f" "$OUT/ksud-${triple}"
done

# 3) kernel modules (.ko) for every KMI/arch that was built
find "$DL" -path "*${PREFIX}-*-lkm/*.ko" -exec cp -f {} "$OUT/" \; 2>/dev/null || true

# 4) checksums (exclude the sums file itself)
( cd "$OUT" && find . -maxdepth 1 -type f ! -name SHA256SUMS -printf '%P\n' | sort | xargs -r sha256sum > SHA256SUMS )

# 5) emit the asset list (what the release will contain)
( cd "$OUT" && find . -maxdepth 1 -type f -printf '%P\n' | sort )
