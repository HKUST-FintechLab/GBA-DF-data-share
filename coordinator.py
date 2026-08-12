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
  FED_READ_PASSWORD
                 optional separate token for dashboard/model/audit/inference endpoints.
                 Defaults to FED_PASSWORD when unset.
  FED_REQUIRE_INVITATION
                 "1" = /register additionally requires a coordinator-signed institution
                 invitation (see invitations.py and admin_invite.py), which is bound to the
                 node's Ed25519 key on first use and re-checked for expiry/revocation on
                 every submission. Required for a pilot; default "0" for local demos.
  FED_INVITATION_REGISTRY
                 path to the signed issuance/revocation ledger written by admin_invite.py.
                 Defaults to <FED_STATE_DIR>/invitations.json.
  FED_ROUND_TIMEOUT_SECONDS
                 how long a partially-submitted round waits for the rest of the cohort before
                 it is discarded and its submitters may send it again (default 900). Nothing
                 was aggregated, so an abandoned round costs no epsilon.
  FED_SESSION_IDLE_SECONDS / FED_MAX_ACTIVE_SESSIONS
                 bounds in-memory per-guest solo-demo sessions (defaults 3600 seconds / 100).
  FED_COHORT     override the cohort published in meta.json. FED_COHORT=1 turns on
                 PER-GUEST ISOLATION by default: each client (keyed by its X-Fed-Session
                 header) gets its OWN private federation. Set FED_SOLO_SHARED=1 together
                 with FED_COHORT=1 for a single shared one-node room whose model is visible
                 through the ordinary dashboard/model endpoints. (cohort=1 => no masking,
                 so the privacy story is central DP only, not secure aggregation.)
