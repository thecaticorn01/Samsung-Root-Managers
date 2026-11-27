#!/usr/bin/env python3
"""
watch_decide.py — debounce decision for the upstream watcher.

Rule (per backend):
  * The quiet-period clock starts at the upstream HEAD commit's own committer
    timestamp. A backend is "settled" once its HEAD commit is at least
    DEBOUNCE_SECONDS old. A newer commit becomes the new HEAD with a newer
    timestamp, i.e. the timer resets to zero.
  * Counting from the commit time (not from when we first noticed it) matters
    because GitHub runs the 5-minute schedule very irregularly (often hours
    apart). Counting from "first seen" restarted the timer on almost every poll
    and starved rebuilds; counting from the commit time rebuilds on the first
    poll after upstream has been quiet for the full period.
  * Fallback only if the commit time can't be fetched: the first time the
    watcher saw that SHA (.watch/<id>.firstseen, kept in the Actions cache).
  * A SHA that was already dispatched (.watch/<id>.dispatched) is never
    dispatched again by the watcher — so a commit whose build fails does not
    re-queue every poll. The next upstream commit (or the daily run) retries.

Usage:  watch_decide.py <backend-id> [<backend-id> ...]
Env:    DEBOUNCE_SECONDS (default 600)
        <ID>_CHANGED=true|false, <ID>_SHA=<sha>   (ID = backend id, '-'->'_', upper)
Writes GITHUB_OUTPUT:
        settled=<id>,<id>     any_settled=true|false     pin=<id>=<sha>,...
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

WATCH = Path(".watch")
TARGETS = Path(__file__).resolve().parent / "targets.json"


def commit_time(repo: str, sha: str):
    """Committer epoch of <sha> in github.com/<repo>, or None."""
    try:
        with tempfile.TemporaryDirectory() as d:
            run = lambda *a: subprocess.run(["git", "-C", d, *a], check=True,
                                            capture_output=True, text=True, timeout=120)
            run("init", "-q")
            run("fetch", "-q", "--depth=1", "--filter=blob:none", f"https://github.com/{repo}", sha)
            return int(run("log", "-1", "--format=%ct", "FETCH_HEAD").stdout.strip())
    except Exception as e:
        print(f"  (could not read commit time for {repo}@{sha[:9]}: {e})")
        return None


def main() -> int:
    debounce = int(os.environ.get("DEBOUNCE_SECONDS", "600"))
    now = int(time.time())
    settled, pins = [], []
    targets = json.loads(TARGETS.read_text())["backends"]

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

        ref = commit_time(targets[bid]["upstream_repo"], sha)
        basis = "last upstream commit"
        if ref is None:
            basis = "first seen (fallback)"
            try:
                ref = int((WATCH / f"{bid}.firstseen").read_text().strip())
            except Exception:
                ref = now
        age = max(0, now - ref)

        if age >= debounce:
            print(f"{bid:<14} {short} {basis} {age // 60}m{age % 60:02d}s ago "
                  f"(>= {debounce // 60}m quiet) -> REBUILD")
            settled.append(bid)
            pins.append(f"{bid}={sha}")
        else:
            print(f"{bid:<14} {short} {basis} {age // 60}m{age % 60:02d}s ago; "
                  f"rebuild once quiet for {debounce // 60}m (~{(debounce - age) // 60}m{(debounce - age) % 60:02d}s more; "
                  f"a newer commit restarts the timer)")

    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as fh:
            fh.write(f"settled={','.join(settled)}\n")
            fh.write(f"pin={','.join(pins)}\n")
            fh.write(f"any_settled={'true' if settled else 'false'}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
