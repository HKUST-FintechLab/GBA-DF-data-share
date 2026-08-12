# Compressed Delivery Timeline

Last updated: 2026-08-12

> **Read [`human-critical-path.md`](human-critical-path.md) alongside this page.** Since 2026-07-26
> the engineering path has run ahead of schedule, and the binding constraint on the pilot date is now
> partner selection, institutional approvals, certificates, and an external review — none of which
> can be accelerated by writing code.

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

**Revision, 2026-07-27.** Assumptions 1 and 5 held better than planned: the Jul 27–Aug 2, Aug 3–9,
and most of the Aug 10–16 engineering landed on 2026-07-26. Assumption 3 (institutions selected
before 2026-08-03) is now the schedule's weakest link, together with certificate and external-review
lead times. An earlier pilot than 2026-09-07 is achievable **only** by starting the owner-required
items in [`human-critical-path.md`](human-critical-path.md) now; no further engineering brings the
date forward.

**Governance refinement, 2026-08-01.** “Institutional approval” is not one generic signature. The
exact path depends on whether all nodes and operators are in Hong Kong, a Shenzhen node uses the GBA
route, a Beijing node exports under the national Mainland route, or an EU/UK/US institution exports
to Hong Kong. The required admission pack and no-go rules are now specified in
[`legal-and-policy.md`](legal-and-policy.md); route selection and signatures remain owner work.

## Progress

- **Shared game shell complete on 2026-08-12 (outside the pilot critical path):** the coordinator and
  desktop client now use one built Phaser/Tiled front end; coordinator state remains behind the same
  read-access boundary, and the client embeds rather than forks its existing `node_core.py` workflow.
  This does not close the owner-required signed-installer or real-OS E2E gates below.

- **Completed early on 2026-07-26:** explicit public/contributor/read endpoint classes; protection for
  status, audit packages, models, and hosted inference; separate contributor and read/operator
  passwords; constant-time checks; request-body limits; a per-process pilot rate limiter; `/health`
  and `/ready`; authenticated dashboard and CLI consumers; and API security regressions.
- **Aug 3–9 gate complete on 2026-07-26:** signed institution invitations with expiry, contributor/
  observer roles, node-key binding on first use, a signed issuance/revocation registry re-read on
  every enrolment and submission, the host-only `admin_invite.py`, and invitation-import UX in both
  the desktop client and `node.py --config`. The node also pins the coordinator against the key
  fingerprint in its invitation and aborts without uploading on a mismatch; the pilot TLS topology is
  frozen and documented. Verified live: an uninvited node cannot register, a revoked institution
  stops being accepted without a coordinator restart, and an invitation pointed at a second
  coordinator holding a different key is refused.
- **Offline browser assets complete on 2026-07-27:** the MediaPipe release is mirrored and pinned by
  a committed hash manifest, the client prefers the verified mirror and hash-checks the loader before
  executing it. The go/no-go item "raw-video extraction works without a public CDN" is satisfied
  technically; redistributing the assets remains an owner licensing decision.
- **Aug 17–23 backend half complete on 2026-07-27:** backup/inspect/restore for the coordinator key,
  signed state, and invitation registry, with a regression covering a clean-host restore; structured
  JSON operational logging with a no-secrets regression. **Aug 24–30 partly complete:** CI runs the
  full suite, a known-vulnerability audit, and a CycloneDX SBOM. The audit immediately failed the
  "no known high-severity dependency issue" gate on a transitively locked `pillow` (20 advisories),
  now upgraded and clean.
- **Aug 10–16 largely complete on 2026-07-26:** cohort-fingerprint binding, round timeout with
  resubmission, idempotent retries, node reconnect, a per-round epsilon ledger, and dashboard
  visibility of a stalled round. Building it surfaced a real corruption bug: a reconnecting node's
  stale `x_pub` would have left residual masks in the pooled sum. Still open in this band: surviving
  a coordinator restart *mid-round* without resubmission, and client-side offline detection.

