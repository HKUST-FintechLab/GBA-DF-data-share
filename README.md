# GBA-DF Federated Learning POC — multi-modal (eye-gaze · action · neuro time series)

A **working, end-to-end and auditable** federated-learning proof-of-concept for the Greater Bay Area
Data Federation. One privacy kernel serves four heterogeneous local signal front ends—eye gaze,
body-action/pose, experimental CDP pose representation, and EEG-like time series—through a desktop
node client a partner can run as **pick modality → pick data → connect → contribute**.

The architecture deliberately separates representation innovation from the privacy-preserving
classifier. Each modality converts raw recordings to a versioned local feature vector; every modality
then uses the same data-independent federated DP forest. This makes the system broad enough to
demonstrate a multi-modal research platform while keeping the wire protocol, privacy budget and audit
story inspectable rather than hiding them inside an opaque training service.

Current release status is **labeled supervised classification**. Unlabeled inference is partially
available; active learning, semi-supervised learning, frozen self-supervised encoders and true
federated SSL are now a staged post-pilot research track, not shipped training features.

Detailed references:

| Guide | What it answers |
|---|---|
| [`wiki/modalities-and-models.md`](wiki/modalities-and-models.md) | Exactly what model/feature front end each modality uses, dimensions, assumptions and limitations |
| [`wiki/learning-modes.md`](wiki/learning-modes.md) | Labeled vs unlabeled data, current supervised learning, active learning, semi-supervised and self-supervised designs |
| [`wiki/evaluation-and-claims.md`](wiki/evaluation-and-claims.md) | AUC/sensitivity/specificity/calibration, test-set provenance and defensible claims |
| [`wiki/legal-and-policy.md`](wiki/legal-and-policy.md) | 香港、深圳/GBA、北京/内地及海外合作的数据流、隐私风险、传输路径、准入包和 no-go 条件 |
| [`TODO.md`](TODO.md) | Prioritized implementation roadmap and the decision on self/semi-supervised work |
| [`wiki/state-of-project.md`](wiki/state-of-project.md) | Release readiness, blockers and pilot boundary |

| Claim | How it's shown | Honest scope |
|---|---|---|
| **Multi-node** | Coordinator + N independent node processes (each can run on a different machine). | Fully supported. |
| **DP + secure aggregation** | With a cohort of 3 or more, every node uploads **pairwise-masked** integer leaf×class counts of a **shared, data-independent** forest. Masks cancel only in the full pooled sum; the coordinator then adds **Laplace(1/ε)** and meters a **global ε-budget**. | Genuine **(ε,0)-DP release** under row-level add/remove adjacency and basic composition. Secure aggregation hides each node's own counts, but the trusted central-DP curator sees the exact pooled pre-noise counts. It assumes an honest-but-curious, non-colluding coordinator and the exact full cohort. Cohort 1 has central DP only and no pairwise masking. |
| **Persistent, exportable audit** | Each node update is **Ed25519-signed**; every event is coordinator-signed and hash-chained. The coordinator key, chain, node public keys, signed submission receipts, privacy spend, and latest model survive restarts. `GET /audit/bundle` exports a self-contained package for `verify_audit_bundle.py`. | Detects edits to the package, chain, receipts, or model. Files are written atomically with mode `0600`. A *fully compromised* coordinator still needs external anchoring (future work). |
| **Federated ≈ centralized-DP, robust to non-IID** | Multi-seed benchmark (`bench.py`) vs centralized-DP + the non-private ceiling, IID **and** non-IID. | Secure-agg tracks centralized-DP and **recovers the non-IID collapse**: the naive per-node ensemble drops to **0.51±0.10** under label skew; secure-agg holds **0.73±0.03** (figure below). |

`verify_security.py` exercises the core, API boundary, invitations/pinning, shared-solo mode,
CDP adapter, round integrity and backup/restore; `modalities.py` runs every synthetic raw-data front end
through its real extractor. The tracked HAR multi-seed figure below is the reproducible utility
benchmark. Modality-demo metrics are synthetic engineering checks unless a separately governed real,
grouped and institution-held-out evaluation artifact is supplied.

