"""Back up and restore the coordinator's identity and evidence.

Everything that cannot be regenerated lives in one directory: the coordinator's Ed25519 signing
key, the signed per-room audit state, and the signed invitation registry. Losing the key means
every audit bundle ever exported becomes unverifiable and every issued invitation becomes
worthless, so this is an operational necessity rather than a convenience.

  uv run python admin_backup.py backup  --out backups/gba-df-2026-09-07.tar.gz
  uv run python admin_backup.py inspect backups/gba-df-2026-09-07.tar.gz
  uv run python admin_backup.py restore backups/gba-df-2026-09-07.tar.gz --state-dir /srv/gba-df

The archive contains a private key. It is written mode 0600, and restore refuses to overwrite a
populated state directory unless `--force` is given, so a restore drill cannot quietly destroy the
live coordinator's identity. Stop the coordinator before restoring.

Environment: FED_STATE_DIR, FED_INVITATION_REGISTRY (the same values the coordinator runs with).
"""
import argparse
import io
import json
import os
import tarfile
import tempfile
import time

import fed_common as fc

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST_NAME = "gba-df-backup.json"
BACKUP_FORMAT = "gba-df-coordinator-backup"
BACKUP_VERSION = 1
KEY_NAME = "coordinator_key.pem"


def _state_dir() -> str:
    return os.path.abspath(os.path.expanduser(
        os.environ.get("FED_STATE_DIR", os.path.join(HERE, "data", "coordinator_state"))))


def _registry_path(state_dir: str) -> str:
    return os.path.abspath(os.path.expanduser(os.environ.get(
        "FED_INVITATION_REGISTRY", os.path.join(state_dir, "invitations.json"))))


def _collect(state_dir: str) -> list[tuple[str, str]]:
    """Return [(archive_name, absolute_path)] for everything that must survive a host loss."""
    if not os.path.isdir(state_dir):
        raise SystemExit(f"state directory not found: {state_dir}")
    items = []
    key = os.path.join(state_dir, KEY_NAME)
    if not os.path.exists(key):
        raise SystemExit(f"coordinator key not found: {key}\n"
                         f"Start the coordinator once, or point FED_STATE_DIR at the right host.")
    items.append((KEY_NAME, key))
    for name in sorted(os.listdir(state_dir)):
        if name.startswith("audit-") and name.endswith(".json"):
            items.append((name, os.path.join(state_dir, name)))
    registry = _registry_path(state_dir)
    if os.path.exists(registry):
        items.append(("invitations.json", registry))
    return items


def cmd_backup(args):
    state_dir = _state_dir()
    items = _collect(state_dir)
    manifest = {
        "format": BACKUP_FORMAT, "version": BACKUP_VERSION,
        "created_at": round(time.time(), 3),
        "state_dir": state_dir,
        "files": {name: {"sha256": fc.sha256_hex(open(path, "rb").read()),
                         "bytes": os.path.getsize(path)}
                  for name, path in items},
    }
    out = os.path.abspath(os.path.expanduser(args.out))
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)

    fd, tmp = tempfile.mkstemp(prefix=".gba-df-backup-", suffix=".tar.gz",
                               dir=os.path.dirname(out) or ".")
    os.close(fd)
    try:
        os.chmod(tmp, 0o600)
        with tarfile.open(tmp, "w:gz") as tar:
            for name, path in items:
                tar.add(path, arcname=name)
            body = json.dumps(manifest, indent=2, sort_keys=True).encode()
            info = tarfile.TarInfo(MANIFEST_NAME)
            info.size, info.mtime, info.mode = len(body), int(manifest["created_at"]), 0o600
            tar.addfile(info, io.BytesIO(body))
        os.replace(tmp, out)
        os.chmod(out, 0o600)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise

    print(f"Wrote {out} (mode 0600)")
    for name in manifest["files"]:
        print(f"  {name}  {manifest['files'][name]['bytes']} bytes")
    print("This archive contains the coordinator PRIVATE KEY. Store it where the coordinator host's "
          "compromise would not also expose it, and never commit it.")