"""
import base64
from collections import deque
import json
import os
import secrets
import tempfile
import threading
import time

import numpy as np
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse

import client_config as cfg
import dp
import fed_common as fc
import invitations as invites
import secure_agg as sa

HERE = os.path.dirname(os.path.abspath(__file__))

# Audit-detail keys that are safe and useful to mirror into the operational log. Anything not
# listed stays in the signed chain only, so a new detail field cannot leak by default.
_LOGGED_DETAIL = frozenset({
    "round", "reason", "participants", "epsilon", "global_eps", "samples", "name",
    "invitation_id", "institution_name", "missing", "submitted", "timeout_seconds",
    "key_fingerprint", "n_samples", "global_trees", "discarded_incomplete_rounds",
    "session_cleanup_reason",
})

def client_connection_config(coordinator_url: str) -> dict:
    """Return the connection-only desktop-client configuration for this coordinator.

    A configured shared password is included at the user's request. The exported runtime
    file is therefore written with owner-only permissions and must never be committed. When
    invitations are enforced, issue per-institution configs with admin_invite.py instead —
    those also carry the signed invitation the node needs to enrol.
    """
    return cfg.build(coordinator_url, password=FED_PASSWORD, cohort=COHORT, modality=MODALITY)


def write_client_connection_config(path: str, coordinator_url: str) -> tuple[str, dict]:
    """Atomically write a shareable desktop-client config JSON file with mode 0600."""
    config = client_connection_config(coordinator_url)
    return cfg.write(path, config), config

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
SOLO_SHARED = os.environ.get("FED_SOLO_SHARED", "0").strip().lower() in {"1", "true", "yes", "on"}
if SOLO_SHARED and COHORT != 1:
    raise RuntimeError("FED_SOLO_SHARED requires FED_COHORT=1")
ISOLATE = COHORT == 1 and not SOLO_SHARED  # private solo rooms unless the owner explicitly shares one
PRIVACY_MODE = "secure_aggregation" if SECURE_COHORT else "central_dp_solo"
FED_PASSWORD = os.environ.get("FED_PASSWORD", "")      # shared access token; "" = open (local dev)
FED_READ_PASSWORD = os.environ.get("FED_READ_PASSWORD", FED_PASSWORD)
STATE_DIR = os.path.abspath(os.path.expanduser(
    os.environ.get("FED_STATE_DIR", os.path.join(HERE, "data", "coordinator_state"))))
REQUIRE_INVITATION = os.environ.get("FED_REQUIRE_INVITATION", "0").strip().lower() in {
    "1", "true", "yes", "on"}
REGISTRY_PATH = os.path.abspath(os.path.expanduser(os.environ.get(
    "FED_INVITATION_REGISTRY", os.path.join(STATE_DIR, "invitations.json"))))


def _bounded_env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, default))
    except (TypeError, ValueError):
        raise RuntimeError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}")
    return value


MAX_BODY_BYTES = _bounded_env_int("FED_MAX_BODY_BYTES", 32 * 1024 * 1024,
                                  1024, 128 * 1024 * 1024)
RATE_LIMIT_PER_MINUTE = _bounded_env_int("FED_RATE_LIMIT_PER_MINUTE", 600, 10, 10000)
ROUND_TIMEOUT_SECONDS = _bounded_env_int("FED_ROUND_TIMEOUT_SECONDS", 900, 30, 86400)
WRITE_RATE_LIMIT_PER_MINUTE = _bounded_env_int(
    "FED_WRITE_RATE_LIMIT_PER_MINUTE", 120, 5, 5000)
SESSION_IDLE_SECONDS = _bounded_env_int("FED_SESSION_IDLE_SECONDS", 3600, 60, 604800)
MAX_ACTIVE_SESSIONS = _bounded_env_int("FED_MAX_ACTIVE_SESSIONS", 100, 1, 10000)
N_FEATURES = int(X_TEST.shape[1])
if not SECURE_COHORT:
    print(f"WARNING: cohort={COHORT} < 3 — pairwise masking provides weak/no privacy "
          f"(cohort 1 = no masking, central DP only). Use >=3 nodes for a meaningful "
          f"secure-aggregation guarantee.")
if ISOLATE:
    print("cohort=1 -> PER-GUEST ISOLATION on: each X-Fed-Session gets its own private federation.")
elif SOLO_SHARED:
    print("FED_SOLO_SHARED=1 -> one shared cohort-1 room: dashboard/model endpoints show its model.")
if FED_PASSWORD:
    print("FED_PASSWORD set -> node endpoints require the X-Fed-Key header.")
if FED_READ_PASSWORD:
    print("Read/model/audit/inference endpoints require the X-Fed-Key header.")
if REQUIRE_INVITATION:
    print(f"FED_REQUIRE_INVITATION set -> /register requires a signed institution invitation "
          f"({REGISTRY_PATH}).")
else:
    print("WARNING: invitations are NOT enforced — any holder of the contributor password can "
          "enrol. Set FED_REQUIRE_INVITATION=1 for a pilot deployment.")
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


class InvitationRefused(Exception):
    """Enrolment or submission denied by the invitation layer. `status` is the HTTP code."""

    def __init__(self, reason: str, status: int = 403):
        super().__init__(reason)
        self.reason, self.status = reason, status


def _read_registry() -> dict:
    """Read the signed issuance/revocation ledger fresh from disk.

    Reading per request is what makes revocation take effect without a restart: the offline
    admin CLI is the only writer, so the running coordinator never races it. A corrupt or
    wrongly-signed ledger refuses enrolment instead of silently dropping revocations.
    """
    try:
        return invites.load_registry(REGISTRY_PATH, COORD_PUB)
    except (OSError, ValueError, RuntimeError) as e:
        raise InvitationRefused(f"invitation registry unavailable: {e}", status=503)


def _admit_invitation(st: dict, node_id: str, pubkey_pem: str, invitation) -> dict:
    """Validate an invitation for `node_id` and return the binding record to persist.

    First use binds the invitation to this node's Ed25519 key permanently, so a leaked
    invitation file cannot later be redeemed under a different key.
    """
    if invitation is None:
        raise InvitationRefused("a signed institution invitation is required", status=401)
    reason = invites.verify_invitation(invitation, COORD_PUB, expected_institution=node_id,
                                       require_role="contributor")
    if reason:
        raise InvitationRefused(reason, status=403)
    registry_reason = invites.registry_status(_read_registry(), invitation["invitation_id"])
    if registry_reason:
        raise InvitationRefused(registry_reason, status=403)

    key_hash = fc.sha256_hex(pubkey_pem.encode())
    bindings = st["invitation_bindings"]
    bound = bindings.get(invitation["invitation_id"])
    if bound and (bound["node_id"] != node_id or bound["pubkey_sha256"] != key_hash):
        raise InvitationRefused("invitation already bound to a different node key", status=409)
    other = next((iid for iid, b in bindings.items()
                  if b["node_id"] == node_id and iid != invitation["invitation_id"]), None)
    if other:
        raise InvitationRefused("node id already enrolled under another invitation", status=409)
    return {"node_id": node_id, "pubkey_sha256": key_hash,
            "institution_name": invitation["institution_name"],
            "role": invitation["role"], "expires_at": float(invitation["expires_at"])}


def _check_still_invited(st: dict, node_id: str):
    """Re-check a registered node's invitation before accepting a round submission, so an
    expiry or an administrator revocation stops an already-enrolled institution."""
    if not REQUIRE_INVITATION:
        return
    entry = next(((iid, b) for iid, b in st["invitation_bindings"].items()
                  if b["node_id"] == node_id), None)
    if entry is None:
        raise InvitationRefused("no invitation is bound to this node", status=403)
    invitation_id, binding = entry
    if time.time() - invites.CLOCK_SKEW_SECONDS > float(binding["expires_at"]):
        raise InvitationRefused("invitation: expired", status=403)
    reason = invites.registry_status(_read_registry(), invitation_id)
    if reason:
        raise InvitationRefused(reason, status=403)

# ---- per-room state: one federation per room. Group mode uses a single "default" room;
#      solo/isolated mode gives each guest session its own room. ----
SESSIONS = {}          # room_id -> state dict
EVICTED_SESSION_ROOMS = {}  # room_id -> cleanup reason; memory-only bookkeeping


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
        "invitation_bindings": st["invitation_bindings"],
        "submission_receipts": st["submission_receipts"],
        "model": st["model"].serialize() if st["model"].n_updates() else None,
        "metrics": st["metrics"], "global_eps": st["global_eps"],
        "epsilon_spent": st["epsilon_spent"],
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


def oplog(event: str, **fields):
    """Emit one JSON operational log line to stdout for the pilot operator's log collector.

    This is monitoring, not evidence — the signed audit chain remains the record of what
    happened. It therefore carries only protocol facts: identifiers, counts, and outcomes.
    Never put feature values, masked vectors, passwords, or invitation contents in here.
    """
    line = {"ts": round(time.time(), 3), "log": "gba-df", "event": event, **fields}
    try:
        print(json.dumps(line, ensure_ascii=False, sort_keys=True), flush=True)
    except (TypeError, ValueError):                  # never let logging break a request
        print(json.dumps({"ts": line["ts"], "log": "gba-df", "event": event,
                          "error": "unserialisable log fields"}), flush=True)


def _append_audit(room: str, st: dict, event: str, node: str, detail: dict,
                  payload_sha256: str = ""):
    entry = st["audit"].append(event, node, detail, payload_sha256=payload_sha256,
                               ts=time.time())
    _persist_state(room, st)
    oplog(event, node=node, room=fc.sha256_hex(room.encode())[:12], seq=entry["seq"],
          **{k: v for k, v in detail.items() if k in _LOGGED_DETAIL})
    return entry


def new_state(room: str, session_resume_reason: str = ""):
    st = {
        "nodes": {}, "model": fc.GlobalModel(CLASSES), "audit": fc.Audit(COORD_KEY),
        "metrics": [], "rounds": {}, "round_done": {}, "global_eps": 0.0,
        "rejected": 0, "started": time.time(), "evidence_participants": {},
        "submission_receipts": [], "invitation_bindings": {}, "epsilon_spent": {},
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
        st["invitation_bindings"] = saved.get("invitation_bindings", {})
        st["submission_receipts"] = saved.get("submission_receipts", [])
        st["metrics"] = saved.get("metrics", [])
        st["epsilon_spent"] = {str(k): float(v)
                               for k, v in (saved.get("epsilon_spent") or {}).items()}
        st["global_eps"] = float(saved.get("global_eps", 0.0))
        st["rejected"] = int(saved.get("rejected", 0))
        if saved.get("model"):
            st["model"] = fc.GlobalModel.from_serialized(saved["model"])
        event = "session_resumed" if session_resume_reason else "coordinator_restart"
        detail = {"discarded_incomplete_rounds": True,
                  "global_eps_restored": round(st["global_eps"], 4)}
        if session_resume_reason:
            detail["session_cleanup_reason"] = session_resume_reason
        _append_audit(room, st, event, "coordinator", detail)
    else:
        _append_audit(room, st, "genesis", "coordinator",
                      {"dataset": DATASET, "cohort": COHORT,
                       "secure_aggregation": SECURE_COHORT,
                       f"centralized_{PRIMARY}": round(CENTRAL[PRIMARY], 4)})
    return st


def cohort_fingerprint(st: dict) -> str:
    """Fingerprint of the currently enrolled (node_id, x_pub) set."""
    return fc.cohort_fingerprint((nid, v["x_pub"]) for nid, v in st["nodes"].items())


def _discard_round(room: str, st: dict, rnd: int, reason: str, detail: dict = None):
    """Drop a pending round's buffered submissions and let its submitters send it again.

    Nothing was aggregated, so no epsilon was spent; rolling `last_round` back below the
    round is what makes the retry acceptable rather than a replay.
    """
    record = st["rounds"].pop(rnd, None)
    if not record:
        return
    submitters = sorted(record["subs"])
    for node_id in submitters:
        node = st["nodes"].get(node_id)
        if node and node["last_round"] >= rnd:
            node["last_round"] = rnd - 1
    _append_audit(room, st, "round_discarded", "coordinator",
                  {"round": rnd, "reason": reason, "submitted": submitters,
                   "missing": sorted(set(st["nodes"]) - set(submitters)),
                   "epsilon_spent": 0.0, **(detail or {})})


def _expire_stale_rounds(room: str, st: dict):
    """Abort rounds that never completed within the timeout, so one absent institution
    stalls the federation for a bounded period instead of indefinitely."""
    now = time.time()
    for rnd in [r for r, rec in st["rounds"].items()
                if r not in st["round_done"] and now - rec["started"] > ROUND_TIMEOUT_SECONDS]:
        _discard_round(room, st, rnd, "round timed out waiting for the full cohort",
                       {"timeout_seconds": ROUND_TIMEOUT_SECONDS})


def _invalidate_changed_cohort(room: str, st: dict, fingerprint: str):
    """Drop pending rounds whose masks were built against a different peer set."""
    for rnd in [r for r, rec in st["rounds"].items()
                if r not in st["round_done"] and rec["cohort"] != fingerprint]:
        _discard_round(room, st, rnd, "cohort membership or masking keys changed")


def _evict_session(room: str, reason: str):
    """Discard a solo room's in-memory state without retaining masked vectors."""
    st = SESSIONS.get(room)
    if st is None:
        return
    for rnd in list(st["rounds"]):
        _discard_round(room, st, rnd, "session cleanup", {"session_cleanup_reason": reason})
    SESSIONS.pop(room, None)
    EVICTED_SESSION_ROOMS[room] = reason
    oplog("session_cleanup", room=fc.sha256_hex(room.encode())[:12], reason=reason)


