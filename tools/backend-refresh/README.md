# Samsung backend-refresh kit

Everything the daily rebuild system needs lives here (plus `patches/`,
`keystores/` and `state/` at the repo root). The orchestrator workflow
[`.github/workflows/samsung-refresh.yml`](../../.github/workflows/samsung-refresh.yml)
drives it; this folder holds the data and the small scripts it calls.

## What it does, once a day

1. **Detect.** `detect_changes.py` asks each upstream (`git ls-remote`) for its
   branch HEAD and compares it to the last commit we built (`state/<id>.json`).
2. **Mirror.** For every backend that moved, the orchestrator force-pushes that
   upstream commit to the `upstream-<id>` branch of this repo, so those branches
   always reflect the exact upstream we rebuilt from.
3. **Rebuild** (only the changed backends). The matching `build-<id>.yml`
   reusable workflow clones fresh upstream at that commit, re-applies this repo's
   Samsung patch set (`patches/<id>-samsung.patch`), swaps in the backend's own
   signing certificate, and builds the manager APK + `ksud` + kernel `.ko`
   modules exactly the way that backend's own CI does.
4. **Release.** The changed backend's rolling release is updated in place (its
   assets fully replaced, its notes re-rendered). A brand-new release is created
   only if the dedicated one does not exist yet.

If **nothing** moved, the only thing that happens is the *"Last successful
workflow run"* timestamp in each release's notes is refreshed. If **one** moved,
only that backend's release is touched; the other is left exactly as it was.

## Near-real-time rebuilds (debounced upstream watcher)

GitHub can't notify this repo about pushes to repositories we don't own, so
[`.github/workflows/upstream-watch.yml`](../../.github/workflows/upstream-watch.yml)
polls both upstream branches every 5 minutes (GitHub's minimum — it can run
later under load). It takes seconds and does nothing when nothing changed.

Debounce rule, per backend:

1. The first time the watcher sees a new upstream HEAD, it records "first seen"
   in the Actions cache, keyed by that exact commit SHA.
2. The backend is rebuilt only once that **same** HEAD has stayed unchanged for
   **10 minutes** (`DEBOUNCE_SECONDS`). A newer commit is a new SHA with a fresh
   first-seen time, so the timer starts over — a burst of commits yields **one**
   rebuild, of the final commit, after the burst goes quiet.
3. The rebuild is a normal *Samsung backend refresh* run dispatched with
   `only=<settled backends>` and `pin=<exact SHAs>`, so a backend still mid-burst
   is never built and the build can't drift to a newer commit.
4. No stacking: nothing is dispatched while a refresh run is queued or running;
   the next poll re-evaluates afterwards.
5. Each upstream SHA is dispatched **at most once** by the watcher. If that build
   fails (e.g. the patch no longer applies), it is not re-queued every poll — the
   next upstream commit, the daily run, or a manual run retries it.

The daily scheduled refresh stays as a fallback and as the "last successful run"
heartbeat. Tune the quiet period via `DEBOUNCE_SECONDS` in `upstream-watch.yml`.

## Files

| File | Role |
| --- | --- |
| `targets.json` | Source of truth: upstream repo/branch, patch, keystore, release tag, driver-version formula per backend. |
| `detect_changes.py` | Compares upstream HEAD vs `state/<id>.json`; emits `*_changed` / `*_sha` outputs. Accepts `force=`, `only=`, `pin=`. |
| `watch_decide.py` | The watcher's debounce decision (10-minute quiet period, once-per-SHA dispatch). |
| `prepare_source.sh` | Clones upstream @ commit, 3-way applies the Samsung patch, swaps the signing cert, prints version/UAPI/cert metadata. Dependency-light (git + openssl); runs inside the DDK container too (`--skip-signing`). |
| `collect_assets.sh` | Flattens a build's artifacts into clean release assets (APK, `ksud-<triple>`, `*.ko`) + `SHA256SUMS`, excluding logs/mappings. |
| `update_state.py` | Writes `state/<id>.json` — full rewrite on rebuild, timestamp-only on heartbeat. |
| `render_release_notes.py` | Renders a release's notes purely from its state file. |
| `publish_release.sh` | Updates the rolling release in place (or creates it once); replaces all assets. |

## Patch sets

`patches/<id>-samsung.patch` is the diff that makes each manager boot-safe on the
Galaxy S26 Ultra (SM-S948U1): the Samsung KDP/RKP/DEFEX late-load compat layer,
the `__nocfi` CFI fix, the kprobe-redirect SELinux hiding, and the `ksud`
late-load staging. They are applied with `git apply`, falling back to a
**conflict-free 3-way merge** against the upstream base blobs (the build uses a
full clone, so those blobs are present). A real conflict **stops the run before
anything is built** — that is the signal that upstream moved under the patch and
it needs a human refresh. To refresh a patch, re-apply it onto the new upstream
by hand, fix the conflict, and regenerate:

```bash
git -C <upstream-checkout> diff <base> <head> \
    -- . ':(exclude).github/**' ':(exclude)**/keystore/**' \
    > patches/<id>-samsung.patch
```

Keep `.github/**` and the upstream keystore out of the patch — this repo supplies
its own build workflows and signing keys.

## Signing — two different certificates, on purpose

Each backend is signed with its **own** key (`keystores/<id>.jks`). Earlier we
learned the hard way that signing both managers with the *same* certificate makes
BakaSU's dynamic-manager registration collide (a cert that already matches a
built-in key can never occupy the dynamic slot). Distinct certs avoid that, so
both managers can be installed and registered at once.

The kernel's expected-manager signature is injected at build time from the
keystore (`KSU_NEXT_MANAGER_SIZE/HASH` for KernelSU-Next, `KSU_EXPECTED_SIZE/HASH`
for BakaSU); BakaSU's manager-side `isOfficialSignature()` check is rewritten to
this cert by `prepare_source.sh --sed-cert`.

These keystores are committed with known passwords (see `targets.json`). They are
throwaway self-rooting keys, not secrets — their only job is to be *stable* so the
baked-in hash keeps matching. Rotating a keystore just needs a new `.jks` here;
the fingerprint is recomputed every build.

## Adding a backend

Drop `patches/<id>-samsung.patch` and `keystores/<id>.jks`, add an entry to
`targets.json` and a `state/<id>.json`, write a `build-<id>.yml` reusable
workflow (copy the nearest existing one), and wire a `build-<id>` + `release-<id>`
pair into `samsung-refresh.yml`.

## Caveats

- These are **automated builds, not hardware-validated by CI.** The on-device
  result is the user's responsibility.
- Re-applying a patch onto moving upstream is inherently fragile; a conflicting
  week fails loudly and waits for a human, by design.
- A manual run is available from **Actions → Samsung backend refresh → Run
  workflow**, with a `force` input (`all`, `kernelsu-next`, or `bakasu`).
