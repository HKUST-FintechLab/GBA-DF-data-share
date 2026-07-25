"""Regression checks for the coordinator HTTP security boundary."""
import os
import tempfile


_state_tmp = tempfile.TemporaryDirectory(prefix="gba-df-api-security-")
os.environ["FED_PASSWORD"] = "contribute-secret"
os.environ["FED_READ_PASSWORD"] = "read-secret"
os.environ["FED_STATE_DIR"] = _state_tmp.name
os.environ["FED_MAX_BODY_BYTES"] = "1024"
os.environ["FED_RATE_LIMIT_PER_MINUTE"] = "600"
os.environ["FED_WRITE_RATE_LIMIT_PER_MINUTE"] = "120"

from fastapi.testclient import TestClient

import coordinator


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
      client.post("/predict", headers=read, content=b"x" * 1025).status_code == 413)

coordinator._RATE_EVENTS.clear()
first = coordinator._rate_allowed("test-client", "test", 2, 100.0)
second = coordinator._rate_allowed("test-client", "test", 2, 100.1)
third = coordinator._rate_allowed("test-client", "test", 2, 100.2)
check("rate limiter rejects requests after the configured bucket is full",
      first[0] and second[0] and not third[0] and third[1] >= 1)

print("\nRESULT:", "API SECURITY CHECKS PASSED" if ok_all else "FAILURES PRESENT")
raise SystemExit(0 if ok_all else 1)
