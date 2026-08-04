# State of Project

Last updated: 2026-08-04

## Executive status

GBA-DF is a functioning engineering POC. It is ready for demonstrations and internal dry runs, and it
has the core ingredients for a controlled research pilot: four versioned front ends across three
signal families, local extraction,
pairwise-masked secure aggregation, coordinator-enforced central DP, a global epsilon budget,
signed/persistent audit evidence, real JSON-payload accounting, a desktop client, and a dashboard.

It is **not yet ready for unattended exposure on a hospital network**. Institution identity, round
reliability, backup/restore, operational logging, offline browser-asset tooling, and CI are now done.
What remains is installable client delivery, real-OS E2E, institutional governance, and the
owner-required items in [`human-critical-path.md`](human-critical-path.md). None of it is another
model feature.

The shipped training path is a **labeled supervised DP forest**. Unlabeled training,
self-supervised learning, semi-supervised learning and federated neural encoders are documented
post-pilot research tracks, not implemented capabilities. The staged decision and backlog are in
[`learning-modes.md`](learning-modes.md) and [`../TODO.md`](../TODO.md).

The legal/data-governance review is now documented in
[`legal-and-policy.md`](legal-and-policy.md). It confirms that raw-data-local, secure aggregation and
DP reduce risk but do not automatically make updates, models, metrics or audit bundles anonymous, nor
remove cross-border, consent or ethics duties. The review is a planning aid, not an institutional
approval; every real-data institution still needs a route-specific admission pack and written sign-off.

## Readiness by target

| Target | Readiness estimate | Status |
|---|---:|---|
| Demonstration/internal dry run | 90%+ | Available now |
| Controlled three-institution research pilot | ~85% (engineering) | Remaining gap is mostly owner-required, not code |
| 7×24 production research platform | ~40% | Follows the pilot |
| Clinical screening/diagnostic deployment | <20% | Separate validation/regulatory programme |

These percentages are planning estimates, not formal maturity certifications.

## Verified baseline

Verified on 2026-07-30:

- `uv run python verify_security.py` — the complete core and coordinator
  HTTP/invitation/pinning/logging, shared-solo, CDP-adapter, round-integrity, and backup/restore
  suites passed.
- `uv run python modalities.py` — eyegaze, action, experimental action_cdp, and neuro extraction
  checks passed.
- `uv run python client_app.py --selftest` — desktop API smoke test passed.
- Live `action_cdp` rehearsal: three nodes completed a full secure-aggregation round over the
  104-feature schema and produced a downloadable DP JSON forest; this synthetic dry run verifies the
  integration path, not screening utility.
- Live three-command rehearsal: an issued invitation enrolled and trained a node, an uninvited node
  was refused, and a revocation stopped the enrolled node without restarting the coordinator.
- Live pinning rehearsal against two coordinators: the node trained against the one holding the
  issuing key and aborted, uploading nothing, when the same invitation was pointed at the other.

## Pilot blockers

| Priority | Blocker | Pilot solution |
|---|---|---|
| P0 | Coordinator is a single-process service with in-memory live sessions | Supported single-instance pilot deployment, health checks, and monitoring. Backup/restore and structured operational logs are done; a coordinator restart mid-round still requires the nodes to resubmit that round |
| P0 | Desktop client still depends on a Python environment | Signed Windows/macOS pilot builds with fixed dependencies |
| P0 | ~~Browser pose extraction depends on a public CDN~~ | Closed 2026-07-27: `fetch_offline_assets.py` mirrors and hash-pins the assets, and the client prefers the verified mirror. Whether to redistribute them is an owner licensing decision |
| P0 | Desktop/E2E coverage on the real operating systems | CI now runs the full suite, a dependency audit, and an SBOM on every push; Windows/macOS end-to-end on the pilot machines remains owner work |
| P0 | Governance is not encoded in the product | Complete the route-specific admission pack in `legal-and-policy.md`: data-flow and role maps, ethics/consent, DPIA/PIPIA, applicable transfer contract/filing, retention/incident/onward-transfer terms, and institution approvals |

## Recently completed

- **2026-08-01 — Contribution-impact and transparent coordinator console:** the coordinator now
  reports binary held-out diagnostics with ASD explicitly treated as the positive class: AUC,
  balanced accuracy, sensitivity, specificity, precision, F1, MCC, Brier score, ECE, a confusion
  matrix, and compact ROC points. The dashboard adopts the `frontendv2` full-canvas topology and
  makes the latest round's honest metric delta, added trees, privacy spend, local sample count, and
  signed audit events visually prominent. Its animation and wording now distinguish three-or-more
  node pairwise-masked secure aggregation from cohort-1 central-DP sharing; the latter is never
  labelled secure aggregation. The desktop scan summary separately reports files per ASD/TD class
  and derived training windows, so a 10+10 video batch is visible locally without sending class
  counts to the coordinator. This remains demo/experiment UX and does not enter the September pilot
  critical path or establish clinical validity.

- **2026-07-31 — Switchable desktop interfaces and global settings:** the partner desktop client
  now keeps one shared upload/training implementation while offering the existing blue-and-white
  interface and the `frontendv2` full-canvas dark federation console as persistent, instantly
  switchable visual modes. The latter retains the branch's canvas-drawn modality sketches, corner
  chrome, scene caption, and bottom navigation instead of translating them into cards. Advanced
  settings include both appearance and the extracted-NPZ destination. The dark mode also shows the
  source recording beside the movement-only skeleton actually retained by the local extraction
  pipeline.

