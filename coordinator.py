"""GBA-DF federated coordinator — SECURE-AGGREGATION + central DP.

Per round, every enrolled node uploads a MASKED integer leaf-count vector (pairwise
X25519 masks). The coordinator sums the masked vectors — masks cancel, so it learns only
the POOLED leaf counts, never an individual node's — then adds Laplace(1/ε) noise to that
sum (central DP on the secure aggregate) and meters a GLOBAL ε budget. So the coordinator
never sees any single institution's data or even its un-noised aggregate.

  uv run uvicorn coordinator:app --host 127.0.0.1 --port 8055

Deployment knobs (env vars):
  FED_PASSWORD   shared access token. If set, node-facing endpoints (/schema, /register,
                 /participants, /submit, /round) require header  X-Fed-Key: <password>.
                 Unset (default) = open, for local dev.
  FED_COHORT     override the cohort published in meta.json. FED_COHORT=1 turns on
                 PER-GUEST ISOLATION: each client (keyed by its X-Fed-Session header) gets
                 its OWN private cohort-1 federation — anyone can try alone, anytime, and
                 never sees another guest's data or model. (cohort=1 => no masking, so the
                 privacy story there is central DP only, not secure aggregation.)
"""
import base64
import json
import os
import tempfile
import threading
import time
from urllib.parse import urlparse

import numpy as np
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse

import dp
import fed_common as fc
import secure_agg as sa

HERE = os.path.dirname(os.path.abspath(__file__))

CLIENT_CONFIG_FORMAT = "gba-df-client-config"
CLIENT_CONFIG_VERSION = 1


def client_connection_config(coordinator_url: str) -> dict:
    """Return the desktop-client configuration for this coordinator.

    A configured shared password is included at the user's request. The exported runtime
    file is therefore written with owner-only permissions and must never be committed.
    """
    url = str(coordinator_url or "").strip().rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("public coordinator URL must be a full http(s) URL")
    if parsed.username or parsed.password:
        raise ValueError("public coordinator URL must not contain credentials")
    if parsed.path not in {"", "/"} or parsed.params or parsed.query or parsed.fragment:
        raise ValueError("public coordinator URL must not include a path, query, or fragment")
    config = {
        "format": CLIENT_CONFIG_FORMAT,
        "version": CLIENT_CONFIG_VERSION,
        "coordinator_url": url,
        "password_required": bool(FED_PASSWORD),
        "cohort": COHORT,
        "modality": MODALITY,
    }
    if FED_PASSWORD:
        config["password"] = FED_PASSWORD
    return config


def write_client_connection_config(path: str, coordinator_url: str) -> tuple[str, dict]:
    """Atomically write a shareable desktop-client config JSON file with mode 0600."""
    config = client_connection_config(coordinator_url)
    out = os.path.abspath(os.path.expanduser(path))
    parent = os.path.dirname(out) or "."
    os.makedirs(parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".gba-df-client-config-", suffix=".json", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, out)
        os.chmod(out, 0o600)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return out, config

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
# cohort can be overridden at deploy time (e.g. FED_COHORT=1 for the public "try it solo" server)
COHORT = int(os.environ.get("FED_COHORT", META.get("cohort", len(META.get("nodes", []))) or 1))
SECURE_COHORT = COHORT >= 3        # masking gives meaningful privacy only with >=3 non-colluding nodes
ISOLATE = COHORT == 1              # per-guest private federations (multi-tenant), keyed by session
FED_PASSWORD = os.environ.get("FED_PASSWORD", "")      # shared access token; "" = open (local dev)
STATE_DIR = os.path.abspath(os.path.expanduser(
    os.environ.get("FED_STATE_DIR", os.path.join(HERE, "data", "coordinator_state"))))
N_FEATURES = int(X_TEST.shape[1])
if not SECURE_COHORT:
    print(f"WARNING: cohort={COHORT} < 3 — pairwise masking provides weak/no privacy "
          f"(cohort 1 = no masking, central DP only). Use >=3 nodes for a meaningful "
          f"secure-aggregation guarantee.")
if ISOLATE:
    print("cohort=1 -> PER-GUEST ISOLATION on: each X-Fed-Session gets its own private federation.")
