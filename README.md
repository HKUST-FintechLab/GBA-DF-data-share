# GBA-DF Federated Learning POC — multi-modal (eye-gaze · action · EEG/fMRI)

A **working** federated-learning proof-of-concept for the Greater Bay Area Data Federation.
It demonstrates, end-to-end and recordable, the four claims the federation rests on — across
**three data modalities** (eye-tracking, body-action/pose, EEG/fMRI), with a **desktop node
client** a partner runs on their own machine (pick modality → pick folder → connect):

Project status and the compressed delivery schedule are maintained in the
[`wiki/`](wiki/README.md).

| Claim | How it's shown | Honest scope |
|---|---|---|
| **Multi-node** | Coordinator + N independent node processes (each can run on a different machine). | Fully supported. |
| **DP + secure aggregation** | Every node uploads **pairwise-masked** integer leaf counts of a **shared, data-independent** forest. The coordinator can only recover the **pooled sum** (masks cancel) — never an individual node's counts — then adds **Laplace(1/ε)** to that secure aggregate (central DP on the sum) and meters a **global ε-budget**. | Genuine **(ε,0)-DP** on the aggregate, **basic composition**, ε **coordinator-enforced**. The coordinator never sees individual node data. Caveats: honest-but-curious, **non-colluding** coordinator; **full cohort required per round** (no Shamir dropout recovery — future work). |
| **Persistent, exportable audit** | Each node update is **Ed25519-signed**; every event is coordinator-signed and hash-chained. The coordinator key, chain, node public keys, signed submission receipts, privacy spend, and latest model survive restarts. `GET /audit/bundle` exports a self-contained package for `verify_audit_bundle.py`. | Detects edits to the package, chain, receipts, or model. Files are written atomically with mode `0600`. A *fully compromised* coordinator still needs external anchoring (future work). |
| **Federated ≈ centralized-DP, robust to non-IID** | Multi-seed benchmark (`bench.py`) vs centralized-DP + the non-private ceiling, IID **and** non-IID. | Secure-agg tracks centralized-DP and **recovers the non-IID collapse**: the naive per-node ensemble drops to **0.51±0.10** under label skew; secure-agg holds **0.73±0.03** (figure below). |

Verified run (HAR, 3 nodes × 5 rounds, **ε=1/round**): federated **secure-agg DP ≈ 0.80 ≈ centralized-DP
0.72** vs **non-private ceiling 0.972** (the DP utility cost); coordinator sees only masked sums, global
ε metered (5.0/10), under-budget/`429` enforced, audit **chain + signatures verified**.
`verify_security.py` runs **91 checks** (its own 40 plus the API-security and round-integrity suites it
invokes). Hardened across **four rounds** of adversarial code audit
(security · regressions · DP correctness · secure aggregation).

Each modality is its **own federation** (its own feature schema); the privacy machinery is identical —
only the front end that turns raw recordings into features changes. Verified live end-to-end on all three
(3 nodes × 4 rounds, ε=1/round): eye-gaze fed AUC **0.78**, action **~0.80**, EEG/fMRI **0.80**, each
≈ its centralized-DP reference and below its non-private ceiling.

