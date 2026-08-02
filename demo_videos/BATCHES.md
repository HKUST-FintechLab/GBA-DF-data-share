# The fixed on-stage upload plan

Three operators, one batch each. The desktop client shows a `Batch 1 / Batch 2 / Batch 3` bar and
loads the clips with one click — no file dialog on camera. The authoritative list is the `BATCHES`
const at the top of [`../static/client_batchimport.js`](../static/client_batchimport.js); this file
records *why* it holds what it holds.

| Batch | Client | Clips | Class |
|---|---|---|---|
| 1 | `node_1` | `asd_01.mp4`, `td_01.mp4` | one each |
| 2 | `node_2` | `asd_03.mp4`, `td_03.mp4` | one each |
| 3 | `node_3` | `asd_02.mp4`, `asd_04.mp4` | both ASD |

Six of the eleven clips. The other five are deliberately unreachable from the batch buttons:

- **`td_02`, `td_04`, `td_05` — never show these.** They draw confident lower-body landmarks outside
  the camera frame (46.7% / 31.7% / 46.9% of drawn lower-body landmark-slots, against 0.0–0.9% for
  every other clip). The children's legs are cropped out of shot and MediaPipe extrapolates them, so
  the overlay paints a leg where the picture has none. On a privacy and trust demo that reads as the
  system inventing data. Full measurement in
  [`../rehearsal_studies/clip_pose_quality/`](../rehearsal_studies/clip_pose_quality/).
- **`asd_06` — clean, but 38.7 s**, roughly three times the next longest clip. Extraction runs in the
  browser on stage; it is left out to keep the demo moving, not for quality.

**Batch 3 is single-class on purpose.** Only two clips in the whole set show a TD child with the
legs in frame, and they are already assigned to batches 1 and 2. One institution's upload happening
to be all one cohort is realistic and worth saying out loud — it is also the question partners ask
("what if a site only has ASD recordings?"). The answer is in the measurements: an ASD-only spread
upload put 4 of 4 runs above the pooled-centralized reference, because the coordinator sums count
histograms rather than averaging models, and the displayed metric's class balance comes from each
node's synthetic baseline, not from these six rows.

**What this plan is for.** It makes the live upload reproducible and keeps the headline above the
reference — measured at 0.793 ± 0.003 with the clips against 0.801 ± 0.010 without, 5 of 5 runs
above the reference either way. It does **not** make the number go up. Six clips are six feature
rows against a 581-row baseline, at the DP noise floor by construction. Narrate the upload as *what
left the machine* — raw video never did — and leave the metric out of it.

Re-verify after any change to this list:

```bash
uv run python verify_demo_run.py
```
