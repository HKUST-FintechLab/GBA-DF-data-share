"""Regression checks for the explicitly shared, one-node coordinator mode."""
import os
import tempfile


_state_tmp = tempfile.TemporaryDirectory(prefix="gba-df-solo-shared-")
os.environ["FED_STATE_DIR"] = _state_tmp.name
os.environ["FED_COHORT"] = "1"
os.environ["FED_SOLO_SHARED"] = "1"
os.environ.pop("FED_PASSWORD", None)
os.environ.pop("FED_READ_PASSWORD", None)
os.environ.pop("FED_REQUIRE_INVITATION", None)

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
node_key = fc.gen_key()
x_key = sa.gen_x25519()
node_id = "solo_node"
samples = 12

print("== explicitly shared one-node room ==")
check("the mode disables per-guest room isolation",
      coordinator.COHORT == 1 and coordinator.SOLO_SHARED and not coordinator.ISOLATE)

enrol = client.post("/register", json={
    "node_id": node_id, "name": "Shared solo node",
    "pubkey_pem": fc.pub_pem(node_key).decode(), "x_pub": sa.x_pub_hex(x_key),
    "samples": samples,
})
check("a single node enrols into the shared room", enrol.status_code == 200)
participants = client.get("/participants").json()
fingerprint = participants["cohort_sha256"]
masked = [0] * coordinator.EXPECT_LEN
payload_hash = fc.sha256_hex(fc._canon(masked))
signature = node_key.sign(f"{node_id}|1|{samples}|{payload_hash}".encode())
submitted = client.post("/submit", json={
    "node_id": node_id, "round": 1, "n_samples": samples, "masked": masked,
    "sig_hex": signature.hex(), "cohort_sha256": fingerprint,
})
check("the one-node contribution aggregates immediately", submitted.status_code == 200)

status = client.get("/status").json()
check("ordinary dashboard status contains the shared node and model",
      not status["isolated"] and status["solo_shared"]
      and status["nodes"][0]["node_id"] == node_id and status["global_trees"] > 0)
check("status labels cohort-1 as central DP rather than secure aggregation",
      status["privacy_mode"] == "central_dp_solo" and not status["secure_aggregation"]
      and "central-DP" in status["transmission_label"])
diagnostics = status.get("latest_metrics") or {}
check("dashboard receives binary diagnostics and compact ROC points",
      diagnostics.get("positive_class") == "ASD"
      and {"sensitivity", "specificity", "f1", "mcc", "brier", "ece",
           "confusion", "roc"}.issubset(diagnostics)
      and len(diagnostics["roc"]["fpr"]) <= 32)
check("a caller's session header does not hide the shared model",
      client.get("/status", headers={"X-Fed-Session": "another-browser"}).json()["global_trees"]
      == status["global_trees"])
check("the normal model endpoint downloads the one-node model",
      client.get("/model").status_code == 200)

print("\nRESULT:", "SOLO SHARED CHECKS PASSED" if ok_all else "FAILURES PRESENT")
raise SystemExit(0 if ok_all else 1)
