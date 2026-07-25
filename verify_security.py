"""Reproducible security checks for the federated POC — run after any change.

  uv run python verify_security.py

Demonstrates the post-audit fixes:
  * audit log: signature + hash-chain verify; edit / truncate / forge all fail
  * /submit signature binds (node_id, round, n_samples, payload) — tampering fails
  * model payload schema rejects non-tree (e.g. pickle / raw-array) content
"""
import base64
import copy
import json
import os
import subprocess
import sys
import tempfile

import numpy as np
from sklearn.ensemble import ExtraTreesClassifier

import fed_common as fc

ok_all = True
def check(name, cond):
    global ok_all
    ok_all = ok_all and cond
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")


print("== Audit log: tamper-evidence ==")
ck = fc.gen_key(); pub = ck.public_key()
au = fc.Audit(ck)
for i in range(5):
    au.append("submit", f"node_{i%2+1}", {"round": i, "trees": 40}, ts=float(i))
check("clean log verifies (chain + signatures)", au.verify(pub, expected_len=5))

edited = fc.Audit(ck); edited.entries = copy.deepcopy(au.entries)
edited.entries[2]["detail"] = {"round": 99, "trees": 999}
check("editing one entry -> verify FAILS", not edited.verify(pub, expected_len=5))

trunc = fc.Audit(ck); trunc.entries = copy.deepcopy(au.entries)[:-1]
check("dropping the tail (committed len) -> verify FAILS", not trunc.verify(pub, expected_len=5))

# attacker re-signs a forged log with their OWN key -> fails against the pinned pubkey
atk = fc.gen_key()
forged = fc.Audit(atk); forged.entries = copy.deepcopy(au.entries)
forged.entries[2]["detail"] = {"round": 99}
for e in forged.entries:
    body = {k: e[k] for k in fc.Audit._FIELDS}
    e["hash"] = fc.sha256_hex(fc._canon(body))
    e["sig"] = base64.b64encode(atk.sign(e["hash"].encode())).decode()
# relink prev_hash so the chain is internally consistent, then re-sign
prev = "0" * 64
for e in forged.entries:
    e["prev_hash"] = prev
    body = {k: e[k] for k in fc.Audit._FIELDS}
    e["hash"] = fc.sha256_hex(fc._canon(body)); prev = e["hash"]
    e["sig"] = base64.b64encode(atk.sign(e["hash"].encode())).decode()
check("forged+re-signed log (wrong key) -> verify FAILS vs pinned pubkey", not forged.verify(pub))

print("== exportable audit evidence bundle ==")
from verify_audit_bundle import verify_bundle
node_key = fc.gen_key(); node_id = "hospital_a"; rnd = 1; n_samples = 42
payload_hash = fc.sha256_hex(fc._canon([11, 22, 33]))
node_sig = node_key.sign(f"{node_id}|{rnd}|{n_samples}|{payload_hash}".encode())
bundle_audit = fc.Audit(ck)
bundle_audit.append("genesis", "coordinator", {"dataset": "test"}, ts=1.0)
bundle_audit.append("register", node_id, {"name": "Hospital A", "samples": n_samples}, ts=2.0)
bundle_audit.append("submit", node_id,
                    {"round": rnd, "n_samples": n_samples, "masked_cells": 3},
                    payload_sha256=payload_hash, ts=3.0)
bundle_body = {
    "format": "gba-df-audit-bundle", "version": 1, "generated_at": 4.0,
    "room": "test", "federation": {},
    "coordinator_public_key_pem": fc.pub_pem(ck).decode(),
    "participants": {node_id: {"pubkey_pem": fc.pub_pem(node_key).decode(),
                                "name": "Hospital A", "samples": n_samples}},
    "submission_receipts": [{"node_id": node_id, "round": rnd,
                              "n_samples": n_samples, "payload_sha256": payload_hash,
                              "sig_hex": node_sig.hex(), "ts": 3.0}],
    "audit_count": len(bundle_audit.entries), "audit_tip": bundle_audit.entries[-1]["hash"],
    "audit_entries": bundle_audit.entries, "model": None, "model_sha256": None,
}
bundle_hash = fc.sha256_hex(fc._canon(bundle_body))
bundle = {**bundle_body, "bundle_sha256": bundle_hash,
          "bundle_signature": base64.b64encode(ck.sign(bundle_hash.encode())).decode()}
check("self-contained bundle verifies offline", verify_bundle(bundle)["ok"])
tampered_bundle = copy.deepcopy(bundle); tampered_bundle["submission_receipts"][0]["n_samples"] = 999
check("editing an exported node receipt -> bundle verification FAILS",
      not verify_bundle(tampered_bundle)["ok"])

