# GBA-DF Project Wiki

Last updated: 2026-07-26

This is the canonical project-memory area for the standalone `federated_poc` repository. It records
release readiness and delivery decisions only for GBA-DF; do not inherit a parent repository's wiki.

## Current targets

- **Controlled three-institution research pilot:** target 2026-09-07.
- **Production-grade research platform:** aggressive target 2026-10-26.
- **Clinical screening or diagnostic use:** outside this engineering timeline; it requires separate
  real-world validation, ethics, governance, and regulatory work.

The two dated targets are planning targets, not external promises. They assume two focused engineers,
part-time security/DevOps support, pre-selected pilot institutions, and decisions within one business day.

## Pages

| Page | Purpose |
|---|---|
| [`state-of-project.md`](state-of-project.md) | Current capability, readiness level, and blocking gaps |
| [`timeline.md`](timeline.md) | Compressed implementation schedule, parallel workstreams, and go/no-go gates |
| [`decisions-log.md`](decisions-log.md) | Locked scope and timeline decisions |

## Update rules

- After a blocker is completed or slips, update `state-of-project.md` and `timeline.md`.
- When a target date or production boundary changes, append the decision to `decisions-log.md`.
- Re-stamp `Last updated:` on every edited wiki page.
- Do not describe the research pilot as clinical deployment.

