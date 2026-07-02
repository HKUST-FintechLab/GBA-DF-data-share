"""GBA-DF federated coordinator — SECURE-AGGREGATION + central DP.

Per round, every enrolled node uploads a MASKED integer leaf-count vector (pairwise
X25519 masks). The coordinator sums the masked vectors — masks cancel, so it learns only
the POOLED leaf counts, never an individual node's — then adds Laplace(1/ε) noise to that
sum (central DP on the secure aggregate) and meters a GLOBAL ε budget. So the coordinator
never sees any single institution's data or even its un-noised aggregate.

  uv run uvicorn coordinator:app --host 127.0.0.1 --port 8055
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
import secure_agg as sa

HERE = os.path.dirname(os.path.abspath(__file__))

_test = np.load(os.path.join(HERE, "data", "test.npz"))
X_TEST, Y_TEST = _test["X"], _test["y"].astype(str)
with open(os.path.join(HERE, "data", "meta.json")) as f:
    META = json.load(f)
CENTRAL = META["centralized"]
CEILING = META.get("centralized_nonprivate", {})
CLASSES = [str(c) for c in META["classes"]]
PRIMARY = META["primary_metric"]
DATASET = META["dataset"]
MODALITY = META.get("modality")
MODALITY_INFO = META.get("modality_info")
BOUNDS = np.asarray(META["feature_bounds"], dtype=float)
DP = META["dp"]
EPS_ROUND = float(DP["epsilon_per_round"])
BUDGET = float(DP.get("budget", 10.0))                 # GLOBAL cumulative ε cap
N_TREES, DEPTH = int(DP["trees_per_round"]), int(DP["depth"])
STRUCT_SEED = int(DP.get("structure_seed", 2024))
COHORT = int(META.get("cohort", len(META.get("nodes", []))) or 1)
SECURE_COHORT = COHORT >= 3        # masking gives meaningful privacy only with >=3 non-colluding nodes
N_FEATURES = int(X_TEST.shape[1])
if not SECURE_COHORT:
    print(f"WARNING: cohort={COHORT} < 3 — pairwise masking provides weak/no privacy "
          f"(cohort 1 = no masking). Use >=3 nodes for a meaningful secure-aggregation guarantee.")
# expected masked-vector length (complete trees -> constant cell count)
EXPECT_LEN = N_TREES * (2 ** (DEPTH + 1) - 1) * len(CLASSES)


def shared_trees(rnd: int):
    return dp.build_shared_structure(STRUCT_SEED + rnd, N_FEATURES, BOUNDS, DEPTH, N_TREES)


COORD_KEY = fc.gen_key()
COORD_PUB = COORD_KEY.public_key()
LOCK = threading.Lock()
STATE = {
    "nodes": {}, "model": fc.GlobalModel(CLASSES), "audit": fc.Audit(COORD_KEY),
    "metrics": [], "round_buf": {}, "round_done": {}, "global_eps": 0.0,
    "rejected": 0, "started": time.time(),
}
STATE["audit"].append("genesis", "coordinator",
                      {"dataset": DATASET, "cohort": COHORT, "secure_aggregation": True,
                       f"centralized_{PRIMARY}": round(CENTRAL[PRIMARY], 4)}, ts=time.time())

app = FastAPI(title="GBA-DF Federated Coordinator (secure aggregation)")


@app.get("/")
async def dashboard():
    return FileResponse(os.path.join(HERE, "static", "dashboard.html"))


@app.get("/pubkey")
async def pubkey():
    return PlainTextResponse(fc.pub_pem(COORD_KEY).decode())


@app.get("/schema")
async def schema():
    return {"classes": CLASSES, "feature_bounds": BOUNDS.tolist(), "n_features": N_FEATURES,
            "primary_metric": PRIMARY, "cohort": COHORT, "dataset": DATASET,
            "modality": MODALITY, "modality_info": MODALITY_INFO,
            "dp": {**DP, "structure_seed": STRUCT_SEED}, "epsilon_budget": BUDGET}


@app.get("/participants")
async def participants():
    with LOCK:
        ps = [{"node_id": nid, "x_pub": v["x_pub"]} for nid, v in STATE["nodes"].items()]
        return {"ready": len(ps) >= COHORT, "cohort": COHORT, "participants": ps}


@app.post("/register")
async def register(req: Request):
    try:
        b = await req.json()
        node_id, pub, xpub = b["node_id"], b["pubkey_pem"], b["x_pub"]
        name, samples = b.get("name", b["node_id"]), int(b.get("samples", 0))
    except Exception:
        return JSONResponse({"ok": False, "error": "bad request"}, status_code=422)
    if samples <= 0:
        return JSONResponse({"ok": False, "error": "samples must be > 0"}, status_code=422)
    with LOCK:
        cur = STATE["nodes"].get(node_id)
        if cur and cur["pubkey"] != pub:
            STATE["audit"].append("rejected", node_id, {"reason": "pubkey rebind"}, ts=time.time())
            return JSONResponse({"ok": False, "error": "node_id already enrolled"}, status_code=409)
        if not cur and len(STATE["nodes"]) >= COHORT:       # enrollment cap: extra nodes would break masking
            STATE["audit"].append("rejected", node_id, {"reason": "cohort full"}, ts=time.time())
            return JSONResponse({"ok": False, "error": f"cohort full ({COHORT})"}, status_code=409)
        if not cur:
            STATE["nodes"][node_id] = {"pubkey": pub, "x_pub": xpub, "name": name,
                                       "samples": samples, "last_round": 0}
            STATE["audit"].append("register", node_id, {"name": name, "samples": samples}, ts=time.time())
    return {"ok": True, "node_id": node_id, "cohort": COHORT}


@app.post("/submit")
async def submit(req: Request):
    try:
        b = await req.json()
        node_id, rnd, n_samples = b["node_id"], int(b["round"]), int(b["n_samples"])
        masked, sig = b["masked"], bytes.fromhex(b["sig_hex"])
    except Exception:
        return JSONResponse({"ok": False, "error": "bad request"}, status_code=422)

    with LOCK:
        node = STATE["nodes"].get(node_id)
        if node is None:
            return JSONResponse({"ok": False, "error": "unregistered node"}, status_code=403)
        if rnd <= node["last_round"]:
            STATE["rejected"] += 1
            STATE["audit"].append("rejected", node_id, {"round": rnd, "reason": "replay/stale"}, ts=time.time())
            return JSONResponse({"ok": False, "error": "stale or replayed round"}, status_code=409)
        # validate masked vector: exact length, ints in range
        if (not isinstance(masked, list) or len(masked) != EXPECT_LEN
                or not all(isinstance(x, int) and 0 <= x < sa.MOD for x in masked)):
            STATE["rejected"] += 1
            STATE["audit"].append("rejected", node_id, {"round": rnd, "reason": "bad masked vector"}, ts=time.time())
            return JSONResponse({"ok": False, "error": "invalid masked payload"}, status_code=400)
        payload_hash = fc.sha256_hex(fc._canon(masked))
        message = f"{node_id}|{rnd}|{n_samples}|{payload_hash}".encode()
        if not fc.verify_sig(fc.load_pub(node["pubkey"].encode()), sig, message):
            STATE["rejected"] += 1
            STATE["audit"].append("rejected", node_id, {"round": rnd, "reason": "bad signature"}, ts=time.time())
            return JSONResponse({"ok": False, "error": "signature verification failed"}, status_code=401)
        if rnd not in STATE["round_done"] and STATE["global_eps"] + EPS_ROUND > BUDGET + 1e-9:
            STATE["rejected"] += 1
            STATE["audit"].append("rejected", node_id, {"round": rnd, "reason": "global ε budget exceeded"}, ts=time.time())
            return JSONResponse({"ok": False, "error": "global epsilon budget exceeded"}, status_code=429)

        node["last_round"] = rnd
        buf = STATE["round_buf"].setdefault(rnd, {})
        buf[node_id] = np.asarray(masked, dtype=np.int64)
        STATE["audit"].append("submit", node_id,
                              {"round": rnd, "masked_cells": len(masked)},
                              payload_sha256=payload_hash, ts=time.time())

        # full cohort for this round -> SECURE-SUM (masks cancel only if the exact enrolled set submits)
        if (len(buf) >= COHORT and set(buf) == set(STATE["nodes"]) and rnd not in STATE["round_done"]):
            summed = sa.secure_sum(list(buf.values()))             # coordinator sees only the pooled sum
            trees = shared_trees(rnd)
            fd = dp.forest_from_summed_counts(trees, summed, CLASSES, EPS_ROUND)
            weight = float(sum(STATE["nodes"][x]["samples"] for x in buf))
            STATE["model"].add(fc.JsonForest(fd), weight, "secure-agg", rnd)
            STATE["global_eps"] += EPS_ROUND
            m = STATE["model"].evaluate(X_TEST, Y_TEST)
            STATE["metrics"].append({"seq": len(STATE["metrics"]), "ts": time.time(),
                                     "round": rnd, **m, "central": CENTRAL[PRIMARY]})
            STATE["round_done"][rnd] = {"fed_primary": m[PRIMARY], "global_trees": m["n_trees"]}
            STATE["audit"].append("aggregate", "coordinator",
                                  {"round": rnd, "participants": len(buf), "global_trees": m["n_trees"],
                                   "epsilon": EPS_ROUND, "global_eps": round(STATE["global_eps"], 4),
                                   f"fed_{PRIMARY}": round(m[PRIMARY], 4)}, ts=time.time())

        done = STATE["round_done"].get(rnd)
    return {"ok": True, "primary_metric": PRIMARY, "pending": done is None,
            "fed_primary": (done or {}).get("fed_primary"),
            "global_eps": STATE["global_eps"], "epsilon_budget": BUDGET}


@app.get("/round/{rnd}")
async def round_result(rnd: int):
    with LOCK:
        d = STATE["round_done"].get(rnd)
        return {"ready": d is not None, **(d or {}), "primary_metric": PRIMARY}


@app.get("/status")
async def status():
    with LOCK:
        nodes = [{"node_id": nid, "name": v["name"], "samples": v["samples"],
                  "rounds_submitted": v["last_round"]} for nid, v in STATE["nodes"].items()]
        last = STATE["metrics"][-1] if STATE["metrics"] else None
        return {
            "dataset": DATASET, "modality": MODALITY, "modality_info": MODALITY_INFO,
            "classes": CLASSES, "primary_metric": PRIMARY,
            "secure_aggregation": True, "cohort": COHORT, "secure_cohort": SECURE_COHORT, "nodes": nodes,
            "metrics": STATE["metrics"], "centralized": CENTRAL, "centralized_nonprivate": CEILING,
            "dp": DP, "epsilon_budget": BUDGET, "global_eps": round(STATE["global_eps"], 3),
            "test_windows": int(len(Y_TEST)), "rejected_payloads": STATE["rejected"],
            "global_trees": last["n_trees"] if last else 0,
            "fed_primary": last[PRIMARY] if last else None,
            "audit_len": len(STATE["audit"].entries),
        }


@app.get("/audit")
async def audit():
    with LOCK:
        e = STATE["audit"].entries
        return {"verified": STATE["audit"].verify(COORD_PUB, expected_len=len(e)),
                "count": len(e), "tip": e[-1]["hash"] if e else "0" * 64, "entries": e}


@app.get("/model")
async def model():
    """Download the aggregated global model (pickle-free JSON) so a data-user can run it
    LOCALLY — their query data then never leaves their machine either. Carries provenance:
    modality, feature schema, DP budget spent, current test metric, and the audit tip."""
    with LOCK:
        gm = STATE["model"]
        if gm.n_updates() == 0:
            return JSONResponse({"ok": False, "error": "no model yet — run some rounds first"},
                                status_code=409)
        last = STATE["metrics"][-1] if STATE["metrics"] else None
        e = STATE["audit"].entries
        return {"ok": True, "modality": MODALITY, "modality_info": MODALITY_INFO,
                "classes": CLASSES, "n_features": N_FEATURES, "primary_metric": PRIMARY,
                "feature_bounds": BOUNDS.tolist(), "dataset": DATASET,
                "rounds": len(STATE["metrics"]), "n_trees": gm.n_trees(),
                "test_metric": (last or {}).get(PRIMARY), "test_windows": int(len(Y_TEST)),
                "global_eps": round(STATE["global_eps"], 4), "epsilon_budget": BUDGET,
                "dp": DP, "audit_tip": e[-1]["hash"] if e else "0" * 64,
                "coordinator_pubkey": fc.pub_pem(COORD_KEY).decode(),
                "model": gm.serialize()}


@app.post("/predict")
async def predict(req: Request):
    """Hosted inference: send feature rows (X: [[...]] in the published feature order); get
    class probabilities + predicted labels. Convenience path — for full data-locality, prefer
    GET /model and run predict.py on your own machine so your query data stays local too."""
    try:
        b = await req.json()
        X = np.asarray(b["X"], dtype=float)
    except Exception:
        return JSONResponse({"ok": False, "error": "bad request: expected {\"X\": [[...]]}"}, status_code=422)
    if X.ndim != 2 or X.shape[1] != N_FEATURES:
        return JSONResponse({"ok": False, "error": f"X must be [n, {N_FEATURES}] in feature order"},
                            status_code=422)
    if X.shape[0] > 10000:
        return JSONResponse({"ok": False, "error": "too many rows (max 10000 per call)"}, status_code=413)
    with LOCK:
        gm = STATE["model"]
        if gm.n_updates() == 0:
            return JSONResponse({"ok": False, "error": "no model yet"}, status_code=409)
        proba = gm.predict_proba(X)
    pred = [CLASSES[i] for i in proba.argmax(1)]
    return {"ok": True, "classes": CLASSES, "primary_metric": PRIMARY,
            "proba": np.round(proba, 5).tolist(), "pred": pred}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("coordinator:app", host="127.0.0.1", port=8055)
