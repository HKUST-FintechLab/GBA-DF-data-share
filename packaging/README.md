# Pilot desktop-client packaging

This is the repeatable, unsigned build procedure for the GBA-DF partner client. It produces a
native bundle so pilot users do not need a Python environment. It does **not** sign, notarize,
upload, auto-update, or distribute the client.

## Frozen pilot policy

- Target only native **Windows 11 22H2+ x64** and **macOS 13+** (arm64 or x64) pilot machines.
- The pilot has **no auto-update channel**. Replacements are manually distributed, signed and recorded
  by the operational owner after validation.
- Build on the target OS; do not cross-compile a macOS `.app` or Windows executable.
- The output is unsigned by design. Apple Developer ID signing/notarization and Windows organisational
  code signing require owner-held credentials and occur after the hash manifest is reviewed.

## Build

From the repository root on the target OS:

```bash
uv sync --extra client
uv run --extra client --with pyinstaller python packaging/build_client.py --check
uv run --extra client --with pyinstaller python packaging/build_client.py --clean
```

The bundle and `build-manifest.json` appear under `dist/desktop-client/`. The manifest records the
host platform, PyInstaller version and SHA-256 for every packaged source input. Archive that manifest
with the installer candidate; it is build provenance, not a code-signing substitute.

## Owner gate before a pilot install

1. Review the manifest and run `uv run python client_app.py --selftest` from the matching source.
2. Sign/notarize using the organisation's Apple Developer ID and Windows certificate.
3. Install the signed artifact on each actual pilot machine and run the E2E checklist: launch, import
   invitation, verify coordinator pinning, offline MediaPipe policy, local extraction, and a monitored
   three-node staging round.
4. Record artifact hash, signing identity, operating-system version, WebView2 availability (Windows),
   installation operator and rollback location in the deployment record.

Unsigned output is for internal packaging validation only; institutional pilot machines should receive
the owner-approved signed artifact.