## Six-week pilot critical path

Stream A and Stream B are repository work. Items marked **[owner]** need a person and are dated in
[`human-critical-path.md`](human-critical-path.md); they are repeated here only so the gates read
completely.

| Period | Stream A — backend/security | Stream B — client/QA | Exit gate |
|---|---|---|---|
| **Jul 27–Aug 2** | ~~Invitation schema and TLS topology~~ (done 07-26); freeze threat model, endpoint permission matrix, and API v1 | Freeze supported OS/version matrix and installer approach; remove stale documentation claims | Scope signed off; no unresolved security architecture decision |
| **Aug 3–9** | ~~Signed institution invitations, roles, expiry/revocation~~ (done 07-26); finish secret handling | ~~Invitation import UX and pinning diagnostics~~ (done 07-26) | An uninvited or revoked node cannot register, read audit/model data, or invoke hosted inference |
| **Aug 10–16** | ~~Idempotency, timeout, cancel/restart, reconnect, epsilon double-spend protection~~ (done 07-26); ~~freeze reconnect-and-resubmit for a coordinator restart mid-round~~ (verified 08-04) | ~~Waiting/retry surfacing~~ (done 07-26); add offline detection and network-failure recovery | ~~Kill/restart/duplicate-submit tests never corrupt a round or spend epsilon twice~~ (covered by `verify_round_integrity.py` and `verify_backup_restore.py`) |
| **Aug 17–23** | ~~Structured logs, backup and restore commands~~ (done 07-27); **[owner]** TLS certificate and coordinator host | ~~Offline-asset tooling with hash verification~~ (done 07-27); packaging specification; **[owner]** code-signing identities, notarization, install on the real machines | Fresh hospital machine installs without Python; coordinator backup restores successfully |
| **Aug 24–30** | ~~CI configuration, dependency/SBOM scanning~~ (done 07-27); ~~load limits and session cleanup~~ (done 08-04) | Windows/macOS E2E, large-video, proxy, offline, localization, and accessibility checks | All P0 CI jobs green; no known high-severity dependency issue |
| **Aug 31–Sep 6** | Fix findings from staging | **[owner]** staging deployment, three full three-institution rehearsals, soak and restore drill on the real host; finalize partner runbook | Go/no-go checklist passes |
| **Sep 7** | **Start monitored three-institution research pilot** | **[owner]** named operator and rollback owner on duty | Pilot only; no clinical claims |

## Pilot go/no-go checklist

All items are mandatory:

- TLS is enforced and coordinator identity is pinned or institutionally trusted.
- Every non-public endpoint has an explicit authorization policy.
- The pilot coordinator runs with `FED_REQUIRE_INVITATION=1`, and every enrolled institution holds a
  current invitation recorded in the signed registry.
- Invitations can expire and be revoked without reinstalling the client.
- Restart, timeout, duplicate submission, and one-node disconnect have documented outcomes.
- No failure path can spend epsilon twice for one completed round.
- No reconnect or dropout path can pool submissions built against different peer sets.
- Coordinator key/state backup and restore are demonstrated on a clean host. **[owner]**
- Audit bundle verification succeeds after restore.
- Signed client packages work on the actual pilot Windows/macOS machines. **[owner]**
- Raw-video extraction works without access to a public CDN, or the pilot formally disables it. (Technically closed 07-27; the **[owner]** part is the licensing decision on redistributing the assets.)
- At least three consecutive full-cohort rehearsals complete without manual database/file editing. **[owner]**
- There are no unresolved critical/high security findings. **[owner]** (external review)
- Each institution approves the exact data flow, roles, purpose, consent/ethics basis, retention,
  audit/model visibility, onward recipients and incident contact; each cross-border direction has its
  applicable impact assessment, contract/filing and jurisdiction lock. **[owner]**
- No real participant data uses cohort 1, plaintext HTTP, a shared demo password, an unapproved
  centralized test set or hosted cross-border inference. **[owner]**

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
