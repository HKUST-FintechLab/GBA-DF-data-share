"""Offline administration of institution invitations.

Run this on the coordinator host, as the account that owns the coordinator state directory.
It signs invitations with the coordinator's existing Ed25519 key and maintains the signed
issuance/revocation ledger the running coordinator reads on every enrolment and submission.
It is deliberately NOT an HTTP endpoint: issuing and revoking institution identities needs
host access, not a bearer token.

  # one-time: start the coordinator once so its key exists, then
  uv run python admin_invite.py issue --institution-id node_1 \
      --name "HK Children's Hospital" --coordinator-url https://coordinator.example \
      --days 30 --include-password --out invite-node_1.json
  uv run python admin_invite.py list
  uv run python admin_invite.py revoke --invitation-id <id> --reason "partner exit"

Revocation takes effect on the coordinator's next enrolment or submission check — no
restart, and no client reinstall.

Environment: FED_STATE_DIR, FED_INVITATION_REGISTRY, FED_PASSWORD (same values the
coordinator runs with).
"""
import argparse
import os
import time

import client_config as cfg
import fed_common as fc
import invitations as invites

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.abspath(os.path.expanduser(
    os.environ.get("FED_STATE_DIR", os.path.join(HERE, "data", "coordinator_state"))))
REGISTRY_PATH = os.path.abspath(os.path.expanduser(os.environ.get(
    "FED_INVITATION_REGISTRY", os.path.join(STATE_DIR, "invitations.json"))))
KEY_PATH = os.path.join(STATE_DIR, "coordinator_key.pem")


def _load_coordinator_key():
    """Load the coordinator's signing key. Never creates one: invitations must be signed by
    the key the running coordinator actually verifies against."""
    if not os.path.exists(KEY_PATH):
        raise SystemExit(f"coordinator key not found: {KEY_PATH}\n"
                         f"Start the coordinator once (or set FED_STATE_DIR) before issuing "
                         f"invitations.")
    with open(KEY_PATH, "rb") as f:
        return fc.load_priv(f.read())


def _load_registry(key):
    try:
        return invites.load_registry(REGISTRY_PATH, key.public_key())
    except (OSError, ValueError, RuntimeError) as e:
        raise SystemExit(f"cannot read the invitation registry: {e}")


def _human_time(ts) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(float(ts)))


def cmd_issue(args):
    key = _load_coordinator_key()
    registry = _load_registry(key)
    try:
        invitation = invites.build_invitation(
            key, institution_id=args.institution_id, institution_name=args.name,
            role=args.role, lifetime_seconds=args.days * 24 * 3600.0)
        password = os.environ.get("FED_PASSWORD", "") if args.include_password else ""
        config = cfg.build(args.coordinator_url, password=password,
                           node_id=args.institution_id, display_name=args.name,
                           invitation=invitation)
    except ValueError as e:
        raise SystemExit(f"cannot issue invitation: {e}")

    invites.record_issue(registry, invitation)
    invites.save_registry(REGISTRY_PATH, registry, key)
    out = cfg.write(args.out or f"invite-{args.institution_id}.json", config)

    print(f"Issued invitation {invitation['invitation_id']}")
    print(f"  institution : {args.institution_id} ({args.name})")
    print(f"  role        : {args.role}")
    print(f"  valid until : {_human_time(invitation['expires_at'])}")
    print(f"  registry    : {REGISTRY_PATH}")
    print(f"  client file : {out} (mode 0600)")
    if args.include_password and not password:
        print("  NOTE: FED_PASSWORD is unset, so no password was embedded.")
    elif password:
        print("  The file contains the shared password — send it over an approved channel only.")


def cmd_list(args):
    key = _load_coordinator_key()
    registry = _load_registry(key)
    records = registry.get("invitations", {})
    if not records:
        print(f"No invitations issued yet ({REGISTRY_PATH}).")
        return
    now = time.time()
    print(f"{'invitation_id':34} {'institution':20} {'role':12} {'status':10} until")
    for invitation_id, r in sorted(records.items(), key=lambda kv: kv[1]["issued_at"]):
        if r.get("revoked_at"):
            status = "revoked"
        elif float(r["expires_at"]) < now:
            status = "expired"
        else:
            status = "active"
        print(f"{invitation_id:34} {r['institution_id']:20} {r['role']:12} {status:10} "
              f"{_human_time(r['expires_at'])}")


def cmd_revoke(args):
    key = _load_coordinator_key()
    registry = _load_registry(key)
    if not invites.revoke(registry, args.invitation_id, args.reason):
        raise SystemExit("no such active invitation (unknown id, or already revoked)")
    invites.save_registry(REGISTRY_PATH, registry, key)
    record = registry["invitations"][args.invitation_id]
    print(f"Revoked {args.invitation_id} ({record['institution_id']}).")
    print("The coordinator refuses further enrolment and submissions from that institution "
          "on its next check; already-aggregated rounds are unaffected.")


def main():
    parser = argparse.ArgumentParser(description="Issue and revoke GBA-DF institution invitations")
    sub = parser.add_subparsers(dest="command", required=True)

    issue = sub.add_parser("issue", help="mint a signed invitation and a partner client config")
    issue.add_argument("--institution-id", required=True,
                       help="node id the institution will register with")
    issue.add_argument("--name", required=True, help="institution display name")
    issue.add_argument("--coordinator-url", required=True,
                       help="partner-reachable http(s) coordinator origin")
    issue.add_argument("--role", default="contributor", choices=list(invites.ROLES))
    issue.add_argument("--days", type=float, default=30.0, help="validity in days (default: 30)")
    issue.add_argument("--include-password", action="store_true",
                       help="embed FED_PASSWORD in the exported client config")
    issue.add_argument("--out", help="output path (default: invite-<institution-id>.json)")
    issue.set_defaults(func=cmd_issue)

    listing = sub.add_parser("list", help="show issued invitations and their status")
    listing.set_defaults(func=cmd_list)

    revoking = sub.add_parser("revoke", help="revoke an issued invitation")
    revoking.add_argument("--invitation-id", required=True)
    revoking.add_argument("--reason", default="", help="recorded in the signed registry")
    revoking.set_defaults(func=cmd_revoke)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