![Privacy–utility tradeoff: the price of the ε-guarantee, and secure aggregation's non-IID recovery](assets/epsilon_utility.png)

*The privacy dial (HAR, 3 nodes, 5 seeds). Non-private ceiling ≈ 0.98 → DP ≈ 0.73 is the honest cost of
the ε-guarantee. Under non-IID label skew the naive per-node ensemble **collapses** (~0.51) while secure
aggregation **holds** (~0.73), tracking the centralized-DP reference. Regenerate with `uv run python bench.py`.*

## Method — DP federated forest

**Secure aggregation + central differential privacy** (a strategy that fits tree / random-forest models
whose leaves are class histograms):

- **Shared, data-independent forest** — all nodes build the *same* trees from a **public** structure
  seed; splits are random features + thresholds from **public** per-feature bounds (HAR is documented-
  normalised to [-1,1]; each modality is mapped into the same public [-1,1] range by a shipped public
  `tanh(raw/scale)` transform). Private data never influences tree shape (`verify_security.py` proves this).
- **Node** — routes its local data to leaves (each record → one tree ⇒ L1 sensitivity 1), then masks
  its integer count vector with **pairwise X25519 masks** (`secure_agg.mask_counts`) and uploads only
  the masked vector.
- **Coordinator** — sums the masked vectors; the masks cancel, so it recovers **only the pooled leaf
  counts** (never an individual node's), then adds **Laplace(1/ε)** to that sum (`dp.forest_from_summed_counts`)
  and meters a **global ε-budget**. Disjoint records ⇒ *parallel* composition within a round; rounds
  compose sequentially (basic composition).
- Because the secure sum is the pooled distribution, the result tracks **centralized-DP even under
  non-IID** — fixing the per-node-ensemble collapse.

The non-private ceiling (label-optimised ExtraTrees) and a centralized-DP reference are computed in
`prepare_data.py`; `bench.py` produces the multi-seed IID/non-IID comparison and the ε-utility figure
above (`assets/epsilon_utility.png`, regenerated at `data/epsilon_utility.png`).
The legacy per-node-ensemble path (`dp.build_dp_counts`/`add_dp_noise`) is retained for that benchmark.

## Modalities (`modalities.py`) and benchmark datasets

**Modalities** — each turns a partner's folder of *raw recordings* into a fixed-width feature vector via
its own front end, then feeds the identical federation. `demo_dataset()` synthesizes a realistic cohort so
every modality runs end-to-end through the **same** extractor a real folder would:

| Modality | Raw files a partner has | Features → task | Dim |
|---|---|---|---|
| **`eyegaze`** | one gaze CSV per recording (`x, y[, pupil]`), under `asd/` `td/` | fixation / saccade / spatial-attention summary → ASD/TD | 32 |
| **`action`** | raw video converted locally by the desktop client, or one MediaPipe-pose `.npz` (key `body`, `(T,33,4)`) per clip | kinematic pose features (`features.py`) → ASD/TD | 174 |
| **`neuro`** | one EEG/fMRI `.npz` (key `ts`, channels×time) or CSV per scan | spectral band-power + functional-connectivity summary → ASD/TD | 48 |

Features are squashed into the **public** `[-1,1]` DP range by `tanh(raw / scale)`, where `scale` is a
**shipped public constant** (`public_scales.json`) computed once from a fixed-seed synthetic *reference*
cohort — **never** from participant data (`verify_security.py` proves it stays public and participant-
independent). `tanh` is monotone, so tree accuracy is unchanged while the DP forest gets a genuinely
public range to draw thresholds from.

**Benchmark datasets** (for the strong-signal numbers, no modality front end):

- **`har`** (default) — UCI Human Activity Recognition (6 activities, 561 features, 10,299 windows;
  fetched once via OpenML, cached to `data/`). Real action data, strong signal, the canonical FL benchmark.
- **`pose`** — an optional loader for MediaPipe-pose `.npz` seed data with a subject-level split. The
  seed data is **not shipped** with this repo; supply your own (see `data_loaders.load_pose`) or just use
  `har` / the `action` modality. `load_pose()` raises a clear error if the seed data is absent.

## Quick start (uv)

This project uses [uv](https://docs.astral.sh/uv/) (`pyproject.toml` + `uv.lock`).

```bash
git clone https://github.com/HKUST-FintechLab/GBA-DF-data-share.git
cd GBA-DF-data-share
uv sync                                   # creates .venv from pyproject.toml / uv.lock
uv run python verify_security.py          # 91 checks: privacy, API boundary, invitations, round integrity
uv run python modalities.py               # optional: self-check all three feature extractors

# one command: prepare data -> start coordinator -> run all nodes -> live dashboard
uv run python run_demo.py --nodes 3 --rounds 5                 # HAR benchmark
uv run python run_demo.py --modality eyegaze --prepare         # eye-tracking federation
uv run python run_demo.py --modality neuro --noniid --prepare  # EEG/fMRI, skewed cohort
# open the dashboard URL it prints (http://localhost:8055), then start your screen recorder
```

> The first run creates two **git-ignored working directories**: `data/` (the fetched HAR cache, the
> coordinator's held-out test set, per-node partitions, and any figures `bench.py` writes) and `nodes/`
> (each node's local data + its `0600` private signing key). Nothing in them is committed.

Re-prepare / change dataset or modality:

```bash
uv run python prepare_data.py --modality eyegaze --nodes 3     # eye-tracking (synth demo cohort)
uv run python prepare_data.py --modality action  --nodes 3     # body-pose action
uv run python prepare_data.py --modality neuro   --nodes 3     # EEG/fMRI
uv run python prepare_data.py --dataset  har     --nodes 3 --total-trees 600   # benchmark
uv run python run_demo.py --prepare --modality eyegaze --nodes 3 --rounds 5
```

## Desktop node client (partner side, pywebview)

A partner runs a small desktop app instead of the CLI: **pick a data modality → choose or prepare local
data → enter node + coordinator info → connect**, with a live, recordable progress view. Same code path
as `node.py` (both call `node_core.py`) — raw data never leaves the machine.

```bash
uv sync --extra client                    # adds pywebview (WebKit/macOS, WebView2/Windows, GTK/Linux)
uv run python client_app.py               # opens the window
uv run python client_app.py --selftest    # headless API smoke test (no GUI)
```

No data of your own? The client's **"Generate a demo folder"** button writes a synthetic cohort (clearly
labelled) in the right format so a partner can walk the whole flow before wiring up real recordings.

For the **action** modality, step 2 has two inputs:

- **Choose NPZ folder** — use existing `body: (T,33,4)` files under `asd/` and `td/` as before.
- **Extract raw video** — choose one or more local videos, assign the batch to ASD or TD, and select a
  2/4/8 fps sampling rate. The web view loads the pinned MediaPipe Holistic JavaScript package from
  jsDelivr only when requested, decodes every video locally, and shows the video with a live 33-point
  skeleton overlay and extraction progress. The browser sends only the extracted landmark array to the
  local Python bridge; the existing NumPy dependency atomically writes a compressed compatible NPZ into
  the selected dataset folder. The app then scans that folder and continues through the unchanged
  feature-extraction and federation path.

The CDN receives normal library/model requests but never receives the selected video or its landmarks.
Raw-video conversion therefore needs network access the first time MediaPipe assets are loaded; direct
NPZ input remains available without that step. Python MediaPipe is not required.

To join a hosted federation, you only run the **desktop client** — no server to stand up. On the *Node &
coordinator* step, either enter the coordinator **URL** and **password** manually, or choose **Import
connection config…** and paste the JSON supplied by the coordinator. The importer accepts
`coordinator_url`, `password`, `node_id`, `display_name`, `rounds`, and — in a version 2 file — the
signed `invitation`, then requires a fresh **Test connection** before training starts. Raw data never
leaves your machine either way.

### Access control, request limits & cohort mode

The coordinator reads these environment variables at startup. For a cross-site deployment, set
separate contributor and read/operator passwords:

```bash
# protected per-guest "solo" federation
FED_PASSWORD=<contributor-password> FED_READ_PASSWORD=<read-password> FED_COHORT=1 \
    uv run uvicorn coordinator:app --host 0.0.0.0 --port <port>

# protected real 3-node secure-aggregation federation
FED_PASSWORD=<contributor-password> FED_READ_PASSWORD=<read-password> FED_COHORT=3 \
    uv run uvicorn coordinator:app --host 0.0.0.0 --port <port>
```

| Variable | Effect |
|---|---|
| `FED_PASSWORD` | Protects contributor calls: `/schema`, `/register`, `/participants`, `/submit`, and `/round`. The desktop client sends it from its **Password** field; the node CLI and `make_node_data.py` use `--password`. |
| `FED_READ_PASSWORD` | Protects `/status`, `/audit` (including `/audit/bundle`), `/model`, and `/predict`. It defaults to `FED_PASSWORD` for compatibility. The dashboard prompts for it and keeps it only in tab-scoped `sessionStorage`; `predict.py` uses `--password`. |
| `FED_COHORT` | Overrides the cohort in `meta.json`. **`FED_COHORT=1`** turns on **per-guest isolation**: each client (keyed by a private session id) gets its *own* cohort-1 federation, so independent testers never collide or see each other's model — connect **alone, anytime** (privacy = central DP, no masking with one node). **`FED_COHORT=3`** is a real **secure-aggregation** run: **3 clients must be connected together**; masks cancel so the coordinator only recovers the pooled sum, never any node's own counts. |
| `FED_STATE_DIR` | Directory for the persistent coordinator signing key and per-room audit state. Default: `data/coordinator_state/`. State is coordinator-signed; key/state files are atomically written with owner-only mode `0600`. Back this directory up and never commit it. |
| `FED_MAX_BODY_BYTES` | Maximum POST/PUT/PATCH body size; default 32 MiB, allowed range 1 KiB–128 MiB. |
| `FED_RATE_LIMIT_PER_MINUTE` | Per-process pilot limit for authenticated reads; default 600/minute per client address. |
| `FED_WRITE_RATE_LIMIT_PER_MINUTE` | Per-process pilot limit for authenticated writes; default 120/minute per client address. A shared limiter is still required for multi-instance production. |
| `FED_REQUIRE_INVITATION` | `1` additionally requires a coordinator-signed institution invitation at `/register`. Required for a pilot; default `0` for local demos. |
| `FED_INVITATION_REGISTRY` | Path to the signed issuance/revocation ledger. Default: `<FED_STATE_DIR>/invitations.json`. |
| `FED_ROUND_TIMEOUT_SECONDS` | How long a partially-submitted round waits for the rest of the cohort before it is discarded and may be submitted again; default 900, allowed range 30–86400. |

Only `/`, `/health`, `/ready`, and `/pubkey` are intentionally public. If both password variables are
unset, all paths remain open for local development. Share runtime passwords out-of-band; do not commit
them.

### Institution invitations (identity, expiry, revocation)

A password says only that the caller knows a token. An invitation says *which institution* is
speaking, for how long, and lets one partner be withdrawn without rotating everyone. Issue them on
the coordinator host with `admin_invite.py`, which signs with the coordinator's existing key:

```bash
FED_STATE_DIR=<state-dir> FED_PASSWORD=<contributor-password> \
  uv run python admin_invite.py issue --institution-id partner_lab \
  --name "University Lab" --coordinator-url https://federation.example.org:8055 \
  --days 30 --include-password --out invite-partner_lab.json

uv run python admin_invite.py list
uv run python admin_invite.py revoke --invitation-id <id> --reason "pilot exit"
```

`invite-partner_lab.json` is a version 2 client configuration: URL, node id, display name, optional
password, and the signed invitation in one file (mode `0600`). The partner imports it in the desktop
client, or passes it to the CLI:

```bash
uv run python node.py --config invite-partner_lab.json --folder /path/to/recordings --rounds 5
```

Properties worth stating precisely:

- The invitation is bound to the node's own Ed25519 key on first registration, so a leaked file
  cannot afterwards be redeemed under a different key.
- The coordinator re-reads the signed registry on every enrolment *and* every submission, so expiry
  or revocation stops an already-enrolled institution without a restart or a client reinstall.
- Invitations absent from the registry, edited registries, and unreadable registries are all refused;
  the failure mode is denial, never open access.
- `admin_invite.py` is deliberately a host-access tool, not an HTTP endpoint. Issuing institution
  identity should require the coordinator host, not a bearer token.
- An invitation is still a bearer credential until first use, and it authenticates an institution,
  not the honesty of its counts. Distribute it over an approved channel.

### Transport and coordinator identity

The pilot topology is deliberately simple, so that what each layer proves stays easy to state:

```text
partner node ──HTTPS──▶ institutional reverse proxy (TLS terminates here)
                          │  private network / loopback
                          ▼
                        uvicorn coordinator, bound to 127.0.0.1
```

| Layer | What it proves |
|---|---|
| TLS on the proxy | The transport is encrypted and the *hostname* is the one the certificate was issued for. |
| Invitation pinning | The process answering at that address holds the coordinator key that signed your invitation. Checked by the node before it registers; a mismatch aborts before anything is uploaded. |
| Contributor password | The caller knows a shared token. |
| Signed invitation | *Which* institution is calling, until when. |

The node reports the pinning outcome (`coordinator identity pinned to the key that signed your
invitation`) and warns when the address is plain `http://`. Pinning is not a substitute for TLS: on
its own it authenticates the peer but leaves the payloads readable in transit. mTLS remains optional
— the invitation plus a locally generated node key is the default onboarding path, because it needs
no certificate authority on the partner side.

Never expose the uvicorn process directly on a public interface; it binds `127.0.0.1` by default
precisely so exposure is a deliberate act.

### Export and verify the audit package

The dashboard's **audit package** button downloads the complete verification evidence. It can be
verified offline without trusting the running coordinator:

```bash
curl -H "X-Fed-Key: <read-password>" \
  -o audit-bundle.json http://<host>:8055/audit/bundle
uv run python verify_audit_bundle.py audit-bundle.json
```

The verifier checks the package signature, coordinator-signed hash chain, every retained node
submission signature, the audit tip/count, and the included model hash. A restart resumes the signed
chain and restores the global privacy spend/model; an incomplete in-flight round is intentionally
discarded and recorded as a `coordinator_restart` event.

The desktop client also reports the exact UTF-8 JSON application payload it sends, split into the
masked vector and protocol metadata. This is not a packet-capture figure: HTTP headers, TCP/IP, and
TLS framing are excluded, while raw recording bytes remain exactly zero in the recommended path.

### Shareable desktop connection configuration

When starting the coordinator through `coordinator.py`, it can write a JSON configuration that the
desktop client can paste directly. Use a client-reachable address for `--public-url`; a wildcard bind
address such as `0.0.0.0` is not a usable partner address by itself.

```bash
FED_PASSWORD=<your-password> FED_COHORT=3 \
  uv run python coordinator.py --host 0.0.0.0 --port 8055 \
  --public-url https://federation.example.org:8055 \
  --write-client-config ./federation-client-config.json
```

The generated JSON contains the coordinator URL, modality/cohort metadata, and—when
`FED_PASSWORD` is set—the shared `password`. It is written with owner-only `0600` permissions and is
never safe to commit, attach to a public issue, or share through an unapproved channel.

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

## Using the trained model (as a data-user / central node)

The model everyone trained together lives in the coordinator as an aggregated, pickle-free JSON forest
(a weighted ensemble of the per-round secure-aggregated DP forests). Two ways to consume it:

```bash
# (A) LOCAL inference — download the model once, score your OWN recordings offline so your
#     query data also stays on your machine (symmetric with training):
uv run python predict.py --coord http://<host>:8062 --password <read-password> \
  --folder my_new_cases --out predictions.csv

# (B) HOSTED inference — send feature rows to the coordinator's /predict (convenience):
uv run python predict.py --coord http://<host>:8062 --password <read-password> \
  --folder my_new_cases --hosted --out predictions.csv

# just archive the model artifact (JSON, with provenance) for offline / audit use:
uv run python predict.py --coord http://<host>:8062 --password <read-password> \
  --save-model global_model.json
```

`predict.py` prints a per-recording ASD/TD call + confidence, and (if your folder is labelled) the
accuracy. The endpoints are:

- **`GET /model`** — the aggregated model + provenance (modality, feature schema, rounds, DP ε spent
  vs budget, held-out test metric, the **audit tip** you can verify against `/pubkey`, and the
  coordinator's public key). Pickle-free JSON — safe to archive and re-load.
- **`POST /predict`** — `{"X": [[…]]}` in the published feature order → `{proba, pred}`. Prefer `GET
  /model` + local inference when the query data is itself sensitive.

Verified live (action modality, 5 rounds, ε=1/round): downloaded a 100-tree model (held-out AUC 0.805),
scored 10 unseen recordings locally at **9/10 correct**; the hosted path returns identical predictions.

## Files

| File | Role |
|---|---|
| `modalities.py` | **modality registry** — eyegaze / action / neuro: raw-folder feature extractors + synthetic demo generators + public normalization |
| `public_scales.json` | shipped **public** per-feature normalization constants (from a fixed-seed reference cohort, not participant data) |
| `data_loaders.py` | `har` / `pose` benchmark dataset loaders |
| `features.py` | pose-window → engineered feature vector (for `action` / `pose`) |
| `prepare_data.py` | split off coordinator test set, partition train across nodes, train centralized baseline (`--modality` or `--dataset`) |
| `fed_common.py` | Ed25519 signing, signature-verified hash-chained `Audit`, multiclass `GlobalModel` (forest merge) |
| `dp.py` | DP random forest: data-independent splits, leaf counts, shared-forest + curator noise |
| `secure_agg.py` | pairwise X25519 masking — coordinator recovers only the summed counts |
| `bench.py` | multi-seed IID/non-IID benchmark + the ε-utility figure (`assets/epsilon_utility.png`) |
| `coordinator.py` | FastAPI server: register / verify-signature / secure-sum / evaluate / audit / dashboard (publishes modality in `/schema`) |
| `invitations.py` | signed institution invitations + the signed issuance/revocation registry |
| `admin_invite.py` | host-side CLI to issue, list, and revoke institution invitations |
| `client_config.py` | the partner connection-config format (v1 connection only, v2 with invitation) |
| `verify_audit_bundle.py` | offline verifier for exported audit packages: bundle/chain/node signatures + model hash |
| `node_core.py` | **shared node loop** used by both the CLI and the desktop client (extract locally, mask, submit, poll) |
| `node.py` | CLI node: `--data` baked features **or** `--folder`+`--modality` raw-folder ingestion |
| `client_app.py` | **desktop node client** (pywebview): pick modality → folder picker → node info → connect, live progress |
| `static/client.html` | the client's English / 简体中文 / 繁體中文 4-step desktop wizard |
| `predict.py` | **data-user / central-node client** — download the global model (`GET /model`) and score local recordings offline, or via `POST /predict` |
| `run_demo.py` | one-command recordable demo (`--modality`, `--noniid`) |
| `verify_security.py` | reproducible audit-tamper / signature-binding / payload-schema / DP / secure-agg / modality checks |
| `verify_api_security.py` | coordinator endpoint-authentication, invitation-enforcement, request-size, rate-limit, and identity-pinning regression checks |
| `verify_round_integrity.py` | reconnect, cohort-fingerprint, idempotency, round-timeout, and single-spend ε regression checks |
| `static/dashboard.html` | live coordinator dashboard: accuracy, nodes, persistent signed audit and package download |
| `DEMO_SCRIPT.md` | recording guide + narration for internal / partner demos |
| `PARTNER_GUIDE.md` | **cross-group experiment guide for a partner institution** (deploy, prepare data, run a node) |

## Security (hardened after an adversarial code audit)

- **No pickle on the wire.** Updates are a constrained JSON tree schema (`children_left/right,
  feature, threshold, leaf-proba`), validated and rebuilt into a pure-numpy predictor server-side —
  closing the `pickle.loads` RCE. Off-schema or raw-array payloads are rejected.
- **Signatures bind the payload.** The node signs `node_id | round | n_samples | sha256(masked)`, so
  nothing can be altered in transit. The merge weight is the `n_samples` the node **declared at
  enrolment** (signature-bound, but not independently verified — see honesty notes).
- **Secure aggregation + global ε-budget:** nodes upload only pairwise-masked counts; the coordinator
  recovers just the pooled sum (masks cancel), adds the DP noise itself, meters a **global** ε budget,
  and rejects (`429`) once exhausted. ε is coordinator-set, never node-declared.
- **Cohort integrity:** enrolment is **capped at the cohort size** (extra nodes → `409`) and a round
  aggregates only when the **exact enrolled set** has submitted — otherwise residual masks would
  silently corrupt the sum. A startup warning fires if **cohort < 3** (masking needs ≥3 to be meaningful).
- **Rounds are bound to one peer set.** Pairwise masks cancel only for the exact `(node_id, x_pub)`
  set they were built against, so every submission carries a **cohort fingerprint**. A node that
  reconnects brings a fresh ephemeral masking key; the coordinator adopts it, **discards** any round
  built against the old set, and refuses stale-fingerprint submissions with a code that tells the node
  to rebuild. A corrupted pooled sum is therefore not reachable through reconnect or dropout.
- **Bounded stalls, idempotent retries, single-spend ε.** A partially-submitted round is discarded
  after `FED_ROUND_TIMEOUT_SECONDS` and its submitters may send it again — one absent institution
  stalls the federation for a bounded time, not indefinitely. An identical retry is idempotent (no
  second receipt, no second audit entry); a *different* payload for the same pending round is refused.
  A persisted per-round ε ledger means no restart, retry, or duplicate aggregation can charge the
  same round twice. A discarded round aggregates nothing and so costs nothing.
- **Replay protection** (round must increase) and **TOFU enrolment** (`node_id` can't be rebound to a
  new key). Coordinator binds **127.0.0.1 by default** — expose deliberately and add TLS for cross-site.
- **Explicit API boundary:** health/readiness and the coordinator public key are public; contributor
  and read/operator paths use separate constant-time token checks, request-size limits, and a
  single-process pilot rate limiter. Shared multi-instance limiting remains pre-pilot work.
- **Institution identity:** with `FED_REQUIRE_INVITATION=1`, enrolment needs a coordinator-signed
  invitation that names the institution, expires, and is bound to the node's Ed25519 key on first
  use. Every submission re-checks the signed registry, so revocation takes effect without a restart;
  an edited or unreadable registry denies rather than admits.
- **Audit evidence is persistent and portable.** The coordinator key and signed per-room state are
  written atomically with mode `0600`; `/audit/bundle` includes the chain, node signature receipts, public keys,
  privacy spend, and model hash. `verify_audit_bundle.py` verifies it offline. This is still not external
  anchoring against a fully compromised coordinator host.
- Node private keys are written `0600` and git-ignored.

Run `uv run python verify_security.py` to see all of this pass (and the attacks fail).

## Honesty notes (deliberate — meant to be defensible, not self-certified)

- **Privacy is secure-aggregation + central-DP:** the coordinator only ever sees **pairwise-masked**
  vectors whose sum is the pooled leaf counts — it never sees an individual node's data or un-noised
  aggregate — then adds Laplace at ε (coordinator-enforced) on the secure sum. Trust model:
  **honest-but-curious, non-colluding** coordinator; **full cohort required per round** (no Shamir
  dropout recovery yet). Accounting is **basic composition** (RDP would be tighter). A fully
  compromised coordinator is out of scope.
- **Secure aggregation hides inputs; it does NOT verify them.** A malicious node could upload in-range
  garbage counts and skew the model — input-robustness (range proofs / Byzantine-robust aggregation) is
  out of scope, and the (ε,0)-DP guarantee assumes *honest* leaf counts (the sensitivity-1 bound is not
  cryptographically enforced). Privacy needs a **non-colluding coordinator and cohort ≥ 3**.
- **The DP accuracy cost is real and mostly structural:** data-independent splits cap accuracy
  (~0.76 on HAR vs 0.97 non-private); the Laplace noise itself costs little at ε=1. This is the honest
  price of the guarantee — shown explicitly via the non-private ceiling and the `dp.py` ε-sweep.
- **The "convergence" curve is ensemble-size variance reduction, not round-over-round learning** —
  tree-merge has no iterative training; the dashboard labels the axis accordingly.
- **HAR uses a window-level stratified, IID, single-seed split** (the OpenML variant has no subject
  ids). Absolute ~0.96/0.97 is optimistic; the federated-vs-centralized *gap* is the honest result.
  The optional `pose` loader uses a subject-level split when you supply seed data.
- **The eyegaze / action / neuro demo cohorts are SYNTHETIC** — recordings generated with class-dependent
  statistics (graded, *overlapping* severities so accuracy is realistic, not trivially separable). They
  validate the pipeline and the privacy mechanism **end-to-end on each modality**; they are **not** a
  claim of clinical accuracy on real patients. The feature extractors are standard, literature-shaped
  summaries (fixation/saccade; pose kinematics; band-power + connectivity), not tuned biomarkers. Point
  the client at real recordings in the documented format and the identical path runs on real data.