if FED_PASSWORD:
    print("FED_PASSWORD set -> node endpoints require the X-Fed-Key header.")
# expected masked-vector length (complete trees -> constant cell count)
EXPECT_LEN = N_TREES * (2 ** (DEPTH + 1) - 1) * len(CLASSES)


def shared_trees(rnd: int):
    return dp.build_shared_structure(STRUCT_SEED + rnd, N_FEATURES, BOUNDS, DEPTH, N_TREES)


def _atomic_private_write(path: str, payload: bytes):
    """Atomically persist coordinator evidence with owner-only permissions."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".gba-df-state-", dir=os.path.dirname(path))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(payload)
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _load_or_make_coordinator_key():
    path = os.path.join(STATE_DIR, "coordinator_key.pem")
    if os.path.exists(path):
        os.chmod(path, 0o600)
        with open(path, "rb") as f:
            return fc.load_priv(f.read())
    key = fc.gen_key()
    _atomic_private_write(path, fc.priv_pem(key))
    return key


COORD_KEY = _load_or_make_coordinator_key()
COORD_PUB = COORD_KEY.public_key()
LOCK = threading.Lock()

# ---- per-room state: one federation per room. Group mode uses a single "default" room;
#      solo/isolated mode gives each guest session its own room. ----
SESSIONS = {}          # room_id -> state dict


def _state_path(room: str) -> str:
    room_hash = fc.sha256_hex(room.encode())[:24]
    return os.path.join(STATE_DIR, f"audit-{room_hash}.json")


def _federation_config() -> dict:
    return {"dataset": DATASET, "modality": MODALITY, "classes": CLASSES,
            "n_features": N_FEATURES, "cohort": COHORT, "dp": DP,
            "structure_seed": STRUCT_SEED}


def _persist_state(room: str, st: dict):
    payload = {
        "format": "gba-df-audit-state", "version": 1, "room": room,
        "federation_config": _federation_config(),
        "coordinator_public_key_pem": fc.pub_pem(COORD_KEY).decode(),
        "audit_entries": st["audit"].entries,
        "participants": st["evidence_participants"],
        "submission_receipts": st["submission_receipts"],
        "model": st["model"].serialize() if st["model"].n_updates() else None,
        "metrics": st["metrics"], "global_eps": st["global_eps"],
        "rejected": st["rejected"], "updated_at": time.time(),
    }
    digest = fc.sha256_hex(fc._canon(payload))
    sealed = {**payload, "state_sha256": digest,
              "state_signature": base64.b64encode(COORD_KEY.sign(digest.encode())).decode()}
    _atomic_private_write(_state_path(room), fc._canon(sealed))


def _valid_state_seal(saved: dict) -> bool:
    try:
        signed = {k: v for k, v in saved.items()
                  if k not in {"state_sha256", "state_signature"}}
        digest = fc.sha256_hex(fc._canon(signed))
        signature = base64.b64decode(saved.get("state_signature", ""), validate=True)
        return saved.get("state_sha256") == digest and fc.verify_sig(
            COORD_PUB, signature, digest.encode())
    except Exception:
        return False


def _append_audit(room: str, st: dict, event: str, node: str, detail: dict,
                  payload_sha256: str = ""):
    entry = st["audit"].append(event, node, detail, payload_sha256=payload_sha256,
                               ts=time.time())
    _persist_state(room, st)
    return entry


def new_state(room: str):
    st = {
        "nodes": {}, "model": fc.GlobalModel(CLASSES), "audit": fc.Audit(COORD_KEY),
        "metrics": [], "round_buf": {}, "round_done": {}, "global_eps": 0.0,
        "rejected": 0, "started": time.time(), "evidence_participants": {},
        "submission_receipts": [],
    }
    path = _state_path(room)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)
        if (saved.get("format") != "gba-df-audit-state" or saved.get("version") != 1
                or saved.get("room") != room
                or saved.get("federation_config") != _federation_config()
                or saved.get("coordinator_public_key_pem") != fc.pub_pem(COORD_KEY).decode()
                or not _valid_state_seal(saved)):
            raise RuntimeError(f"invalid persisted audit state: {path}")
        st["audit"].entries = saved.get("audit_entries", [])
        if not st["audit"].verify(COORD_PUB, expected_len=len(st["audit"].entries)):
            raise RuntimeError(f"persisted audit chain verification failed: {path}")
        st["evidence_participants"] = saved.get("participants", {})
        st["submission_receipts"] = saved.get("submission_receipts", [])
        st["metrics"] = saved.get("metrics", [])
        st["global_eps"] = float(saved.get("global_eps", 0.0))
        st["rejected"] = int(saved.get("rejected", 0))
        if saved.get("model"):
            st["model"] = fc.GlobalModel.from_serialized(saved["model"])
        _append_audit(room, st, "coordinator_restart", "coordinator",
                      {"discarded_incomplete_rounds": True,
                       "global_eps_restored": round(st["global_eps"], 4)})
    else:
        _append_audit(room, st, "genesis", "coordinator",
                      {"dataset": DATASET, "cohort": COHORT,
                       "secure_aggregation": SECURE_COHORT,
                       f"centralized_{PRIMARY}": round(CENTRAL[PRIMARY], 4)})
    return st


def get_state(room: str):
    """Return the mutable federation state for a room, creating it on first use.
    Call while holding LOCK."""
    st = SESSIONS.get(room)
    if st is None:
        st = SESSIONS[room] = new_state(room)
    return st


def room_of(request: Request) -> str:
    """Which federation this request belongs to. Group mode: one shared room. Solo mode:
    the client's session id (header, or ?session= for browser/consumer convenience)."""
    if not ISOLATE:
        return "default"
    return (request.headers.get("x-fed-session")
            or request.query_params.get("session") or "default")


