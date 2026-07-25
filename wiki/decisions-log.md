# Decisions Log

Last updated: 2026-07-26

Newest decisions appear first.

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
