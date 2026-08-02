# Clip pose quality — phantom limbs

**Question.** During rehearsal the pose overlay on `td_02` drew legs that are not in the camera
frame. On stage that reads as the system inventing data, which is the one impression a
privacy/trust demo cannot afford. Is `td_02` the problem, or is it just the one that got noticed?

**Headline.** It is not `td_02`. Three of the five TD clips are affected and `td_02` is the *second*
worst of them. `td_05` (46.9%), `td_02` (46.7%) and `td_04` (31.7%) draw confident lower-body
landmarks outside the frame; the other eight clips are at 0.0–0.9%. There is no continuum — the
distribution is bimodal, so the three bad clips are separable by any threshold between 1% and 30%.
The cause is framing, not a model failure: **100% of the phantom landmarks in all three clips sit
below the bottom edge**, and all three are wide, letterboxed 640-px clips (360, 266 and 216 px tall)
in which the child's legs are simply not in shot. `td_04` is the structurally worst of the three —
even the *hips* are below the frame in 88–95% of frames, so MediaPipe is drawing an entire invented
lower body.

The recommendation is **do not show `td_02`, `td_04` or `td_05` on camera**. Only `td_02` is
currently staged for a live upload, so the fix on stage is a single substitution. No replacement TD
clip exists anywhere on this machine. The metric is unaffected either way — see
[Metric consequence](#metric-consequence).

---

## What was measured

The metric has to match what the audience sees, not what is "wrong" in the abstract. MediaPipe Pose
regresses all 33 landmarks whether or not they are visible, so normalised x/y routinely leave
`[0,1]`, and the visibility score for an *occluded-but-inferred* joint stays well above the drawing
threshold. So:

> a landmark is a **phantom** in a frame iff
> `visibility >= 0.25` **and** (`x < 0` or `x > 1` or `y < 0` or `y > 1`)

`0.25` is not a chosen number — it is the exact gate in `static/client.js::paintSkeleton`, for both
the joint dots and (on both endpoints) the skeleton bones. A landmark below that gate is never
painted and cannot be what anyone saw.

Layout was confirmed from the repo rather than assumed:

- `rehearsal_studies/metric_response/extract_pose.py` writes `[p.x, p.y, p.z, p.visibility]` straight
  off `res.pose_landmarks.landmark`, so the stored coordinates are **normalised** and channel 3 is
  visibility. No scaling by frame size anywhere on the write path.
- `static/client.js::poseArray` does the same for the in-browser path, and `paintSkeleton` multiplies
  `x,y` by canvas width/height at *draw* time — confirming the stored numbers are normalised there too.
- `static/client.js::POSE_CONNECTIONS` is the standard MediaPipe Pose 33-point topology, and indices
  23–32 are the lower body (hips 23/24, knees 25/26, ankles 27/28, heels 29/30, foot-index 31/32).

One write-path difference worth knowing: `client.js::fillMissingPose` sets visibility to **0** on
interpolated frames (so they are never drawn), while `extract_pose.py` carries the last valid pose
forward *with its original visibility*. The NPZ pool is therefore very slightly more
phantom-prone than a live browser extraction of the same clip would be. It does not change the
ranking — the three bad clips have near-continuous detection.

## Per-clip ranking

Sorted by phantom rate over the 10 lower-body landmarks. `strict%` uses a 0.50 gate instead of 0.25;
`frames%` is the share of frames with at least one phantom, `>=3%` with at least three; `maxOver` is
the furthest a drawn landmark strays past an edge, in normalised units (1.000 = a whole frame height
below the bottom); `oof%` is out-of-frame *regardless* of visibility; `vis|oof` is the mean visibility
of the out-of-frame landmarks; `bone%` is the share of drawn lower-body bones with an endpoint
outside; `upper%` is the same phantom rate for landmarks 0–22, as a control.

| clip | res | T | phantom% | strict% | frames% | >=3% | maxOver | medOver | oof% | vis&#124;oof | bone% | upper% |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **td_05** | 640x216 | 64 | **46.9%** | 23.3% | 96.9% | 81.2% | 1.066 | 0.124 | 54.4% | 0.457 | 53.0% | 0.0% |
| **td_02** | 640x360 | 43 | **46.7%** | 18.1% | 100.0% | 81.4% | 0.529 | 0.170 | 63.5% | 0.397 | 53.3% | 0.0% |
| **td_04** | 640x266 | 60 | **31.7%** | 20.0% | 100.0% | 55.0% | 0.950 | 0.120 | 71.7% | 0.351 | 85.4% | 4.4% |
| asd_06 | 1280x720 | 146 | 0.9% | 0.0% | 2.1% | 1.4% | 0.368 | 0.290 | 1.0% | 0.312 | 0.7% | 0.0% |
| asd_03 | 1080x1420 | 42 | 0.5% | 0.5% | 4.8% | 0.0% | 0.010 | 0.007 | 0.5% | 0.959 | 0.7% | 3.1% |
| asd_01 | 720x998 | 75 | 0.0% | 0.0% | 0.0% | 0.0% | 0.000 | 0.000 | 0.0% | — | 0.0% | 0.0% |
| asd_02 | 1080x1920 | 29 | 0.0% | 0.0% | 0.0% | 0.0% | 0.000 | 0.000 | 0.0% | — | 0.0% | 0.0% |
| asd_04 | 1080x1920 | 25 | 0.0% | 0.0% | 0.0% | 0.0% | 0.000 | 0.000 | 0.0% | — | 0.0% | 0.0% |
| asd_05 | 1080x1650 | 21 | 0.0% | 0.0% | 0.0% | 0.0% | 0.000 | 0.000 | 0.0% | — | 0.0% | 0.0% |
| td_01 | 360x640 | 42 | 0.0% | 0.0% | 0.0% | 0.0% | 0.000 | 0.000 | 0.0% | — | 0.0% | 0.2% |
| td_03 | 640x360 | 55 | 0.0% | 0.0% | 0.0% | 0.0% | 0.000 | 0.000 | 0.0% | — | 0.0% | 0.0% |

n = 11, median 0.0%, mean 11.5%. Every phantom slot in `td_02`, `td_04` and `td_05` is **below the
bottom edge** — 201/201, 190/190, 300/300 respectively. Zero are off the sides or the top. The two
non-zero ASD clips are qualitatively different: `asd_03`'s two slots are a right knee grazing a side
edge by 0.010 (one hundredth of a frame width — invisible), and `asd_06`'s 13 slots over 146 frames
are toes flickering across the boundary in ~2% of frames.

Which joint goes missing differs by clip, and it tracks how much of the body is cropped:

| clip | hip_L | hip_R | knee_L | knee_R | ank_L | ank_R | heel_L | heel_R | toe_L | toe_R |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| td_02 | 0 | 0 | 79 | 5 | 81 | 58 | 88 | 88 | 37 | 30 |
| td_04 | 95 | 88 | 45 | 17 | 20 | 0 | 32 | 7 | 13 | 0 |
| td_05 | 5 | 6 | 6 | 6 | 59 | 73 | 69 | 91 | 67 | 86 |

(% of frames in which that landmark is a phantom.) `td_05` invents feet, `td_02` invents from the
knee down, `td_04` invents from the pelvis down.

Aspect ratio is suggestive but not sufficient: `td_03` is also 640x360 and is completely clean. It is
whether the child's legs are in shot, which is a framing property of the individual clip.

## Is `td_02` an outlier?

**No — confirmed on the substance, refuted on the framing.** The user's observation is exactly right
about `td_02`: in 100% of its 43 frames MediaPipe draws at least one lower-body landmark outside the
picture, in 81% it draws three or more, and those landmarks carry a mean visibility of 0.397 —
comfortably above the 0.25 gate, i.e. the model is not hedging. Half of every drawn lower-body bone
(53.3%) has an endpoint off the picture.

But `td_02` is not an outlier within the set. `td_05` is fractionally worse on the headline metric
(46.9% vs 46.7%) and twice as far off the picture (1.066 vs 0.529 frame heights below the bottom),
and `td_04` puts a larger share of its *drawn skeleton* outside the frame than either (85.4% of
lower-body bones). `td_02` is simply the one that was staged for a live upload and therefore the one
that got looked at. Screening on `td_02` alone would have left two equally bad clips in the pool.

Note that all three violate the screening criterion already written down in `DEMO_SCRIPT.md`:
"one child, **whole body in frame**, no burned-in captions, no shot changes". The README is candid
that "the automated pass was not trustworthy on this material and the final selection is a visual
one" — this is where the visual pass let three through.

## Could a renderer change fix this instead?

Two candidate fixes were checked, because dropping a clip from a set of eleven is not free.

**(a) Raise the visibility gate above 0.25.** It does not work. The gate has to reach **0.90** before
the phantoms are gone, and at that setting 61.2% of the genuinely in-frame lower-body landmarks on
the eight clean clips stop being drawn:

| gate | 0.25 | 0.40 | 0.50 | 0.60 | 0.70 | 0.80 | 0.90 |
|---|---:|---:|---:|---:|---:|---:|---:|
| td_02 | 46.7% | 25.8% | 18.1% | 12.3% | 7.4% | 3.5% | 0.7% |
| td_04 | 31.7% | 24.2% | 20.0% | 18.2% | 12.8% | 6.0% | 1.8% |
| td_05 | 46.9% | 38.3% | 23.3% | 12.0% | 3.0% | 0.0% | 0.0% |
| *cost on clean clips* | 0% | — | 17.2% | — | 34.5% | — | **61.2%** |

That is the finding: **the visibility score does not separate "inferred off-screen" from "visible but
partly occluded".** Any gate that suppresses the invented legs also guts the real ones. This is worth
knowing independently of the clip decision — it rules out the obvious one-line fix.

**(b) Clip the skeleton at the frame box** — never draw a landmark whose normalised coordinates leave
`[0,1]`. This is honest (the overlay stops where the picture stops) and nearly free on good material:
it removes 0.0% of drawn bones on six of eight clean clips, 0.2% on `td_01`, 3.1% on `asd_03`. On the
bad three it removes 16.1% / 24.8% / 18.7% of the whole drawn skeleton — which is the correct
outcome, but a visibly truncated skeleton on stage still invites the question. **Fix (b) is worth
doing as a general robustness improvement, but it is not a substitute for not showing these clips.**
No client code was changed by this study.

## Recommendation

**Drop `td_02` from the on-camera set. Never use `td_04` or `td_05` on camera either.**

The on-camera allocation is what matters, and it is smaller than the pool. `demo_nodes/` currently
stages six of the eleven clips, one ASD + one TD per operator:

| operator | node | ASD clip | phantom% | TD clip | phantom% |
|---|---|---|---:|---|---:|
| 1 | `node_1` | asd_01 | 0.0% clean | td_01 | 0.0% clean |
| 2 | `node_2` | asd_03 | 0.7% clean | td_03 | 0.0% clean |
| 3 | `node_3` | asd_02 | 0.0% clean | **td_02** | **41.2% BAD** |

(These are the browser-extracted copies actually sitting in `demo_nodes/`, which sample frames
slightly differently from the `extract_pose.py` pool — `td_02` measures 41.2% there against 46.7% in
the pool, still 100% of frames affected. Same conclusion, and the script prints both.)

So exactly one substitution is needed, and the two clean TD clips are already the ones assigned to
operators 1 and 2. `td_04` and `td_05` are not staged for anybody — they exist only in the NPZ pool,
which is never rendered. That is why the problem showed up as "one bad clip" rather than three.

**A replacement TD clip does not exist.** Checked: `D:\agent\dean\0803\demo_selected` does not exist;
there are exactly 11 `.mp4` files anywhere under `D:\agent\dean\0803` and they are these 11; every
commit in this repo's history contains the same 11 and no more (`git ls-tree -r` on `be69cb2` and
`bfa1c83`); the only other `.npz` outside `demo_videos/` are `synthetic_*` / `*_10N_00K.npz` files
generated by `stage_demo_nodes.py`. The 172 screened source clips referenced in `README.md` are not
on this machine. If they can be recovered, re-screening them for "legs in frame" is the right fix and
this script is the screen to use.