def _read_manifest(archive: str) -> dict:
    with tarfile.open(archive, "r:gz") as tar:
        member = tar.extractfile(MANIFEST_NAME)
        if member is None:
            raise SystemExit(f"not a GBA-DF backup (no {MANIFEST_NAME}): {archive}")
        manifest = json.loads(member.read().decode())
    if (manifest.get("format") != BACKUP_FORMAT
            or manifest.get("version") != BACKUP_VERSION
            or not isinstance(manifest.get("files"), dict)):
        raise SystemExit(f"unsupported backup format: {archive}")
    return manifest


def verify_archive(archive: str) -> dict:
    """Check every recorded file is present and matches its manifest hash. Never trusts the
    archive's own paths: only names recorded in the manifest are read."""
    manifest = _read_manifest(archive)
    problems = []
    with tarfile.open(archive, "r:gz") as tar:
        present = set(tar.getnames())
        for name, meta in manifest["files"].items():
            if name not in present:
                problems.append(f"missing from archive: {name}")
                continue
            member = tar.extractfile(name)
            digest = fc.sha256_hex(member.read()) if member else ""
            if digest != meta["sha256"]:
                problems.append(f"content hash mismatch: {name}")
    if KEY_NAME not in manifest["files"]:
        problems.append("archive contains no coordinator key")
    return {"ok": not problems, "problems": problems, "manifest": manifest}


def cmd_inspect(args):
    result = verify_archive(os.path.expanduser(args.archive))
    manifest = result["manifest"]
    created = time.strftime("%Y-%m-%d %H:%M", time.localtime(manifest["created_at"]))
    print(f"{'VALID' if result['ok'] else 'INVALID'} backup · created {created} · "
          f"from {manifest['state_dir']}")
    for name, meta in sorted(manifest["files"].items()):
        print(f"  {name:34} {meta['bytes']:>10} bytes  {meta['sha256'][:16]}…")
    for problem in result["problems"]:
        print(f"  - {problem}")
    raise SystemExit(0 if result["ok"] else 1)


def cmd_restore(args):
    archive = os.path.expanduser(args.archive)
    result = verify_archive(archive)
    if not result["ok"]:
        for problem in result["problems"]:
            print(f"- {problem}")
        raise SystemExit(f"refusing to restore a backup that does not verify: {archive}")

    target = os.path.abspath(os.path.expanduser(args.state_dir or _state_dir()))
    existing = [n for n in (os.listdir(target) if os.path.isdir(target) else [])
                if n == KEY_NAME or n.startswith("audit-") or n == "invitations.json"]
    if existing and not args.force:
        raise SystemExit(
            f"{target} already holds coordinator state ({', '.join(sorted(existing))}).\n"
            f"Restoring would replace this coordinator's identity. Stop the coordinator and "
            f"re-run with --force if that is what you intend.")

    os.makedirs(target, exist_ok=True)
    os.chmod(target, 0o700)
    manifest = result["manifest"]
    with tarfile.open(archive, "r:gz") as tar:
        for name in manifest["files"]:
            member = tar.extractfile(name)
            payload = member.read()
            path = os.path.join(target, os.path.basename(name))    # never honour archive paths
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(payload)
            os.chmod(path, 0o600)
    print(f"Restored {len(manifest['files'])} files into {target} (mode 0600)")
    print("Start the coordinator with FED_STATE_DIR pointing here, then confirm the restore by "
          "downloading /audit/bundle and running verify_audit_bundle.py on it.")


def main():
    parser = argparse.ArgumentParser(description="Back up and restore GBA-DF coordinator state")
    sub = parser.add_subparsers(dest="command", required=True)

    backup = sub.add_parser("backup", help="archive the key, signed state, and invitation registry")
    backup.add_argument("--out", required=True, help="output .tar.gz path")
    backup.set_defaults(func=cmd_backup)

    inspect = sub.add_parser("inspect", help="verify an archive without writing anything")
    inspect.add_argument("archive")
    inspect.set_defaults(func=cmd_inspect)

    restore = sub.add_parser("restore", help="restore an archive into a state directory")
    restore.add_argument("archive")
    restore.add_argument("--state-dir", help="target directory (default: FED_STATE_DIR)")
    restore.add_argument("--force", action="store_true",
                         help="replace existing coordinator state in the target directory")
    restore.set_defaults(func=cmd_restore)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
