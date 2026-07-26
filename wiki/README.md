# GBA-DF Project Wiki

Last updated: 2026-07-27

This is the canonical project-memory area for the standalone `federated_poc` repository. It records
release readiness and delivery decisions only for GBA-DF; do not inherit a parent repository's wiki.

## Current targets

- **Controlled three-institution research pilot:** target 2026-09-07.
- **Production-grade research platform:** aggressive target 2026-10-26.
- **Clinical screening or diagnostic use:** outside this engineering timeline; it requires separate
  real-world validation, ethics, governance, and regulatory work.

The two dated targets are planning targets, not external promises. They assume two focused engineers,
part-time security/DevOps support, pre-selected pilot institutions, and decisions within one business day.

As of 2026-07-27 the engineering path is ahead of schedule and the pilot date is limited by the
owner-required items in [`human-critical-path.md`](human-critical-path.md). Read that page first when
asking "can we go live sooner?" — the answer is not in the code.

## Pages

| Page | Purpose |
|---|---|
| [`state-of-project.md`](state-of-project.md) | Current capability, readiness level, and blocking gaps |
| [`timeline.md`](timeline.md) | Compressed implementation schedule, parallel workstreams, and go/no-go gates |
| [`human-critical-path.md`](human-critical-path.md) | Dated actions that need a person — partners, approvals, certificates, external review — and cannot be delivered by engineering |
| [`decisions-log.md`](decisions-log.md) | Locked scope and timeline decisions |

## Update rules

- After a blocker is completed or slips, update `state-of-project.md` and `timeline.md`.
- When an item turns out to need a person rather than engineering, move it to `human-critical-path.md`
  with a date, rather than leaving it to look like pending code work.
- When a target date or production boundary changes, append the decision to `decisions-log.md`.
- Re-stamp `Last updated:` on every edited wiki page.
- Do not describe the research pilot as clinical deployment.

