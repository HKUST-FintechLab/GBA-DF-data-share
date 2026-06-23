# GBA-DF Federated Learning POC — action data

A **working** federated-learning proof-of-concept for the Greater Bay Area Data Federation.
It demonstrates, end-to-end and recordable, the four claims the federation rests on:

| Claim | How it's shown | Honest scope |
|---|---|---|
| **Multi-node** | Coordinator + N independent node processes (each can run on a different machine). | Fully supported. |
| **Differential privacy (central-DP)** | **Trusted-curator model:** each node ships integer leaf histograms of **data-independent** random trees; the **coordinator adds the Laplace(1/ε) noise**, *sets* ε, and meters a **per-node ε-budget**. | A genuine **(ε,0)-DP** release per node per round, **basic composition**. ε is **enforced by the curator** (not self-declared). The coordinator sees un-noised leaf *aggregates* (never raw records); local-DP + secure aggregation are future work. |
| **Signed + hash-chained audit** | Each node update is **Ed25519-signed** (binds round, n_samples, payload); each event is signed by the coordinator and **hash-chained**. `verify()` checks the chain **and** every signature against the coordinator's published key (`/pubkey`). | Detects any edit / truncation / re-sign-with-wrong-key within a run (`verify_security.py`). A *fully compromised* coordinator needs external anchoring (future work). |
| **Federated ≈ centralized-DP** | Global accuracy plotted live vs a **centralized-DP** reference (same mechanism, pooled, ε=1) AND the non-private ceiling. | Federated tracks the centralized-DP reference (the gap is small/favourable across seeds). The non-private→DP drop is the real **utility cost of privacy**. HAR numbers are IID / single-seed / window-level. |

Verified run (HAR, 3 nodes × 5 rounds, **ε=1/round, curator-enforced**): **federated-DP acc ≈ 0.77 vs
centralized-DP ≈ 0.72** vs **non-private ceiling 0.972** (the DP utility cost); per-node ε metered
(5.0/10), budget-exceed blocked (`429`), audit **chain + signatures verified**, and an under-declared-ε
attack is ignored (ε is curator-set). `verify_security.py` runs **16 checks**. This POC was hardened
across **three rounds** of adversarial code audit (security, regressions, DP correctness).

## Method — DP federated forest

**Central differential privacy** (trusted-curator), the strategy the protocol specifies for tree
models like CDP-TreeFusion:

- **Data-independent structure** — each tree's splits are random features + random thresholds drawn
  from the federation's **public** per-feature bounds (HAR is documented-normalised to [-1,1]); private
  data never influences the tree shape (`verify_security.py` proves this).
- **Node → curator** — the node routes its local data to leaves and ships **integer leaf histograms**
  (`dp.build_dp_counts`); it adds no noise and does not choose ε.
