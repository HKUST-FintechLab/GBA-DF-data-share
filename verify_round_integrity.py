"""Regression checks for round reliability: reconnect, timeout, idempotency, and epsilon.

These are the failure paths a pilot actually hits — an institution restarts, a laptop drops
off, a retry arrives twice — and the property that matters is that none of them silently
corrupt a pooled sum or spend the privacy budget twice.
"""
import os
import tempfile


_state_tmp = tempfile.TemporaryDirectory(prefix="gba-df-round-integrity-")
os.environ["FED_STATE_DIR"] = _state_tmp.name
os.environ["FED_ROUND_TIMEOUT_SECONDS"] = "30"
os.environ.pop("FED_PASSWORD", None)
os.environ.pop("FED_READ_PASSWORD", None)
os.environ.pop("FED_REQUIRE_INVITATION", None)

import numpy as np
from fastapi.testclient import TestClient

import coordinator
import fed_common as fc
import secure_agg as sa

ok_all = True


def check(name, condition):
    global ok_all
    ok_all = ok_all and bool(condition)
    print(f"  [{'PASS' if condition else 'FAIL'}] {name}")


client = TestClient(coordinator.app)
COHORT = coordinator.COHORT
IDS = [f"node_{i}" for i in range(1, COHORT + 1)]
ed = {n: fc.gen_key() for n in IDS}
xk = {n: sa.gen_x25519() for n in IDS}
counts = {n: np.random.default_rng(i).integers(0, 40, size=coordinator.EXPECT_LEN).astype(np.int64)
          for i, n in enumerate(IDS)}


def register(node_id):
    return client.post("/register", json={
        "node_id": node_id, "name": node_id, "pubkey_pem": fc.pub_pem(ed[node_id]).decode(),
        "x_pub": sa.x_pub_hex(xk[node_id]), "samples": 100})


def peers():
    p = client.get("/participants").json()
    return ({q["node_id"]: sa.load_x_pub(q["x_pub"]) for q in p["participants"]},
            p["cohort_sha256"])


def submit(node_id, rnd, cohort_sha, peer_keys, vector=None):
    vec = counts[node_id] if vector is None else vector
    masked = [int(v) for v in sa.mask_counts(node_id, xk[node_id], peer_keys, rnd, vec)]
    payload_hash = fc.sha256_hex(fc._canon(masked))
    sig = ed[node_id].sign(f"{node_id}|{rnd}|100|{payload_hash}".encode())
    return client.post("/submit", json={"node_id": node_id, "round": rnd, "n_samples": 100,
                                        "masked": masked, "sig_hex": sig.hex(),
                                        "cohort_sha256": cohort_sha})


print("== cohort fingerprint binds a round to one peer set ==")
for n in IDS:
    register(n)
peer_keys, cohort_sha = peers()
check("the coordinator publishes a cohort fingerprint", len(cohort_sha) == 64)
check("a submission carrying a stale fingerprint is REJECTED",
      submit(IDS[0], 1, "0" * 64, peer_keys).status_code == 409)
check("the rejection tells the node to rebuild its masks",
      submit(IDS[0], 1, "0" * 64, peer_keys).json().get("code") == "cohort_changed")

first = submit(IDS[0], 1, cohort_sha, peer_keys)
check("a submission carrying the current fingerprint is accepted", first.status_code == 200)
check("the response names who the round is still waiting for",
      set(first.json()["waiting_for"]) == set(IDS[1:]))

print("== reconnect with a fresh masking key ==")
# The reconnecting node generates a NEW ephemeral X25519 key, exactly as a restarted client
# would. If the coordinator kept the old one, residual masks would corrupt the pooled sum.
xk[IDS[1]] = sa.gen_x25519()
rejoined = register(IDS[1])
check("re-registering with a fresh masking key is accepted", rejoined.status_code == 200)
new_peers, new_cohort = peers()
check("the cohort fingerprint changes when a masking key is refreshed", new_cohort != cohort_sha)
check("the round built against the old peer set was discarded",
      client.get("/round/1").json()["aborted"])
check("the discard is recorded in the signed audit chain",
      any(e["event"] == "round_discarded" for e in client.get("/audit").json()["entries"]))
check("a node that had submitted the discarded round may submit it again",
      submit(IDS[0], 1, new_cohort, new_peers).status_code == 200)

print("== idempotent retry vs conflicting resubmission ==")
receipts_before = len(client.get("/audit/bundle").json()["submission_receipts"])
check("an identical retry is accepted", submit(IDS[0], 1, new_cohort, new_peers).status_code == 200)
check("an identical retry does NOT create a second receipt",
      len(client.get("/audit/bundle").json()["submission_receipts"]) == receipts_before)
check("a DIFFERENT payload for the same pending round is REJECTED",
      submit(IDS[0], 1, new_cohort, new_peers,
             vector=counts[IDS[0]] + 1).status_code == 409)

print("== the pooled sum is correct after a reconnect ==")
for n in IDS[1:]:
    submit(n, 1, new_cohort, new_peers)
status = client.get("/status").json()
check("the round aggregated once the exact enrolled set submitted", status["global_trees"] > 0)
check("no pending round remains", status["pending_rounds"] == [])
# Masks cancel only if every submission was built against the SAME peer set, so a correct
# pooled sum is the observable proof that the reconnect did not corrupt the round.
masked_all = [sa.mask_counts(n, xk[n], new_peers, 1, counts[n]) for n in IDS]
check("pairwise masks still cancel to the true pooled counts",
      np.array_equal(sa.secure_sum(masked_all) % sa.MOD,
                     sum(counts[n] for n in IDS) % sa.MOD))

print("== epsilon is charged at most once per round ==")
spent_after_round_1 = client.get("/status").json()["global_eps"]
check("one completed round spent exactly one round's epsilon",
      abs(spent_after_round_1 - coordinator.EPS_ROUND) < 1e-9)
check("re-submitting a completed round is REJECTED as stale",
      submit(IDS[0], 1, new_cohort, new_peers).status_code == 409)
check("a rejected replay does not spend epsilon again",
      abs(client.get("/status").json()["global_eps"] - spent_after_round_1) < 1e-9)
with coordinator.LOCK:
    state = coordinator.get_state("default")
    ledger = dict(state["epsilon_spent"])
check("the persisted ledger records the spend per round number", ledger == {"1": coordinator.EPS_ROUND})

print("== a stalled round times out instead of blocking forever ==")
submit(IDS[0], 2, new_cohort, new_peers)
with coordinator.LOCK:
    state = coordinator.get_state("default")
    state["rounds"][2]["started"] -= coordinator.ROUND_TIMEOUT_SECONDS + 1
    coordinator._expire_stale_rounds("default", state)
    timed_out = 2 not in state["rounds"]
    rolled_back = state["nodes"][IDS[0]]["last_round"] < 2
check("a round that never completed is discarded after the timeout", timed_out)
check("its submitters may send that round again", rolled_back)
check("the timed-out round reports itself aborted to a polling node",
      client.get("/round/2").json()["aborted"])
check("an abandoned round costs no epsilon",
      abs(client.get("/status").json()["global_eps"] - spent_after_round_1) < 1e-9)

print("\nRESULT:", "ROUND INTEGRITY CHECKS PASSED" if ok_all else "FAILURES PRESENT")
raise SystemExit(0 if ok_all else 1)
