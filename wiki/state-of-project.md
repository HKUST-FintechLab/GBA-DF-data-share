# State of Project

Last updated: 2026-07-26

## Executive status

GBA-DF is a functioning engineering POC. It is ready for demonstrations and internal dry runs, and it
has the core ingredients for a controlled research pilot: three modalities, local extraction,
pairwise-masked secure aggregation, coordinator-enforced central DP, a global epsilon budget,
signed/persistent audit evidence, real JSON-payload accounting, a desktop client, and a dashboard.

It is **not yet ready for unattended exposure on a hospital network**. The remaining critical work is
mainly identity/access control, failure recovery, production operations, installable client delivery,
and institutional governance rather than another model feature.

## Readiness by target

| Target | Readiness estimate | Status |
|---|---:|---|
| Demonstration/internal dry run | 90%+ | Available now |
| Controlled three-institution research pilot | ~65% | Six-week hardening plan active |
| 7×24 production research platform | ~40% | Follows the pilot |
| Clinical screening/diagnostic deployment | <20% | Separate validation/regulatory programme |

These percentages are planning estimates, not formal maturity certifications.

## Verified baseline

Verified on 2026-07-26:

- `uv run python verify_security.py` — all 27 security/privacy checks passed.
- `uv run python modalities.py` — eyegaze, action, and neuro extraction checks passed.
- `uv run python client_app.py --selftest` — desktop API smoke test passed.

## Pilot blockers

| Priority | Blocker | Pilot solution |
|---|---|---|
| P0 | Shared password does not provide institution-level authorization | Signed one-time invitation JSON, per-institution Ed25519 identity, revocation, and role-based endpoint access |
| P0 | Some read/model/audit/inference endpoints are not protected | Authenticate and authorize every non-public endpoint |
| P0 | Full-cohort aggregation stalls if one node drops | Explicit round timeout, abort/restart, reconnect, and idempotent submission |
| P0 | Coordinator is a single-process service with in-memory live sessions | Supported single-instance pilot deployment, durable round state, backup/restore, health checks, and monitoring |
| P0 | Desktop client still depends on a Python environment | Signed Windows/macOS pilot builds with fixed dependencies |
| P0 | Browser pose extraction depends on a public CDN | Bundled or institution-hosted MediaPipe/WASM assets with hashes and an offline path |
| P0 | No automated CI/E2E/failure suite | CI plus three-node network, restart, timeout, duplicate-submit, and restore tests |
| P0 | Governance is not encoded in the product | Data-processing scope, audit visibility, retention, incident response, and institution approvals |

## Production-after-pilot blockers

- Threshold/dropout-recovery secure aggregation with an independent security review.
- Transactional database-backed federation state and safe multi-worker/multi-instance operation.
- High availability, key-management integration, automated backups, restore drills, and SLA monitoring.
- External audit anchoring and a completed penetration test with no unresolved high-severity findings.
- Real multi-institution subject-level utility, calibration, subgroup, and device/domain-shift evaluation.

## Scope boundary

The September target is a **monitored research pilot** with a small fixed cohort and a documented
abort/restart procedure. It is not a clinical claim, a diagnostic product, or an unattended public
service. Clinical use cannot be accelerated merely by completing engineering tasks.

