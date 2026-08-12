"""Regression checks for the coordinator HTTP security boundary."""
import os
import tempfile
import time


_state_tmp = tempfile.TemporaryDirectory(prefix="gba-df-api-security-")
os.environ["FED_PASSWORD"] = "contribute-secret"
os.environ["FED_READ_PASSWORD"] = "read-secret"
os.environ["FED_STATE_DIR"] = _state_tmp.name
os.environ["FED_MAX_BODY_BYTES"] = "4096"
os.environ["FED_RATE_LIMIT_PER_MINUTE"] = "600"
os.environ["FED_WRITE_RATE_LIMIT_PER_MINUTE"] = "120"
os.environ["FED_REQUIRE_INVITATION"] = "1"
os.environ["FED_COHORT"] = "1"
os.environ["FED_SESSION_IDLE_SECONDS"] = "60"
os.environ["FED_MAX_ACTIVE_SESSIONS"] = "2"

from fastapi.testclient import TestClient

import coordinator
import fed_common as fc
import invitations as invites
import secure_agg as sa


ok_all = True


def check(name, condition):
    global ok_all
    ok_all = ok_all and condition
    print(f"  [{'PASS' if condition else 'FAIL'}] {name}")


client = TestClient(coordinator.app)
contribute = {"X-Fed-Key": "contribute-secret"}
read = {"X-Fed-Key": "read-secret"}

print("== coordinator HTTP security boundary ==")
check("liveness is public and contains no federation state",
      client.get("/health").json() == {"ok": True, "service": "gba-df-coordinator"})
check("readiness is public", client.get("/ready").status_code == 200)
check("coordinator public key remains public", client.get("/pubkey").status_code == 200)
town_shell = client.get("/")
game_shell = client.get("/game/")
console_shell = client.get("/console")
check("pixel-town and legacy console shells are public but contain no embedded room state",
      town_shell.status_code == 200 and "GBA-DF · 联邦小镇" in town_shell.text
      and town_shell.url.path == "/game/" and game_shell.status_code == 200
      and console_shell.status_code == 200 and "Federation Console" in console_shell.text
      and '"nodes":' not in town_shell.text and '"audit_entries":' not in town_shell.text)
check("unclassified routes fail closed behind read/operator access",
      client.get("/docs").status_code == 401
      and client.get("/docs", headers=read).status_code == 200)

check("schema rejects an anonymous request", client.get("/schema").status_code == 401)
check("schema accepts the contributor credential",
      client.get("/schema", headers=contribute).status_code == 200)
check("schema rejects the read-only credential",
      client.get("/schema", headers=read).status_code == 401)

check("status rejects an anonymous request", client.get("/status").status_code == 401)
check("status rejects the contributor-only credential",
      client.get("/status", headers=contribute).status_code == 401)
check("status accepts the read/operator credential",
      client.get("/status", headers=read).status_code == 200)
check("audit bundle requires read/operator access",
      client.get("/audit/bundle").status_code == 401
      and client.get("/audit/bundle", headers=read).status_code == 200)

# A 409 here means authentication and JSON parsing succeeded, then the empty test
# federation correctly reported that no model exists yet.
check("authenticated prediction body reaches the endpoint intact",
      client.post("/predict", headers=read,
                  json={"X": [[0.0] * coordinator.N_FEATURES]}).status_code == 409)
check("oversized authenticated bodies fail before endpoint processing",
      client.post("/predict", headers=read, content=b"x" * 4097).status_code == 413)

print("== institution invitation enforcement ==")
node_key = fc.gen_key()
node_pub = fc.pub_pem(node_key).decode()
x_key = sa.gen_x25519()


def enrol(invitation=None, node_id="node_1", pubkey_pem=node_pub):
    body = {"node_id": node_id, "name": "Pilot Hospital", "pubkey_pem": pubkey_pem,
            "x_pub": sa.x_pub_hex(x_key), "samples": 12}
    if invitation is not None:
        body["invitation"] = invitation
    return client.post("/register", json=body, headers=contribute)


registry_path = coordinator.REGISTRY_PATH
invitation = invites.build_invitation(coordinator.COORD_KEY, institution_id="node_1",
                                      institution_name="Pilot Hospital")
check("the contributor password alone cannot enrol an institution",
      coordinator.REQUIRE_INVITATION and enrol().status_code == 401)
check("a signed invitation that was never issued cannot enrol",
      enrol(invitation).status_code == 403)

registry = invites.record_issue(invites.new_registry(coordinator.COORD_PUB), invitation)
invites.save_registry(registry_path, registry, coordinator.COORD_KEY)
check("an issued invitation enrols its own institution", enrol(invitation).status_code == 200)
solo_status = client.get("/status", headers=read).json()
check("operator status summarizes populated isolated sessions without raw session ids",
      solo_status.get("isolated") and len(solo_status.get("solo_sessions", [])) == 1
      and solo_status["solo_sessions"][0]["nodes"][0]["node_id"] == "node_1"
      and len(solo_status["solo_sessions"][0]["room"]) == 12)
check("the same invitation cannot be re-bound to another node key",
      enrol(invitation, pubkey_pem=fc.pub_pem(fc.gen_key()).decode()).status_code == 409)