def _cleanup_idle_sessions(now=None):
    """Bound isolated-demo memory; shared multi-institution rooms are never evicted here."""
    if not ISOLATE:
        return 0
    now = time.time() if now is None else float(now)
    stale = [room for room, st in SESSIONS.items()
             if now - st.get("last_activity", st["started"]) >= SESSION_IDLE_SECONDS]
    for room in stale:
        _evict_session(room, "idle timeout")
    return len(stale)


def get_state(room: str):
    """Return the mutable federation state for a room, creating it on first use.
    Call while holding LOCK."""
    now = time.time()
    _cleanup_idle_sessions(now)
    st = SESSIONS.get(room)
    if st is None:
        if ISOLATE and len(SESSIONS) >= MAX_ACTIVE_SESSIONS:
            oldest = min(SESSIONS, key=lambda item: SESSIONS[item].get("last_activity", 0))
            _evict_session(oldest, "active session capacity")
        st = SESSIONS[room] = new_state(room, EVICTED_SESSION_ROOMS.pop(room, ""))
    st["last_activity"] = now
    return st


def room_of(request: Request) -> str:
    """Which federation this request belongs to. Group mode: one shared room. Solo mode:
    the client's session id (header, or ?session= for browser/consumer convenience)."""
    if not ISOLATE:
        return "default"
    return (request.headers.get("x-fed-session")
            or request.query_params.get("session") or "default")


