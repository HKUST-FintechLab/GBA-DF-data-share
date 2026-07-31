# Decisions Log

Last updated: 2026-08-01

Newest decisions appear first.

## 2026-08-01 — Add unlabeled learning as a staged post-pilot research track

- Keep the monitored September pilot on the current labeled, auditable leaf-count classifier. Do not
  put semi-supervised, self-supervised or federated-gradient work on its critical path.
- Add unlabeled learning to the roadmap because local video volume can materially exceed expert label
  capacity, but make capability status explicit: it is a design/research track, not a current feature.
- Fix the legacy unlabeled-to-TD fallback before exposing any unlabeled workflow.
- Build local active learning with human confirmation first. It gives immediate label-efficiency value
  while reusing the existing model download, supervised counts, secure aggregation and DP proof.
- Evaluate hard pseudo-label self-training only after provenance, deduplication, abstention and
  per-subject contribution limits exist. Never merge pseudo and human labels invisibly.
- Prefer a public, frozen, hash-pinned SSL encoder feeding a new versioned modality and the current DP
  forest before attempting federated encoder training.
- Treat true federated SSL/FedAvg as a new protocol requiring update clipping, parameter aggregation,
  a multi-step DP accountant, dropout recovery, poisoning tests and independent review. Do not inherit
  the leaf-count protocol's security or sensitivity claims by analogy.
- Split EEG and fMRI schemas before learned neuro representations; do not build on the current shared
  128 Hz engineering assumption.

## 2026-07-30 — Keep CDP federation as a parallel experiment, outside the pilot path

- Add `action_cdp` as an explicitly experimental front end; do not replace the existing `action`
  schema or add it to the September pilot critical path.
- Reuse only the historical champion's pose mapping, feature definitions, frozen scaler parameters,
  and 40/64 selected indices. Train the shared data-independent DP forest on that 104-dimensional
  representation; do not describe this as averaging or continuing the original ExtraTrees model.
- Never load the historical pickle in a node or coordinator. A one-time local migration requires an
  exact source SHA-256 and explicit risk acknowledgement, exports only allow-listed numeric metadata,
  strips sample IDs/groups/reports/classifier trees, and pins the resulting JSON to the
  `action_cdp` v1 schema.
- Treat the existing CDP locked-test result as historical evidence only. Any improvement claim
  requires grouped, institution-held-out comparison of frozen CDP, existing `action`, `action_cdp`,
  and a future calibration/residual design.

## 2026-07-26 — Handle dropout by discarding rounds, not by persisting masked vectors

- Bind every round to a fingerprint of the exact `(node_id, x_pub)` set its masks were built against,
  and refuse to pool submissions across fingerprints. A wrong peer set produces a *silently* wrong
  sum, so this must fail loudly rather than degrade.
- A reconnecting node's fresh ephemeral masking key is adopted, and rounds built against its previous
  key are discarded. Keeping the old key would have left residual masks in the pooled sum — this was
  a live defect, not a hypothetical.
- Do not persist in-flight masked vectors. Discarding an incomplete round and having nodes resubmit
  achieves the same recovery without writing participant-linkable material to disk. Coordinator
  restart recovery is therefore reconnect-and-resubmit, and this is stated in the partner guide.
- Bound a stall rather than waiting forever: a partially-submitted round is discarded after
  `FED_ROUND_TIMEOUT_SECONDS` and may be sent again. Nothing was aggregated, so nothing was spent.
- Treat an identical retry as idempotent and a conflicting payload for the same pending round as a
  refusal, so no institution can revise its contribution after watching the others wait.
- Make the per-round epsilon ledger the authority on what a round cost, so double-spending is
  structurally impossible rather than merely unlikely.

## 2026-07-26 — Freeze the pilot TLS topology and coordinator pinning

- Pilot topology: partner node → HTTPS → institutional reverse proxy terminating TLS → uvicorn
  coordinator bound to `127.0.0.1`. The coordinator process is never exposed directly.
- Pin coordinator identity using the key fingerprint already inside the invitation, rather than
  distributing certificates or fingerprints separately. The node checks it before registering and
  aborts without uploading on a mismatch.
- Keep mTLS optional. Requiring a certificate authority on the partner side would slow onboarding for
  a guarantee the invitation plus a locally generated node key already provides at the application
  layer.
- State the division of labour rather than blurring it: TLS proves the hostname and encrypts the
  transport; pinning proves the process holds the issuing key; the password proves token knowledge;
  the invitation proves which institution is calling. Do not present pinning as a TLS substitute.

## 2026-07-26 — Lock the institution-invitation design

- An invitation is a coordinator-signed record naming one institution, its role, and an expiry, and
  is valid only against the coordinator public key that signed it.
- Bind the invitation to the node's Ed25519 key on first registration. First use wins; a leaked
  invitation cannot afterwards be redeemed under a different key.
- Keep issuance and revocation OUT of the HTTP API. `admin_invite.py` requires access to the
  coordinator host, because issuing institution identity should not be reachable with a bearer token.
- Let the offline CLI be the only writer of the registry and the running coordinator only a reader,
  so revocation needs no restart and the two processes never race for the file.
- Fail closed everywhere: unknown, edited, expired, revoked, and unreadable registries all deny.
  An invitation absent from the registry is refused even when its signature verifies.
- Keep enforcement behind `FED_REQUIRE_INVITATION` so demo and solo modes are unaffected, and make
  `=1` a pilot go/no-go checklist item rather than a silent default.
- State the limit plainly: an invitation authenticates an institution, not the honesty of its counts,
  and it is a bearer credential until first use.

## 2026-07-26 — Establish the interim coordinator access boundary

- Keep only the dashboard shell, liveness/readiness probes, and coordinator public key public.
- Split protected APIs into contributor and read/operator roles, with separate runtime passwords.
- Let `FED_READ_PASSWORD` inherit `FED_PASSWORD` when omitted for backwards compatibility.
- Store the dashboard read credential only for the browser tab and use authenticated fetches for
  status, model, audit-package, and hosted-inference access.
- Treat the in-process rate limiter as a controlled-pilot safeguard, not a multi-instance production
  control.
- Do not confuse this boundary with institution identity: signed invitations, expiry, roles, and
  revocation remain mandatory before the pilot gate.

## 2026-07-26 — Compress the deployment schedule

- Target a monitored three-institution research pilot on **2026-09-07**.
- Target a production-grade research platform on **2026-10-26**, with a security-review contingency
  date of **2026-11-16**.
- Run backend/security and client/QA workstreams in parallel.
- Freeze new model and modality work until pilot P0 gates pass.
- Use timeout + abort/restart + reconnect for the pilot; do not delay the pilot solely for full
  cryptographic dropout recovery.
- Require full dropout recovery and an independent protocol review before production research status.
- Keep mTLS optional. Default institution onboarding should use an administrator-signed invitation
  configuration plus a locally generated Ed25519 key.
- Do not describe either target as clinical deployment.
