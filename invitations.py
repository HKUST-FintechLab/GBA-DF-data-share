"""Signed institution invitations — per-institution identity on top of the shared password.

A shared password says "this request came from someone who knows the token". It cannot say
WHICH institution is speaking, cannot expire, and cannot be withdrawn from one partner
without rotating everyone. An invitation closes that gap:

  * the coordinator SIGNS a small JSON record binding an institution id, a display name, a
    role, an issue/expiry window, and the coordinator public key it is valid against;
  * the node presents that record at /register and the coordinator binds it, permanently, to
    the node's own Ed25519 public key (first use wins — a leaked invitation cannot be
    re-bound to a different key afterwards);
  * a separate coordinator-signed REGISTRY records every issued invitation and any
    revocation, so an institution can be cut off without reinstalling any client.

The registry is written only by the offline admin CLI (admin_invite.py) and only READ by the
running coordinator, so the two never race for the same file. Both artifacts fail closed:
a bad signature, an unknown format, or a truncated file is treated as "not authorised".
"""
import base64
import json
import os
import secrets
import tempfile
import time

from cryptography.hazmat.primitives import serialization

import fed_common as fc

INVITATION_FORMAT = "gba-df-invitation"
INVITATION_VERSION = 1
REGISTRY_FORMAT = "gba-df-invitation-registry"
REGISTRY_VERSION = 1

# Institution roles. `contributor` may register and submit masked counts; `observer` is an
# invited institution that is entitled to read evidence but must not join a training cohort.
ROLES = ("contributor", "observer")

# Tolerance for clock skew between the issuing admin host and the coordinator.
CLOCK_SKEW_SECONDS = 300.0
MAX_LIFETIME_SECONDS = 365 * 24 * 3600.0

_STR_FIELDS = ("invitation_id", "institution_id", "institution_name", "role",
               "coordinator_key_sha256")
_NUM_FIELDS = ("issued_at", "expires_at")


def coordinator_key_id(coord_pub) -> str:
    """Stable identifier for the coordinator key an invitation is valid against."""
    pem = coord_pub.public_bytes(serialization.Encoding.PEM,
                                 serialization.PublicFormat.SubjectPublicKeyInfo)
    return fc.sha256_hex(pem)


def _sealed(body: dict, signer_key, digest_field: str, sig_field: str) -> dict:
    digest = fc.sha256_hex(fc._canon(body))
    return {**body, digest_field: digest,
            sig_field: base64.b64encode(signer_key.sign(digest.encode())).decode()}


def _seal_valid(sealed: dict, pub, digest_field: str, sig_field: str) -> bool:
    try:
        body = {k: v for k, v in sealed.items() if k not in {digest_field, sig_field}}
        digest = fc.sha256_hex(fc._canon(body))
        if sealed.get(digest_field) != digest:
            return False
        signature = base64.b64decode(sealed.get(sig_field, ""), validate=True)
        return fc.verify_sig(pub, signature, digest.encode())
    except Exception:
        return False


# ---------- issuing ----------
def build_invitation(signer_key, *, institution_id: str, institution_name: str,
                     role: str = "contributor", lifetime_seconds: float = 30 * 24 * 3600.0,
                     issued_at: float = None, invitation_id: str = None) -> dict:
    """Mint a coordinator-signed invitation for one institution."""
    if not institution_id or not isinstance(institution_id, str) or len(institution_id) > 128:
        raise ValueError("institution_id must be a non-empty string of at most 128 characters")
    if not institution_name or not isinstance(institution_name, str) or len(institution_name) > 160:
        raise ValueError("institution_name must be a non-empty string of at most 160 characters")
    if role not in ROLES:
        raise ValueError(f"role must be one of {', '.join(ROLES)}")
    if not 60.0 <= float(lifetime_seconds) <= MAX_LIFETIME_SECONDS:
        raise ValueError("lifetime must be between 60 seconds and 365 days")
    issued = float(issued_at if issued_at is not None else time.time())
    body = {
        "format": INVITATION_FORMAT, "version": INVITATION_VERSION,
        "invitation_id": invitation_id or secrets.token_hex(16),
        "institution_id": institution_id, "institution_name": institution_name,
        "role": role,
        "coordinator_key_sha256": coordinator_key_id(signer_key.public_key()),
        "issued_at": round(issued, 3), "expires_at": round(issued + float(lifetime_seconds), 3),
    }
    return _sealed(body, signer_key, "invitation_sha256", "invitation_signature")