- **Curator (coordinator) → DP** — adds **Laplace(1/ε)** to each leaf count at the federation's ε, then
  normalises (`dp.add_dp_noise`). Records are **partitioned disjointly across a node's trees** ⇒
  *parallel* composition ⇒ the forest costs ε, not ε·(#trees); leaf-histogram L1 sensitivity = 1. ε is
  **enforced by the curator** and metered per node; rounds compose sequentially (basic composition).
- **Merge** — the coordinator combines node forests into a sample-weighted global ensemble
  (`fed_common.JsonForest`).

The non-private ceiling (label-optimised ExtraTrees) is computed in `prepare_data.py` for comparison.

## Datasets

- **`har`** (default) — UCI Human Activity Recognition (6 activities, 561 features, 10,299 windows;
  fetched once via OpenML, cached to `data/`). Real action data, strong signal, the canonical FL benchmark.
- **`pose`** — the project's own ASD action/pose seeds (real, on-brand). Small 65-subject *seed* set →
  weak subject-generalizable signal (centralized AUC ≈ chance on this seed subset); kept as an option,
  not the headline demo. The full CDP-TreeFusion corpus (≈779 videos) is where the 0.92 lives.

## Quick start (uv)

```bash
cd data_share/federated_poc
uv sync                                   # creates .venv from pyproject.toml / uv.lock
uv run python verify_security.py          # 15 checks (tamper-evidence, sig binding, schema/bounds, DP)
uv run python dp.py                        # optional: print the ε–accuracy tradeoff on HAR

# one command: prepare data -> start coordinator -> run all nodes -> live dashboard
uv run python run_demo.py --nodes 3 --rounds 5
# open the dashboard URL it prints (http://localhost:8055), then start your screen recorder
```

Re-prepare / change dataset:

```bash
uv run python prepare_data.py --dataset har  --nodes 3 --total-trees 600
uv run python prepare_data.py --dataset pose --nodes 3        # project pose seeds
uv run python run_demo.py --prepare --nodes 3 --rounds 5
```

## Run a node on another machine (partner group)

The federation is just a coordinator + clients over HTTP, so a partner runs a node on their own
hardware against their own data:

```bash
# on the coordinator host
uv run uvicorn coordinator:app --host 0.0.0.0 --port 8055

# on the partner's machine (their data stays on their machine)
uv run python node.py --node-id partner_lab --coord http://<coordinator-host>:8055 \
    --data /path/to/their/local/data.npz --rounds 5 --trees 40 --name "University Lab"
```

`data.npz` holds their local `X` (features) and `y` (labels). Their private signing key is generated
next to it (`node_key.pem`) and **never leaves the machine**.

## Files

| File | Role |
|---|---|
| `data_loaders.py` | `har` / `pose` dataset loaders |
| `features.py` | pose-window → engineered feature vector (for `pose`) |
| `prepare_data.py` | split off coordinator test set, partition train across nodes, train centralized baseline |
| `fed_common.py` | Ed25519 signing, signature-verified hash-chained `Audit`, multiclass `GlobalModel` (forest merge) |
| `dp.py` | differentially private random forest (data-independent splits + Laplace leaf noise) + ε-sweep |
| `coordinator.py` | FastAPI server: register / verify-signature / merge / evaluate / audit / dashboard |
| `node.py` | a node: load local data, train locally, sign (binds round + n_samples + payload), submit JSON tree schema |
| `run_demo.py` | one-command recordable demo |
| `verify_security.py` | reproducible audit-tamper / signature-binding / payload-schema checks |
| `static/dashboard.html` | live dashboard (warm GAIVRT theme): accuracy vs ensemble size, nodes, signed audit log |
| `DEMO_SCRIPT.md` | recording guide + narration for internal / partner demos |
| `PARTNER_GUIDE.md` | **cross-group experiment guide for a partner institution** (deploy, prepare data, run a node) |

## Security (hardened after an adversarial code audit)

- **No pickle on the wire.** Updates are a constrained JSON tree schema (`children_left/right,
  feature, threshold, leaf-proba`), validated and rebuilt into a pure-numpy predictor server-side —
  closing the `pickle.loads` RCE. Off-schema or raw-array payloads are rejected.
- **Signatures bind the payload.** The node signs `node_id | round | n_samples | sha256(update)`, so
  the merge weight and model can't be altered in transit; the coordinator uses the *enrolled* sample
  count as the weight (forged `n_samples` can't dominate aggregation).
- **DP ε-budget ledger:** every submission declares its ε (bound by the signature); the coordinator
  meters cumulative ε per node and rejects (`429`) once the per-node budget is exhausted.
- **Replay protection** (round must increase) and **TOFU enrolment** (`node_id` can't be rebound to a
  new key). Coordinator binds **127.0.0.1 by default** — expose deliberately and add TLS for cross-site.
- **Audit signatures are actually verified** against the coordinator's published key (`/pubkey`); the
  in-process check is integrity-against-accident + naive tampering, not against a compromised host.
- Node private keys are written `0600` and git-ignored.

Run `uv run python verify_security.py` to see all of this pass (and the attacks fail).

## Honesty notes (deliberate — meant to be defensible, not self-certified)

- **DP is central-DP (trusted curator):** the coordinator adds the Laplace noise and *enforces* ε, so
  ε is not self-declared by nodes. Trade-off: the coordinator receives **un-noised integer leaf
  aggregates** (of data-independent trees — never raw records) before noising; a *fully compromised*
  coordinator is out of scope. **Local-DP** (node-side noise) and **secure aggregation** (so the
  curator never sees un-noised aggregates) are future work. Accounting is **basic composition**.
- **The DP accuracy cost is real and mostly structural:** data-independent splits cap accuracy
  (~0.76 on HAR vs 0.97 non-private); the Laplace noise itself costs little at ε=1. This is the honest
  price of the guarantee — shown explicitly via the non-private ceiling and the `dp.py` ε-sweep.
- **The "convergence" curve is ensemble-size variance reduction, not round-over-round learning** —
  tree-merge has no iterative training; the dashboard labels the axis accordingly.
- **HAR uses a window-level stratified, IID, single-seed split** (the OpenML variant has no subject
  ids). Absolute ~0.96/0.97 is optimistic; the federated-vs-centralized *gap* is the honest result.
  The `pose` loader uses an honest subject-level split; the project's flagship CDP-TreeFusion 0.92 is
  on the full corpus and is **not** produced by this POC.