app = FastAPI(title="GBA-DF Federated Coordinator (secure aggregation)")

# Public endpoints intentionally carry no institution/model/audit information. Any route not
# explicitly classified below defaults to read/operator access so newly added endpoints fail closed.
_PUBLIC_PATHS = ("/", "/console", "/health", "/ready", "/pubkey")
_CONTRIBUTE_PATHS = ("/schema", "/participants", "/register", "/submit", "/round")
_READ_PATHS = ("/status", "/audit", "/model", "/predict")
_RATE_LOCK = threading.Lock()
_RATE_EVENTS = {}
_RATE_LAST_CLEANUP = 0.0


def _matches_path(path: str, prefixes: tuple[str, ...]) -> bool:
    return any(path == p or path.startswith(p + "/") for p in prefixes)


def _required_access(path: str) -> tuple[str, str]:
    if path in _PUBLIC_PATHS:
        return "public", ""
    if _matches_path(path, _READ_PATHS):
        return "read", FED_READ_PASSWORD
    if _matches_path(path, _CONTRIBUTE_PATHS):
        return "contribute", FED_PASSWORD
    return "read", FED_READ_PASSWORD


def _rate_allowed(client: str, bucket: str, limit: int, now: float) -> tuple[bool, int]:
    """Per-process pilot limiter. A shared backend replaces this for multi-instance production."""
    global _RATE_LAST_CLEANUP
    cutoff = now - 60.0
    key = (client, bucket)
    with _RATE_LOCK:
        if now - _RATE_LAST_CLEANUP >= 60.0:
            stale = [k for k, q in _RATE_EVENTS.items() if not q or q[-1] < cutoff]
            for old in stale:
                _RATE_EVENTS.pop(old, None)
            _RATE_LAST_CLEANUP = now
        events = _RATE_EVENTS.setdefault(key, deque())
        while events and events[0] < cutoff:
            events.popleft()
        if len(events) >= limit:
            retry_after = max(1, int(61 - (now - events[0])))
            return False, retry_after
        events.append(now)
        return True, 0