Given that, for operator 3:

1. **Preferred: operator 3 uploads `asd_02` only.** The live upload proves the privacy claim — raw
   video never leaves the laptop — and one clip proves it as well as two. `DEMO_SCRIPT.md` already
   says "uploading two or three clips on camera shows the privacy path", not six. The TD class stays
   represented on camera by `td_01` and `td_03`.
2. **Acceptable: swap in an ASD clip.** `asd_04`, `asd_05` and `asd_06` are unstaged and clean
   (0.0%, 0.0%, 0.9%). If operator 3 needs two uploads, give them a second ASD clip rather than a
   bad TD one. Say "this operator's two recordings happen to be from the ASD cohort" — that is a
   truthful and unremarkable thing for one institution's upload to look like.
3. **Do not** substitute `td_04` or `td_05`. Both are worse than what is being removed.

**Leave the NPZ pool at 11.** The pool is never rendered, so it carries none of the visual risk, and
editing it re-rolls row→tree assignments and invalidates the `0.802 ± 0.008` figure recorded in
`DEMO_SCRIPT.md` for no visible benefit. If you would rather keep the pool and the on-camera set
consistent, dropping all three at once is equally safe — but re-run `verify_demo_run.py` afterwards
so the quoted numbers still match the artefact.

**On "is 4 TD clips enough" — the honest count is worse than 4 and it does not matter.** If `td_02`
is dropped from the pool the TD side is `td_01, td_03, td_04, td_05`, but only **two of those are
clean**. The TD side that is *presentable* has been two clips all along; the demo did not know it.
This is fine, because the clips are not what the metric rides on: every node carries a 16-per-class
synthetic baseline (581 feature rows across three nodes — 210 / 186 / 185) and the eleven clips add
eleven rows. Class balance in the *displayed metric* comes from the baseline, not the uploads. What
the uploads have to do is look right on camera, and two clean TD clips plus five clean ASD clips is
more than a 90-second recording can use.

