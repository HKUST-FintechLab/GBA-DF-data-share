# AGENTS.md

This file contains the complete development guidance for this repository.

## Repository boundary

- Treat this repository as a standalone project.
- Do not inherit instructions, wikis, or project memory from a containing repository or parent directory.
- Use only files in this repository unless the user explicitly places an external source in scope.

## Local project wiki

- `wiki/` is the canonical release-readiness and timeline memory for this standalone project.
- For questions such as “where are we?”, “what is next?”, or “when can this ship?”, read:
  1. `wiki/README.md`;
  2. `wiki/state-of-project.md`;
  3. `wiki/timeline.md`;
  4. `wiki/decisions-log.md` when a recommendation could change a locked target or scope boundary.
- Update the relevant wiki pages and their `Last updated:` stamps when a blocker, target, or locked
  delivery decision changes.

## Project overview

GBA-DF is a Python proof of concept for privacy-preserving federated learning across independent institutions. It supports three separate data modalities:

- `eyegaze`: eye-tracking CSV recordings;
- `action`: raw videos converted locally by the desktop client, or MediaPipe pose `.npz` recordings;
- `neuro`: EEG/fMRI time-series CSV or `.npz` recordings.

Each modality has its own feature schema and federation. All modalities use the same privacy and aggregation machinery.

The project demonstrates:

- multiple independent federation nodes;
- local feature extraction so raw recordings remain on the node;
- pairwise-masked secure aggregation of integer tree-leaf counts;
- coordinator-applied central `(epsilon, 0)` differential privacy;
- a coordinator-enforced global epsilon budget;
- persistent Ed25519-signed, hash-chained audit events and exportable verification packages;
- exact application-layer JSON payload-byte accounting in every node run;
- comparison with centralized-DP and non-private reference models;
- downloadable, pickle-free JSON models for local inference;
- a CLI node, desktop partner client, coordinator dashboard, and reproducible demo.

This is an engineering proof of concept. Synthetic modality results are not clinical-validation results.

## Environment

The project requires Python 3.10+ and uses `uv` with `pyproject.toml` and `uv.lock`.

```bash
uv sync
```

Install the optional desktop-client dependencies with:

```bash
uv sync --extra client
```

## Common commands

```bash
# Security, privacy, aggregation, and schema regression checks
uv run python verify_security.py

# Check all modality feature extractors
uv run python modalities.py

# Headless desktop-client smoke test
uv run python client_app.py --selftest

# Syntax check
uv run python -m compileall -q *.py

# One-command three-node HAR demo
uv run python run_demo.py --nodes 3 --rounds 5

# Prepare and run a modality demo
uv run python run_demo.py --modality eyegaze --prepare

# Regenerate the multi-seed benchmark and utility figure
uv run python bench.py
```

`run_demo.py` intentionally keeps the coordinator alive until `Ctrl+C`. Arrange process cleanup before using it in automated tests.

## Architecture

| File | Responsibility |
|---|---|
| `modalities.py` | Modality registry, feature extraction, synthetic demo cohorts, and public normalization |
| `features.py` | Pose/action feature engineering |
| `data_loaders.py` | HAR and optional pose benchmark loaders |
| `prepare_data.py` | Test split, node partitions, baselines, and runtime metadata |
| `dp.py` | Data-independent forest structure, local leaf counts, and curator DP noise |
| `secure_agg.py` | Pairwise X25519 masks and secure summation |
| `fed_common.py` | Signing, audit chain, JSON forest validation, and global model |
| `invitations.py` | Signed institution invitations and the signed issuance/revocation registry |
| `admin_invite.py` | Host-side CLI to issue, list, and revoke institution invitations |
| `client_config.py` | Partner connection-config format (v1 connection, v2 with invitation) |
| `node_core.py` | Shared node execution path used by the CLI and desktop client |
| `node.py` | Command-line federation node |
| `client_app.py` | Desktop partner client |
| `coordinator.py` | FastAPI coordinator |
| `predict.py` | Downloaded-model local inference and optional hosted inference |
| `verify_audit_bundle.py` | Offline audit-package signature, chain, receipt, and model-hash verifier |
| `verify_security.py` | Security and privacy regression checks |
| `verify_round_integrity.py` | Reconnect, cohort-binding, idempotency, timeout, and epsilon-ledger regression checks |
| `verify_backup_restore.py` | Archive integrity, clean-host restore, and post-restore audit verification |
| `admin_backup.py` | Host-side CLI to back up, inspect, and restore coordinator state |
| `verify_api_security.py` | Coordinator HTTP access-control, invitation-enforcement, body-limit, and rate-limit regression checks |
| `bench.py` | IID/non-IID privacy-utility benchmark |
| `run_demo.py` | Demo orchestration |
| `static/` | Desktop-client and coordinator-dashboard interfaces |

Training data flow:

```text
raw local recordings
  -> local modality features
  -> shared data-independent forest
  -> local integer leaf counts
  -> pairwise masking
  -> pooled secure sum
  -> coordinator Laplace noise
  -> global JSON forest
```

## Security and privacy invariants

Do not weaken or overstate these constraints:

