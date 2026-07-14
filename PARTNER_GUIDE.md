# GBA-DF Cross-Group Federated Experiment — Partner Guide

**Greater Bay Area Data Federation (GBA-DF) · HKUST**

> 中文摘要：本指南面向合作机构。我们计划做一次**跨机构联邦学习实验**:贵机构的**原始数据全程不出本地**,
> 只在本地训练并上传**带差分隐私(DP)保护的模型参数**。本文说明如何**准备数据、部署节点、运行实验**,
> 以及我们提供的**隐私与审计保障**。技术命令为英文,如需全中文版请告知。

---

## 1. What we're proposing

A joint experiment where several institutions train **one shared model together without sharing data**.
Each institution runs a small "node" program on its own machine. The node:

1. builds the federation's **shared, data-independent trees** and counts **your local data** into them, on your hardware;
2. **masks** those integer leaf counts (pairwise keys with the other institutions) and uploads only the masked vector;
3. the coordinator sums the masked vectors — the masks cancel, so it recovers **only the pooled total across all institutions**, never your individual counts — then adds **differential-privacy noise** and returns the stronger global model.

**Your raw data (videos, signals, tables, identifiers) never leaves your machine, and the coordinator
never sees your institution's individual contribution** — only the masked sum. This is **secure
aggregation + differential privacy**. (Trust model: an honest-but-curious, non-colluding coordinator;
the round needs all enrolled institutions to take part — dropout recovery is a planned next step.)

## 2. What you are protected by

| Guarantee | What it means for you |
|---|---|
| **Raw data stays local** | The node uploads only **masked integer leaf-count vectors** of data-independent trees — no raw arrays, and every payload is validated/bounds-checked. |
| **Secure aggregation** | Your counts are **pairwise-masked** so the coordinator can only recover the **pooled sum across all institutions** — it never sees your institution's own counts. |
| **Differential privacy (ε)** | The published model is **(ε)-differentially private**: tree splits come from a *public* feature range (never from your data), and the coordinator adds calibrated **Laplace noise to the secure aggregate** at ε. ε is **coordinator-set and enforced**, with a **global ε-budget** capping cumulative privacy loss. |
| **You sign everything** | Your node holds a private key (generated locally, never sent). Every upload is **digitally signed**; the coordinator rejects anything not signed by your enrolled key. |
| **Tamper-evident audit** | Every operation is hash-chained and signed by the coordinator; the log is verifiable against the coordinator's published public key (`/pubkey`). |
| **You can read the code** | The node loop is short, dependency-light Python (`node_core.py` + `dp.py` + `modalities.py`). You can inspect exactly what is computed locally and what is sent before running it. |

> Honest scope: research POC. **Secure aggregation** means the coordinator only ever sees masked
> vectors and their pooled sum — not any institution's individual counts — then adds the DP noise
> (**basic composition**). Assumptions: an **honest-but-curious, non-colluding** coordinator, a cohort
> of **≥ 3** institutions, and a round needs the **full enrolled cohort** (no dropout recovery yet — the
> Shamir part of Bonawitz, a planned next step). Secure aggregation protects **privacy, not input
> integrity** — a malicious participant could submit garbage to skew the shared model (robustness to bad
> inputs is future work). A *fully compromised* coordinator is out of scope. You can read the node code (§10).

## 3. Prerequisites (on your machine)

