# GBA-DF TODO

Last updated: 2026-08-04

This backlog separates the monitored-pilot path from post-pilot model research. A checked item means
the repository contains the implementation and proportionate verification; prose in a design page
does not make a capability complete.

## Decision summary

- **Yes, add semi-supervised and self-supervised work to the research roadmap.** Unlabeled recordings
  are strategically valuable, especially for video, where expert labels are expensive.
- **Do not put a new learning protocol on the September pilot critical path.** The pilot continues to
  use the current, auditable labeled leaf-count classifier.
- **First priority is correctness, not a new model:** unlabeled raw files currently fall back to TD.
  The training path must fail closed before any unlabeled workflow is advertised.
- **Preferred first semi-supervised feature:** local active learning with human confirmation. It reuses
  the existing inference, labeled training, DP and secure-aggregation path.
- **Preferred first SSL feature:** a public, frozen, versioned encoder feeding the existing DP forest.
  Fully federated encoder training is a later protocol, not a small extension to leaf counts.
- **Do not silently mutate existing schemas.** New encoders become `*_v2` modalities; EEG and fMRI
  should split before either receives a learned encoder.

The detailed rationale and privacy implications are in
[`wiki/learning-modes.md`](wiki/learning-modes.md).

## G0 — mandatory governance before any real-data or cross-border run

The route matrix, exact current data flow, official sources, admission-pack template and immediate
no-go conditions are in [`wiki/legal-and-policy.md`](wiki/legal-and-policy.md). These items require
institution owners; completing code does not complete them.

- [ ] Choose and record the pilot topology: all Hong Kong, Hong Kong↔Shenzhen GBA, Beijing/other
  Mainland↔Hong Kong, or another overseas route. Record every cloud, backup, log, administrator and
  remote-support location—not just the coordinator hostname.
- [ ] Build the field-level transfer register for raw recordings, local features, masked/unmasked
  leaf×class counts, node-reported input-row counts, node/public-key metadata, pre-noise pool, model, metrics,
  audit bundle, test set, reverse-proxy log and backup.
- [ ] Sign the factual role matrix and data-sharing/processing agreement: data user/controller,
  joint controller/共同处理者, processor/受托人, purpose, onward recipient, retention/deletion,
  rights, government requests, incident timing, audit, model/IP and termination.
- [ ] Confirm each original PICS/consent and ethics approval covers the actual learning mode,
  cross-institution submission, coordinator/test-set location, dashboard/audit visibility, model
  release and future use; obtain amendment, guardian permission and age-appropriate assent where needed.
- [ ] Complete the applicable DPIA/PIPIA and written model/update anonymization assessment; test
  membership, attribute, extraction and small-cohort inference rather than declaring DP output anonymous.
- [ ] Complete the applicable transfer instrument and filing: Hong Kong RMC/GBA contract, Mainland
  standard contract/certification/security assessment, applicable EU/UK transfer mechanism, or
  destination-specific equivalent. For U.S. partners also complete HIPAA/Common Rule/state-law
  analysis, DOJ DSP bulk/covered-transaction screening, and a separate PADFAA data-broker screening.
- [ ] Have every Mainland institution classify sensitive personal information, important data,
  CIIO/medical-industry constraints and any HGR boundary; maintain a natural-person-level annual
  outbound count rather than a video/window count.
- [ ] Adopt a real-data policy that prohibits cohort 1/`FED_SOLO_SHARED`, plaintext HTTP, shared demo
  passwords, unapproved centralized real `test.npz`, hosted cross-border `/predict`, public exact
  institution counts and unknown-territory monitoring or backups.
- [ ] Obtain named written go-live approval from legal/DPO, ethics/PI, information security/data owner,
  and the operational system owner at every institution.

## U0 — mandatory before any unlabeled-data release

- [x] Change raw-folder training to fail closed when a file has no explicit ASD/TD label; never
  silently assign unlabeled data to TD.
- [x] Add an explicit `unlabeled/` contract that is accepted for inference/review but excluded from
  supervised counts until a human or governed pseudo-label is attached.