print("== /submit signature binding ==")
nk = fc.gen_key(); npub = nk.public_key()
msg = b"node_1|3|2577|" + b"a" * 64
sig = nk.sign(msg)
check("valid (node,round,n_samples,payload) signature verifies", fc.verify_sig(npub, sig, msg))
check("flipping n_samples in the message -> signature FAILS",
      not fc.verify_sig(npub, sig, b"node_1|3|999999999|" + b"a" * 64))

print("== model payload schema (no pickle / no raw arrays / bounds-safe) ==")
X = np.random.RandomState(0).rand(60, 8); y = np.array(["A"] * 30 + ["B"] * 30)
clf = ExtraTreesClassifier(n_estimators=4, min_samples_leaf=5, random_state=0).fit(X, y)
fwd = fc.serialize_forest(clf)
check("legit forest passes validate_forest", fc.validate_forest(fwd, ["A", "B"], 8) == "")
check("dict with a raw 'X' array is REJECTED",
      fc.validate_forest({"classes": ["A", "B"], "trees": [], "X": [[1, 2]]}, ["A", "B"], 8) != "")
check("pickle-style/opaque payload is REJECTED",
      fc.validate_forest("gANjc2tsZWFybg==", ["A", "B"], 8) != "")
bad_idx = {"classes": ["A", "B"], "trees": [{"cl": [999], "cr": [-1], "f": [0], "t": [0.5], "v": [[1.0, 0.0]]}]}
check("out-of-range child index REJECTED (no server crash possible)",
      fc.validate_forest(bad_idx, ["A", "B"], 8) != "")
check("type-malformed payload returns a reason (does NOT throw)",
      fc.validate_forest({"classes": ["A", "B"], "trees": ["x"]}, ["A", "B"], 8) != "")
jf = fc.JsonForest(fwd)
check("rebuilt JsonForest predicts (pure numpy, no sklearn/pickle)",
      jf.predict_proba(X).shape == (60, 2))

print("== differential privacy (central-DP: curator adds the noise) ==")
import dp as dpmod
bnds = np.tile([-1.0, 1.0], (8, 1)).astype(float)              # PUBLIC bounds (not data-derived)
cfA = dpmod.build_dp_counts(X, y, ["A", "B"], bnds, 3, 5, seed=7)
# same seed+bounds but REVERSED data -> identical tree structure (splits never see data values)
cfB = dpmod.build_dp_counts(X[::-1].copy(), y[::-1].copy(), ["A", "B"], bnds, 3, 5, seed=7)
same_struct = all(cfA["trees"][i]["f"] == cfB["trees"][i]["f"] and cfA["trees"][i]["t"] == cfB["trees"][i]["t"]
                  and cfA["trees"][i]["cl"] == cfB["trees"][i]["cl"] for i in range(3))
check("DP tree STRUCTURE is data-independent (splits from PUBLIC bounds only)", same_struct)
check("node ships INTEGER leaf counts (no noise applied node-side)",
      all(all(isinstance(x, int) for row in t["n"] for x in row) for t in cfA["trees"]))
fLo = dpmod.add_dp_noise(cfA, 0.3, np.random.default_rng(1))
fHi = dpmod.add_dp_noise(cfA, 5.0, np.random.default_rng(1))
check("curator Laplace noise scales with epsilon (ε=0.3 ≠ ε=5)",
      any(fLo["trees"][i]["v"] != fHi["trees"][i]["v"] for i in range(3)))
bad = {"classes": ["A", "B"], "trees": [{"cl": [-1], "cr": [-1], "f": [-2], "t": [-2.0], "n": [[0.5, 0.5]]}]}
check("count schema rejects non-integer (proba/float) leaf payloads",
      fc.validate_count_forest(cfA, ["A", "B"], 8) == "" and fc.validate_count_forest(bad, ["A", "B"], 8) != "")

print("== secure aggregation ==")
import secure_agg as sa
ids = ["node_1", "node_2", "node_3"]
privs = {i: sa.gen_x25519() for i in ids}
pubs = {i: sa.load_x_pub(sa.x_pub_hex(privs[i])) for i in ids}
rv = np.random.default_rng(0)
vecs = {i: rv.integers(0, 5000, size=40).astype(np.int64) for i in ids}
masked = [sa.mask_counts(i, privs[i], pubs, 2, vecs[i]) for i in ids]
plain = sum(vecs[i] for i in ids) % sa.MOD
check("secure sum recovers the true total (pairwise masks cancel)",
      np.array_equal(sa.secure_sum(masked) % sa.MOD, plain))
check("an individual masked vector reveals nothing (≠ true counts)",
      not np.array_equal(masked[0] % sa.MOD, vecs["node_1"] % sa.MOD))
check("a missing node corrupts the sum (full cohort required)",
      not np.array_equal(sa.secure_sum(masked[:2]) % sa.MOD, (vecs["node_1"] + vecs["node_2"]) % sa.MOD))

