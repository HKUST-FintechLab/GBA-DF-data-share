"""Mirror the browser pose-extraction assets locally, with pinned hashes.

Raw-video import runs MediaPipe Holistic inside the desktop client's web view. By default those
assets come from a public CDN, which a hospital network may block outright and which is, in any
case, a third party in the trust path of code that runs over participant video.

This tool mirrors the pinned release into `static/vendor/mediapipe/` and records a SHA-256 for
every file. The manifest is committed; the binaries are not. Once a manifest exists, `fetch`
verifies every download against it and refuses anything that does not match, so a later fetch
cannot silently pick up different code.

  uv run python fetch_offline_assets.py fetch     # download + pin (needs network, once)
  uv run python fetch_offline_assets.py verify    # re-hash local files against the manifest
  uv run python fetch_offline_assets.py status    # is the client running offline or from the CDN?

The client prefers the local copy whenever the manifest and files are present, and verifies the
loader's hash in the browser before executing it. With no local copy it falls back to the CDN and
says so. Whether to redistribute these assets is a licensing decision for the project owner — see
`wiki/human-critical-path.md`.
"""
import argparse
import json
import os
import urllib.error
import urllib.request

import fed_common as fc

HERE = os.path.dirname(os.path.abspath(__file__))
VENDOR_DIR = os.path.join(HERE, "static", "vendor", "mediapipe")
MANIFEST_PATH = os.path.join(VENDOR_DIR, "manifest.json")
MANIFEST_FORMAT = "gba-df-offline-assets"
MANIFEST_VERSION = 1

# Pinned to the exact release the client requests. Changing this is a deliberate upgrade: it
# invalidates every hash in the manifest, so re-pin and re-review rather than editing in place.
HOLISTIC_VERSION = "0.5.1675471629"
CDN_BASE = f"https://cdn.jsdelivr.net/npm/@mediapipe/holistic@{HOLISTIC_VERSION}"

# Everything Holistic requests at runtime. `holistic.js` is the loader; the rest are fetched
# through its locateFile hook. The lite/heavy pose variants are included so a deployment can
# switch modelComplexity without needing the network again.
ASSETS = [
    "holistic.js",
    "holistic.binarypb",
    "holistic_solution_packed_assets.data",
    "holistic_solution_packed_assets_loader.js",
    "holistic_solution_simd_wasm_bin.data",
    "holistic_solution_simd_wasm_bin.js",
    "holistic_solution_simd_wasm_bin.wasm",
    "holistic_solution_wasm_bin.js",
    "holistic_solution_wasm_bin.wasm",
    "pose_landmark_full.tflite",
    "pose_landmark_lite.tflite",
    "pose_landmark_heavy.tflite",
]
MAX_ASSET_BYTES = 64 * 1024 * 1024


def load_manifest() -> dict:
    if not os.path.exists(MANIFEST_PATH):
        return {}
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        manifest = json.load(f)
    if (manifest.get("format") != MANIFEST_FORMAT
            or manifest.get("version") != MANIFEST_VERSION
            or not isinstance(manifest.get("files"), dict)):
        raise SystemExit(f"unsupported asset manifest: {MANIFEST_PATH}")
    return manifest


def _download(name: str) -> bytes:
    url = f"{CDN_BASE}/{name}"
    request = urllib.request.Request(url, headers={"User-Agent": "gba-df-offline-assets"})
    with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310 (pinned https)
        payload = response.read(MAX_ASSET_BYTES + 1)
    if len(payload) > MAX_ASSET_BYTES:
        raise SystemExit(f"{name} exceeds the {MAX_ASSET_BYTES} byte limit")
    return payload


