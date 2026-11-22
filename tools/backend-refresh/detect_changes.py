#!/usr/bin/env python3
"""
detect_changes.py — compare each backend's upstream HEAD against the last SHA
we built, and tell the orchestrator which backends (if any) need a rebuild.

Reads  : tools/backend-refresh/targets.json
         state/<backend>.json   (last_built_sha; missing/!exists => force build)
Queries: git ls-remote <upstream_repo> <upstream_branch>
Writes : GITHUB_OUTPUT lines  (also prints a human summary)
           <id>_changed=true|false
           <id>_sha=<full-remote-sha>
           <id>_short=<short>
           <id>_prev=<previously-built-sha-or-empty>
           any_changed=true|false
           changed_list=<space-separated backend ids>

A backend is "changed" when its remote HEAD differs from state, when it has no
state yet (first build), or when force=<id|all> is passed on the command line.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGETS = ROOT / "tools" / "backend-refresh" / "targets.json"


def ls_remote(repo: str, branch: str) -> str:
    url = f"https://github.com/{repo}"
    out = subprocess.check_output(
        ["git", "ls-remote", url, f"refs/heads/{branch}"], text=True
    ).strip()
    if not out:
        raise SystemExit(f"detect: {repo} has no branch {branch}")
    return out.split()[0]


def read_state(backend_id: str) -> str:
    p = ROOT / "state" / f"{backend_id}.json"
    if not p.is_file():
        return ""
    try:
        return json.loads(p.read_text()).get("last_built_sha", "") or ""
    except Exception:
        return ""


def main() -> int:
    force = ""
    for a in sys.argv[1:]:
        if a.startswith("force="):
            force = a.split("=", 1)[1].strip()

    targets = json.loads(TARGETS.read_text())["backends"]
    out_lines, summary, changed_ids = [], [], []

    for bid, cfg in targets.items():
        remote = ls_remote(cfg["upstream_repo"], cfg["upstream_branch"])
        prev = read_state(bid)
        forced = force in ("all", bid)
        changed = forced or (remote != prev)
        if changed:
            changed_ids.append(bid)
        key = bid.replace("-", "_")  # safe for GitHub Actions output references
        out_lines += [
            f"{key}_changed={'true' if changed else 'false'}",
            f"{key}_sha={remote}",
            f"{key}_short={remote[:9]}",
            f"{key}_prev={prev}",
        ]
        summary.append(
            f"{cfg['display_name']:<26} {cfg['upstream_repo']}@{cfg['upstream_branch']}  "
            f"remote={remote[:9]}  built={prev[:9] or '(none)'}  "
            f"-> {'REBUILD' if changed else 'up-to-date'}"
            + ("  [forced]" if forced else "")
        )

    out_lines.append(f"any_changed={'true' if changed_ids else 'false'}")
    out_lines.append(f"changed_list={' '.join(changed_ids)}")

    print("\n".join(summary))
    gh = os.environ.get("GITHUB_OUTPUT")
    if gh:
        with open(gh, "a") as fh:
            fh.write("\n".join(out_lines) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
