# GBA-DF Project Wiki

Last updated: 2026-08-01

This is the canonical project-memory and technical-reference area for the standalone `federated_poc`
repository. It covers current capability, model/data contracts, evidence boundaries, delivery state
and locked decisions only for GBA-DF; do not inherit a parent repository's wiki.

技术页以中文为主并保留英文术语，方便合作方、工程团队和研究团队使用同一套定义。每个页面
严格区分 **Implemented**、**Experimental**、**Design only** 和 **Not supported**，避免把研究
路线图误读成现成功能。

## Current targets

- **Controlled three-institution research pilot:** target 2026-09-07.
- **Production-grade research platform:** aggressive target 2026-10-26.
- **Clinical screening or diagnostic use:** outside this engineering timeline; it requires separate
  real-world validation, ethics, governance, and regulatory work.

The two dated targets are planning targets, not external promises. They assume two focused engineers,
part-time security/DevOps support, pre-selected pilot institutions, and decisions within one business day.

As of 2026-08-01 the engineering path is ahead of schedule and the pilot date is limited by the
owner-required items in [`human-critical-path.md`](human-critical-path.md). Read that page first when
asking "can we go live sooner?" — adding a new model or learning mode does not move that date forward.

## Start here

| Page | Purpose |
|---|---|
| [`state-of-project.md`](state-of-project.md) | Current capability, readiness level, and blocking gaps |
| [`../README.md`](../README.md) | Public-facing project overview, quick start, security and operator entry points |
| [`../TODO.md`](../TODO.md) | Prioritized implementation backlog, including the decision on semi/self-supervised work |

## Technical reference

| Page | Purpose |
|---|---|
| [`modalities-and-models.md`](modalities-and-models.md) | Exact model stack for eyegaze, action, experimental action_cdp and neuro; shared DP forest; dimensions and limitations |
| [`learning-modes.md`](learning-modes.md) | Labeled vs unlabeled data, current supervised path, active learning, semi-supervised and self-supervised designs, privacy implications |
| [`evaluation-and-claims.md`](evaluation-and-claims.md) | Dashboard metrics, test-set provenance, evidence levels, contribution deltas and defensible external claims |

## Delivery and governance

| Page | Purpose |
|---|---|
| [`timeline.md`](timeline.md) | Compressed implementation schedule, parallel workstreams, and go/no-go gates |
| [`human-critical-path.md`](human-critical-path.md) | Dated actions that need a person — partners, approvals, certificates, external review — and cannot be delivered by engineering |
| [`decisions-log.md`](decisions-log.md) | Locked scope and timeline decisions |

## Update rules

- After a blocker is completed or slips, update `state-of-project.md` and `timeline.md`.
- When an item turns out to need a person rather than engineering, move it to `human-critical-path.md`
  with a date, rather than leaving it to look like pending code work.
- When a target date or production boundary changes, append the decision to `decisions-log.md`.
- When a modality, model schema, label contract, metric definition or learning-mode status changes,
  update the matching technical-reference page and `TODO.md` together.
- Never describe a **Design only** self/semi-supervised route as implemented merely because its design
  is documented.
- Re-stamp `Last updated:` on every edited wiki page.
- Do not describe the research pilot as clinical deployment.