- **Windows, macOS, or Linux** with **Python 3.10+** and outbound network access to the coordinator host.
- **[uv](https://docs.astral.sh/uv/)** —
  - macOS / Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
  - **Windows** (PowerShell): `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
- The `federated_poc` folder (we send it, or share a repo link).
- No GPU needed; CPU is fine.

```bash
cd federated_poc
uv sync                 # installs the pinned dependencies into .venv (cross-platform)
uv sync --extra client  # ALSO installs the desktop app (recommended — see §6, Option A)
```

> **Windows is fine for running a node.** A node needs only CPU libraries (numpy, scikit-learn,
> cryptography, httpx), all of which have Windows wheels, and `uv run …` behaves identically on every
> OS — **no venv activation needed**. (Only the *coordinator* uses `uvicorn`/`uvloop`, which is
> Linux/macOS-only and auto-skipped on Windows — and we host the coordinator anyway.)
>
> **Windows key note:** the private key's POSIX `0600` permission doesn't apply on Windows (the code
> still runs). Protect `node_key.pem` with your normal account/disk controls or full-disk encryption.

## 4. Agree the modality & schema first (one-time, before any run)

Each experiment runs on **one data modality**, and every node must use the **same feature
representation**. We support three modalities out of the box (the coordinator publishes which one it is
at `GET /schema` as `modality`):

| Modality | Your raw recordings | Task |
|---|---|---|
| **`eyegaze`** — eye-tracking | one gaze **CSV** per recording (columns `x, y[, pupil]`) | ASD/TD social-attention screening |
| **`action`** — body pose | raw video converted locally in the desktop client, or one MediaPipe-pose **`.npz`** per clip (key `body`, shape `(T,33,4)`) | ASD/TD behavioural screening |
| **`neuro`** — EEG / fMRI | one **`.npz`** (key `ts`, channels×time) or CSV per scan | ASD/TD neuroimaging screening |

The feature extraction for each modality is **built in** (`modalities.py`) — you don't write feature
code; you just organise your raw files (§5). The coordinator publishes at `GET /schema`:

- **`modality`** — which of the above this federation runs.
- **`classes`** — the label set (e.g. `ASD`, `TD`).
- **`n_features`** — the fixed feature width for that modality (32 / 174 / 48).
- **`feature_bounds`** — public `[-1,1]` range used for DP splits (public, **not** your data).
- **`dp`** — `epsilon_per_round`, tree `depth`, `trees_per_round`, and the `budget`.

(A raw benchmark schema — HAR — is also supported for internal dry-runs.)

## 5. Prepare your data (stays local)

**Just organise your raw recordings into class subfolders** — feature extraction happens locally, on
your machine, at run time. Lay out a folder like:

```
your_data/
  asd/   your_recording_001.csv   your_recording_002.csv   …   (or .npz, per the modality)
  td/    control_001.csv          control_002.csv          …
```

The class is taken from the subfolder name (`asd/` → ASD, `td/` → TD). Use the file type your modality
expects (§4): CSV for eyegaze, `.npz` for action/neuro. That's it — point the desktop app or the CLI at
`your_data/` and it extracts the agreed features locally, uploading nothing. (Prefer ≥ a few hundred
recordings per node, with both classes represented.)

**Action video shortcut (desktop app only).** If you have original video rather than pose NPZ files,
choose **Extract raw video** in step 2. Select a batch label (ASD or TD), a 2/4/8 fps sampling rate, and
one or more videos. The app loads a pinned JavaScript build of MediaPipe Holistic from the CDN on demand,
shows pose extraction live, and saves `body: (T,33,4)` NPZ files under the corresponding class folder.
It then returns to the same folder-scan and federation flow used by existing NPZ data. Video decoding and
MediaPipe inference happen inside the local web view; the source video is never sent to Python or the
coordinator. The local Python bridge uses the already-installed NumPy only to validate and write the NPZ.
The CDN receives library/model requests, not your video or extracted landmarks.

*No data yet?* The desktop app's **"Generate a demo folder"** button (or `client_app.py`) writes a
synthetic cohort in the right layout so you can rehearse the whole flow first.

> **Advanced (pre-computed features):** if you already have an aligned feature matrix, you can instead
> build a baked `data.npz` (`X` float32 `[n, n_features]`, `y` string labels) — e.g. from a CSV via
> `uv run python make_node_data.py --csv your.csv --label-col label --coord http://<host>:8055 --out
> nodes/your_org/data.npz` — and pass `--data` instead of `--folder` in §6.

## 6. Run your node

### Option A — Desktop app (recommended)

```bash
uv run python client_app.py
```

A window opens and walks you through four steps: **① pick your data modality → ② choose your data
folder or locally convert action videos** (with a live skeleton preview; it scans and shows how many
recordings and the ASD/TD split) **→
③ enter the coordinator URL, the federation password, a node id, and a display name** (a "Test
connection" button confirms the password and that the federation matches your modality) **→ ④ Connect &
start**, with a live view of the rounds, the running
global accuracy, the ε budget, and a standing **"0 bytes raw uploaded"** banner. It is bilingual (中/EN,
top-right). The app runs the exact same node loop as the CLI below.

Raw-video conversion is intentionally not duplicated in the CLI. Use the desktop client to create the
compatible NPZ folder once; that folder can subsequently be used by either the desktop app or `node.py`.

### Option B — Command line

```bash
uv run python node.py \
    --node-id your_org \
    --name "Your Institution" \
    --coord http://<coordinator-host>:<port> \
    --password <federation-password> \
    --folder your_data \
    --rounds 5
```

`--folder your_data` ingests the raw recordings from §5 (the modality is taken from the coordinator's
`/schema`; pass `--modality eyegaze|action|neuro` to be explicit). For a pre-baked feature file, use
`--data nodes/your_org/data.npz` instead of `--folder`.

> **Windows (PowerShell/cmd):** the `\` line-continuations above are bash syntax — put the whole
> command on **one line** instead (just delete the `\` and newlines). `uv run …` itself works
> identically on Windows, and the desktop app (Option A) uses the built-in Edge **WebView2** runtime.

What happens each round: the node counts its local data into the shared trees, **masks** the counts,
signs the upload (binding round, sample count, and a hash of the masked vector), uploads it, and waits
for the cohort's secure aggregate. It prints e.g.:

```
[your_org] round 3: raw arrays sent=0 | MASKED counts uploaded (1288 KB) | global ε 3.00/10.0 | global acc=0.79
```

Your private key is created at `nodes/your_org/node_key.pem` (POSIX mode `0600`) and **must not be
shared**. **ε is set and enforced by the coordinator**, not chosen by nodes; the federation spends
`epsilon_per_round` of a **global** budget each round (shown as `global ε … / budget`). The round
completes once **all enrolled institutions** have submitted (secure aggregation needs the full cohort).

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

### Using the shared model (as a data-user / central node)

Once the run finishes, **everyone who took part can use the jointly-trained model** — it is the whole
point of federating. The model is an aggregated, pickle-free JSON forest held by the coordinator.

```bash
# (A) recommended — download the model and score YOUR OWN new recordings locally,
#     so your query data also stays on your machine:
uv run python predict.py --coord http://<coordinator-host>:8055 \
    --folder my_new_cases --out predictions.csv

# (B) convenience — send feature rows to the coordinator to score:
uv run python predict.py --coord http://<coordinator-host>:8055 --folder my_new_cases --hosted

# just archive the model artifact (JSON, carries provenance + the audit tip):
uv run python predict.py --coord http://<coordinator-host>:8055 --save-model global_model.json
```

It prints an ASD/TD call + confidence per recording (and accuracy if your folder is labelled) and
writes a CSV. The downloaded model carries its **provenance** — which modality, how many rounds, the DP
ε spent vs the budget, the held-out test metric, and the audit tip you can verify against `/pubkey`.
`GET /model` returns the artifact; `POST /predict` scores `{"X": [[…]]}` rows. Prefer (A) when the cases
you are screening are themselves sensitive.

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
| `no usable recordings found` | The folder has no files in the modality's format, or they aren't under `asd/` / `td/` subfolders — check §4/§5 layout and file type. |
| `feature mismatch: local N vs federation M` | You picked the wrong modality (or a stale schema) — select the modality the coordinator publishes at `/schema`. |
| `labels [...] not in federation classes` | A subfolder/label isn't in the agreed class set — put recordings under `asd/` and `td/`. |
| `signature verification failed` | Wrong/missing key, or payload mangled by a proxy — re-run with the original `node_key.pem`. |
| `epsilon budget exceeded (429)` | You've spent the agreed ε budget; we raise it together if the experiment needs more rounds. |
| `unregistered node` | Run `node.py` once to enrol, or your `node-id` differs from what we enrolled. |
| `cohort full` | The enrolled cohort is already complete — confirm your `node-id` is on the agreed list. |
| Round never completes / node hangs at a round | Secure aggregation needs the **whole cohort** each round — a missing or slow institution stalls it for everyone. We confirm all nodes are up before starting; restart the lagging node. |
| Can't reach coordinator | Check the URL/port, TLS, and your firewall's outbound rules. |

## 10. FAQ

- **Do you ever see our raw data — or even our institution's counts?** Neither. The node transmits
  only **masked** count vectors; with secure aggregation we can recover **only the pooled sum across
  all institutions**, never your individual counts (and never raw records). We then add the DP noise
  to that sum. (Assumes we don't collude to defeat the masking; the full enrolled cohort must take part.)
- **Can the published model leak our data?** The released model is **(ε)-differentially private**,
  which formally bounds what can be inferred about any individual record. Lower ε = stronger privacy;
  we set and enforce ε and meter your budget.
- **Can we audit what runs?** Yes — read `node.py` / `node_core.py`, `modalities.py`, and `dp.py`
  (short, dependency-light: local feature extraction, masking, signing, upload), and verify the
  federation's audit log against `/pubkey`.
- **What hardware/time?** CPU-only; a 5-round run is minutes. No persistent service required on your
  side — you run the node only during the experiment window.

## 11. Contact

Greater Bay Area Data Federation — HKUST (Prof. Kani Chen, Department of Mathematics). Please reply to
your existing contact to schedule the kickoff and exchange the coordinator URL + node enrolment details.
