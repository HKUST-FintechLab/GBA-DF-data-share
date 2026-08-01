# Recording the federated POC demo (内部 / 伙伴演示)

Goal: a clean ~90-second screen recording that shows the claims live.
Verified run (HAR, ε=1/round): **federated-DP 0.760 ≈ centralized-DP 0.723** (siloing is free) vs
**non-private ceiling 0.972** (the DP utility cost); global ε metered (5/10), budget-exceed blocked;
audit **chain + signatures verified**; `verify_security.py` → **28/28** checks pass. The same demo runs
on any of three modalities — add `--modality eyegaze|action|neuro` (see the last section).

## Pre-flight

```bash
cd GBA-DF-data-share
uv sync
rm -rf data nodes            # optional: clean slate for a fresh recording
```

## The take (one command, then narrate)

```bash
uv run python run_demo.py --prepare --nodes 3 --rounds 5
```

Open **http://localhost:8055** and start the screen recorder. The nodes finish in seconds; the
dashboard stays live for the whole recording.

### Narration → what's on screen → which claim it proves

1. **Header** — "This is the GBA-DF federation training on action-recognition data across three
   institutions." Point at **`audit chain verified ✓`**.
2. **Headline row** —
   - *Federated accuracy 0.971* vs *Centralized baseline 0.984* → "the federation reaches essentially
     the same accuracy as if all data were pooled — **without pooling it**." (claim: federated≈centralized)
   - **DP guarantee ε=1/round** + **Non-private ceiling 0.972** → "each node's update is formally
     (ε=1)-differentially private — random-forest splits never see the data, and we add Laplace noise
     to the leaf histograms. That privacy costs accuracy (0.97 → 0.76); the gap to *centralized-DP*
     (0.72) is ~zero, so federating across institutions is free."
   - **Per-node ε-budget bars (5/10)** → "every release is metered against a privacy budget; past it
     the coordinator refuses." (claim: ε-budget ledger)
3. **Convergence chart** — the federated line tracking the dashed centralized baseline.
4. **Participating nodes** — three cards, each `data stays local`, `raw bytes sent 0`. Say "one of
   these can be a partner group running on their own machine — they keep their data." (claim: multi-node)
5. **Audit log** — "every model update is cryptographically signed by the contributing node, and every
   event is hash-chained — tamper-evident." (claim: signed audit)

### Optional "wow": prove tamper-evidence + security on camera

```bash
uv run python verify_security.py
```

Shows, reproducibly: the clean audit log verifies (chain + signatures); **editing** one entry,
**truncating** the tail, or **forging + re-signing with another key** all FAIL against the
coordinator's pinned public key; the `/submit` signature breaks if `n_samples` is altered; and a
pickle / raw-array payload is rejected by the schema.

## Two audiences, two scripts

- **Internal / technical:** forest-merge federated learning (random-forest / tree-merge); Ed25519-signed
  updates; SHA-256 hash-chained audit; held-out test set; coordinator-applied Laplace noise and a
  global ε budget.
- **Partner / non-technical:** "Your data never leaves your hospital. You get a stronger shared
  screening model trained with everyone's data. Every step is signed and auditable, and you can run
  the node on your own machine."

## Multi-modal + desktop-client take (the "landing" for partners)

Show the SAME machinery on the modality a partner cares about, driven from the desktop app.

```bash
# 1) coordinator for the chosen modality (eyegaze | action | neuro)
uv run python prepare_data.py --modality eyegaze --nodes 3
uv run uvicorn coordinator:app --host 0.0.0.0 --port 8055
# 2) the partner desktop client
uv run python client_app.py
```

Narrate the client's four steps on camera: **pick modality → choose data folder** (native picker; it
scans and shows the ASD/TD split locally) **→ enter coordinator + node info** ("Test connection" confirms
the federation matches your modality) **→ Connect & start**. Point at **"Raw data stays local"**, the
exact **FL JSON payload sent** counter, and the live ε bar. Key line: *"same privacy machinery, any modality — only the
front end that reads your recordings changes; your raw data never leaves this window."*

> The eye-gaze / action / EEG-fMRI demo cohorts are **synthetic** (clearly labelled) — they prove the
> pipeline end-to-end per modality, not clinical accuracy. Point the client at real recordings in the
> documented format (§4/§5 of the Partner Guide) and the identical path runs on real data.

### Rehearsal staging: a baseline cohort plus real clips to upload live

Uploading two or three clips on camera shows the privacy path, but two or three feature rows cannot
carry a metric: the coordinator adds Laplace noise to every leaf-count cell, so with that little data
the AUC is a coin flip and the demo argues against itself. Stage a synthetic baseline per node first,
then upload real clips into the same folder so one run carries both the privacy story and a metric
with signal.

```bash
uv run python stage_demo_nodes.py --modality action --nodes 3 --per-class 6
```

This writes `demo_nodes/node_1|2|3`, each an independent synthetic cohort (its own seed, both classes,
every file named `synthetic_…` under a `SYNTHETIC-DATA.txt` marker). `client_app.py --node-id node_N`
then defaults its extracted-NPZ folder to the matching `demo_nodes/node_N`, so clips extracted on
camera land beside that baseline and train together. Pass `--video-out` to override, and note the
advanced settings correctly report the folder as permanent — retention is a deliberate choice.

`demo_videos/asd|td` holds clips screened for this rehearsal: one child, whole body in frame, no
burned-in captions, no shot changes, roughly 5–20 s, audio stripped. `demo_videos/manifest.csv` lists
length and resolution. **These are real recordings of real children.** They are git-ignored, must not
be redistributed, and the ethics coverage in
[`wiki/human-critical-path.md`](wiki/human-critical-path.md) applies to any run that touches them.

Say the composition out loud rather than letting the number speak for itself:

> "Each node also holds a synthetic baseline cohort so the metric has statistical meaning. The clips
> just uploaded joined that same pool."

Do **not** attribute a round's metric change to the clips just uploaded — a round mixes fresh random
trees, fresh DP noise and the whole cohort's contribution, which is why
[`wiki/evaluation-and-claims.md`](wiki/evaluation-and-claims.md) rules out reading Δ as one
institution's contribution.

## Re-record / reset

```bash
pkill -f "coordinator:app"
uv run python run_demo.py --prepare --nodes 3 --rounds 5                 # HAR
uv run python run_demo.py --prepare --modality eyegaze --nodes 3 --rounds 5
```

For the staged desktop rehearsal, `reset_demo.py` puts the federation back to round 1 without
touching the coordinator's identity — it deletes the room state and keeps `coordinator_key.pem`, so
issued invitations stay valid. It refuses to run while something still holds the port, because a
live coordinator keeps its state in memory and would write the cleared files straight back.

```bash
uv run python reset_demo.py                    # stop, clear, restart
uv run python reset_demo.py --purge-videos     # also drop clips extracted into demo_nodes/
uv run python reset_demo.py --export audit.zip # archive the chain before clearing it
```
