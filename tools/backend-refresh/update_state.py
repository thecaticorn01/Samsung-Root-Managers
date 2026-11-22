#!/usr/bin/env python3
"""
update_state.py — update a backend's state/<id>.json.

Modes:
  rebuild   : merge --field values, set assets from --assets-file, and stamp
              BOTH release_updated_utc and last_run_utc to now.
  heartbeat : touch ONLY last_run_utc (everything else — version, commit, assets
              — is preserved, so the release notes keep describing the last build).

Usage:
  update_state.py --state state/<id>.json --mode rebuild \
      --field last_built_sha=... --field driver_version=... [...] \
      --assets-file assets.txt
  update_state.py --state state/<id>.json --mode heartbeat
"""
import argparse
import datetime
import json
from pathlib import Path


def now_utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True)
    ap.add_argument("--mode", choices=["rebuild", "heartbeat"], required=True)
    ap.add_argument("--field", action="append", default=[], help="key=value")
    ap.add_argument("--assets-file")
    args = ap.parse_args()

    p = Path(args.state)
    st = json.loads(p.read_text()) if p.is_file() else {}

    st["last_run_utc"] = now_utc()
    if args.mode == "rebuild":
        for kv in args.field:
            k, _, v = kv.partition("=")
            st[k] = v
        if args.assets_file and Path(args.assets_file).is_file():
            st["assets"] = [
                ln.strip()
                for ln in Path(args.assets_file).read_text().splitlines()
                if ln.strip()
            ]
        st["release_updated_utc"] = st["last_run_utc"]

    p.write_text(json.dumps(st, indent=2) + "\n")
    print(f"updated {p} (mode={args.mode})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