- **2026-07-31 — Single-dialog video import:** browser-extracted pose NPZ files now default to a
  private per-process temporary folder that is cleaned when the desktop app exits. Video selection
  therefore opens only the video picker. The global advanced settings allow an institution to choose
  a permanent NPZ output folder when retention is intentional.

- **2026-07-30 — Experimental CDP feature adapter:** `action_cdp` now reproduces the historical
  CDP-TreeFusion 33→17 pose mapping and 230/1150-dimensional feature branches, then applies a
  hash-pinned, data-only 40+64 selector/scaler adapter before entering the existing federated DP
  forest. The node and coordinator never load the historical pickle. This is a parallel model
  experiment and does not alter the frozen September pilot scope or establish a clinical result.

- **2026-07-27 — Offline browser assets:** the MediaPipe release the client runs over participant
  video is now mirrored locally and pinned by a committed SHA-256 manifest, with the loader's hash
  checked in the browser before execution. Verified in a real browser: offline resolution, refusal of
  a wrong pin, and full Holistic inference with no CDN access.
- **2026-07-27 — Pilot operations:** `admin_backup.py` backs up, verifies, and restores the
  coordinator key, signed state, and invitation registry, with a regression proving that a clean-host
  restore preserves the chain, the model, the privacy spend, and prior revocations. The coordinator
  emits one JSON operational log line per event and per denial, with an allow-list so a new audit
  field cannot leak. CI runs the whole suite plus a known-vulnerability audit and an SBOM — which
  immediately caught 20 advisories in a transitively locked `pillow`, now upgraded.

- **2026-07-26 — Round reliability, and a corruption bug found while building it:** a re-registering
  node previously kept its stale `x_pub` at the coordinator while masking with a fresh ephemeral key,
  so its residual masks would have silently corrupted the pooled sum on any reconnect. Rounds are now
  bound to a fingerprint of the exact `(node_id, x_pub)` set their masks were built against; a
  reconnect adopts the new key and discards rounds built against the old set. Partially-submitted
  rounds are discarded after a configurable timeout and may be resubmitted, identical retries are
  idempotent, conflicting ones are refused, and a persisted per-round ledger makes double-spending
  epsilon structurally impossible. The node re-enrols and rebuilds masks on its own; the dashboard
  names the institution a stalled round is waiting for.

- **2026-07-26 — Institution invitations:** `FED_REQUIRE_INVITATION=1` makes enrolment require a
  coordinator-signed invitation naming the institution, with an expiry, bound to the node's Ed25519
  key on first use. A separate coordinator-signed registry records issuance and revocation and is
  re-read on every enrolment and submission, so a partner can be withdrawn without a coordinator
  restart, a client reinstall, or a password rotation for anyone else. Issuance lives in the
  host-only `admin_invite.py`, which also exports a version 2 partner configuration carrying the
  invitation, imported by the desktop client or passed to `node.py --config`. The node also pins the
  coordinator against the key fingerprint in its invitation before registering, so a redirected or
  impersonating address aborts the run before anything is uploaded. This closes the
  institution-identity blocker; the remaining P0 items are reliability, operations, and governance.
- **2026-07-26 — Coordinator API boundary:** all contributor and read/model/audit/inference paths now
  have explicit access classes; contributor and read/operator passwords can be separated; only the
  dashboard shell, `/health`, `/ready`, and `/pubkey` are public. Constant-time token checks,
  configurable request-body limits, a per-process pilot rate limiter, authenticated dashboard/model/
  audit consumers, and an automated API regression suite were added.

## Production-after-pilot blockers

- Threshold/dropout-recovery secure aggregation with an independent security review.
- Invitation-layer hardening: the file-backed registry assumes a single administrative writer and an
  invitation is a bearer credential until its first use. Production needs the registry in the same
  transactional store as federation state, and a decision on whether to require mTLS or an
  out-of-band key confirmation at first enrolment.
- Transactional database-backed federation state and safe multi-worker/multi-instance operation.
- High availability, key-management integration, automated backups, restore drills, and SLA monitoring.
- External audit anchoring and a completed penetration test with no unresolved high-severity findings.
- Real multi-institution subject-level utility, calibration, subgroup, and device/domain-shift evaluation.

## What is now blocking, honestly

The remaining pilot blockers are no longer mostly code. Partner selection, institutional approvals,
TLS certificates, code-signing identities, and an external security review all need a person and
carry lead time; they are dated in [`human-critical-path.md`](human-critical-path.md). “Institutional
approval” is route-specific: an all-Hong-Kong pilot, Shenzhen→Hong Kong GBA transfer, Beijing→Hong
Kong transfer and EU/US→Hong Kong transfer require different documents. The matrix and immediate
no-go conditions are in [`legal-and-policy.md`](legal-and-policy.md).

Engineering's remaining pilot list is short: the unsigned packaging specification and surviving a
coordinator restart mid-round without resubmission. Session cleanup and measured request-body/load
limits are now implemented. None of these is the long pole. **The pilot date
now moves only if the owner-required items start.**

## Scope boundary

The September target is a **monitored research pilot** with a small fixed cohort and a documented
abort/restart procedure. It is not a clinical claim, a diagnostic product, or an unattended public
service. It remains on the current labeled classifier; new self/semi-supervised protocols do not
enter its critical path. Clinical use cannot be accelerated merely by completing engineering tasks.