- Raw recordings and per-record feature rows stay on the node in the recommended training path.
- Nodes upload masked integer leaf-count vectors, not raw examples.
- Forest structure must remain data-independent. Splits come only from a public seed and public feature bounds.
- Modality normalization must remain a fixed public transform using `public_scales.json`, never scales estimated from participant data.
- Each record contributes to one leaf per tree, giving L1 sensitivity 1 for a tree's leaf-count vector.
- The coordinator adds Laplace noise after recovering the pooled secure sum and meters the global epsilon budget using basic composition.
- A secure-aggregation round requires the exact enrolled cohort. Dropout recovery is not implemented.
- Every submission carries a cohort fingerprint over the exact `(node_id, x_pub)` set its masks were built against. Never pool submissions across fingerprints, and never keep a stale `x_pub` for a reconnecting node: either would silently corrupt the pooled sum instead of failing.
- A partially-submitted round is discarded after `FED_ROUND_TIMEOUT_SECONDS`, and a discarded round must aggregate nothing and spend no epsilon.
- Identical resubmissions are idempotent; a conflicting payload for the same pending round must be refused. Epsilon is charged through the persisted per-round ledger, at most once per round number.
- Meaningful pairwise-masking privacy requires at least three non-colluding nodes.
- `FED_COHORT=1` is isolated solo-demo mode with central DP only. Never describe it as secure aggregation.
- The trust model assumes an honest-but-curious, non-colluding coordinator and honest leaf-count construction.
- Institution invitations are coordinator-signed, bound to the node key on first registration, and re-checked against the signed registry on every submission. Keep every failure path closed: unknown, edited, expired, revoked, and unreadable all deny.
- `admin_invite.py` is intentionally host-access only. Do not expose invitation issuance or revocation as an HTTP endpoint.
- An invitation authenticates an institution. It does not attest to the honesty of that institution's counts.
- A node pins the coordinator against the key fingerprint inside its invitation before registering, and must upload nothing on a mismatch. Pinning authenticates the peer; it does not encrypt the transport, so do not present it as a replacement for TLS.
- Secure aggregation hides node inputs but does not provide Byzantine robustness or cryptographically prove that submitted counts are valid.
- The signed hash chain is tamper-evident within the documented trust model. A fully compromised coordinator requires external anchoring.
- Preserve coordinator audit persistence: state is coordinator-signed, files are atomic/mode `0600`, and corruption fails closed.
- Backup archives contain the coordinator private key. Keep them mode `0600`, never commit them, and keep restore refusing both a manifest mismatch and an unforced overwrite of populated state.
- The operational log is monitoring, not evidence. Mirror only allow-listed audit-detail keys into it; never log credentials, keys, invitation contents, or masked payloads.
- Transfer statistics mean exact UTF-8 JSON application payload bytes. Do not present them as total network/TLS bytes.
- Keep all wire and model formats constrained and pickle-free. Do not introduce `pickle.loads` or opaque executable payloads.
- Node Ed25519 private keys must remain local, use file mode `0600`, and never be committed.
- The convergence curve represents ensemble-size variance reduction, not iterative gradient-style learning.

## Scientific claims

- Synthetic `eyegaze`, `action`, and `neuro` cohorts test the end-to-end pipeline; they do not establish clinical accuracy.
- HAR is an engineering benchmark. Its window-level split does not establish subject-level or ASD clinical performance.
- Secure aggregation reproducing the pooled centralized-DP mechanism in the included benchmark is not a general guarantee for arbitrary models or adversarial participants.
- Prefer precise wording such as "raw recordings remain local" over absolute claims such as "no information leaves the node" because masked aggregates and protocol metadata are transmitted.

## Runtime configuration and repository hygiene

- `FED_PASSWORD`, `FED_READ_PASSWORD`, `FED_COHORT`, `FED_STATE_DIR`,
  `FED_MAX_BODY_BYTES`, `FED_RATE_LIMIT_PER_MINUTE`,
  `FED_WRITE_RATE_LIMIT_PER_MINUTE`, `FED_REQUIRE_INVITATION`,
  `FED_INVITATION_REGISTRY`, and `FED_ROUND_TIMEOUT_SECONDS` are runtime environment variables. Never hard-code credentials.
- Issued invitation files and the invitation registry are runtime secrets. Never commit them.
- Do not commit real passwords, access tokens, private keys, server addresses, or deployment-specific connection details.
- Cross-site deployment requires appropriate TLS, authentication, firewall, key-management, and institutional data-processing controls.
- `data/`, `nodes/`, `.venv/`, caches, logs, and generated artifacts are runtime-local and git-ignored.
- Treat ignored runtime files as disposable state, even when they are present in a working checkout.
- `public_scales.json` and `assets/epsilon_utility.png` are tracked source artifacts.

## Change and verification policy

- Preserve the shared node path: both `node.py` and `client_app.py` should use `node_core.py`.
- When changing the coordinator protocol, update every producer, consumer, regression check, and relevant repository document together.
- For changes to security, DP, aggregation, payload schemas, or modalities, run at minimum:

```bash
uv run python verify_security.py
uv run python modalities.py
uv run python client_app.py --selftest
```

`verify_security.py` runs `verify_api_security.py` and `verify_round_integrity.py` as subprocesses;
run those directly when iterating on the coordinator protocol.

- For documentation changes, verify commands and claims against current code and tracked artifacts.
- Keep limitations visible. Do not replace technical caveats with stronger marketing language.
- Do not regenerate benchmarks unless the task requires it; `bench.py` may fetch HAR when no local cache exists.
