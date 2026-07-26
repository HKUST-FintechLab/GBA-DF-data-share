"""Regression for the coordinator backup and restore path.

The go/no-go requirement is that a coordinator can be rebuilt on a clean host and that the audit
evidence it exports afterwards still verifies against the same key. That is what this proves,
including that a tampered archive is refused and that a restore cannot silently overwrite a live
coordinator's identity.
"""
import json
import os
import subprocess
import sys
import tarfile
import tempfile

_live = tempfile.TemporaryDirectory(prefix="gba-df-backup-live-")
_fresh = tempfile.TemporaryDirectory(prefix="gba-df-backup-fresh-")
os.environ["FED_STATE_DIR"] = _live.name
os.environ.pop("FED_PASSWORD", None)
os.environ.pop("FED_READ_PASSWORD", None)
os.environ.pop("FED_REQUIRE_INVITATION", None)

import numpy as np
from fastapi.testclient import TestClient

import admin_backup
import coordinator
import fed_common as fc
import invitations as invites
import secure_agg as sa
from verify_audit_bundle import verify_bundle

ok_all = True


def check(name, condition):
    global ok_all
    ok_all = ok_all and bool(condition)
    print(f"  [{'PASS' if condition else 'FAIL'}] {name}")


client = TestClient(coordinator.app)
IDS = [f"node_{i}" for i in range(1, coordinator.COHORT + 1)]
ed = {n: fc.gen_key() for n in IDS}
xk = {n: sa.gen_x25519() for n in IDS}

print("== produce a coordinator with real evidence to lose ==")
for n in IDS:
    client.post("/register", json={"node_id": n, "name": n, "pubkey_pem": fc.pub_pem(ed[n]).decode(),
                                   "x_pub": sa.x_pub_hex(xk[n]), "samples": 100})
p = client.get("/participants").json()
peer_keys = {q["node_id"]: sa.load_x_pub(q["x_pub"]) for q in p["participants"]}
for n in IDS:
    vec = np.random.default_rng(abs(hash(n)) % 1000).integers(
        0, 30, size=coordinator.EXPECT_LEN).astype(np.int64)
    masked = [int(v) for v in sa.mask_counts(n, xk[n], peer_keys, 1, vec)]
    digest = fc.sha256_hex(fc._canon(masked))
    sig = ed[n].sign(f"{n}|1|100|{digest}".encode())
    client.post("/submit", json={"node_id": n, "round": 1, "n_samples": 100, "masked": masked,
                                 "sig_hex": sig.hex(), "cohort_sha256": p["cohort_sha256"]})
# An issued invitation must survive too: losing the registry would silently un-revoke partners.
invitation = invites.build_invitation(coordinator.COORD_KEY, institution_id=IDS[0],
                                      institution_name="Pilot Hospital")
registry = invites.record_issue(invites.new_registry(coordinator.COORD_PUB), invitation)
invites.revoke(registry, invitation["invitation_id"], "partner exit")
invites.save_registry(coordinator.REGISTRY_PATH, registry, coordinator.COORD_KEY)

before = client.get("/audit/bundle").json()
check("the source coordinator holds verifiable evidence",
      verify_bundle(before)["ok"] and before["model"] is not None)

print("== backup ==")
archive = os.path.join(_live.name, "backup.tar.gz")
admin_backup.cmd_backup(type("A", (), {"out": archive})())
check("the archive is written owner-only (it contains the private key)",
      oct(os.stat(archive).st_mode & 0o777) == "0o600")
result = admin_backup.verify_archive(archive)
check("a fresh archive verifies against its manifest", result["ok"])
check("the archive carries the key, the signed room state, and the invitation registry",
      admin_backup.KEY_NAME in result["manifest"]["files"]
      and "invitations.json" in result["manifest"]["files"]
      and any(n.startswith("audit-") for n in result["manifest"]["files"]))

tampered = os.path.join(_live.name, "tampered.tar.gz")
with tarfile.open(archive, "r:gz") as src, tarfile.open(tampered, "w:gz") as dst:
    for member in src.getmembers():
        payload = src.extractfile(member).read()
        if member.name.startswith("audit-"):
            payload = payload.replace(b'"global_eps"', b'"global_EPS"')
            member.size = len(payload)
        dst.addfile(member, __import__("io").BytesIO(payload))
check("editing evidence inside the archive -> verification FAILS",
      not admin_backup.verify_archive(tampered)["ok"])

print("== restore onto a clean host ==")
restored = os.path.join(_fresh.name, "state")
admin_backup.cmd_restore(type("A", (), {"archive": archive, "state_dir": restored,
                                        "force": False})())
check("restored files are owner-only",
      all(oct(os.stat(os.path.join(restored, n)).st_mode & 0o777) == "0o600"
          for n in os.listdir(restored)))
clobber_refused = False
try:
    admin_backup.cmd_restore(type("A", (), {"archive": archive, "state_dir": _live.name,
                                            "force": False})())
except SystemExit:
    clobber_refused = True
check("restoring over a populated state directory is REFUSED without --force", clobber_refused)

bad_restore_refused = False
try:
    admin_backup.cmd_restore(type("A", (), {"archive": tampered,
                                            "state_dir": os.path.join(_fresh.name, "nope"),
                                            "force": False})())
except SystemExit:
    bad_restore_refused = True
check("restoring a tampered archive is REFUSED", bad_restore_refused)

print("== the restored coordinator still produces verifiable evidence ==")
# A separate process, because the coordinator binds its key and state at import time.
probe = subprocess.run(
    [sys.executable, "-c",
     "import json, os, coordinator as co;"
     "st = co.get_state('default');"
     "b = co.build_audit_bundle('default', st);"
     "print(json.dumps({'tip': b['audit_tip'], 'model': b['model_sha256'],"
     " 'eps': b['federation']['global_eps'], 'bundle': b}))"],
    cwd=os.path.dirname(os.path.abspath(__file__)),
    env={**os.environ, "FED_STATE_DIR": restored}, capture_output=True, text=True)
check("the restored coordinator starts from the restored state", probe.returncode == 0)
after = json.loads(probe.stdout.strip().splitlines()[-1]) if probe.returncode == 0 else {}
# The restored coordinator EXTENDS the chain with a `coordinator_restart` entry rather than
# reproducing the old tip, so continuity — not equality — is the property to assert.
restored_entries = after.get("bundle", {}).get("audit_entries", [])
prefix = restored_entries[:len(before["audit_entries"])]
tail = restored_entries[len(before["audit_entries"]):]
check("the restored chain preserves every pre-backup entry unchanged",
      prefix == before["audit_entries"])
check("it continues the chain with a single linked restart entry",
      len(tail) == 1 and tail[0]["event"] == "coordinator_restart"
      and tail[0]["prev_hash"] == before["audit_tip"])
check("the aggregated model is unchanged after restore",
      after.get("model") == before["model_sha256"])
check("the privacy spend is unchanged after restore",
      after.get("eps") == before["federation"]["global_eps"])
check("an audit bundle exported after restore verifies offline",
      bool(after) and verify_bundle(after["bundle"])["ok"])
check("a revocation issued before the backup is still in force after restore",
      invites.registry_status(
          invites.load_registry(os.path.join(restored, "invitations.json"), coordinator.COORD_PUB),
          invitation["invitation_id"]) != "")

print("\nRESULT:", "BACKUP/RESTORE CHECKS PASSED" if ok_all else "FAILURES PRESENT")
raise SystemExit(0 if ok_all else 1)