print("== multi-modal front end (public, participant-independent normalization) ==")
import modalities as mods
for key in ("eyegaze", "action", "neuro"):
    m = mods.get(key)
    # extract two DIFFERENT synthetic partner folders through the SAME public scale
    with tempfile.TemporaryDirectory() as da, tempfile.TemporaryDirectory() as db:
        m.synth_folder(da, 8, seed=11); m.synth_folder(db, 8, seed=22)
        Xa, _, _ = m.extract_folder(da)
        Xb, _, _ = m.extract_folder(db)
    in_bounds = (Xa.min() >= -1 - 1e-6 and Xa.max() <= 1 + 1e-6
                 and Xb.min() >= -1 - 1e-6 and Xb.max() <= 1 + 1e-6)
    check(f"{key}: features land in the PUBLIC [-1,1] DP bounds", in_bounds)
    # the normalization scale is a fixed shipped constant -> same raw always maps the same way,
    # regardless of what other participants' data looks like (data-independent public transform)
    raw = np.array([m.scale * 0.5])           # a fixed raw point
    map1 = m.normalize(raw); map2 = m.normalize(raw)
    check(f"{key}: normalization is a fixed public function (scale is a shipped constant)",
          np.allclose(map1, map2) and np.allclose(map1, np.tanh(0.5)))

print("== institution invitations (identity, expiry, revocation) ==")
import time

import invitations as iv
admin = fc.gen_key(); admin_pub = admin.public_key()
invite = iv.build_invitation(admin, institution_id="node_1", institution_name="Hospital A")
check("a freshly issued invitation verifies for its own institution",
      iv.verify_invitation(invite, admin_pub, expected_institution="node_1",
                           require_role="contributor") == "")
check("presenting it as a different institution is REJECTED",
      iv.verify_invitation(invite, admin_pub, expected_institution="node_2") != "")
edited = copy.deepcopy(invite); edited["institution_name"] = "Attacker General"
check("editing an invitation field -> signature verification FAILS",
      iv.verify_invitation(edited, admin_pub) != "")
check("an invitation signed by another key is REJECTED (coordinator key is pinned)",
      iv.verify_invitation(invite, fc.gen_key().public_key()) != "")
stale = iv.build_invitation(admin, institution_id="node_1", institution_name="Hospital A",
                            lifetime_seconds=3600.0, issued_at=time.time() - 7200.0)
check("an expired invitation is REJECTED", iv.verify_invitation(stale, admin_pub) != "")
check("malformed invitations return a reason (do NOT throw)",
      iv.verify_invitation("gANjc2tsZWFybg==", admin_pub) != ""
      and iv.verify_invitation({"format": "gba-df-invitation"}, admin_pub) != "")

with tempfile.TemporaryDirectory() as reg_dir:
    reg_path = os.path.join(reg_dir, "invitations.json")
    registry = iv.record_issue(iv.new_registry(admin_pub), invite)
    iv.save_registry(reg_path, registry, admin)
    check("the registry file is written owner-only (0600)",
          oct(os.stat(reg_path).st_mode & 0o777) == "0o600")
    check("an issued invitation is admitted by the signed registry",
          iv.registry_status(iv.load_registry(reg_path, admin_pub),
                             invite["invitation_id"]) == "")
    check("an invitation absent from the registry is REJECTED",
          iv.registry_status(iv.load_registry(reg_path, admin_pub), "0" * 32) != "")
    iv.revoke(registry, invite["invitation_id"], "partner exit")
    iv.save_registry(reg_path, registry, admin)
    check("a revoked invitation is REJECTED on the next check (no restart needed)",
          iv.registry_status(iv.load_registry(reg_path, admin_pub),
                             invite["invitation_id"]) != "")
    with open(reg_path, encoding="utf-8") as f:
        forged = json.load(f)
    forged["invitations"][invite["invitation_id"]]["revoked_at"] = None
    with open(reg_path, "w", encoding="utf-8") as f:
        json.dump(forged, f)
    try:
        iv.load_registry(reg_path, admin_pub)
        tampered_registry_rejected = False
    except RuntimeError:
        tampered_registry_rejected = True
    check("un-revoking by editing the registry file -> load FAILS CLOSED",
          tampered_registry_rejected)

print("== coordinator API boundary ==")
api_check = subprocess.run(
    [sys.executable, os.path.join(os.path.dirname(__file__), "verify_api_security.py")],
    check=False,
)
check("coordinator endpoint authentication, size limits, and rate limiting",
      api_check.returncode == 0)

print("== round integrity under failure ==")
round_check = subprocess.run(
    [sys.executable, os.path.join(os.path.dirname(__file__), "verify_round_integrity.py")],
    check=False,
)
check("reconnect, cohort binding, idempotency, timeout, and single-spend epsilon",
      round_check.returncode == 0)

print("\nRESULT:", "ALL SECURITY CHECKS PASSED" if ok_all else "FAILURES PRESENT")
sys.exit(0 if ok_all else 1)
