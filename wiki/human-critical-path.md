# Human Critical Path

Last updated: 2026-07-27

Work in this repository splits cleanly into two kinds. Most of the remaining engineering can be
written and regression-tested inside the repository. The items below **cannot** be, no matter how
much engineering time is spent: they need a person with an institutional identity, a credential, a
budget, a signature, a physical machine, or another organisation's cooperation.

They are listed here because several carry **procurement or negotiation lead time**. If the goal is
to go live earlier, these — not the code — are now the binding constraint.

## Why this page exists

As of 2026-07-27 the engineering critical path is running ahead of schedule: the Aug 3–9 identity
gate and most of the Aug 10–16 reliability gate are already complete. The pilot date is therefore no
longer limited by what remains to be built. It is limited by partner selection, institutional
approvals, certificates, and an external security review — all of which start with a human decision.

**Nothing below can be accelerated by writing more code.** Starting them late is the single most
likely cause of a slipped 2026-09-07 pilot.

## Owner-required actions, by date

| Due | Action | Why a person is required | What it blocks |
|---|---|---|---|
| **2026-08-03** | Select the three pilot institutions and name an IT contact at each | Requires an institutional relationship and their consent | Everything downstream; no technical substitute exists |
| **2026-08-03** | Decide who holds the coordinator private key, where its backup lives, and who may issue or revoke invitations | A custody and accountability decision, not a configuration value | Key management, incident response, go/no-go |
| **2026-08-10** | Data-processing scope agreed and signed per institution: purpose, retention, audit visibility, incident contact | Legal review and institutional signatures | Go/no-go checklist item; lawful processing |
| **2026-08-10** | Confirm ethics/IRB coverage for the pilot data flow | Ethics committee decision | Any run touching real participant recordings |
| **2026-08-17** | Provision the coordinator host, DNS, firewall rules, and a **real TLS certificate** on the institutional reverse proxy | Needs institutional infrastructure access and credentials | Every cross-site run; the frozen TLS topology assumes it |
| **2026-08-17** | Procure code-signing identities: Apple Developer ID *and* a Windows certificate | Paid organisational identities with issuing lead time — often the longest single wait | Signed installers; a hospital machine may refuse unsigned software |
| **2026-08-23** | Build, notarize, and install the client on the **actual** pilot Windows/macOS machines | Notarization needs an Apple account; validation needs the real hardware and its lockdown policy | Go/no-go checklist item |
| **2026-08-23** | Decide the MediaPipe policy: the mirroring and hash-pinning tooling now exists and works offline, so what remains is the **licence review** on redistributing the assets (or a decision to host them institutionally, or to disable raw-video import for the pilot) | A licensing decision, not an engineering one | Go/no-go checklist item |
| **2026-08-30** | Engage an independent security/protocol review or penetration test | External party, with procurement lead time | Production target; contingency date exists for its findings |
| **2026-08-31 – 09-06** | Deploy to staging on the institutional network and run **at least three** full three-institution rehearsals with partner staff | Requires the partners' people, machines, and schedules | Go/no-go checklist item |
| **2026-08-31 – 09-06** | Run the 72-hour soak and the backup/restore drill on the real host | Needs the production-like host and elapsed wall-clock time | Go/no-go checklist item |
| **2026-09-07** | Name the on-duty operator and the rollback owner for the pilot window | A staffing commitment | Pilot start |

## What does *not* need a person

For clarity, the following remain ordinary engineering and are tracked in
[`timeline.md`](timeline.md): structured logging and metrics, backup and restore commands, CI
configuration, protocol and failure integration tests, session cleanup, dependency and SBOM
scanning, the unsigned packaging specification, and every runbook and partner document. Structured
logging, backup/restore, CI with a dependency audit, and offline-asset tooling are already done.

## Explicitly out of scope

These are not late items; they are a different programme with their own evidence and regulatory
schedule, and no engineering work in this repository advances them:

- Clinical efficacy claims or diagnostic use.
- Medical-device classification or registration.
- Prospective multi-centre clinical validation.
- Recruiting participants or running any real-world human study.
