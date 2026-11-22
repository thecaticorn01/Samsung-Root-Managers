#!/usr/bin/env bash
#
# prepare_source.sh — materialize a Samsung-compatible manager source tree.
#
# Clones an upstream manager repo at a pinned commit, re-applies this repo's
# Samsung (Galaxy S26 Ultra: KDP/RKP/DEFEX late-load) patch set on top of it,
# swaps in the backend's dedicated signing certificate, and emits the version
# metadata the release notes need.
#
# It is deliberately dependency-light: it needs only git + openssl + coreutils,
# so it runs unchanged on the GitHub-hosted runner AND inside the ddk-min
# kernel-build container (which has no Java/keytool).
#
# Usage:
#   prepare_source.sh \
#     --repo OWNER/NAME --sha <commit> \
#     --patch patches/<id>-samsung.patch \
#     --keystore keystores/<id>.jks --storepass <pw> --alias <alias> \
#     --out <dir> \
#     --driver-extra <0|700> \
#     [--sed-cert 'relative/path/to/file.ext']   # repeatable; see below
#
# --sed-cert FILE: inside FILE, replace the stock fork signing-cert marker
#   'size: 0x307, hash: 4fb9...641c' with this backend's real cert marker
#   'size: 0x<NEW>, hash: <NEW>'. Used by BakaSU's KsuCli isOfficialSignature().
#
# On success it writes KEY=VALUE pairs to stdout and, when $GITHUB_OUTPUT is
# set, appends them there too:
#   upstream_sha, upstream_short, commit_count, driver_version, uapi_version,
#   version_name, cert_size_hex, cert_hash, cert_size_dec
set -euo pipefail

REPO="" SHA="" PATCH="" KEYSTORE="" STOREPASS="" ALIAS="" OUT="src"
DRIVER_EXTRA="0"
SKIP_SIGNING="0"
SED_CERT_FILES=()

# The stock fork marker these patches historically embed; swapped for the
# backend's own cert so the two managers never collide (see project history).
STOCK_MARKER='size: 0x307, hash: 4fb9754b5d8721499b229a47a9a0f80a52f180a81fef8fcb474066840d13641c'

while [ $# -gt 0 ]; do
  case "$1" in
    --repo)       REPO="$2"; shift 2;;
    --sha)        SHA="$2"; shift 2;;
    --patch)      PATCH="$2"; shift 2;;
    --keystore)   KEYSTORE="$2"; shift 2;;
    --storepass)  STOREPASS="$2"; shift 2;;
    --alias)      ALIAS="$2"; shift 2;;
    --out)        OUT="$2"; shift 2;;
    --driver-extra) DRIVER_EXTRA="$2"; shift 2;;
    --skip-signing) SKIP_SIGNING="1"; shift 1;;
    --sed-cert)   SED_CERT_FILES+=("$2"); shift 2;;
    *) echo "prepare_source.sh: unknown arg '$1'" >&2; exit 2;;
  esac
done

REQUIRED="REPO SHA PATCH OUT"
[ "$SKIP_SIGNING" = "1" ] || REQUIRED="$REQUIRED KEYSTORE STOREPASS ALIAS"
for v in $REQUIRED; do
  if [ -z "${!v}" ]; then echo "prepare_source.sh: --${v,,} is required" >&2; exit 2; fi
done

KIT="$(pwd)"
PATCH_ABS="$KIT/$PATCH"
[ -f "$PATCH_ABS" ] || { echo "patch not found: $PATCH_ABS" >&2; exit 1; }
if [ "$SKIP_SIGNING" != "1" ]; then
  KEYSTORE_ABS="$KIT/$KEYSTORE"
  [ -f "$KEYSTORE_ABS" ] || { echo "keystore not found: $KEYSTORE_ABS" >&2; exit 1; }
fi

echo "== cloning https://github.com/$REPO (full history, for 3-way apply) =="
rm -rf "$OUT"
git clone --no-single-branch "https://github.com/$REPO" "$OUT"
git -C "$OUT" config --global --add safe.directory "$(cd "$OUT" && pwd)" 2>/dev/null || true
git config --global --add safe.directory "$(cd "$OUT" && pwd)" 2>/dev/null || true
git -C "$OUT" checkout --quiet "$SHA"