def cmd_fetch(args):
    if not CDN_BASE.startswith("https://"):
        raise SystemExit("assets must be fetched over https")
    pinned = load_manifest().get("files", {}) if not args.repin else {}
    if pinned:
        print(f"Verifying downloads against the committed manifest ({len(pinned)} pinned files).")
    else:
        print("No pinned manifest — recording hashes from this download. Commit the manifest, and "
              "review it as you would any dependency pin.")

    os.makedirs(VENDOR_DIR, exist_ok=True)
    files, changed = {}, 0
    for name in ASSETS:
        payload = _download(name)
        digest = fc.sha256_hex(payload)
        expected = pinned.get(name, {}).get("sha256")
        if expected and digest != expected:
            raise SystemExit(
                f"{name}: downloaded content does not match the pinned hash.\n"
                f"  expected {expected}\n  got      {digest}\n"
                f"Do not use this download. Re-pin deliberately with --repin only after review.")
        path = os.path.join(VENDOR_DIR, name)
        previous = open(path, "rb").read() if os.path.exists(path) else None
        if previous != payload:
            with open(path, "wb") as f:
                f.write(payload)
            changed += 1
        files[name] = {"sha256": digest, "bytes": len(payload)}
        print(f"  {name:44} {len(payload):>10} bytes  {digest[:16]}…")

    manifest = {"format": MANIFEST_FORMAT, "version": MANIFEST_VERSION,
                "package": "@mediapipe/holistic", "package_version": HOLISTIC_VERSION,
                "source": CDN_BASE, "files": files}
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        f.write("\n")
    total = sum(v["bytes"] for v in files.values())
    print(f"\n{len(files)} assets ({total / 1048576:.1f} MiB), {changed} written, "
          f"manifest at {MANIFEST_PATH}")
    print("The client will now load MediaPipe from this directory instead of the CDN.")


def verify_local() -> dict:
    """Re-hash the mirrored files against the manifest. Returns a report; never raises."""
    try:
        manifest = load_manifest()
    except SystemExit as e:
        return {"ok": False, "present": False, "problems": [str(e)], "files": 0}
    if not manifest:
        return {"ok": False, "present": False,
                "problems": ["no local assets: the client will use the public CDN"], "files": 0}
    problems = []
    for name, meta in manifest["files"].items():
        path = os.path.join(VENDOR_DIR, name)
        if not os.path.exists(path):
            problems.append(f"missing: {name}")
            continue
        with open(path, "rb") as f:
            if fc.sha256_hex(f.read()) != meta["sha256"]:
                problems.append(f"hash mismatch: {name}")
    return {"ok": not problems, "present": True, "problems": problems,
            "files": len(manifest["files"]), "version": manifest.get("package_version")}


def cmd_verify(args):
    report = verify_local()
    for problem in report["problems"]:
        print(f"- {problem}")
    if report["ok"]:
        print(f"VALID offline assets · {report['files']} files · "
              f"@mediapipe/holistic {report['version']}")
    raise SystemExit(0 if report["ok"] else 1)


def cmd_status(args):
    report = verify_local()
    if report["ok"]:
        print(f"OFFLINE: the client loads MediaPipe from static/vendor/mediapipe "
              f"({report['files']} pinned files, verified).")
    elif report["present"]:
        print("BROKEN: local assets exist but do not match the manifest. The client refuses them "
              "and falls back to the CDN. Re-run `fetch`.")
        for problem in report["problems"]:
            print(f"  - {problem}")
    else:
        print(f"CDN: no local assets, so raw-video import needs access to {CDN_BASE}.")
        print("Run `fetch_offline_assets.py fetch` on a machine with network access, or disable "
              "raw-video import for the pilot.")


def main():
    parser = argparse.ArgumentParser(description="Mirror and pin the browser MediaPipe assets")
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("fetch", help="download the pinned assets and write the manifest")
    fetch.add_argument("--repin", action="store_true",
                       help="accept new hashes for an intentional version change")
    fetch.set_defaults(func=cmd_fetch)

    sub.add_parser("verify", help="re-hash local assets against the manifest").set_defaults(
        func=cmd_verify)
    sub.add_parser("status", help="report whether the client runs offline or from the CDN"
                   ).set_defaults(func=cmd_status)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
