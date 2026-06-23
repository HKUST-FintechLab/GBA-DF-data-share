# GBA-DF Federated Learning POC — action data

A **working** federated-learning proof-of-concept for the Greater Bay Area Data Federation.
It demonstrates, end-to-end and recordable, the four claims the federation rests on:

| Claim | How it's shown | Honest scope |
|---|---|---|
| **Multi-node** | Coordinator + N independent node processes (each can run on a different machine). | Fully supported. |
| **Raw data stays local** | Nodes submit a constrained JSON tree schema; **raw feature/label arrays cannot be expressed in the accepted payload** and are rejected. | Raw arrays are not transmitted. The **model itself is NOT privacy-protected** (it encodes dataset statistics); DP / secure-aggregation is future work. |
| **Signed + hash-chained audit** | Each node update is **Ed25519-signed**; each event is signed by the coordinator and **hash-chained**. `verify()` checks the chain **and** every signature against the coordinator's published key (`/pubkey`). | Detects any edit / truncation / re-sign-with-wrong-key within a run (see `verify_security.py`). Defending a *fully compromised* coordinator needs external anchoring (future work). |
| **Federated ≈ centralized** | Global accuracy plotted live vs a centralized baseline on the pooled data (same held-out test set, same metric, matched tree budget). | The **gap** is the honest result. Absolute HAR numbers are window-level / IID / single-seed and optimistic. |

Verified run (HAR, 3 nodes × 5 rounds): **federated acc 0.962 vs centralized 0.972** (gap 0.010),
`/submit` rejects non-tree payloads, audit **chain + signatures verified**, and `verify_security.py`
shows edit / truncate / forge all fail. This POC was hardened against an adversarial code audit
(see "Security").

## Method (federated forest)

The pose classifier (CDP-TreeFusion) is a tree ensemble, so the federation strategy is the one the
protocol specifies for pose: **each node trains Extra-Trees locally and contributes only the trained
trees**; the coordinator merges them into a sample-weighted global forest. This needs no raw-data
exchange and naturally lands federated ≈ centralized.

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
uv run python verify_security.py          # 12 security checks (audit tamper-evidence, sig binding, schema/bounds)

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
| `fed_common.py` | Ed25519 signing, hash-chained `Audit`, multiclass `GlobalModel` (forest merge) |
| `coordinator.py` | FastAPI server: register / verify-signature / merge / evaluate / audit / dashboard |
| `node.py` | a node: load local data, train locally, sign (binds round + n_samples + payload), submit JSON tree schema |
| `run_demo.py` | one-command recordable demo |
| `verify_security.py` | reproducible audit-tamper / signature-binding / payload-schema checks |
| `static/dashboard.html` | live dashboard (warm GAIVRT theme): accuracy vs ensemble size, nodes, signed audit log |
| `DEMO_SCRIPT.md` | recording guide + narration for internal / partner demos |

## Security (hardened after an adversarial code audit)

- **No pickle on the wire.** Updates are a constrained JSON tree schema (`children_left/right,
  feature, threshold, leaf-proba`), validated and rebuilt into a pure-numpy predictor server-side —
  closing the `pickle.loads` RCE. Off-schema or raw-array payloads are rejected.
- **Signatures bind the payload.** The node signs `node_id | round | n_samples | sha256(update)`, so
  the merge weight and model can't be altered in transit; the coordinator uses the *enrolled* sample
  count as the weight (forged `n_samples` can't dominate aggregation).
- **Replay protection** (round must increase) and **TOFU enrolment** (`node_id` can't be rebound to a
  new key). Coordinator binds **127.0.0.1 by default** — expose deliberately and add TLS for cross-site.
- **Audit signatures are actually verified** against the coordinator's published key (`/pubkey`); the
  in-process check is integrity-against-accident + naive tampering, not against a compromised host.
- Node private keys are written `0600` and git-ignored.

Run `uv run python verify_security.py` to see all of this pass (and the attacks fail).

## Honesty notes (deliberate — meant to be defensible, not self-certified)

- **Differential privacy is NOT implemented.** "Raw data stays local" means raw feature/label arrays
  are never transmitted — but the shipped model still encodes dataset statistics and (with small
  leaves) per-record information. `min_samples_leaf` blunts this; DP / secure-aggregation is the
  protocol's next layer, not done here.
- **The "convergence" curve is ensemble-size variance reduction, not round-over-round learning** —
  tree-merge has no iterative training; the dashboard labels the axis accordingly.
- **HAR uses a window-level stratified, IID, single-seed split** (the OpenML variant has no subject
  ids). Absolute ~0.96/0.97 is optimistic; the federated-vs-centralized *gap* is the honest result.
  The `pose` loader uses an honest subject-level split; the project's flagship CDP-TreeFusion 0.92 is
  on the full corpus and is **not** produced by this POC.
