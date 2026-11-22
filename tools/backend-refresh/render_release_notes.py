#!/usr/bin/env python3
"""
render_release_notes.py — render a rolling release's notes from its state file.

The release notes are a pure function of state/<backend>.json, so the two update
paths stay trivial and consistent:
  * rebuild   -> workflow rewrites every field in state, then re-renders
  * heartbeat -> workflow bumps only last_run_utc in state, then re-renders
                 (assets/version/commit all stay exactly as the last build left them)

Usage:  render_release_notes.py state/<backend>.json  > notes.md
"""
import json
import sys
from pathlib import Path


def md(s: Path) -> str:
    st = json.loads(s.read_text())
    repo = st.get("upstream_repo", "")
    sha = st.get("last_built_sha", "")
    short = st.get("last_built_short") or (sha[:9] if sha else "")
    commit_url = f"https://github.com/{repo}/commit/{sha}" if (repo and sha) else ""
    commit_link = f"[`{short}`]({commit_url})" if commit_url else "(not built yet)"
    driver = st.get("driver_version", "?")
    uapi = st.get("uapi_version", "?")
    vname = st.get("version_name", "?")
    vcode = st.get("manager_version_code", driver)
    assets = st.get("assets", [])

    lines = []
    lines.append(f"# {st.get('display_name','')}")
    lines.append("")
    lines.append(
        "Rolling, continuously-rebuilt build of this manager with the Galaxy "
        "S26 Ultra (SM-S948U1) Samsung KDP/RKP/DEFEX late-load compatibility "
        "patches applied. This release is updated in place — the download links "
        "below always point at the newest build."
    )
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("| --- | --- |")
    lines.append(f"| **Manager version** | `{vname}` (code `{vcode}`) |")
    lines.append(f"| **Kernel driver / UAPI** | `{driver}` / `{uapi}` |")
    lines.append(f"| **Upstream** | `{repo}` @ {commit_link} |")
    lines.append(f"| **Signing cert** | size `{st.get('cert_size_hex','?')}`, sha256 `{st.get('cert_hash','?')}` |")
    lines.append(f"| **Release last rebuilt** | {st.get('release_updated_utc','?')} |")
    lines.append(f"| **Last successful workflow run** | {st.get('last_run_utc','?')} |")
    lines.append("")
    lines.append("### Backend summary")
    lines.append("")
    lines.append("| Backend | Driver / UAPI | Upstream commit | Manager |")
    lines.append("| --- | --- | --- | --- |")
    lines.append(f"| {st.get('display_name','')} | {driver} / {uapi} | {commit_link} | `{vname}` |")
    lines.append("")
    if assets:
        lines.append("### Assets in this release")
        lines.append("")
        for a in assets:
            lines.append(f"- `{a}`")
        lines.append("")
    lines.append("### Install (Galaxy S26 Ultra)")
    lines.append("")
    lines.append(
        "1. Download the `arm64-v8a` manager APK below and install it "
        "(uninstall any prior copy of this manager first — the signing key "
        "differs from upstream, so Android will reject an in-place update)."
    )
    lines.append(
        "2. Load the matching `android16-6.12_kernelsu.ko` late (e.g. DirtyFrag), "
        "then **fully reboot and re-load** before relying on it — a manager "
        "update alone does not replace the loaded kernel module."
    )
    lines.append("")
    lines.append("### Notes")
    lines.append("")
    lines.append(
        "- The two managers in this repository are signed with **different** "
        "certificates on purpose, so both can be registered at once without the "
        "dynamic-manager signature collision."
    )
    lines.append(
        "- These are automated builds. They are **not** hardware-validated by CI; "
        "the on-device result is your responsibility."
    )
    lines.append("")
    lines.append("_Generated automatically by the Samsung backend-refresh workflow._")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: render_release_notes.py state/<backend>.json")
    sys.stdout.write(md(Path(sys.argv[1])))