app = FastAPI(title="GBA-DF Federated Coordinator (secure aggregation)")

# endpoints that require the shared password (the "contribute your data" surface)
_PROTECTED = ("/schema", "/participants", "/register", "/submit", "/round")


@app.middleware("http")
async def _auth(request: Request, call_next):
    if FED_PASSWORD:
        path = request.url.path
        if any(path == p or path.startswith(p + "/") for p in _PROTECTED):
            if request.headers.get("x-fed-key", "") != FED_PASSWORD:
                return JSONResponse({"ok": False, "error": "unauthorized: bad or missing password"},
                                    status_code=401)
    return await call_next(request)


@app.get("/")
async def dashboard():
    return FileResponse(os.path.join(HERE, "static", "dashboard.html"))


@app.get("/pubkey")
async def pubkey():
    return PlainTextResponse(fc.pub_pem(COORD_KEY).decode())


@app.get("/schema")
async def schema(request: Request):
    room = room_of(request)
    with LOCK:
        st = get_state(room)
        completed = [int(e["detail"]["round"]) for e in st["audit"].entries
                     if e.get("event") == "aggregate" and "round" in e.get("detail", {})]
        next_round = max(completed, default=0) + 1
    return {"classes": CLASSES, "feature_bounds": BOUNDS.tolist(), "n_features": N_FEATURES,
            "primary_metric": PRIMARY, "cohort": COHORT, "dataset": DATASET,
            "modality": MODALITY, "modality_info": MODALITY_INFO, "isolated": ISOLATE,
            "dp": {**DP, "structure_seed": STRUCT_SEED}, "epsilon_budget": BUDGET,
            "next_round": next_round}


@app.get("/participants")
async def participants(request: Request):
    room = room_of(request)
    with LOCK:
        st = get_state(room)
        ps = [{"node_id": nid, "x_pub": v["x_pub"]} for nid, v in st["nodes"].items()]
        return {"ready": len(ps) >= COHORT, "cohort": COHORT, "participants": ps}


