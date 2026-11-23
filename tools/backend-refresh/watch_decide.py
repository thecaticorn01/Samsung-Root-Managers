#!/usr/bin/env python3
"""
watch_decide.py — debounce decision for the upstream watcher.

Rule (per backend):
  * When the watcher first sees a new upstream HEAD, it records that moment
    (.watch/<id>.firstseen, persisted in the Actions cache keyed by the SHA).
  * A backend is "settled" once that SAME HEAD has been seen, unchanged, for at
    least DEBOUNCE_SECONDS. A newer commit means a new SHA -> a fresh first-seen
    time, i.e. the timer resets to zero.
  * A SHA that was already dispatched (.watch/<id>.dispatched) is never
    dispatched again by the watcher — so a commit whose build fails does not
    re-queue every poll. The next upstream commit (or the daily run) retries.

Usage:  watch_decide.py <backend-id> [<backend-id> ...]
Env:    DEBOUNCE_SECONDS (default 600)
        <ID>_CHANGED=true|false, <ID>_SHA=<sha>   (ID = backend id, '-'->'_', upper)
Writes GITHUB_OUTPUT:
        settled=<id>,<id>     any_settled=true|false     pin=<id>=<sha>,...
"""
import os
import sys
import time
from pathlib import Path

WATCH = Path(".watch")


def main() -> int:
    debounce = int(os.environ.get("DEBOUNCE_SECONDS", "600"))
    now = int(time.time())
    settled, pins = [], []

    for bid in sys.argv[1:]:
        env = bid.replace("-", "_").upper()
        changed = os.environ.get(f"{env}_CHANGED") == "true"
        sha = os.environ.get(f"{env}_SHA", "")
        short = sha[:9]

        if not changed:
            print(f"{bid:<14} up-to-date")
            continue

        if (WATCH / f"{bid}.dispatched").is_file():
            print(f"{bid:<14} {short} already dispatched once; waiting for a newer commit")
            continue

        fs = WATCH / f"{bid}.firstseen"
        try:
            first_seen = int(fs.read_text().strip())
        except Exception:
            first_seen = now
        age = now - first_seen

        if age >= debounce:
            print(f"{bid:<14} {short} quiet for {age}s (>= {debounce}s) -> REBUILD")
            settled.append(bid)
            pins.append(f"{bid}={sha}")
        else:
            print(f"{bid:<14} {short} first seen {age}s ago; waiting "
                  f"{debounce - age}s more (timer resets on any newer commit)")

    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as fh:
            fh.write(f"settled={','.join(settled)}\n")
            fh.write(f"pin={','.join(pins)}\n")
            fh.write(f"any_settled={'true' if settled else 'false'}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
