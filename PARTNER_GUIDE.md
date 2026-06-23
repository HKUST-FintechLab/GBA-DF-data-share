# GBA-DF Cross-Group Federated Experiment — Partner Guide

**Greater Bay Area Data Federation (GBA-DF) · HKUST**

> 中文摘要：本指南面向合作机构。我们计划做一次**跨机构联邦学习实验**:贵机构的**原始数据全程不出本地**,
> 只在本地训练并上传**带差分隐私(DP)保护的模型参数**。本文说明如何**准备数据、部署节点、运行实验**,
> 以及我们提供的**隐私与审计保障**。技术命令为英文,如需全中文版请告知。

---

## 1. What we're proposing

A joint experiment where several institutions train **one shared model together without sharing data**.
Each institution runs a small "node" program on its own machine. The node:

1. trains **data-independent random trees on your local data, on your hardware**;
2. sends only **integer leaf-count summaries** of those trees to a coordinator we host;
3. the coordinator (the **trusted curator**) adds calibrated **differential-privacy noise**, merges
   everyone's contributions into a stronger global model, and sends back results.

**Your raw data (videos, signals, tables, identifiers) never leaves your machine** — the node uploads
only aggregated leaf counts of trees whose structure never depended on your data. (We use a
*central-DP / trusted-curator* model: the coordinator we host adds the privacy noise and sees the
un-noised aggregates; *local-DP* and *secure aggregation*, so even we can't see un-noised aggregates,
are planned next steps.)

## 2. What you are protected by

| Guarantee | What it means for you |
|---|---|
| **Raw data stays local** | The node uploads only **integer leaf-count summaries** of data-independent trees — the accepted schema carries no raw feature/label arrays, and the coordinator validates/bounds-checks every payload. |
| **Differential privacy (ε)** | The published model is **(ε)-differentially private**: tree splits come from a *public* feature range (never from your data), and the **coordinator adds calibrated Laplace noise** at the federation's ε. ε is **set and enforced by the coordinator** (not self-declared), and a **per-node ε-budget** caps cumulative privacy loss. |
| **You sign everything** | Your node holds a private key (generated locally, never sent). Every upload is **digitally signed**; the coordinator rejects anything not signed by your enrolled key. |
| **Tamper-evident audit** | Every operation is hash-chained and signed by the coordinator; the log is verifiable against the coordinator's published public key (`/pubkey`). |
| **You can read the code** | The node is ~120 lines of Python (`node.py`, `dp.py`). You can inspect exactly what is computed and sent before running it. |

> Honest scope: this is a research POC using **central-DP** — the coordinator (us) is the trusted
> curator that adds the noise, so it sees your **un-noised integer leaf aggregates** (not raw records)
> before privatising. DP uses **basic composition**; a *fully compromised coordinator* is out of scope.
> **Local-DP** (you add the noise) and **secure aggregation** (we never see un-noised aggregates) are
> planned next steps. The trust assumption is exactly the one in §10 — you can read the node code.

## 3. Prerequisites (on your machine)