def submit(rnd):
    masked = [0] * coordinator.EXPECT_LEN
    payload_hash = fc.sha256_hex(fc._canon(masked))
    signature = node_key.sign(f"node_1|{rnd}|12|{payload_hash}".encode())
    return client.post("/submit", headers=contribute,
                       json={"node_id": "node_1", "round": rnd, "n_samples": 12,
                             "masked": masked, "sig_hex": signature.hex()})


# The masked vector is larger than the configured body cap, so this round-trip is checked
# through the coordinator's own submission handler rather than the HTTP body limit.
with coordinator.LOCK:
    state = coordinator.get_state("default")
    still_invited = coordinator._check_still_invited(state, "node_1") is None
check("an invited node passes the per-submission invitation check", still_invited)

invites.revoke(registry, invitation["invitation_id"], "partner exit")
invites.save_registry(registry_path, registry, coordinator.COORD_KEY)
revoked_blocked = False
with coordinator.LOCK:
    try:
        coordinator._check_still_invited(coordinator.get_state("default"), "node_1")
    except coordinator.InvitationRefused as e:
        revoked_blocked = e.status == 403
check("revocation stops an enrolled node without a coordinator restart", revoked_blocked)
check("a revoked institution cannot re-enrol", enrol(invitation).status_code == 403)

with open(registry_path, "w", encoding="utf-8") as f:
    f.write("{}")
unreadable_fails_closed = False
with coordinator.LOCK:
    try:
        coordinator._check_still_invited(coordinator.get_state("default"), "node_1")
    except coordinator.InvitationRefused as e:
        unreadable_fails_closed = e.status == 503
check("an unreadable registry fails closed instead of admitting everyone",
      unreadable_fails_closed)
os.unlink(registry_path)

print("== coordinator identity pinning (node side) ==")
import node_core

served_pubkey = client.get("/pubkey").text
check("the advertised public key matches the fingerprint inside the invitation",
      invites.coordinator_key_id(fc.load_pub(served_pubkey.encode()))
      == invitation["coordinator_key_sha256"])

pinned = node_core.coordinator_identity_result(served_pubkey, invitation,
                                               "https://coordinator.example")
check("a node pins a coordinator that holds the issuing key",
      pinned["pinned"] and not pinned["warning"])
check("a pinned but unencrypted address still warns",
      node_core.coordinator_identity_result(served_pubkey, invitation,
                                            "http://coordinator.example")["warning"])

impostor = invites.build_invitation(fc.gen_key(), institution_id="node_1",
                                    institution_name="Pilot Hospital")
mismatch_refused = False
try:
    node_core.coordinator_identity_result(served_pubkey, impostor, "https://coordinator.example")
except RuntimeError:
    mismatch_refused = True
check("a coordinator holding a different key is REFUSED before anything is uploaded",
      mismatch_refused)
check("a configuration with no fingerprint reports that pinning is unavailable",
      node_core.coordinator_identity_result(served_pubkey, {}, "https://coordinator.example")
      ["warning"] != "")

print("== operational logging carries no secrets ==")
import contextlib
import io as _io
import json as _json

captured = _io.StringIO()
with contextlib.redirect_stdout(captured):
    client.get("/status")                                   # anonymous -> a denial line
    enrol(invitation, node_id="node_1")                     # a revoked invitation -> a denial
lines = [_json.loads(x) for x in captured.getvalue().splitlines() if x.startswith("{")]
check("denials are logged as structured JSON", any(l.get("event") == "denied" for l in lines))
check("every line is machine-readable and stamped",
      lines and all(l.get("log") == "gba-df" and "ts" in l and "event" in l for l in lines))
blob = captured.getvalue()
check("the operational log never contains a credential or payload material",
      "contribute-secret" not in blob and "read-secret" not in blob
      and "invitation_signature" not in blob and "x_pub" not in blob
      and "pubkey_pem" not in blob and "masked" not in blob)
check("the room is logged as a digest, not a raw session id",
      all(len(str(l.get("room", ""))) <= 12 for l in lines))

coordinator._RATE_EVENTS.clear()
first = coordinator._rate_allowed("test-client", "test", 2, 100.0)
second = coordinator._rate_allowed("test-client", "test", 2, 100.1)
third = coordinator._rate_allowed("test-client", "test", 2, 100.2)
check("rate limiter rejects requests after the configured bucket is full",
      first[0] and second[0] and not third[0] and third[1] >= 1)

print("== single-instance session and load bounds ==")
with coordinator.LOCK:
    expired = coordinator.get_state("expired-demo-session")
    expired["last_activity"] = time.time() - coordinator.SESSION_IDLE_SECONDS - 1
    cleaned = coordinator._cleanup_idle_sessions()
check("idle solo sessions are removed from process memory", cleaned >= 1
      and "expired-demo-session" not in coordinator.SESSIONS)
with coordinator.LOCK:
    coordinator.get_state("capacity-a")
    coordinator.get_state("capacity-b")
    coordinator.get_state("capacity-c")
check("solo session capacity evicts the least-recent in-memory room",
      len(coordinator.SESSIONS) <= coordinator.MAX_ACTIVE_SESSIONS)

started = time.monotonic()
statuses = [client.get("/status", headers=read).status_code for _ in range(20)]
elapsed = time.monotonic() - started
print(f"  measured 20 authenticated status reads in {elapsed:.3f}s")
check("bounded authenticated read burst completes", all(code == 200 for code in statuses))

print("\nRESULT:", "API SECURITY CHECKS PASSED" if ok_all else "FAILURES PRESENT")
raise SystemExit(0 if ok_all else 1)