@app.middleware("http")
async def _security_boundary(request: Request, call_next):
    path = request.url.path
    access, required_key = _required_access(path)

    if request.method in {"POST", "PUT", "PATCH"}:
        content_length = request.headers.get("content-length")
        try:
            declared = int(content_length) if content_length is not None else None
        except ValueError:
            return JSONResponse({"ok": False, "error": "invalid Content-Length"}, status_code=400)
        if declared is not None and declared > MAX_BODY_BYTES:
            return JSONResponse({"ok": False, "error": "request body too large"},
                                status_code=413)
        body = await request.body()
        if len(body) > MAX_BODY_BYTES:
            return JSONResponse({"ok": False, "error": "request body too large"},
                                status_code=413)

    if access != "public":
        client = request.client.host if request.client else "unknown"
        is_write = request.method not in {"GET", "HEAD", "OPTIONS"}
        limit = WRITE_RATE_LIMIT_PER_MINUTE if is_write else RATE_LIMIT_PER_MINUTE
        allowed, retry_after = _rate_allowed(client, "write" if is_write else "read",
                                             limit, time.monotonic())
        if not allowed:
            # Denials are logged because a burst of them is what an operator needs to see; the
            # credential itself is never logged, only the access class that was demanded.
            oplog("denied", path=path, access=access, client=client, status=429)
            return JSONResponse({"ok": False, "error": "rate limit exceeded"}, status_code=429,
                                headers={"Retry-After": str(retry_after)})

    if required_key:
        supplied = request.headers.get("x-fed-key", "")
        if not secrets.compare_digest(supplied, required_key):
            oplog("denied", path=path, access=access, status=401,
                  client=request.client.host if request.client else "unknown")
            return JSONResponse(
                {"ok": False, "error": f"unauthorized: {access} access required"},
                status_code=401,
            )
    return await call_next(request)


@app.get("/")
async def dashboard():
    return FileResponse(os.path.join(HERE, "static", "town.html"))


@app.get("/console")
async def legacy_dashboard():
    """Serve the information-dense operator console alongside the game-like town UI."""
    return FileResponse(os.path.join(HERE, "static", "dashboard.html"))


@app.get("/health")
async def health():
    """Public liveness check. It deliberately exposes no federation state."""
    return {"ok": True, "service": "gba-df-coordinator"}


@app.get("/ready")
async def ready():
    """Public readiness check for deployment probes."""
    writable = os.path.isdir(STATE_DIR) and os.access(STATE_DIR, os.W_OK)
    if not writable:
        return JSONResponse({"ok": False, "ready": False}, status_code=503)
    return {"ok": True, "ready": True}


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
            "solo_shared": SOLO_SHARED, "secure_aggregation": SECURE_COHORT,
            "privacy_mode": PRIVACY_MODE,
            "dp": {**DP, "structure_seed": STRUCT_SEED}, "epsilon_budget": BUDGET,
            "next_round": next_round, "invitation_required": REQUIRE_INVITATION}


@app.get("/participants")
async def participants(request: Request):
    room = room_of(request)
    with LOCK:
        st = get_state(room)
        _expire_stale_rounds(room, st)
        ps = [{"node_id": nid, "x_pub": v["x_pub"]} for nid, v in st["nodes"].items()]
        return {"ready": len(ps) >= COHORT, "cohort": COHORT, "participants": ps,
                "cohort_sha256": cohort_fingerprint(st)}