## Metric consequence

**Dropping a clip is inert, and the structure of the evidence says so before any federation is run.**
Three independent reasons, in increasing order of strength:

1. **The measured effect of *all eleven* clips is already null.** `metric_response/` reports 80
   paired runs in which every 95% interval straddles zero and win rates are 7–12 of 20;
   `DEMO_SCRIPT.md` records 0.802 ± 0.008 with the clips against 0.804 ± 0.003 without. One clip is
   1/11 of an effect that is already smaller than its own noise.

2. **One clip is one feature row.** `modalities._action_extract` treats a `(T,33,4)` array as a
   *single* window, so each real clip contributes exactly **one** row regardless of how many frames
   it has, whereas each synthetic file is `(W,60,33,4)` with W = 4–8 and contributes ~6. The
   synthetic baseline is 581 rows (node_1 210, node_2 186, node_3 185); `verify_demo_run.py`'s
   "baseline + 11 clips" arm is 592. `td_02` is **1 row in 592 — 0.17%**. (Watch this when counting:
   `body.shape[0]` is *windows* for a synthetic file but *frames* for a clip, so summing it
   overstates the clips' weight by a factor of 20–60.)

3. **The DP mechanism is calibrated to hide exactly one row.** `dp.count_on_shared` assigns each row
   to exactly one tree (disjoint → sensitivity 1), and `dp.forest_from_summed_counts` adds
   `Laplace(1/eps)` per leaf at `epsilon_per_round = 1.0`. One row moves one leaf count in one of 20
   trees by ±1; the noise added to that same leaf has scale 1.0. A single row is *by construction* at
   the noise floor. This is not an empirical claim that needs a sweep.

**The row→tree ordering caveat, checked and cleared.** `rehearsal_studies/README.md` warns that
`modalities._list()` returns sorted paths and `dp.count_on_shared` zips its row→tree draw against
that order, so removing a file re-rolls the tree assignment of every *later* row in that node. Two
cases:

- **Live staging (`demo_nodes/`):** `node_3` sorts as `ASD/synthetic_*`, `ASD/upload_asd_02.npz`,
  `TD/synthetic_*`, `TD/upload_td_02.npz`. `upload_td_02.npz` is the **last file in the node's sort
  order** (`s` < `u`, `ASD` < `TD`, and it is the only upload in that folder). Removing it re-rolls
  **zero** other rows. This is the best possible case and it is not a coincidence — it is the
  `upload_<name>.npz` convention introduced precisely so uploads land at the end of the sort.
- **`verify_demo_run.py` staging (all 11 on `node_1`):** removing `upload_td_02.npz` re-rolls
  `upload_td_03/04/05` — **3 rows out of 592.** A re-roll is a fresh draw from the same distribution,
  not a bias, so the correct reading is "one more seed", not "a shifted result".

Nothing here makes clip count non-inert. The one real consequence is **bit-level**: any recorded AUC
obtained with 11 clips will not reproduce exactly with 10. If a rehearsal screenshot or a quoted
number is being treated as golden, re-run `verify_demo_run.py` after changing the pool. Since the
recommendation above is to leave the pool alone, this does not arise.

## Adjacent observations

Not part of the question, noticed while doing it, each cheap to fix:

- **`asd_06` is missing from `demo_videos/manifest.csv`.** The manifest lists 10 rows
  (`asd_01..05`, `td_01..05`) but 11 clips exist. `asd_06` is 1280x720 and **38.7 s**, outside the
  "roughly 5–20 s" screening window stated in `DEMO_SCRIPT.md`, and it is by far the longest clip
  (146 sampled frames vs 21–75 for the rest). It is clean on the pose metric (0.9%); this is a
  bookkeeping gap, not a quality one. Also: the manifest's `td_02` duration of 10.6 s and 640x360
  resolution match ffprobe exactly, so the manifest is accurate where it exists.
- **The working tree has re-spread the uploads across all three nodes, against the committed
  staging.** `DEMO_SCRIPT.md` and `verify_demo_run.py` both say the live upload goes into **one**
  node's folder, and record that spreading the same clips over three nodes is what previously pushed
  the headline below the pooled-centralized reference. `git status` shows the committed tree had all
  eleven uploads on `node_1` — i.e. the commit follows the guidance — and that the current working
  tree has deleted nine of them and added one clip per class to `node_2` and `node_3` instead. This
  predates and is unrelated to this study; nothing here changed it. But whoever staged it should
  decide deliberately, because it is the one arrangement the earlier work identified as risky, and
  it also changes which case of the sort-order caveat applies (see above: last-in-sort on `node_3`
  in the working tree, mid-block on `node_1` in the commit).
- **Out-of-frame landmarks are not just cosmetic — they feed the model.** `features.py` hip-centres
  and torso-scales the coordinates but applies **no visibility weighting** to the kinematics:
  `sp_mean`, `sp_std`, `sp_max` and `pos_std` for indices 23–32 are computed from the extrapolated
  coordinates at full weight, and visibility enters the 174-dim vector only as a single scalar
  `mean_vis`. So the invented legs of `td_02`/`td_04`/`td_05` are real inputs, not just pixels. This
  changes nothing about the recommendation (11 rows in 592, at the DP noise floor) but it is the
  reason not to reach for "it's only the overlay" as the reassurance on stage.

## Reproducing

```
../../.venv/Scripts/python.exe phantom_limbs.py
```

Reads `demo_videos/npz/{asd,td}/*.npz`, writes `results.json`, prints the ranking table and both fix
sweeps. Runs in under a second; no coordinator, no federation, no network.

`results.json` holds per-clip aggregate statistics only — rates, counts and overshoot magnitudes.
No landmark coordinates, no frames and no images were written by this study, and nothing was copied
outside the repository. The clips are real recordings of real children.
