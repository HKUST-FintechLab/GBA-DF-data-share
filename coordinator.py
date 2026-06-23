"""GBA-DF federated coordinator (hardened after adversarial audit).

Holds ONLY: a held-out test set, node public keys, the global model (accumulated
JsonForests), and a signature-verified hash-chained audit log. Submissions carry
a constrained JSON tree schema (no pickle) — raw feature/label arrays cannot be
expressed in the accepted schema and are rejected.

  uv run uvicorn coordinator:app --host 127.0.0.1 --port 8055
Default bind is localhost; expose deliberately (and add TLS) for cross-site use.
"""
import json
import os
import threading
import time

import numpy as np
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse

import dp
import fed_common as fc

HERE = os.path.dirname(os.path.abspath(__file__))

_test = np.load(os.path.join(HERE, "data", "test.npz"))
X_TEST, Y_TEST = _test["X"], _test["y"].astype(str)
with open(os.path.join(HERE, "data", "meta.json")) as f:
    META = json.load(f)
CENTRAL = META["centralized"]                 # matched DP reference
CEILING = META.get("centralized_nonprivate", {})
CLASSES = [str(c) for c in META["classes"]]
PRIMARY = META["primary_metric"]
DATASET = META["dataset"]
FEATURE_BOUNDS = META.get("feature_bounds", [])
DP = META.get("dp", {"epsilon_per_round": 1.0, "depth": 9, "trees_per_round": 20, "budget": 10.0})
BUDGET = float(DP.get("budget", 10.0))         # per-node cumulative epsilon cap
EPS_ROUND = float(DP.get("epsilon_per_round", 1.0))  # epsilon the CURATOR spends per round (enforced)

COORD_KEY = fc.gen_key()                      # signs every audit entry
COORD_PUB = COORD_KEY.public_key()

LOCK = threading.Lock()
STATE = {
    "nodes": {},                              # node_id -> {pubkey, name, samples, last_round, model_bytes}
    "model": fc.GlobalModel(CLASSES),
    "audit": fc.Audit(COORD_KEY),
    "metrics": [],
    "model_bytes_received": 0,
    "rejected_payloads": 0,                   # off-schema / bad-signature submissions
    "started": time.time(),
}
STATE["audit"].append("genesis", "coordinator",
                      {"dataset": DATASET, "test_windows": int(len(Y_TEST)),
                       f"centralized_{PRIMARY}": round(CENTRAL[PRIMARY], 4)}, ts=time.time())

app = FastAPI(title="GBA-DF Federated Coordinator")


@app.get("/")
async def dashboard():
    return FileResponse(os.path.join(HERE, "static", "dashboard.html"))


@app.get("/pubkey")
async def pubkey():
    # publish out-of-band so a third party can verify the audit log signatures
    return PlainTextResponse(fc.pub_pem(COORD_KEY).decode())


@app.get("/schema")
async def schema():
    # PUBLIC federation schema a node needs to build DP-compatible updates
    return {"classes": CLASSES, "feature_bounds": FEATURE_BOUNDS, "n_features": int(X_TEST.shape[1]),
            "primary_metric": PRIMARY, "dp": DP, "epsilon_budget": BUDGET}


@app.post("/register")
async def register(req: Request):
    try:
        b = await req.json()
        node_id, pub, name = b["node_id"], b["pubkey_pem"], b.get("name", b["node_id"])
        samples = int(b.get("samples", 0))
    except Exception:
        return JSONResponse({"ok": False, "error": "bad request"}, status_code=422)
    if samples <= 0:        # enrolled count is the authoritative merge weight -> must be real
        return JSONResponse({"ok": False, "error": "samples must be > 0"}, status_code=422)
    with LOCK:
        cur = STATE["nodes"].get(node_id)
        if cur and cur["pubkey"] != pub:        # TOFU: cannot rebind an existing id to a new key
            STATE["audit"].append("rejected", node_id, {"reason": "pubkey rebind"}, ts=time.time())
            return JSONResponse({"ok": False, "error": "node_id already enrolled with another key"},
                                status_code=409)
        if not cur:
            STATE["nodes"][node_id] = {"pubkey": pub, "name": name, "samples": samples,
                                       "last_round": 0, "model_bytes": 0, "eps_spent": 0.0}
            STATE["audit"].append("register", node_id, {"name": name, "samples": samples},
                                  ts=time.time())
    return {"ok": True, "node_id": node_id}