# ---------- verifying ----------
def verify_invitation(inv, coord_pub, *, now: float = None, expected_institution: str = None,
                      require_role: str = None) -> str:
    """Return '' when the invitation is authentic and currently valid, else a reason.

    Never raises: any malformed input becomes a rejection reason, so a hostile payload
    cannot crash the coordinator's registration path.
    """
    try:
        if not isinstance(inv, dict):
            return "invitation: not an object"
        if inv.get("format") != INVITATION_FORMAT or inv.get("version") != INVITATION_VERSION:
            return "invitation: unsupported format"
        for field in _STR_FIELDS:
            value = inv.get(field)
            if not isinstance(value, str) or not value or len(value) > 256:
                return f"invitation: bad {field}"
        for field in _NUM_FIELDS:
            value = inv.get(field)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                return f"invitation: bad {field}"
        if inv.get("role") not in ROLES:
            return "invitation: unknown role"
        if inv["coordinator_key_sha256"] != coordinator_key_id(coord_pub):
            return "invitation: issued for a different coordinator key"
        if not _seal_valid(inv, coord_pub, "invitation_sha256", "invitation_signature"):
            return "invitation: signature verification failed"
        now = float(now if now is not None else time.time())
        if float(inv["expires_at"]) <= float(inv["issued_at"]):
            return "invitation: empty validity window"
        if float(inv["expires_at"]) - float(inv["issued_at"]) > MAX_LIFETIME_SECONDS:
            return "invitation: lifetime exceeds the permitted maximum"
        if now + CLOCK_SKEW_SECONDS < float(inv["issued_at"]):
            return "invitation: not yet valid"
        if now - CLOCK_SKEW_SECONDS > float(inv["expires_at"]):
            return "invitation: expired"
        if expected_institution is not None and inv["institution_id"] != expected_institution:
            return "invitation: institution does not match the registering node id"
        if require_role is not None and inv["role"] != require_role:
            return f"invitation: role '{inv['role']}' is not '{require_role}'"
        return ""
    except Exception as e:                       # never throw — always a graceful reason
        return f"invitation: malformed ({type(e).__name__})"


# ---------- registry (issuance ledger + revocation list) ----------
def new_registry(coord_pub) -> dict:
    return {"format": REGISTRY_FORMAT, "version": REGISTRY_VERSION,
            "coordinator_key_sha256": coordinator_key_id(coord_pub), "invitations": {}}


def save_registry(path: str, registry: dict, signer_key) -> None:
    """Atomically persist the coordinator-signed registry with owner-only permissions."""
    body = {**registry, "updated_at": round(time.time(), 3)}
    body.pop("registry_sha256", None)
    body.pop("registry_signature", None)
    sealed = _sealed(body, signer_key, "registry_sha256", "registry_signature")
    parent = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".gba-df-invitations-", dir=parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(fc._canon(sealed))
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_registry(path: str, coord_pub) -> dict:
    """Read the registry. A missing file means 'nothing issued yet'; a corrupt or
    wrongly-signed file raises, so the coordinator refuses to serve rather than silently
    dropping revocations."""
    if not os.path.exists(path):
        return new_registry(coord_pub)
    with open(path, encoding="utf-8") as f:
        saved = json.load(f)
    if (not isinstance(saved, dict) or saved.get("format") != REGISTRY_FORMAT
            or saved.get("version") != REGISTRY_VERSION
            or saved.get("coordinator_key_sha256") != coordinator_key_id(coord_pub)
            or not isinstance(saved.get("invitations"), dict)
            or not _seal_valid(saved, coord_pub, "registry_sha256", "registry_signature")):
        raise RuntimeError(f"invalid invitation registry: {path}")
    return saved


def record_issue(registry: dict, inv: dict) -> dict:
    """Add a freshly minted invitation to the ledger."""
    registry.setdefault("invitations", {})[inv["invitation_id"]] = {
        "institution_id": inv["institution_id"],
        "institution_name": inv["institution_name"],
        "role": inv["role"], "issued_at": inv["issued_at"],
        "expires_at": inv["expires_at"], "revoked_at": None, "revoked_reason": "",
    }
    return registry


def revoke(registry: dict, invitation_id: str, reason: str = "", at: float = None) -> bool:
    """Mark an invitation revoked. Returns False if it is unknown or already revoked."""
    record = registry.get("invitations", {}).get(invitation_id)
    if record is None or record.get("revoked_at"):
        return False
    record["revoked_at"] = round(float(at if at is not None else time.time()), 3)
    record["revoked_reason"] = str(reason or "")[:256]
    return True


def registry_status(registry: dict, invitation_id: str) -> str:
    """Return '' when the registry permits this invitation, else a rejection reason.

    An invitation absent from the ledger is rejected: only invitations the administrator
    actually recorded may register, so a signing key that briefly leaked cannot be replayed
    into an unlogged enrolment.
    """
    record = registry.get("invitations", {}).get(invitation_id)
    if record is None:
        return "invitation: not present in the coordinator registry"
    if record.get("revoked_at"):
        return "invitation: revoked"
    return ""
