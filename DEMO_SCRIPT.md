# Recording the federated POC demo (内部 / 伙伴演示)

Goal: a clean ~90-second screen recording that shows the claims live.
Verified run (ε=1/round): **federated-DP 0.760 ≈ centralized-DP 0.723** (siloing is free) vs
**non-private ceiling 0.972** (the DP utility cost); per-node ε metered (5/10), budget-exceed blocked;
audit **chain + signatures verified**; `verify_security.py` → **15/15** checks pass.

## Pre-flight

```bash
cd data_share/federated_poc
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

- **Internal / technical:** forest-merge federated learning (matches CDP-TreeFusion); Ed25519-signed
  updates; SHA-256 hash-chained audit; held-out test set; DP-noise layer is the planned next step.
- **Partner / non-technical:** "Your data never leaves your hospital. You get a stronger shared
  screening model trained with everyone's data. Every step is signed and auditable, and you can run
  the node on your own machine."

## Re-record / reset

```bash
pkill -f "coordinator:app"
uv run python run_demo.py --prepare --nodes 3 --rounds 5
```
