#!/usr/bin/env bash
#
# publish_release.sh TAG TITLE ASSET_DIR NOTES_FILE
#
# Update the dedicated rolling release in place, or create it only if it does
# not already exist. All previous assets are removed so the release always holds
# exactly the current build's outputs (manager APK + ksud + .ko + SHA256SUMS),
# and never any stale kernel modules or CI logs.
#
# Requires: gh, with GH_TOKEN exported.
set -euo pipefail
TAG="$1"; TITLE="$2"; ASSET_DIR="$3"; NOTES="$4"

shopt -s nullglob
ASSETS=("$ASSET_DIR"/*)
if [ ${#ASSETS[@]} -eq 0 ]; then
  echo "::error::no assets in $ASSET_DIR"; exit 1
fi

if gh release view "$TAG" >/dev/null 2>&1; then
  echo "== updating existing release $TAG =="
  # Remove every current asset, then upload the fresh set.
  gh release view "$TAG" --json assets -q '.assets[].name' | while read -r name; do
    [ -n "$name" ] && gh release delete-asset "$TAG" "$name" -y || true
  done
  gh release upload "$TAG" "${ASSETS[@]}" --clobber
  gh release edit "$TAG" --title "$TITLE" --notes-file "$NOTES" --prerelease=false --latest=false
else
  echo "== creating release $TAG (first time) =="
  gh release create "$TAG" "${ASSETS[@]}" \
    --title "$TITLE" --notes-file "$NOTES" --prerelease=false --latest=false
fi
echo "done: $TAG"
