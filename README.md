# Samsung Root Managers

Continuously-rebuilt **KernelSU Next** and **BakaSU** manager apps patched to run
on the **Samsung Galaxy S26 Ultra** (SM-S948U1 · One UI 9.5 · Android 17 ·
Knox 3.15 · kernel `6.12.69-android16-6`, 4K pages), via LKM late-load.

Each backend is tracked against its upstream and rebuilt automatically whenever
upstream changes, then published to its own rolling GitHub release.

## Releases

| Backend | Rolling release | Upstream |
| --- | --- | --- |
| KernelSU Next (Samsung) | [`kernelsu-next-samsung`](../../releases/tag/kernelsu-next-samsung) | [KernelSU-Next/KernelSU-Next@dev](https://github.com/KernelSU-Next/KernelSU-Next/tree/dev) |
| BakaSU (Samsung) | [`bakasu-samsung`](../../releases/tag/bakasu-samsung) | [Baka-SU/BakaSU@main](https://github.com/Baka-SU/BakaSU/tree/main) |

Each release always holds the **current** build's outputs:

- the manager **APK** (`arm64-v8a` is the one for the phone),
- the `ksud` **daemon** binaries (one per target triple),
- the **`.ko`** kernel modules for every supported KMI (the S26 Ultra uses
  `android16-6.12_kernelsu.ko`),
- a `SHA256SUMS`.

Logs and build-mapping files are **not** attached.

## Automatic backend updates

The [**Samsung backend refresh**](../../actions/workflows/samsung-refresh.yml)
workflow runs daily (04:36 UTC). It checks the upstream KernelSU-Next and BakaSU
commits and, when a source changes:

1. mirrors that upstream commit into the `upstream-kernelsu-next` /
   `upstream-bakasu` branch,
2. re-applies the Galaxy S26 Ultra patch set from `patches/`,
3. rebuilds that backend's manager + `ksud` + `.ko` the same way its own CI does,
   signing with that backend's **own** certificate,
4. updates **only the changed** backend's rolling release (assets + notes).

If no upstream changed, the workflow only refreshes the *"Last successful
workflow run"* timestamp in each release's notes. If only one changed, the other
release is left untouched.

Full design and maintenance notes: [`tools/backend-refresh/README.md`](tools/backend-refresh/README.md).

## Why two certificates

The two managers are signed with **different** keys on purpose. Signing both with
the same certificate makes BakaSU's *Dynamic Manager* registration collide — a
certificate that already matches a built-in manager key can never occupy the
dynamic slot — so the two managers can't both be registered at once. Distinct
certs fix that.

## Install (Galaxy S26 Ultra)

1. Download the `arm64-v8a` APK from the release you want and install it.
   Uninstall any previous copy of that manager first — these builds use a
   different signing key than the upstream app, so Android rejects an in-place
   update.
2. Late-load the matching `android16-6.12_kernelsu.ko` (e.g. with DirtyFrag),
   then **fully reboot and re-load** before relying on it. A manager update alone
   does not replace the loaded kernel module.

Both managers can be installed side by side.

## Repository layout

```
patches/                 Samsung (S26 Ultra) patch set per backend
keystores/               one signing keystore per backend (distinct certs)
state/                   last-built provenance per backend (drives release notes)
tools/backend-refresh/   detection, source-prep, release scripts + docs
.github/workflows/
  samsung-refresh.yml        daily orchestrator (detect / mirror / release)
  build-kernelsu-next.yml    reusable build for KernelSU Next
  build-bakasu.yml           reusable build for BakaSU
```

## Disclaimer

These are automated builds and are **not** hardware-validated by CI. Rooting a
Samsung device carries real bootloop/Knox risk; the on-device result is your
responsibility.