- [x] Make raw-folder inference return “truth unavailable” rather than a fabricated TD truth or
  meaningless accuracy.
- [x] Add regressions for unlabeled, misspelled labels, mixed labeled/unlabeled roots, duplicate files,
  and labels encoded only in filenames.
- [x] Rename split metadata from generic “subject-level” to “recording/file-grouped” unless the input
  actually provides a subject id.
- [x] Preserve group IDs in the coordinator test artifact so evaluation can aggregate windows by
  recording and, when available, subject.
- [x] Document and enforce the DP contribution unit. Add per-video/per-subject caps before claiming
  video-level or person-level privacy.
- [ ] Split the current EEG-like `neuro` POC from a future TR-aware fMRI schema; document or remove the
  20 reserved zero dimensions before a real neuro study.
- [x] Document the four current front ends, the common DP forest, labels, unlabeled limitations and
  post-pilot learning routes.
- [x] Make cohort-1 central-DP and cohort>=3 secure-aggregation wording distinct in node and dashboard
  UI.

## Pilot delivery — remains the critical path

- [ ] Freeze supported Windows/macOS versions and the installer/auto-update policy.
- [ ] Produce signed, notarized pilot packages and install them on the actual partner machines.
- [ ] Complete large-video, proxy, offline, localization and accessibility E2E checks.
- [x] Add session cleanup and measured load/body-size limits for the supported single-instance host.
- [x] Freeze the reconnect-and-resubmit operator procedure for coordinator restart handling.
- [ ] Run three full three-institution staging rehearsals and one backup/restore drill on the real host.
- [ ] Obtain partner selection, data-processing approval, ethics coverage, TLS certificate, signing
  identities and independent security review as tracked in
  [`wiki/human-critical-path.md`](wiki/human-critical-path.md).

## R1 — unlabeled local inference and active learning

Recommended first model-related milestone after the pilot gates.

- [ ] Add a local unlabeled case registry with stable local case ID, modality, source-file hash,
  subject/group ID and acquisition metadata; never upload the raw identifier.
- [ ] Download and pin a global model hash before scoring the unlabeled pool.
- [ ] Store local prediction, confidence, uncertainty method, model hash and timestamp.
- [ ] Add review queues for low confidence, model disagreement and representative coverage.
- [ ] Require a human confirmation step before moving a case into ASD/TD supervised training.
- [ ] Record label source (`human`, `weak`, `pseudo`), reviewer role, version and revocation history.
- [ ] Prevent reviewed training cases from entering the locked evaluation set.
- [ ] Add subject/video deduplication and contribution caps.
- [ ] Evaluate annotation yield: labels reviewed per hour, uncertainty hit rate, class balance and
  labeled-only utility under the same human-label budget.

**Definition of done:** an institution can score an unlabeled video locally, select it for review,
attach a traceable human label, and contribute it through the unchanged supervised protocol without
the coordinator learning the raw case or review queue.

## R2 — hard pseudo-label semi-supervised experiment

Proceed only after R1 provenance and deduplication exist.

- [ ] Write an experiment protocol before implementation: teacher model, class-specific confidence
  thresholds, abstention, refresh cadence and maximum pseudo-label contribution.
- [ ] Bind every pseudo-label to the teacher model hash and the exact preprocessing/schema version.
- [ ] Keep human labels and pseudo-labels distinguishable in local storage and audit summaries.
- [ ] Limit pseudo-labels per class, video and subject so one long recording cannot dominate counts.
- [ ] Decide whether accepted pseudo-labels may be refreshed; prevent the same case from contributing
  repeatedly across teacher versions without explicit accounting.
- [ ] Re-check row/group sensitivity and adaptive sequential privacy composition.
- [ ] Add poisoning/confirmation-bias diagnostics and class-collapse alarms.
- [ ] Compare three fixed-budget arms: labeled-only, labeled+pseudo, and full-label upper bound.
- [ ] Report pseudo-label coverage, precision, abstention, per-class error, calibration and external
  institution performance—not just final AUC.