- **Windows, macOS, or Linux** with **Python 3.10+** and outbound network access to the coordinator host.
- **[uv](https://docs.astral.sh/uv/)** —
  - macOS / Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
  - **Windows** (PowerShell): `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
- The `federated_poc` folder (we send it, or share a repo link).
- No GPU needed; CPU is fine.

```bash
cd federated_poc
uv sync          # installs the pinned dependencies into .venv (cross-platform)
```

> **Windows is fine for running a node.** A node needs only CPU libraries (numpy, scikit-learn,
> cryptography, httpx), all of which have Windows wheels, and `uv run …` behaves identically on every
> OS — **no venv activation needed**. (Only the *coordinator* uses `uvicorn`/`uvloop`, which is
> Linux/macOS-only and auto-skipped on Windows — and we host the coordinator anyway.)
>
> **Windows key note:** the private key's POSIX `0600` permission doesn't apply on Windows (the code
> still runs). Protect `node_key.pem` with your normal account/disk controls or full-disk encryption.

## 4. Agree the schema first (one-time, before any run)

Federated learning requires every node to use the **same feature representation**. Before the
experiment we jointly fix, and the coordinator publishes at `GET /schema`:

- **`classes`** — the exact label set (e.g. the activity / category names).
- **`n_features`** and their **order/meaning** — the agreed feature vector.
- **`feature_bounds`** — public per-feature min/max used for DP splits (public, not your data).
- **`dp`** — `epsilon_per_round`, tree `depth`, `trees_per_round`, and the per-node `budget`.

We provide the **feature-extraction code or spec** so you compute the same features locally. (For the
HAR reference dataset this is already wired; for the real modality we agree it together.)

## 5. Prepare your data (stays local)

Produce a single local file `data.npz` containing:

- `X` — `float32` array, shape `[n_samples, n_features]` (features in the agreed order).
- `y` — string labels, each from the agreed `classes`.

Easiest path — from a CSV (all columns numeric features except the label column):

```bash
uv run python make_node_data.py --csv your_data.csv --label-col activity \
    --coord http://<coordinator-host>:8055 --out nodes/your_org/data.npz
```

`make_node_data.py` **validates locally** that your feature count and labels match the federation
schema and writes `data.npz`. It uploads nothing. (Prefer ≥ a few hundred samples per node, with all
classes represented.)

## 6. Run your node

```bash
uv run python node.py \
    --node-id your_org \
    --name "Your Institution" \
    --coord http://<coordinator-host>:8055 \
    --data nodes/your_org/data.npz \
    --rounds 5
```

> **Windows (PowerShell/cmd):** the `\` line-continuations above are bash syntax — put the whole
> command on **one line** instead (just delete the `\` and newlines). Same for the `make_node_data.py`
> command in §5. `uv run …` itself works identically on Windows.

What happens each round: the node trains data-independent trees on your local data, signs the upload
(binding round, sample count, and a hash of the leaf counts), uploads it, and prints e.g.:

```
[your_org] round 3: local=842 | raw arrays sent=0 | leaf counts uploaded (curator noised) | ε cum 3.00/10 | update=2304 KB | global acc=0.74
```

Your private key is created at `nodes/your_org/node_key.pem` (POSIX mode `0600`) and **must not be
shared**. **ε is set and enforced by the coordinator** (the curator), not chosen by the node — you
spend `epsilon_per_round` of your per-node budget each round, shown as `ε cum … / budget`.

## 7. The experiment protocol

1. **Kickoff** — we agree the schema (§4), the class set, ε per round, number of rounds, and a window.
2. **We host the coordinator** and share its URL + (over a separate channel) the expected node ids /
   public keys for enrolment. You can also host your own coordinator to dry-run internally first.
3. **Each partner prepares `data.npz` locally** (§5) — nothing transmitted yet.
4. **Synchronised run** — at the agreed time each partner runs `node.py` for the agreed rounds.
5. **Read-out** — we share the global metrics, the per-node ε ledger, and the signed audit log;
   anyone can verify the log against `/pubkey`.
6. **Repeat / extend** — add modalities, partners, or a non-IID analysis as agreed.

You can watch progress live on the coordinator dashboard (`http://<coordinator-host>:8055`):
federated-DP accuracy vs the centralized-DP and non-private baselines, every node's ε budget, and the
streaming audit log.

## 8. Security & operations

- **Networking:** the coordinator binds localhost by default; for a real cross-site run we expose it
  deliberately **behind TLS** (HTTPS) and share a pinned certificate / URL. Keep your node's outbound
  access limited to that host.
- **Keys:** `node_key.pem` is your identity — back it up securely, never commit or email it.
- **Enrolment:** a node id binds to the first key it registers (it can't be hijacked afterwards). Send
  us your node id + public key out-of-band so we can confirm it.
- **Budget:** once your cumulative ε reaches the agreed budget, further uploads are refused (HTTP 429)
  — this is the privacy guarantee working as intended.

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| `FEATURE MISMATCH … expects N` | Your feature vector length/order differs from the schema — re-run the agreed feature extraction. |
| `UNKNOWN LABELS […]` | A label isn't in the agreed class set — fix or remap your labels. |
| `signature verification failed` | Wrong/missing key, or payload mangled by a proxy — re-run with the original `node_key.pem`. |
| `epsilon budget exceeded (429)` | You've spent the agreed ε budget; we raise it together if the experiment needs more rounds. |
| `unregistered node` | Run `node.py` once to enrol, or your `node-id` differs from what we enrolled. |
| Can't reach coordinator | Check the URL/port, TLS, and your firewall's outbound rules. |

## 10. FAQ

- **Do you ever see our raw data?** No raw records — the node transmits only integer leaf-count
  summaries of data-independent trees. As the trusted curator we *do* receive those un-noised
  aggregates and then add the privacy noise (central-DP). Local-DP / secure aggregation (so we never
  see un-noised aggregates) are planned.
- **Can the published model leak our data?** The released model is **(ε)-differentially private**,
  which formally bounds what can be inferred about any individual record. Lower ε = stronger privacy;
  we set and enforce ε and meter your budget.
- **Can we audit what runs?** Yes — read `node.py` and `dp.py` (short, dependency-light), and verify
  the federation's audit log against `/pubkey`.
- **What hardware/time?** CPU-only; a 5-round run is minutes. No persistent service required on your
  side — you run the node only during the experiment window.

## 11. Contact

Greater Bay Area Data Federation — HKUST (Prof. Kani Chen, Department of Mathematics). Please reply to
your existing contact to schedule the kickoff and exchange the coordinator URL + node enrolment details.