@app.post("/register")
async def register(req: Request):
    room = room_of(req)
    try:
        b = await req.json()
        node_id, pub, xpub = b["node_id"], b["pubkey_pem"], b["x_pub"]
        name, samples = b.get("name", b["node_id"]), int(b.get("samples", 0))
        invitation = b.get("invitation")
    except Exception:
        return JSONResponse({"ok": False, "error": "bad request"}, status_code=422)
    if samples <= 0:
        return JSONResponse({"ok": False, "error": "samples must be > 0"}, status_code=422)
    if not isinstance(pub, str) or len(pub) > 4096:
        return JSONResponse({"ok": False, "error": "bad request"}, status_code=422)
    with LOCK:
        st = get_state(room)
        binding = None
        if REQUIRE_INVITATION:
            try:
                binding = _admit_invitation(st, node_id, pub, invitation)
            except InvitationRefused as e:
                _append_audit(room, st, "rejected", node_id, {"reason": e.reason})
                return JSONResponse({"ok": False, "error": e.reason}, status_code=e.status)
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
            if binding:
                st["invitation_bindings"][invitation["invitation_id"]] = binding
            _append_audit(room, st, "register", node_id,
                          {"name": name, "samples": samples,
                           "key_fingerprint": fc.sha256_hex(pub.encode())[:16],
                           **({"invitation_id": invitation["invitation_id"],
                               "institution_name": binding["institution_name"]}
                              if binding else {})})
        elif cur["x_pub"] != xpub:
            # A reconnecting node brings a FRESH ephemeral masking key. Keeping the old one
            # would leave residual masks in the pooled sum, so adopt the new key and discard
            # any round whose masks were built against the previous peer set.
            cur["x_pub"], cur["samples"], cur["name"] = xpub, samples, name
            st["evidence_participants"][node_id].update(name=name, samples=samples)
            _append_audit(room, st, "rejoin", node_id,
                          {"name": name, "samples": samples, "reason": "masking key refreshed"})
        _invalidate_changed_cohort(room, st, cohort_fingerprint(st))
        fingerprint = cohort_fingerprint(st)
    return {"ok": True, "node_id": node_id, "cohort": COHORT, "cohort_sha256": fingerprint}