**Go/no-go gate:** promote only if labeled+pseudo improves an institution-held-out, human-labeled test
set over labeled-only under the same true-label and epsilon budgets, without unacceptable subgroup or
calibration regression.

## R3 — public frozen self-supervised encoder

Recommended before attempting federated gradient training.

- [ ] Choose one new, versioned research modality; recommended first target is pose/video because
  unlabeled video volume is high and the raw-data-local value proposition is easy to demonstrate.
- [ ] Define pretext tasks and augmentations that preserve clinically relevant semantics.
- [ ] Train only on data with documented governance and report the exact dataset composition.
- [ ] Export a non-executable or tightly constrained model artifact where practical; pin weights,
  preprocessing, architecture and license by hash.
- [ ] Freeze embedding width, axis contract, public normalization and public bounds.
- [ ] Add deterministic cross-platform golden vectors for macOS and Windows.
- [ ] Register the encoder as a new schema such as `action_ssl_v1`; never change `action` or
  `action_cdp_v1` in place.
- [ ] Evaluate frozen encoder + current DP forest against the 174-dimensional action front end and
  the 104-dimensional CDP adapter under identical grouped splits and privacy budgets.
- [ ] Test identity/site leakage, device shift, missing pose, frame-rate shift and subgroup stability.

**Definition of done:** every node produces numerically compatible embeddings from the same input,
the existing supervised leaf-count head remains valid, and frozen-encoder utility is demonstrated on
a held-out institution without claiming that participant unlabeled data trained the encoder unless it
actually did.

## R4 — federated self-supervised / neural semi-supervised protocol

This is a new protocol generation and should not inherit current security or DP claims automatically.

- [ ] Select FedAvg/FedProx/federated-contrastive or teacher-student semantics and write a threat model.
- [ ] Define fixed-point update encoding, vector bounds and overflow behaviour.
- [ ] Implement per-example or per-client clipping before aggregation.
- [ ] Add secure aggregation for model updates with dropout recovery.
- [ ] Add central/distributed DP noise and an RDP/PRV accountant for many optimization steps.
- [ ] Protect optimizer/checkpoint state and bind every update to model/cohort/version fingerprints.
- [ ] Add malformed-update checks, poisoning simulations and a clear Byzantine-robustness boundary.
- [ ] Extend the signed audit bundle with checkpoint hashes, clipping/noise configuration and privacy
  accountant state.
- [ ] Run membership inference, gradient leakage, site leakage, inversion and malicious-client tests.
- [ ] Complete independent protocol/security review before any cross-institution real-data run.

## R5 — modality-specific research queue

### Eye gaze

- [ ] Consume true timestamps/sampling rate rather than a fixed 30 Hz velocity proxy.
- [ ] Add stimulus/AOI schema and device calibration metadata.
- [ ] Study masked trajectory and temporal-contrastive encoders.

### Action / pose

- [ ] Define a stable video-to-window policy for both browser-extracted and prebuilt NPZ data.
- [ ] Add view/frame-rate robustness and person-level contribution caps.
- [ ] Compare hand-crafted, CDP-adapter and frozen pose-SSL representations.

### EEG

- [ ] Create `eeg_v1` with sampling-rate metadata, filtering, artifact policy, channel mapping and
  missing-channel handling.
- [ ] Evaluate masked channel/time-frequency reconstruction.

### fMRI

- [ ] Create a separate `fmri_v1` contract with TR, parcellation, confound regression and low-frequency
  connectivity semantics.
- [ ] Do not reuse the current 128 Hz EEG band-power assumptions.

## Explicitly not TODO-by-marketing

The following require evidence, not wording changes, and are therefore **not backlog promises**:

- Do not claim clinical screening efficacy or diagnostic use from the engineering POC.
- Do not guarantee that more videos or more rounds monotonically improve AUC.
- Do not claim historical CDP locked-test performance for `action_cdp`.
- Do not claim person-level DP before subject contribution clipping and a new proof.
- Do not call cohort-1 central DP “secure aggregation.”
- Do not call local independent encoders federated SSL when their representation axes are not aligned.
