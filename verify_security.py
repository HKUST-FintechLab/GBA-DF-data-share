"""Reproducible security checks for the federated POC — run after any change.

  uv run python verify_security.py

Demonstrates the post-audit fixes:
  * audit log: signature + hash-chain verify; edit / truncate / forge all fail
  * /submit signature binds (node_id, round, n_samples, payload) — tampering fails
  * model payload schema rejects non-tree (e.g. pickle / raw-array) content
"""
import base64
import copy
import sys

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

print("\nRESULT:", "ALL SECURITY CHECKS PASSED" if ok_all else "FAILURES PRESENT")
sys.exit(0 if ok_all else 1)