@app.post("/submit")
async def submit(req: Request):
    room = room_of(req)
    try:
        b = await req.json()
        node_id, rnd, n_samples = b["node_id"], int(b["round"]), int(b["n_samples"])
        masked, sig = b["masked"], bytes.fromhex(b["sig_hex"])
        claimed_cohort = str(b.get("cohort_sha256") or "")
    except Exception:
        return JSONResponse({"ok": False, "error": "bad request"}, status_code=422)

    with LOCK:
        st = get_state(room)
        _expire_stale_rounds(room, st)
        node = st["nodes"].get(node_id)
        if node is None:
            return JSONResponse({"ok": False, "error": "unregistered node",
                                 "code": "unregistered"}, status_code=403)
        try:
            _check_still_invited(st, node_id)
        except InvitationRefused as e:
            st["rejected"] += 1
            _append_audit(room, st, "rejected", node_id, {"round": rnd, "reason": e.reason})
            return JSONResponse({"ok": False, "error": e.reason}, status_code=e.status)
        # Masks cancel only for the exact peer set they were built against, so a submission
        # carrying a stale fingerprint must never be pooled with current ones.
        fingerprint = cohort_fingerprint(st)
        if claimed_cohort != fingerprint:
            st["rejected"] += 1
            _append_audit(room, st, "rejected", node_id,
                          {"round": rnd, "reason": "cohort fingerprint mismatch"})
            return JSONResponse({"ok": False, "code": "cohort_changed",
                                 "error": "cohort membership or masking keys changed — "
                                          "re-fetch /participants and rebuild the masks",
                                 "cohort_sha256": fingerprint}, status_code=409)
        pending = st["rounds"].get(rnd)
        prior = (pending or {}).get("subs", {}).get(node_id)
        if rnd in st["round_done"]:
            st["rejected"] += 1
            _append_audit(room, st, "rejected", node_id,
                          {"round": rnd, "reason": "round already aggregated"})
            return JSONResponse({"ok": False, "error": "round already completed",
                                 "code": "stale"}, status_code=409)
        if prior is None and rnd <= node["last_round"]:
            st["rejected"] += 1
            _append_audit(room, st, "rejected", node_id,
                          {"round": rnd, "reason": "replay/stale"})
            return JSONResponse({"ok": False, "error": "stale or replayed round",
                                 "code": "stale"}, status_code=409)
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
        if str(rnd) not in st["epsilon_spent"] and st["global_eps"] + EPS_ROUND > BUDGET + 1e-9:
            st["rejected"] += 1
            _append_audit(room, st, "rejected", node_id,
                          {"round": rnd, "reason": "global ε budget exceeded"})
            return JSONResponse({"ok": False, "error": "global epsilon budget exceeded"}, status_code=429)

        if prior is not None and prior["hash"] != payload_hash:
            # A pending round already holds a different vector from this node. Accepting it
            # would let one institution choose its contribution after seeing the others wait.
            st["rejected"] += 1
            _append_audit(room, st, "rejected", node_id,
                          {"round": rnd, "reason": "conflicting resubmission"})
            return JSONResponse({"ok": False, "code": "conflict",
                                 "error": "a different payload was already submitted for this "
                                          "pending round"}, status_code=409)

        node["last_round"] = rnd
        record = st["rounds"].setdefault(rnd, {"cohort": fingerprint, "started": time.time(),
                                               "subs": {}})
        record["subs"][node_id] = {"vec": np.asarray(masked, dtype=np.int64),
                                   "hash": payload_hash}
        if prior is None:
            # A retry of an identical payload is idempotent: no second receipt, no second
            # audit entry, and nothing changes in the pooled sum.
            st["submission_receipts"].append({
                "node_id": node_id, "round": rnd, "n_samples": n_samples,
                "payload_sha256": payload_hash, "sig_hex": sig.hex(), "ts": time.time(),
            })
            _append_audit(room, st, "submit", node_id,
                          {"round": rnd, "n_samples": n_samples,
                           "masked_cells": len(masked)}, payload_sha256=payload_hash)

        # full cohort for this round -> SECURE-SUM (masks cancel only if the exact enrolled set submits)
        subs = record["subs"]
        if (len(subs) >= COHORT and set(subs) == set(st["nodes"])
                and rnd not in st["round_done"]):
            summed = sa.secure_sum([s["vec"] for s in subs.values()])  # only the pooled sum
            trees = shared_trees(rnd)
            fd = dp.forest_from_summed_counts(trees, summed, CLASSES, EPS_ROUND)
            weight = float(sum(st["nodes"][x]["samples"] for x in subs))
            model_source = "secure-agg" if SECURE_COHORT else "central-dp-solo"
            st["model"].add(fc.JsonForest(fd), weight, model_source, rnd)
            # The ledger is the authority on what a round already cost, so no retry, restart,
            # or duplicate aggregation can charge the same round twice.
            st["epsilon_spent"][str(rnd)] = EPS_ROUND
            st["global_eps"] += EPS_ROUND
            m = st["model"].evaluate(X_TEST, Y_TEST)
            st["metrics"].append({"seq": len(st["metrics"]), "ts": time.time(),
                                  "round": rnd, **m, "central": CENTRAL[PRIMARY]})
            st["round_done"][rnd] = {"fed_primary": m[PRIMARY],
                                     "global_trees": m["n_trees"], "metrics": m}
            st["rounds"].pop(rnd, None)          # masked vectors are not kept after pooling
            _append_audit(room, st, "aggregate", "coordinator",
                          {"round": rnd, "participants": len(subs),
                           "global_trees": m["n_trees"], "epsilon": EPS_ROUND,
                           "global_eps": round(st["global_eps"], 4),
                           f"fed_{PRIMARY}": round(m[PRIMARY], 4),
                           "auc": round(m["auc"], 4) if m.get("auc") is not None else None,
                           "balanced_accuracy": round(m["bacc"], 4),
                           "sensitivity": (round(m["sensitivity"], 4)
                                           if m.get("sensitivity") is not None else None),
                           "specificity": (round(m["specificity"], 4)
                                           if m.get("specificity") is not None else None),
                           "privacy_mode": PRIVACY_MODE})

        done = st["round_done"].get(rnd)
        eps = st["global_eps"]
        waiting = sorted(set(st["nodes"]) - set(st["rounds"].get(rnd, {}).get("subs", {})))
    return {"ok": True, "primary_metric": PRIMARY, "pending": done is None,
            "fed_primary": (done or {}).get("fed_primary"),
            "waiting_for": waiting, "cohort_sha256": fingerprint,
            "global_eps": eps, "epsilon_budget": BUDGET}


