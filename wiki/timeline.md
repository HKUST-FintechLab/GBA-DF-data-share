# Compressed Delivery Timeline

Last updated: 2026-07-26

## Targets

- **Pilot go-live target:** 2026-09-07.
- **Production research-platform target:** 2026-10-26.
- **Schedule contingency:** if independent review finds a secure-aggregation issue, production moves
  to 2026-11-16 rather than weakening the protocol.

## Assumptions required to hold the compressed schedule

1. Two engineers work in parallel:
   - Stream A — coordinator, protocol reliability, security, and deployment;
   - Stream B — desktop packaging, offline MediaPipe, UI, E2E tests, and partner documentation.
2. Security/DevOps support is available at least two days per week.
3. Three pilot institutions and their IT contacts are selected before 2026-08-03.
4. Product/security decisions are made within one business day.
5. No new modality, model, benchmark, or dashboard feature enters the pilot critical path.
6. The pilot uses monitored abort/restart handling; full cryptographic dropout recovery is a
   post-pilot production requirement.

If only one engineer is available, move pilot go-live to 2026-09-28 and production to 2026-12.

## Progress

- **Completed early on 2026-07-26:** explicit public/contributor/read endpoint classes; protection for
  status, audit packages, models, and hosted inference; separate contributor and read/operator
  passwords; constant-time checks; request-body limits; a per-process pilot rate limiter; `/health`
  and `/ready`; authenticated dashboard and CLI consumers; and API security regressions.
- **Aug 3–9 gate met early on 2026-07-26:** signed institution invitations with expiry, contributor/
  observer roles, node-key binding on first use, a signed issuance/revocation registry re-read on
  every enrolment and submission, the host-only `admin_invite.py`, and invitation-import UX in both
  the desktop client and `node.py --config`. Verified live: an uninvited node cannot register, and a
  revoked institution stops being accepted without a coordinator restart.
- **Aug 3–9 gate complete on 2026-07-26:** the node pins the coordinator against the key fingerprint
  in its invitation before registering and aborts without uploading on a mismatch; the desktop client
  runs the same check at *Test connection*; the pilot TLS topology is frozen and documented.
  Verified live against a second coordinator holding a different key.

## Six-week pilot critical path

| Period | Stream A — backend/security | Stream B — client/QA | Exit gate |
|---|---|---|---|
| **Jul 27–Aug 2** | ~~Invitation schema and TLS topology~~ (done 07-26); freeze threat model, endpoint permission matrix, and API v1 | Freeze supported OS/version matrix and installer approach; remove stale documentation claims | Scope signed off; no unresolved security architecture decision |
| **Aug 3–9** | ~~Signed institution invitations, roles, expiry/revocation~~ (done 07-26); finish secret handling | ~~Invitation import UX and pinning diagnostics~~ (done 07-26) | An uninvited or revoked node cannot register, read audit/model data, or invoke hosted inference |
| **Aug 10–16** | Add durable round state, idempotency, timeout, cancel/restart, reconnect, and epsilon double-spend protection | Add clear waiting/offline/retry UI and network-failure recovery | Kill/restart/duplicate-submit tests never corrupt a round or spend epsilon twice |
| **Aug 17–23** | Add structured logs, metrics, alerts, backup and restore commands, and hardened TLS deployment (`/health` and `/ready` complete) | Produce signed pilot installers; bundle/cache MediaPipe/WASM and verify asset hashes | Fresh hospital machine installs without Python; coordinator backup restores successfully |
| **Aug 24–30** | Add CI, protocol integration tests, load limits, session cleanup, dependency/SBOM scanning | Run Windows/macOS E2E, large-video, proxy, offline, localization, and accessibility checks | All P0 CI jobs green; no known high-severity dependency issue |
| **Aug 31–Sep 6** | Deploy staging and fix security/operations findings | Conduct at least three complete three-institution rehearsals and finalize partner runbook | Go/no-go checklist passes |
| **Sep 7** | **Start monitored three-institution research pilot** | Named operator and rollback owner on duty | Pilot only; no clinical claims |

## Pilot go/no-go checklist

All items are mandatory:

- TLS is enforced and coordinator identity is pinned or institutionally trusted.
- Every non-public endpoint has an explicit authorization policy.
- The pilot coordinator runs with `FED_REQUIRE_INVITATION=1`, and every enrolled institution holds a
  current invitation recorded in the signed registry.
- Invitations can expire and be revoked without reinstalling the client.
- Restart, timeout, duplicate submission, and one-node disconnect have documented outcomes.
- No failure path can spend epsilon twice for one completed round.
- Coordinator key/state backup and restore are demonstrated on a clean host.
- Audit bundle verification succeeds after restore.
- Signed client packages work on the actual pilot Windows/macOS machines.
- Raw-video extraction works without access to a public CDN, or the pilot formally disables it.
- At least three consecutive full-cohort rehearsals complete without manual database/file editing.
- There are no unresolved critical/high security findings.
- Each institution approves the data-processing purpose, retention, audit visibility, and incident contact.

## Seven-week production track after pilot start

| Period | Deliverable |
|---|---|
| **Sep 7–20** | Observe pilot, fix operational defects, finalize protocol/API compatibility contract |
| **Sep 21–Oct 4** | Implement threshold/dropout recovery and adversarial protocol tests |
| **Oct 5–11** | Move federation state to a transactional database; add multi-worker safety and key-management integration |
| **Oct 12–18** | High-availability deployment, restore/failover drill, external audit anchoring, 72-hour soak test |
| **Oct 19–25** | Independent penetration/protocol review, remediation, release candidate and SLA/runbook approval |
| **Oct 26** | **Production research-platform target** |

## Work intentionally excluded from this timeline

- Clinical efficacy claims or diagnostic use.
- Medical-device classification/registration.
- Prospective multi-centre clinical validation.
- New modalities or classifier redesign.
- Byzantine-proof input validity/range proofs beyond the agreed trusted-partner research model.

Those items need their own evidence, governance, and regulatory schedule.