@app.post("/register")
async def register(req: Request):
    room = room_of(req)
    try:
        b = await req.json()
        node_id, pub, xpub = b["node_id"], b["pubkey_pem"], b["x_pub"]
        name, samples = b.get("name", b["node_id"]), int(b.get("samples", 0))
    except Exception:
        return JSONResponse({"ok": False, "error": "bad request"}, status_code=422)
    if samples <= 0:
        return JSONResponse({"ok": False, "error": "samples must be > 0"}, status_code=422)
    with LOCK:
        st = get_state(room)
        cur = st["nodes"].get(node_id)
        enrolled = st["evidence_participants"].get(node_id)
        if (cur and cur["pubkey"] != pub) or (enrolled and enrolled["pubkey_pem"] != pub):
            _append_audit(room, st, "rejected", node_id, {"reason": "pubkey rebind"})
            return JSONResponse({"ok": False, "error": "node_id already enrolled"}, status_code=409)
        historical_full = len(st["evidence_participants"]) >= COHORT and not enrolled
        if not cur and (len(st["nodes"]) >= COHORT or historical_full):
            # Enrollment remains bound to the original signing keys across restarts.
            _append_audit(room, st, "rejected", node_id, {"reason": "cohort full"})
            return JSONResponse({"ok": False, "error": f"cohort full ({COHORT})"}, status_code=409)
        if not cur:
            # Incomplete rounds are intentionally discarded on restart, so only a completed
            # aggregate advances replay protection. Nodes may safely resubmit an interrupted round.
            previous_round = max((int(e["detail"]["round"]) for e in st["audit"].entries
                                  if e.get("event") == "aggregate"), default=0)
            st["nodes"][node_id] = {"pubkey": pub, "x_pub": xpub, "name": name,
                                    "samples": samples, "last_round": previous_round}
            st["evidence_participants"][node_id] = {
                "pubkey_pem": pub, "name": name, "samples": samples,
            }
            _append_audit(room, st, "register", node_id,
                          {"name": name, "samples": samples,
                           "key_fingerprint": fc.sha256_hex(pub.encode())[:16]})
    return {"ok": True, "node_id": node_id, "cohort": COHORT}


@app.post("/submit")
async def submit(req: Request):
    room = room_of(req)
    try:
        b = await req.json()
        node_id, rnd, n_samples = b["node_id"], int(b["round"]), int(b["n_samples"])
        masked, sig = b["masked"], bytes.fromhex(b["sig_hex"])
    except Exception:
        return JSONResponse({"ok": False, "error": "bad request"}, status_code=422)

    with LOCK:
        st = get_state(room)
        node = st["nodes"].get(node_id)
        if node is None:
            return JSONResponse({"ok": False, "error": "unregistered node"}, status_code=403)
        if rnd <= node["last_round"]:
            st["rejected"] += 1
            _append_audit(room, st, "rejected", node_id,
                          {"round": rnd, "reason": "replay/stale"})
            return JSONResponse({"ok": False, "error": "stale or replayed round"}, status_code=409)
        # validate masked vector: exact length, ints in range
        if (not isinstance(masked, list) or len(masked) != EXPECT_LEN
                or not all(isinstance(x, int) and 0 <= x < sa.MOD for x in masked)):
            st["rejected"] += 1
            _append_audit(room, st, "rejected", node_id,
                          {"round": rnd, "reason": "bad masked vector"})
            return JSONResponse({"ok": False, "error": "invalid masked payload"}, status_code=400)
        payload_hash = fc.sha256_hex(fc._canon(masked))
        message = f"{node_id}|{rnd}|{n_samples}|{payload_hash}".encode()
        if not fc.verify_sig(fc.load_pub(node["pubkey"].encode()), sig, message):
            st["rejected"] += 1
            _append_audit(room, st, "rejected", node_id,
                          {"round": rnd, "reason": "bad signature"})
            return JSONResponse({"ok": False, "error": "signature verification failed"}, status_code=401)
        if rnd not in st["round_done"] and st["global_eps"] + EPS_ROUND > BUDGET + 1e-9:
            st["rejected"] += 1
            _append_audit(room, st, "rejected", node_id,
                          {"round": rnd, "reason": "global ε budget exceeded"})
            return JSONResponse({"ok": False, "error": "global epsilon budget exceeded"}, status_code=429)

        node["last_round"] = rnd
        buf = st["round_buf"].setdefault(rnd, {})
        buf[node_id] = np.asarray(masked, dtype=np.int64)
        st["submission_receipts"].append({
            "node_id": node_id, "round": rnd, "n_samples": n_samples,
            "payload_sha256": payload_hash, "sig_hex": sig.hex(), "ts": time.time(),
        })
        _append_audit(room, st, "submit", node_id,
                      {"round": rnd, "n_samples": n_samples,
                       "masked_cells": len(masked)}, payload_sha256=payload_hash)

        # full cohort for this round -> SECURE-SUM (masks cancel only if the exact enrolled set submits)
        if (len(buf) >= COHORT and set(buf) == set(st["nodes"]) and rnd not in st["round_done"]):
            summed = sa.secure_sum(list(buf.values()))             # coordinator sees only the pooled sum
            trees = shared_trees(rnd)
            fd = dp.forest_from_summed_counts(trees, summed, CLASSES, EPS_ROUND)
            weight = float(sum(st["nodes"][x]["samples"] for x in buf))
            st["model"].add(fc.JsonForest(fd), weight, "secure-agg", rnd)
            st["global_eps"] += EPS_ROUND
            m = st["model"].evaluate(X_TEST, Y_TEST)
            st["metrics"].append({"seq": len(st["metrics"]), "ts": time.time(),
                                  "round": rnd, **m, "central": CENTRAL[PRIMARY]})
            st["round_done"][rnd] = {"fed_primary": m[PRIMARY], "global_trees": m["n_trees"]}
            _append_audit(room, st, "aggregate", "coordinator",
                          {"round": rnd, "participants": len(buf),
                           "global_trees": m["n_trees"], "epsilon": EPS_ROUND,
                           "global_eps": round(st["global_eps"], 4),
                           f"fed_{PRIMARY}": round(m[PRIMARY], 4)})

        done = st["round_done"].get(rnd)
        eps = st["global_eps"]
    return {"ok": True, "primary_metric": PRIMARY, "pending": done is None,
            "fed_primary": (done or {}).get("fed_primary"),
            "global_eps": eps, "epsilon_budget": BUDGET}