@app.get("/round/{rnd}")
async def round_result(rnd: int, request: Request):
    room = room_of(request)
    with LOCK:
        st = get_state(room)
        _expire_stale_rounds(room, st)
        d = st["round_done"].get(rnd)
        pending = st["rounds"].get(rnd)
        # A round that is neither complete nor buffered was aborted: say so, so a node stops
        # waiting on it instead of polling a round that will never finish.
        return {"ready": d is not None, **(d or {}), "primary_metric": PRIMARY,
                "aborted": d is None and pending is None,
                "waiting_for": sorted(set(st["nodes"]) - set((pending or {}).get("subs", {}))),
                "global_eps": st["global_eps"], "epsilon_budget": BUDGET}


@app.get("/status")
async def status(request: Request):
    room = room_of(request)
    with LOCK:
        st = get_state(room)
        nodes = [{"node_id": nid, "name": v["name"], "samples": v["samples"],
                  "rounds_submitted": v["last_round"]} for nid, v in st["nodes"].items()]
        last = st["metrics"][-1] if st["metrics"] else None
        # Cohort-1 rooms deliberately keep their models and audit trails isolated.  The
        # authenticated operator dashboard may still need to see whether a partner run
        # completed, so expose a metadata-only summary for populated rooms.  Never expose
        # the raw session id, masked vectors, model JSON, or audit entries from another room.
        solo_sessions = []
        if ISOLATE:
            for session_room, session_state in SESSIONS.items():
                if not session_state["nodes"] and not session_state["metrics"]:
                    continue
                session_last = session_state["metrics"][-1] if session_state["metrics"] else None
                session_nodes = [
                    {"node_id": nid, "name": v["name"], "samples": v["samples"],
                     "rounds_submitted": v["last_round"]}
                    for nid, v in session_state["nodes"].items()
                ]
                solo_sessions.append({
                    "room": fc.sha256_hex(session_room.encode())[:12],
                    "nodes": session_nodes,
                    "rounds": len(session_state["metrics"]),
                    "global_trees": session_last["n_trees"] if session_last else 0,
                    "fed_primary": session_last[PRIMARY] if session_last else None,
                    "global_eps": round(session_state["global_eps"], 3),
                    "rejected_payloads": session_state["rejected"],
                    "last_activity": (session_last or {}).get(
                        "ts", session_state["audit"].entries[-1].get("ts", 0)),
                })
            solo_sessions.sort(key=lambda s: s["last_activity"], reverse=True)
        return {
            "dataset": DATASET, "modality": MODALITY, "modality_info": MODALITY_INFO,
            "classes": CLASSES, "primary_metric": PRIMARY,
            "secure_aggregation": SECURE_COHORT, "cohort": COHORT, "secure_cohort": SECURE_COHORT,
            "isolated": ISOLATE, "solo_shared": SOLO_SHARED,
            "privacy_mode": PRIVACY_MODE,
            "transmission_label": ("pairwise-masked integer leaf counts"
                                   if SECURE_COHORT else "integer leaf counts to central-DP curator"),
            "active_sessions": len(SESSIONS), "nodes": nodes,
            "solo_sessions": solo_sessions,
            "metrics": st["metrics"], "centralized": CENTRAL, "centralized_nonprivate": CEILING,
            "dp": DP, "epsilon_budget": BUDGET, "global_eps": round(st["global_eps"], 3),
            "test_windows": int(len(Y_TEST)), "rejected_payloads": st["rejected"],
            "global_trees": last["n_trees"] if last else 0,
            "fed_primary": last[PRIMARY] if last else None,
            "latest_metrics": last,
            "total_samples": sum(n["samples"] for n in nodes),
            "audit_len": len(st["audit"].entries),
            "audit_persistent": True,
            "invitation_required": REQUIRE_INVITATION,
            "invited_institutions": len(st["invitation_bindings"]),
            "round_timeout_seconds": ROUND_TIMEOUT_SECONDS,
            "cohort_sha256": cohort_fingerprint(st),
            "pending_rounds": [
                {"round": rnd, "submitted": sorted(rec["subs"]),
                 "waiting_for": sorted(set(st["nodes"]) - set(rec["subs"])),
                 "waited_seconds": round(time.time() - rec["started"], 1)}
                for rnd, rec in sorted(st["rounds"].items())],
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
            "invitation_required": REQUIRE_INVITATION,
        },
        "coordinator_public_key_pem": fc.pub_pem(COORD_KEY).decode(),
        "participants": st["evidence_participants"],
        "invitation_bindings": st["invitation_bindings"],
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