@app.post("/submit")
async def submit(req: Request):
    try:
        b = await req.json()
        node_id = b["node_id"]; rnd = int(b["round"]); n_samples = int(b["n_samples"])
        update = b["update"]; sig = bytes.fromhex(b["sig_hex"])
    except Exception:
        return JSONResponse({"ok": False, "error": "bad request"}, status_code=422)
    eps = EPS_ROUND      # epsilon is set + spent by the curator, NOT declared by the node

    with LOCK:
        node = STATE["nodes"].get(node_id)
        if node is None:
            return JSONResponse({"ok": False, "error": "unregistered node"}, status_code=403)
        if rnd <= node["last_round"]:                       # replay / stale round
            STATE["rejected_payloads"] += 1
            STATE["audit"].append("rejected", node_id, {"round": rnd, "reason": "replay/stale"},
                                  ts=time.time())
            return JSONResponse({"ok": False, "error": "stale or replayed round"}, status_code=409)

        payload_hash = fc.sha256_hex(fc._canon(update))     # signature binds payload + round + n_samples
        message = f"{node_id}|{rnd}|{n_samples}|{payload_hash}".encode()
        if not fc.verify_sig(fc.load_pub(node["pubkey"].encode()), sig, message):
            STATE["rejected_payloads"] += 1
            STATE["audit"].append("rejected", node_id, {"round": rnd, "reason": "bad signature"},
                                  ts=time.time())
            return JSONResponse({"ok": False, "error": "signature verification failed"}, status_code=401)

        if node["eps_spent"] + eps > BUDGET + 1e-9:         # per-node DP budget ledger
            STATE["rejected_payloads"] += 1
            STATE["audit"].append("rejected", node_id,
                                  {"round": rnd, "reason": "epsilon budget exceeded",
                                   "eps_spent": round(node["eps_spent"], 4), "eps_req": eps}, ts=time.time())
            return JSONResponse({"ok": False, "error": f"epsilon budget exceeded "
                                 f"({node['eps_spent']:.2f}+{eps:.2f} > {BUDGET})"}, status_code=429)

        # integer-count tree schema with in-range indices — never raw data, never a crashing forest
        reason = fc.validate_count_forest(update, CLASSES, X_TEST.shape[1])
        if reason:
            STATE["rejected_payloads"] += 1
            STATE["audit"].append("rejected", node_id, {"round": rnd, "reason": reason}, ts=time.time())
            return JSONResponse({"ok": False, "error": f"invalid model payload: {reason}"}, status_code=400)

        noised = dp.add_dp_noise(update, eps)                 # CURATOR adds the calibrated DP noise
        jf = fc.JsonForest(noised)
        weight = float(node["samples"])                       # authoritative: enrolled count, NOT the wire
        STATE["model"].add(jf, weight, node_id, rnd)
        try:
            m = STATE["model"].evaluate(X_TEST, Y_TEST)
        except Exception as exc:                              # defense-in-depth: never let one update persist+crash
            STATE["model"].parts.pop()
            STATE["rejected_payloads"] += 1
            STATE["audit"].append("rejected", node_id,
                                  {"round": rnd, "reason": f"eval error: {type(exc).__name__}"}, ts=time.time())
            return JSONResponse({"ok": False, "error": "model failed evaluation"}, status_code=400)

        nbytes = len(fc._canon(update))
        STATE["model_bytes_received"] += nbytes
        node["model_bytes"] += nbytes
        node["last_round"] = rnd
        node["eps_spent"] += eps                            # charge the DP budget ledger
        STATE["audit"].append("submit", node_id,
                              {"round": rnd, "trees": jf.n_trees, "model_bytes": nbytes,
                               "epsilon": round(eps, 4), "eps_cum": round(node["eps_spent"], 4)},
                              payload_sha256=payload_hash, ts=time.time())
        point = {"seq": len(STATE["metrics"]), "ts": time.time(), "node": node_id,
                 "round": rnd, **m, "central": CENTRAL[PRIMARY]}
        STATE["metrics"].append(point)
        STATE["audit"].append("aggregate", "coordinator",
                              {"round": rnd, "global_trees": m["n_trees"],
                               f"fed_{PRIMARY}": round(m[PRIMARY], 4),
                               f"central_{PRIMARY}": round(CENTRAL[PRIMARY], 4)}, ts=time.time())
    return {"ok": True, "fed_primary": m[PRIMARY], "primary_metric": PRIMARY,
            "global_trees": m["n_trees"], "eps_cum": node["eps_spent"], "eps_budget": BUDGET}


@app.get("/status")
async def status():
    with LOCK:
        nodes = [{"node_id": nid, "name": v["name"], "samples": v["samples"],
                  "rounds_submitted": v["last_round"], "model_kb": round(v["model_bytes"] / 1024, 1),
                  "eps_spent": round(v["eps_spent"], 3)}
                 for nid, v in STATE["nodes"].items()]
        last = STATE["metrics"][-1] if STATE["metrics"] else None
        return {
            "dataset": DATASET, "classes": CLASSES, "primary_metric": PRIMARY,
            "nodes": nodes, "metrics": STATE["metrics"],
            "centralized": CENTRAL, "centralized_nonprivate": CEILING,
            "dp": DP, "epsilon_budget": BUDGET,
            "test_windows": int(len(Y_TEST)),
            "payload_schema_enforced": True,         # raw feature/label arrays cannot pass /submit
            "rejected_payloads": STATE["rejected_payloads"],
            "model_kb_received": round(STATE["model_bytes_received"] / 1024, 1),
            "global_trees": last["n_trees"] if last else 0,
            "global_updates": last["n_updates"] if last else 0,
            "fed_primary": last[PRIMARY] if last else None,
            "audit_len": len(STATE["audit"].entries),
        }


@app.get("/audit")
async def audit():
    with LOCK:
        entries = STATE["audit"].entries
        verified = STATE["audit"].verify(COORD_PUB, expected_len=len(entries))
        tip = entries[-1]["hash"] if entries else "0" * 64
        return {"verified": verified, "count": len(entries), "tip": tip, "entries": entries}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("coordinator:app", host="127.0.0.1", port=8055)