![Privacy–utility tradeoff: the price of the ε-guarantee, and secure aggregation's non-IID recovery](assets/epsilon_utility.png)

*The privacy dial (HAR engineering benchmark, 3 nodes, 5 seeds). Non-private ceiling ≈ 0.98 → DP ≈
0.73 illustrates the utility cost of the current data-independent structure. Under the benchmark's
non-IID label skew the naive per-node ensemble collapses (~0.51) while pooled secure aggregation holds
near the centralized-DP mechanism (~0.73). This is not an ASD clinical result. Regenerate with
`uv run python bench.py`.*

## Method — DP federated forest

**Data-independent forest + central differential privacy**, with pairwise secure aggregation when the
cohort contains at least three nodes (a strategy that fits tree-like models whose leaves are class
histograms):

- **Shared, data-independent forest** — all nodes build the *same* trees from a **public** structure
  seed; splits are random features + thresholds from **public** per-feature bounds (HAR is documented-
  normalised to [-1,1]; each modality is mapped into the same public [-1,1] range by a shipped public
  `tanh(raw/scale)` transform). Private data never influences tree shape (`verify_security.py` proves this).
- **Node** — routes each labeled feature row to one tree and one leaf, incrementing that leaf's class
  bin. Under add/remove-one-row adjacency this gives L1 sensitivity 1. With a cohort of 3 or more the
  integer vector is protected by **pairwise X25519 masks** (`secure_agg.mask_counts`).
- **Coordinator** — in secure mode, sums the masked vectors and recovers the exact **pooled pre-noise
  leaf×class counts**, never an individual node's counts; it then adds **Laplace(1/ε)**
  (`dp.forest_from_summed_counts`) and meters a **global ε-budget**. In cohort-1 mode the submitted
  vector has no pairwise mask, so this is trusted-curator central DP rather than secure aggregation.
  Disjoint rows imply parallel composition within a round; rounds compose sequentially.
- Because the secure sum represents pooled counts, it targets the same mechanism as the
  centralized-DP reference; in the tracked HAR non-IID benchmark this avoids the naive
  per-node-ensemble collapse. This is an empirical benchmark result, not a guarantee for every model
  or adversarial dataset.

The privacy unit is currently one feature row/window, not automatically one video or one person. A
person contributing multiple recordings needs contribution clipping and a new group-level privacy
analysis before the project can claim person-level DP.

The non-private ceiling (label-optimised ExtraTrees) and a centralized-DP reference are computed in
`prepare_data.py`; `bench.py` produces the multi-seed IID/non-IID comparison and the ε-utility figure
above (`assets/epsilon_utility.png`, regenerated at `data/epsilon_utility.png`).
The legacy per-node-ensemble path (`dp.build_dp_counts`/`add_dp_noise`) is retained for that benchmark.

## Modalities (`modalities.py`) and benchmark datasets

**Modalities** — each turns a partner's folder of *raw recordings* into a fixed-width feature vector via
its own front end, then feeds the identical federation. `demo_dataset()` synthesizes a realistic cohort so
every modality runs end-to-end through the **same** extractor a real folder would:

| Modality | Local front end | Analysis unit | Federated representation | Final classifier |
|---|---|---|---:|---|
| **`eyegaze`** | gaze CSV → I-VT-style fixation/saccade, spatial-attention and pupil summaries; assumes roughly 30 Hz | one CSV recording | 32 | common supervised DP forest |
| **`action`** | local MediaPipe 33-point pose → translation/scale-normalized kinematics | one `(T,33,4)` window; a 4D NPZ contributes multiple grouped windows | 174 | common supervised DP forest |
| **`action_cdp`** *(experimental)* | 33→17 points → 230/1150 branches → frozen scaler/selectors → 40+64 | one valid 24–64 sampled-frame clip/window | 104 | common supervised DP forest, **not** the historical CDP ExtraTrees |
| **`neuro`** | 128-Hz EEG-like spectral/connectivity summary from a 2D time series | one scan/file | 48 schema slots: 28 computed + 20 reserved zeros | common supervised DP forest |

Features are squashed into the **public** `[-1,1]` DP range by `tanh(raw / scale)`, where `scale` is a
**shipped public constant** (`public_scales.json`) computed once from a fixed-seed synthetic *reference*
cohort — **never** from participant data (`verify_security.py` proves it stays public and participant-
independent). `tanh` preserves each feature's ordering and supplies a genuinely public threshold range;
it does **not** by itself guarantee unchanged accuracy because the random-threshold distribution and
finite ensemble still matter.

### What model is actually trained?

- `eyegaze` and `neuro` use deterministic statistical front ends; they do not currently contain a
  learned ASD encoder.
- `action` uses a pretrained MediaPipe model locally for **pose extraction**, not ASD classification;
  its 174-dimensional classifier input is then computed deterministically.
- `action_cdp` reuses a frozen historical representation adapter but does not load, aggregate or
  continue training the historical classifier.
- All four final global models are pickle-free ensembles of the same data-independent DP forest type.
- `prepare_data.py`'s label-optimized ExtraTrees is a non-private comparison ceiling, not the deployed
  federated model.

The exact dimensions, assumptions and scientific limitations are documented in
[`wiki/modalities-and-models.md`](wiki/modalities-and-models.md).

### Labeled and unlabeled data

The current training protocol is supervised: every local feature row needs an ASD/TD label because the
node builds leaf×class integer counts. Raw labels are not uploaded row by row, but pooled class-conditioned
statistics do leave the nodes under the documented aggregation boundary.

> **Important:** raw-folder supervised training fails closed when any recording lacks an explicit ASD/TD
> label; it never treats `unlabeled/` as TD. Keep the unlabeled pool separate and score it locally with
> `predict.py` for review; it cannot enter the supervised protocol until a governed label is attached.
> The local importer also refuses byte-identical duplicate recordings, including copies with different
> filenames or label directories.

| Learning mode | Status |
|---|---|
| Labeled supervised forest | **Implemented** |
| Downloaded-model inference on X without truth | Partially implemented |
| Active learning with human confirmation | Chosen near-term design; not yet productized |
| Hard pseudo-label semi-supervised learning | Post-pilot experiment; not implemented |
| Public frozen self-supervised encoder + DP forest | Chosen research route; not implemented |
| True federated SSL/FedAvg/teacher-student | New protocol generation; not implemented |

See [`wiki/learning-modes.md`](wiki/learning-modes.md) for algorithms, privacy implications, evidence
gates and the staged roadmap.

### Experimental CDP adapter

`action_cdp` is a parallel research path and does not replace `action` or enter the September pilot
critical path. It reproduces the historical CDP-TreeFusion feature front end: MediaPipe 33-point
`(T,33,4)` input is mapped to 17 `x/y/visibility` points; the 230-dimensional engineered and
1150-dimensional segment-bag branches are computed with the champion's 32-frame window / 16-frame
stride; clips require at least 24 sampled frames and are uniformly capped at 64; and the frozen
StandardScaler plus 40/64 selectors yield 104 features for the existing
data-independent federated DP forest.

The shipped [`assets/cdp_adapter_v1.json`](assets/cdp_adapter_v1.json) is a data-only, hash-pinned
adapter. It contains no sample IDs, groups, reports, sklearn objects, classifiers, or tree nodes.
The historical `final_model.pkl` is never loaded by a node or coordinator. If an authorized model
owner deliberately replaces the historical model, regenerate the adapter in an isolated local
conversion step using the source model's sklearn version:

```bash
uv run --with scikit-learn==1.8.0 python export_cdp_adapter.py \
  --input /trusted/path/final_model.pkl \
  --output assets/cdp_adapter_v1.json \
  --trusted-sha256 <exact-source-sha256> \
  --acknowledge-pickle-risk
```

Loading pickle can execute code; the hash pin confirms identity, not safety. Only run that conversion
for a model whose provenance has already been independently trusted. A changed adapter also requires
an intentional schema-version/hash-pin change in `cdp_features.py`, preventing different nodes from
silently assigning different meanings to the same 104 columns.

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
uv run python verify_security.py          # complete security/protocol regression suite
uv run python modalities.py               # self-check four front ends, including CDP action experiment

# one command: prepare data -> start coordinator -> run all nodes -> live dashboard
uv run python run_demo.py --nodes 3 --rounds 5                 # HAR benchmark
uv run python run_demo.py --modality eyegaze --prepare         # eye-tracking federation
uv run python run_demo.py --modality action_cdp --prepare      # experimental CDP adapter
uv run python run_demo.py --modality neuro --prepare           # EEG-like time-series POC
# open the pixel-town URL it prints (http://localhost:8055), then start your screen recorder
```

> The first run creates two **git-ignored working directories**: `data/` (the fetched HAR cache, the
> coordinator's held-out test set, per-node partitions, and any figures `bench.py` writes) and `nodes/`
> (each node's local data + its `0600` private signing key). Nothing in them is committed.

### Federated pixel town

The coordinator root and desktop partner client now open the same Phaser 3 pixel-town game. Walk
with **WASD / arrow keys**, press **E** near a building, plot, or NPC, construct cosmetic institution
buildings, and enter the clinic, privacy library, learning workshop, market, community house, or
central machine room. A Tiled JSON object map supplies the collision, interaction, build-plot, and
NPC layers. In coordinator mode the HUD and central machine room read the existing authenticated
`/status` state; the information-dense operator console remains at
`http://localhost:8055/console`.

In desktop-client mode, **Create my institution** opens the existing multilingual four-step flow
inside the game: choose a modality, select or locally prepare recordings, import/test the coordinator
connection, then run the shared `node_core.py` training path. A completed client run updates the local
round counter and grants cosmetic town coins. Coins, buildings, visited rooms, and NPC dialogue are
local presentation state; they never alter training data, participant weights, privacy accounting,
invitations, audit evidence, or model release. NPCs are currently offline scripted guides.

The engine source lives in `game/`; reproducible browser assets are built into `static/game/`:

```bash
cd game
npm install
npm run build
```

Re-prepare / change dataset or modality:

```bash
uv run python prepare_data.py --modality eyegaze --nodes 3     # eye-tracking (synth demo cohort)
uv run python prepare_data.py --modality action  --nodes 3     # body-pose action
uv run python prepare_data.py --modality action_cdp --nodes 3  # CDP adapter experiment
uv run python prepare_data.py --modality neuro   --nodes 3     # EEG-like time-series POC
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

For the **`action` and experimental `action_cdp`** front ends, step 2 has two inputs:

- **Choose NPZ folder** — use existing `body: (T,33,4)` files under `asd/` and `td/` as before.
- **Extract raw video** — choose one or more local videos, assign the batch to ASD or TD, and select a
  2/4/8 fps sampling rate. The web view loads the pinned MediaPipe Holistic JavaScript package from
  jsDelivr only when requested, decodes every video locally, and shows the video with a live 33-point
  skeleton overlay and extraction progress. The browser sends only the extracted landmark array to the
  local Python bridge; the existing NumPy dependency atomically writes a compressed compatible NPZ.
  By default it uses a private per-process temporary folder that is removed when the desktop app exits,
  so selecting video opens only the video picker. The collapsed **Advanced settings** section can choose
  a permanent output folder when the NPZ files should be retained. The app scans the active output
  folder and continues through the unchanged feature-extraction and federation path.

The CDP experiment locks browser extraction to the champion's 4 fps setting. Its local feature
adapter rejects clips with fewer than 24 sampled frames and uniformly caps longer clips at 64.

The CDN receives normal library/model requests but never receives the selected video or its landmarks.
Python MediaPipe is not required.

For a network that blocks the CDN — or to keep a third party out of the trust path of code that runs
over participant video — mirror the pinned assets once and the client will prefer them:

```bash
uv run python fetch_offline_assets.py fetch     # ~64 MiB into static/vendor/mediapipe/
uv run python fetch_offline_assets.py status    # OFFLINE / CDN / BROKEN
```

`fetch` records a SHA-256 per file in a committed manifest and, on every later run, refuses any
download that does not match it (`--repin` makes a version change deliberate). The binaries stay
git-ignored. The client loads from the mirror when it verifies, checks the loader's hash in the
browser *before* the bytes become executable script, and falls back to the CDN otherwise. Direct NPZ
input needs none of this. Whether to redistribute the assets is a licensing decision for the project
owner.

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

# protected shared one-node federation — dashboard and /model use the same room
FED_PASSWORD=<contributor-password> FED_READ_PASSWORD=<read-password> FED_COHORT=1 FED_SOLO_SHARED=1 \
    uv run uvicorn coordinator:app --host 0.0.0.0 --port <port>

# protected real 3-node secure-aggregation federation
FED_PASSWORD=<contributor-password> FED_READ_PASSWORD=<read-password> FED_COHORT=3 \
    uv run uvicorn coordinator:app --host 0.0.0.0 --port <port>
```

| Variable | Effect |
|---|---|
| `FED_PASSWORD` | Protects contributor calls: `/schema`, `/register`, `/participants`, `/submit`, and `/round`. The desktop client sends it from its **Password** field; the node CLI and `make_node_data.py` use `--password`. |
| `FED_READ_PASSWORD` | Protects `/status`, `/audit` (including `/audit/bundle`), `/model`, and `/predict`. It defaults to `FED_PASSWORD` for compatibility. The dashboard prompts for it and keeps it only in tab-scoped `sessionStorage`; `predict.py` uses `--password`. |
| `FED_COHORT` | Overrides the cohort in `meta.json`. **`FED_COHORT=1`** turns on **per-guest isolation**: each client (keyed by a private session id) gets its *own* cohort-1 federation, so independent testers never collide or see each other's model — connect **alone, anytime** (privacy = central DP, no masking with one node). The authenticated operator dashboard shows metadata-only summaries of populated solo sessions (node name, sample count, rounds, metric, trees, ε); it never exposes their session IDs, raw data, masked vectors, audit entries, or model JSON. **`FED_COHORT=3`** is a real **secure-aggregation** run: **3 clients must be connected together**; masks cancel so the coordinator only recovers the pooled sum, never any node's own counts. |
| `FED_SOLO_SHARED` | Set to `1` **only with `FED_COHORT=1`** to use one shared one-node room rather than private per-guest rooms. The trained model, audit, and status then appear in the ordinary authenticated dashboard and `/model` endpoint. This does not enable secure aggregation or multi-node model pooling: only the single enrolled node can contribute in that room. |
| `FED_STATE_DIR` | Directory for the persistent coordinator signing key and per-room audit state. Default: `data/coordinator_state/`. State is coordinator-signed; key/state files are atomically written with owner-only mode `0600`. Back this directory up and never commit it. |
| `FED_MAX_BODY_BYTES` | Maximum POST/PUT/PATCH body size; default 32 MiB, allowed range 1 KiB–128 MiB. |
| `FED_RATE_LIMIT_PER_MINUTE` | Per-process pilot limit for authenticated reads; default 600/minute per client address. |
| `FED_WRITE_RATE_LIMIT_PER_MINUTE` | Per-process pilot limit for authenticated writes; default 120/minute per client address. A shared limiter is still required for multi-instance production. |
| `FED_SESSION_IDLE_SECONDS` | In isolated cohort-1 demo mode, removes an inactive in-memory session after this many seconds; default 3600, allowed range 60–604800. Its signed state remains on disk and a later request records `session_resumed`. |
| `FED_MAX_ACTIVE_SESSIONS` | In isolated cohort-1 demo mode, maximum in-memory sessions; default 100, allowed range 1–10000. Capacity pressure discards only incomplete buffered rounds (no epsilon) before evicting the least-recent room. |
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

### Backup, restore, and operational logs

The coordinator key, the signed per-room state, and the invitation registry are the only artifacts
that cannot be regenerated. Losing the key makes every exported audit bundle unverifiable and every
issued invitation worthless, so back the state directory up on the same schedule as any other
production secret:

```bash
FED_STATE_DIR=<state-dir> uv run python admin_backup.py backup --out backups/gba-df-2026-09-07.tar.gz
uv run python admin_backup.py inspect  backups/gba-df-2026-09-07.tar.gz
uv run python admin_backup.py restore  backups/gba-df-2026-09-07.tar.gz --state-dir /srv/gba-df
```

The archive carries a hashed manifest; `inspect` and `restore` both refuse an archive whose contents
no longer match it, and `restore` refuses to overwrite a populated state directory without `--force`.
After a restore, the chain keeps every pre-backup entry and continues with one linked
`coordinator_restart` entry — `verify_backup_restore.py` asserts exactly that, plus that the model,
the privacy spend, and prior revocations all survive. **The archive contains the private key:** store
it where a compromise of the coordinator host would not also expose it, and never commit it.

The coordinator additionally writes one **JSON line per event** to stdout — enrolments, submissions,
aggregations, discarded rounds, and every 401/429 denial — for a log collector to alert on. It is
monitoring, not evidence: the signed chain remains the record. Only an allow-listed set of fields is
mirrored, and a regression asserts that no credential, key, invitation signature, or masked payload
can appear there.

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
    --data /path/to/their/local/data.npz --rounds 5 --name "University Lab"
```

`data.npz` holds their local `X` (features) and `y` (labels). Their private signing key is generated
next to it (`node_key.pem`) and **never leaves the machine**.

## Using the trained model (as a data-user / central node)

The model everyone trained together lives in the coordinator as an aggregated, pickle-free JSON forest:
a weighted ensemble of per-round DP forests. Cohorts of three or more use secure-aggregated pooled
counts; cohort 1 uses a single-node central-DP count path. Two ways to consume it:

```bash
# (A) LOCAL inference — download the model once, score your OWN recordings offline so your
#     query data also stays on your machine (symmetric with training):
uv run python predict.py --coord http://<host>:8055 --password <read-password> \
  --folder my_new_cases --out predictions.csv

# (B) HOSTED inference — send feature rows to the coordinator's /predict (convenience):
uv run python predict.py --coord http://<host>:8055 --password <read-password> \
  --folder my_new_cases --hosted --out predictions.csv

# just archive the model artifact (JSON, with provenance) for offline / audit use:
uv run python predict.py --coord http://<host>:8055 --password <read-password> \
  --save-model global_model.json
```

`predict.py` prints a per-recording ASD/TD call + confidence, and (if your folder is labelled) the
accuracy. The endpoints are:

- **`GET /model`** — the aggregated model + provenance (modality, feature schema, rounds, DP ε spent
  vs budget, held-out test metric, the **audit tip** you can verify against `/pubkey`, and the
  coordinator's public key). Pickle-free JSON — safe to archive and re-load.
- **`POST /predict`** — `{"X": [[…]]}` in the published feature order → `{proba, pred}`. Prefer `GET
  /model` + local inference when the query data is itself sensitive.

An internal synthetic action rehearsal downloaded a 100-tree model, scored held-out demo recordings
locally, and matched hosted predictions. That verifies artifact portability, not clinical accuracy.

## Files

| File | Role |
|---|---|
| `modalities.py` | **modality registry** — eyegaze / action / experimental action_cdp / neuro: raw-folder feature extractors + synthetic demo generators + public normalization |
| `public_scales.json` | shipped **public** per-feature normalization constants (from a fixed-seed reference cohort, not participant data) |
| `data_loaders.py` | `har` / `pose` benchmark dataset loaders |
| `features.py` | pose-window → engineered feature vector (for `action` / `pose`) |
| `cdp_features.py` | pure-NumPy CDP 33→17 mapping, 230/1150 branch features, pinned JSON validation, and 104-feature transform |
| `assets/cdp_adapter_v1.json` | allow-listed, hash-pinned CDP scaler/selector metadata; no participant IDs, executable model, or classifier trees |
| `export_cdp_adapter.py` | explicit hash-pinned, local-only migration tool from a trusted historical pickle to the data-only adapter |
| `prepare_data.py` | recording/file-grouped coordinator test split when groups exist, with optional explicit `recording,subject_id` mapping for a true subject-grouped split; preserves test groups, partitions nodes, and builds centralized references (`--modality` or `--dataset`) |
| `fed_common.py` | Ed25519 signing, signature-verified hash-chained `Audit`, global JSON-forest ensemble and binary diagnostics |
| `dp.py` | DP random forest: data-independent splits, leaf counts, shared-forest + curator noise |
| `secure_agg.py` | pairwise X25519 masking — coordinator recovers only the summed counts |
| `bench.py` | multi-seed IID/non-IID benchmark + the ε-utility figure (`assets/epsilon_utility.png`) |
| `coordinator.py` | FastAPI server: register / verify-signature / secure-sum / evaluate / audit; `/` opens the shared game and `/console` the operator dashboard |
| `invitations.py` | signed institution invitations + the signed issuance/revocation registry |
| `admin_invite.py` | host-side CLI to issue, list, and revoke institution invitations |
| `client_config.py` | the partner connection-config format (v1 connection only, v2 with invitation) |
| `verify_audit_bundle.py` | offline verifier for exported audit packages: bundle/chain/node signatures + model hash |
| `node_core.py` | **shared node loop** used by both the CLI and the desktop client (extract locally, mask, submit, poll) |
| `node.py` | CLI node: `--data` baked features **or** `--folder`+`--modality` raw-folder ingestion |
| `client_app.py` | **desktop node client** (pywebview): opens the shared game and exposes the existing local node bridge |
| `game/` | Phaser 3 + TypeScript + Vite source: scenes, actors, Tiled object map, local saves, coordinator status service, and client guide shell |
| `static/game/` | committed production build used by both the coordinator and desktop client |
| `static/client.html` | English / 简体中文 / 繁體中文 four-step node wizard, embedded as the game's institution-creation center |
| `static/town.html` | previous single-page pixel-town prototype retained as a design reference; it is no longer the default route |
| `predict.py` | **data-user / central-node client** — download the global model (`GET /model`) and score local recordings offline, or via `POST /predict` |
| `run_demo.py` | one-command recordable demo (`--modality`, `--noniid`) |
| `stage_demo_nodes.py` | safely prepare distinct synthetic folders for a multi-desktop rehearsal; manifest-based refresh preserves local additions |
| `verify_security.py` | reproducible audit-tamper / signature-binding / payload-schema / DP / secure-agg / modality checks |
| `verify_cdp_adapter.py` | CDP mapping/dimensions, adapter pin/tamper, exporter allow-list, and folder-ingestion regression checks |
| `verify_api_security.py` | coordinator endpoint-authentication, invitation-enforcement, request-size, rate-limit, and identity-pinning regression checks |
| `verify_round_integrity.py` | reconnect, cohort-fingerprint, idempotency, round-timeout, and single-spend ε regression checks |
| `verify_backup_restore.py` | archive integrity, clean-host restore, and post-restore audit verification |
| `admin_backup.py` | back up / inspect / restore the coordinator key, signed state, and invitation registry |
| `fetch_offline_assets.py` | mirror + hash-pin the browser MediaPipe assets for offline/CDN-free operation |
| `.github/workflows/verify.yml` | CI: full verification suite, known-vulnerability audit, CycloneDX SBOM |
| `static/dashboard.html` | information-dense topology console at `/console`: cohort/privacy mode, AUC and deltas, sensitivity/specificity, calibration, confusion matrix, ε ledger, signed audit replay and package download |
| `DEMO_SCRIPT.md` | recording guide + narration for internal / partner demos |
| `PARTNER_GUIDE.md` | **cross-group experiment guide for a partner institution** (deploy, prepare data, run a node) |
| `TODO.md` | prioritized pilot and post-pilot backlog, including active/semi/self-supervised learning gates |
| `wiki/` | canonical model, learning-mode, evaluation, delivery and decision documentation |

## Security (hardened after an adversarial code audit)

- **No pickle on the wire.** Updates are a constrained JSON tree schema (`children_left/right,
  feature, threshold, leaf-proba`), validated and rebuilt into a pure-numpy predictor server-side —
  closing the `pickle.loads` RCE. Off-schema or raw-array payloads are rejected.
- **Signatures bind the payload.** The node signs `node_id | round | n_samples | sha256(masked)`, so
  nothing can be altered in transit. The merge weight is the `n_samples` the node **declared at
  enrolment** (signature-bound, but not independently verified — see honesty notes).
- **Secure aggregation + global ε-budget:** with at least three nodes, nodes upload pairwise-masked
  counts and the coordinator recovers the exact pooled pre-noise sum without being able to isolate a
  node. It adds DP noise, meters a **global** ε budget, and rejects (`429`) once exhausted. Cohort 1
  sends unmasked counts to the central-DP curator and is never described as secure aggregation.
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

- **Privacy engineering is not automatic legal compliance.** Raw recordings remaining local,
  pairwise masks and central DP reduce disclosure risk, but updates, exact pre-noise pooled counts,
  models, metrics, audit bundles, backups and remote access may still be regulated personal/sensitive
  data. Cohort 1 must not be used for real child/clinical cross-institution data. Route-specific Hong
  Kong/Mainland/GBA/overseas analysis and admission gates are documented in
  [`wiki/legal-and-policy.md`](wiki/legal-and-policy.md); that research guide is not legal advice or
  an institutional approval.
- **Privacy is central-DP plus secure aggregation for cohorts of at least three:** secure aggregation
  hides each institution's own leaf×class counts, but the trusted curator recovers the exact pooled
  pre-noise counts and then adds coordinator-enforced Laplace noise. Cohort 1 exposes that one node's
  counts to the curator before noise. Trust model: honest-but-curious, non-colluding coordinator;
  full cohort required per secure round. Accounting is basic composition. A fully compromised
  coordinator is out of scope.
- **Secure aggregation hides inputs; it does NOT verify them.** A malicious node could upload in-range
  garbage counts and skew the model — input-robustness (range proofs / Byzantine-robust aggregation) is
  out of scope, and the (ε,0)-DP guarantee assumes *honest* leaf counts (the sensitivity-1 bound is not
  cryptographically enforced). Privacy needs a **non-colluding coordinator and cohort ≥ 3**.
- **The DP accuracy cost is real and mostly structural:** data-independent splits cap accuracy
  (~0.76 on HAR vs 0.97 non-private); the Laplace noise itself costs little at ε=1. This is the honest
  price of the guarantee — shown explicitly via the non-private ceiling and the `dp.py` ε-sweep.
- **The "convergence" curve is ensemble-size variance reduction, not round-over-round learning** —
  tree-merge has no iterative training; the dashboard labels the axis accordingly.
- **The privacy unit is a feature row/window under add/remove adjacency, not automatically a video or
  person.** The schema declares a row-level contribution unit and, when recording/subject groups are
  available, nodes deterministically cap each local group (default: 8 rows). This prevents a long
  recording from dominating training, but it is still **not** recording- or person-level DP: either
  claim needs recalibrated noise and a group-adjacency proof.
- **Current training is labeled only.** A file without an ASD/TD path or filename token currently
  is rejected by supervised training; it never falls back to TD. Active learning,
  pseudo-labeling and SSL are documented roadmap items, not shipped training modes.
- **HAR uses a window-level stratified, IID, single-seed split** (the OpenML variant has no subject
  ids). Absolute ~0.96/0.97 is optimistic; the federated-vs-centralized *gap* is the honest result.
  The optional `pose` loader uses recording/file grouping unless an explicit subject map is supplied.
- **The eyegaze / action / action_cdp / neuro demo cohorts are SYNTHETIC** — recordings generated with class-dependent
  statistics (graded, *overlapping* severities so accuracy is realistic, not trivially separable). They
  validate the pipeline and the privacy mechanism **end-to-end on each modality**; they are **not** a
  claim of clinical accuracy on real patients. The feature extractors are standard, literature-shaped
  summaries (fixation/saccade; pose kinematics; band-power + connectivity), not tuned biomarkers. Point
  the client at real recordings in the documented format and the identical path runs on real data.
- **`neuro` is presently an EEG-oriented engineering adapter.** It assumes 128 Hz, computes 28
  statistics in a 48-slot versioned schema, and leaves 20 slots reserved at zero. Those assumptions
  are not a validated fMRI model; a real fMRI path needs a separate TR-aware schema.
- **The historical CDP locked-test AUC does not transfer to `action_cdp`.** The experiment reuses its
  representation but trains a different data-independent DP forest. Any improvement claim needs a
  grouped, institution-held-out comparison against the frozen CDP model; more data or federation alone
  does not guarantee higher AUC.
- **The frozen CDP scaler/selector values are historical training-derived model parameters**, not
  statistics estimated from current federation participants. Their redistribution still needs
  source-data/model-owner governance approval; `public_scales.json` remains the separate fixed-seed
  synthetic normalization used for the DP split bounds.