@app.get("/round/{rnd}")
async def round_result(rnd: int, request: Request):
    room = room_of(request)
    with LOCK:
        st = get_state(room)
        d = st["round_done"].get(rnd)
        return {"ready": d is not None, **(d or {}), "primary_metric": PRIMARY,
                "global_eps": st["global_eps"], "epsilon_budget": BUDGET}


@app.get("/status")
async def status(request: Request):
    room = room_of(request)
    with LOCK:
        st = get_state(room)
        nodes = [{"node_id": nid, "name": v["name"], "samples": v["samples"],
                  "rounds_submitted": v["last_round"]} for nid, v in st["nodes"].items()]
        last = st["metrics"][-1] if st["metrics"] else None
        return {
            "dataset": DATASET, "modality": MODALITY, "modality_info": MODALITY_INFO,
            "classes": CLASSES, "primary_metric": PRIMARY,
            "secure_aggregation": SECURE_COHORT, "cohort": COHORT, "secure_cohort": SECURE_COHORT,
            "isolated": ISOLATE, "active_sessions": len(SESSIONS), "nodes": nodes,
            "metrics": st["metrics"], "centralized": CENTRAL, "centralized_nonprivate": CEILING,
            "dp": DP, "epsilon_budget": BUDGET, "global_eps": round(st["global_eps"], 3),
            "test_windows": int(len(Y_TEST)), "rejected_payloads": st["rejected"],
            "global_trees": last["n_trees"] if last else 0,
            "fed_primary": last[PRIMARY] if last else None,
            "audit_len": len(st["audit"].entries),
            "audit_persistent": True,
            "audit_bundle_endpoint": "/audit/bundle",
        }


@app.get("/audit")
async def audit(request: Request):
    room = room_of(request)
    with LOCK:
        st = get_state(room)
        e = st["audit"].entries
        return {"verified": st["audit"].verify(COORD_PUB, expected_len=len(e)),
                "count": len(e), "tip": e[-1]["hash"] if e else "0" * 64, "entries": e}


