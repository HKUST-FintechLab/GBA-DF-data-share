# Recording the federated POC demo (内部 / 伙伴演示)

Goal: a clean ~90-second screen recording that shows the claims live.
Verified run (HAR, ε=1/round): **federated-DP 0.760 ≈ centralized-DP 0.723** (siloing is free) vs
**non-private ceiling 0.972** (the DP utility cost); global ε metered (5/10), budget-exceed blocked;
audit **chain + signatures verified**; `verify_security.py` → **25/25** checks pass. The same demo runs
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
  updates; SHA-256 hash-chained audit; held-out test set; DP-noise layer is the planned next step.
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
the federation matches your modality) **→ Connect & start**. Point at the standing **"0 bytes raw
uploaded"** banner and the live ε bar. Key line: *"same privacy machinery, any modality — only the
front end that reads your recordings changes; your raw data never leaves this window."*

> The eye-gaze / action / EEG-fMRI demo cohorts are **synthetic** (clearly labelled) — they prove the
> pipeline end-to-end per modality, not clinical accuracy. Point the client at real recordings in the
> documented format (§4/§5 of the Partner Guide) and the identical path runs on real data.

## Re-record / reset

```bash
pkill -f "coordinator:app"
uv run python run_demo.py --prepare --nodes 3 --rounds 5                 # HAR
uv run python run_demo.py --prepare --modality eyegaze --nodes 3 --rounds 5
```
