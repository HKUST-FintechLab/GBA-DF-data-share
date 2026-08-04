"""Build an unsigned native GBA-DF desktop-client bundle with PyInstaller.

Use from the repository root:
    uv run --extra client --with pyinstaller python packaging/build_client.py --check
    uv run --extra client --with pyinstaller python packaging/build_client.py

Build only on the target operating system. Code signing and macOS notarization deliberately
remain separate owner actions; this script never accepts or reads signing credentials.
"""
import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist" / "desktop-client"
BUILD = ROOT / "build" / "desktop-client"
SOURCES = (
    ROOT / "client_app.py",
    ROOT / "node_core.py",
    ROOT / "modalities.py",
    ROOT / "public_scales.json",
    ROOT / "assets" / "cdp_adapter_v1.json",
    ROOT / "static" / "client.html",
    ROOT / "static" / "vendor" / "mediapipe" / "manifest.json",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_sources() -> None:
    missing = [str(path.relative_to(ROOT)) for path in SOURCES if not path.is_file()]
    if missing:
        raise SystemExit("missing required package input(s): " + ", ".join(missing))


def pyinstaller_version() -> str:
    try:
        return subprocess.check_output([sys.executable, "-m", "PyInstaller", "--version"],
                                       text=True).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise SystemExit("PyInstaller is required. Run via `uv run --extra client --with "
                         "pyinstaller python packaging/build_client.py`.") from error


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate inputs without building")
    parser.add_argument("--clean", action="store_true", help="remove only prior build/desktop-client output")
    args = parser.parse_args()
    validate_sources()
    host = platform.system()
    if host not in {"Darwin", "Windows"}:
        raise SystemExit("pilot packaging is supported only on native macOS or Windows hosts")
    if args.check:
        print(f"Packaging inputs are complete for {host}: {len(SOURCES)} pinned source files.")
        return
    version = pyinstaller_version()
    if args.clean:
        for path in (BUILD, DIST):
            if path.exists():
                shutil.rmtree(path)
    separator = ";" if host == "Windows" else ":"
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
           "--name", "GBA-DF Partner Client", "--distpath", str(DIST),
           "--workpath", str(BUILD), "--specpath", str(BUILD), "--hidden-import", "webview",
           "--add-data", f"{ROOT / 'static'}{separator}static",
           "--add-data", f"{ROOT / 'public_scales.json'}{separator}.",
           "--add-data", f"{ROOT / 'assets'}{separator}assets", str(ROOT / "client_app.py")]
    subprocess.run(cmd, check=True, cwd=ROOT)
    manifest = {
        "format": "gba-df-desktop-build-manifest", "version": 1,
        "platform": host, "machine": platform.machine(), "python": sys.version,
        "pyinstaller": version,
        "sources": {str(path.relative_to(ROOT)): sha256(path) for path in SOURCES},
        "unsigned": True, "auto_update": "disabled",
    }
    path = DIST / "build-manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Built unsigned desktop client at {DIST}")
    print(f"Wrote reproducibility manifest: {path}")


if __name__ == "__main__":
    main()