def build_audit_bundle(room: str, st: dict) -> dict:
    """Build a self-contained, coordinator-signed verification package."""
    entries = st["audit"].entries
    model_data = st["model"].serialize() if st["model"].n_updates() else None
    payload = {
        "format": "gba-df-audit-bundle", "version": 1, "generated_at": time.time(),
        "room": room,
        "federation": {
            "dataset": DATASET, "modality": MODALITY, "classes": CLASSES,
            "cohort": COHORT, "secure_aggregation": SECURE_COHORT,
            "dp": DP, "epsilon_budget": BUDGET,
            "global_eps": round(st["global_eps"], 4),
        },
        "coordinator_public_key_pem": fc.pub_pem(COORD_KEY).decode(),
        "participants": st["evidence_participants"],
        "submission_receipts": st["submission_receipts"],
        "audit_count": len(entries),
        "audit_tip": entries[-1]["hash"] if entries else "0" * 64,
        "audit_entries": entries,
        "model": model_data,
        "model_sha256": fc.sha256_hex(fc._canon(model_data)) if model_data else None,
    }
    digest = fc.sha256_hex(fc._canon(payload))
    return {**payload, "bundle_sha256": digest,
            "bundle_signature": base64.b64encode(COORD_KEY.sign(digest.encode())).decode()}


@app.get("/audit/bundle")
async def audit_bundle(request: Request):
    room = room_of(request)
    with LOCK:
        st = get_state(room)
        bundle = build_audit_bundle(room, st)
    filename = f"gba-df-audit-{fc.sha256_hex(room.encode())[:12]}.json"
    return JSONResponse(bundle, headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "no-store",
    })


@app.get("/model")
async def model(request: Request):
    """Download the aggregated global model (pickle-free JSON) so a data-user can run it
    LOCALLY — their query data then never leaves their machine either. Carries provenance:
    modality, feature schema, DP budget spent, current test metric, and the audit tip."""
    room = room_of(request)
    with LOCK:
        st = get_state(room)
        gm = st["model"]
        if gm.n_updates() == 0:
            return JSONResponse({"ok": False, "error": "no model yet — run some rounds first"},
                                status_code=409)
        last = st["metrics"][-1] if st["metrics"] else None
        e = st["audit"].entries
        return {"ok": True, "modality": MODALITY, "modality_info": MODALITY_INFO,
                "classes": CLASSES, "n_features": N_FEATURES, "primary_metric": PRIMARY,
                "feature_bounds": BOUNDS.tolist(), "dataset": DATASET,
                "rounds": len(st["metrics"]), "n_trees": gm.n_trees(),
                "test_metric": (last or {}).get(PRIMARY), "test_windows": int(len(Y_TEST)),
                "global_eps": round(st["global_eps"], 4), "epsilon_budget": BUDGET,
                "dp": DP, "audit_tip": e[-1]["hash"] if e else "0" * 64,
                "coordinator_pubkey": fc.pub_pem(COORD_KEY).decode(),
                "model": gm.serialize()}


@app.post("/predict")
async def predict(req: Request):
    """Hosted inference: send feature rows (X: [[...]] in the published feature order); get
    class probabilities + predicted labels. Convenience path — for full data-locality, prefer
    GET /model and run predict.py on your own machine so your query data stays local too."""
    room = room_of(req)
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
        st = get_state(room)
        gm = st["model"]
        if gm.n_updates() == 0:
            return JSONResponse({"ok": False, "error": "no model yet"}, status_code=409)
        proba = gm.predict_proba(X)
    pred = [CLASSES[i] for i in proba.argmax(1)]
    return {"ok": True, "classes": CLASSES, "primary_metric": PRIMARY,
            "proba": np.round(proba, 5).tolist(), "pred": pred}


if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="Run the GBA-DF federated coordinator")
    parser.add_argument("--host", default="127.0.0.1", help="bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8055, help="bind port (default: 8055)")
    parser.add_argument("--public-url", help="client-reachable http(s) URL for the exported config")
    parser.add_argument("--write-client-config", metavar="PATH",
                        help="write a desktop-client connection JSON file at startup (mode 0600)")
    args = parser.parse_args()

    if args.write_client_config:
        if args.public_url:
            public_url = args.public_url
        elif args.host in {"0.0.0.0", "::"}:
            parser.error("--public-url is required with a wildcard --host when exporting client config")
        else:
            public_url = f"http://{args.host}:{args.port}"
        try:
            out, config = write_client_connection_config(args.write_client_config, public_url)
        except (OSError, ValueError) as e:
            parser.error(f"could not write client config: {e}")
        print(f"Wrote desktop client config (mode 0600): {out}")
        if config["password_required"]:
            print("The config includes the shared password; distribute it only over an approved channel.")

    uvicorn.run(app, host=args.host, port=args.port)
