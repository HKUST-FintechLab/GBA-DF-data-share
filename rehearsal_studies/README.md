# Rehearsal studies

The scripts and raw results behind the rehearsal claims in [`../README.md`](../README.md) and
[`../DEMO_SCRIPT.md`](../DEMO_SCRIPT.md). They are kept so the conclusions can be re-derived rather
than taken on trust — roughly 350 real federations, each one a coordinator on an isolated port with
an isolated `FED_STATE_DIR` and three real `node.py` processes.

| Folder | Question | Headline |
|---|---|---|
| `baseline_size/` | How does the size of each node's synthetic baseline affect the curve? | Small baselines wobble: at ~72 rows/node, 6 runs in 10 show a visible dip and the final AUC barely clears the pooled-centralized reference. |
| `metric_response/` | Does uploading clips raise any metric? | No. Across 80 paired runs every 95% interval straddles zero; win rates are 7–12 of 20. |
| `upload_placement/` | Can a live upload avoid pushing the headline below the reference? | Yes — one node, not three. The earlier loss was a file-sort-order interaction with the row→tree assignment, not an out-of-distribution penalty. |
| `metric_stability/` | Which metrics are stable enough to display? | 96 federations across three stagings. The stability ranking generalises; the magnitudes do not. |
| `cohort_size/` | Does the model improve as institutions join? | Solo vs three is visible and large; the incremental 2→3 step is a coin flip. Splitting a *fixed* dataset across three sites costs nothing, so the gain is data volume. |
| `clip_pose_quality/` | Do the screened clips draw limbs that are not in frame? | Three of the five TD clips do, and `td_02` is the second worst rather than an outlier. Framing, not model failure — every phantom sits below the bottom edge. No visibility gate fixes it: clearing them costs 61% of the genuinely visible lower-body landmarks. |

Two methodological notes worth carrying into any repeat of this work:

- **Small repeat counts manufacture confident wrong answers.** In `metric_response/`, effect sizes of
  0.67–0.81 at n=10 collapsed to nothing at n=20. Four repeats is not enough to conclude anything
  here; the DP noise is larger than most of the effects being looked for.
- **Results depend on node seeds and on filename sort order.** `modalities._list()` returns files in
  sorted path order and `dp.count_on_shared` zips its row→tree draw against that order, so inserting
  a file early in the sort re-rolls the tree assignment of every later row in that node. An effect
  measured at one seed triple can reverse at another; `upload_placement/` sweeps 12 triples for
  exactly this reason.

Nothing here is needed to run the demo. `../verify_demo_run.py` is the maintained entry point: it
rehearses both arms and reports whether the clips move the final AUC by more than the run-to-run
noise.