echo "== re-applying Samsung patch set =="
# Direct apply if context still matches; otherwise a conflict-free 3-way merge
# against the upstream base blobs (present because this is a full clone). A real
# conflict stops the run here, before anything is built — exactly what we want.
if git -C "$OUT" apply --whitespace=nowarn "$PATCH_ABS"; then
  echo "   applied cleanly"
elif git -C "$OUT" apply --3way --whitespace=nowarn "$PATCH_ABS"; then
  echo "   applied via 3-way merge"
else
  echo "!! Samsung patch did NOT apply onto $REPO@$SHA." >&2
  echo "!! Upstream moved under the patch; it needs a human refresh." >&2
  exit 3
fi

CERT_SIZE_HEX="" CERT_SIZE_DEC="" CERT_HASH=""
if [ "$SKIP_SIGNING" = "1" ]; then
  echo "== skipping signing/cert (kernel-only job) =="
else
  echo "== computing signing certificate fingerprint =="
  mkdir -p "$OUT/.signing"
  cp "$KEYSTORE_ABS" "$OUT/.signing/key.jks"
  openssl pkcs12 -in "$KEYSTORE_ABS" -nokeys -passin "pass:$STOREPASS" 2>/dev/null \
    | openssl x509 -outform DER -out "$OUT/.signing/cert.der" 2>/dev/null
  CERT_SIZE_DEC="$(wc -c < "$OUT/.signing/cert.der" | tr -d ' ')"
  CERT_SIZE_HEX="$(printf '0x%x' "$CERT_SIZE_DEC")"
  CERT_HASH="$(sha256sum "$OUT/.signing/cert.der" | awk '{print $1}')"
  {
    echo "STOREPASS=$STOREPASS"
    echo "ALIAS=$ALIAS"
    echo "CERT_SIZE_HEX=$CERT_SIZE_HEX"
    echo "CERT_SIZE_DEC=$CERT_SIZE_DEC"
    echo "CERT_HASH=$CERT_HASH"
  } > "$OUT/.signing/sign.env"

  NEW_MARKER="size: $CERT_SIZE_HEX, hash: $CERT_HASH"
  for f in "${SED_CERT_FILES[@]:-}"; do
    [ -n "$f" ] || continue
    if [ -f "$OUT/$f" ] && grep -qF "$STOCK_MARKER" "$OUT/$f"; then
      # Literal find/replace via perl (no regex-special interpretation).
      STOCK="$STOCK_MARKER" NEW="$NEW_MARKER" perl -0pi -e 's/\Q$ENV{STOCK}\E/$ENV{NEW}/g' "$OUT/$f"
      echo "   cert marker swapped in $f"
    else
      echo "   (note) cert marker not found in $f — manager may not gate on it; continuing"
    fi
  done
fi

echo "== version metadata =="
COUNT="$(git -C "$OUT" rev-list --count HEAD)"
DRIVER="$(( 30000 + COUNT + DRIVER_EXTRA ))"
SHORT="$(git -C "$OUT" rev-parse --short "$SHA")"
VERSION_NAME="$(git -C "$OUT" describe --tags --always 2>/dev/null || echo "$SHORT")"
# UAPI version constant lives in one of these headers depending on backend.
UAPI="$(grep -rhoE 'KERNEL_SU_UAPI_VERSION[^0-9]*[0-9]+' \
          "$OUT/kernel/include/uapi/supercall.h" "$OUT/uapi/supercall.h" 2>/dev/null \
          | grep -oE '[0-9]+$' | head -1)"
[ -n "$UAPI" ] || UAPI="unknown"

emit() { echo "$1=$2"; [ -n "${GITHUB_OUTPUT:-}" ] && echo "$1=$2" >> "$GITHUB_OUTPUT" || true; }
echo "---- prepared $REPO@$SHORT ----"
emit upstream_sha   "$SHA"
emit upstream_short "$SHORT"
emit commit_count   "$COUNT"
emit driver_version "$DRIVER"
emit uapi_version   "$UAPI"
emit version_name   "$VERSION_NAME"
emit cert_size_hex  "$CERT_SIZE_HEX"
emit cert_size_dec  "$CERT_SIZE_DEC"
emit cert_hash      "$CERT_HASH"
