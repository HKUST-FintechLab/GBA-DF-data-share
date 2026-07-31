"""Regression checks for the experimental CDP federated feature adapter."""

from __future__ import annotations

import copy
import json
import os
import tempfile

import numpy as np

import cdp_features as cdp
import modalities
from export_cdp_adapter import build_adapter


passed = 0
failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
    else:
        failed += 1
    print(f"  [{'PASS' if condition else 'FAIL'}] {name}")


class StubScaler:
    def __init__(self, dim):
        self.n_features_in_ = dim
        self.mean_ = np.linspace(-1.0, 1.0, dim)
        self.scale_ = np.linspace(0.5, 1.5, dim)


class StubSelector:
    def __init__(self, indices):
        self.indices = np.asarray(indices, dtype=np.int64)

    def get_support(self, indices=False):
        if indices:
            return self.indices
        raise AssertionError("exporter must request selector indices")


class StubPipeline:
    def __init__(self, dim, indices):
        self.named_steps = {
            "scale": StubScaler(dim),
            "select": StubSelector(indices),
        }


def source_names(mode):
    rng = np.random.default_rng(123)
    body = rng.normal(0.5, 0.15, (60, 33, 4)).astype(np.float32)
    body[..., 3] = 0.9
    return cdp.extract_raw_branches(body)[mode][1]


print("== pinned, data-only adapter ==")
adapter = cdp.load_adapter()
check("adapter is pinned to action_cdp v1", adapter["payload_sha256"] == cdp.EXPECTED_ADAPTER_PAYLOAD_SHA256)
all_keys = set(cdp._walk_keys(adapter))
check("adapter contains no executable model or participant fields",
      not (all_keys & cdp._FORBIDDEN_ADAPTER_KEYS))
check("adapter exposes the frozen 40+64 feature schema",
      [component["output_dim"] for component in adapter["components"]] == [40, 64])

tampered = copy.deepcopy(adapter)
tampered["decision_threshold"] = 0.99
try:
    cdp.validate_adapter(tampered)
    tamper_rejected = False
except ValueError:
    tamper_rejected = True
check("editing adapter JSON fails its payload hash", tamper_rejected)

print("== faithful feature interface ==")
rng = np.random.default_rng(20260730)
body = rng.normal(0.5, 0.2, (60, 33, 4)).astype(np.float32)
body[..., 3] = rng.uniform(0.2, 1.0, (60, 33))
mapped = cdp.mediapipe33_to_coco17(body)
branches = cdp.extract_raw_branches(body)
selected = cdp.extract_selected_features(body, adapter)
check("MediaPipe 33 points map to COCO-style 17 x/y/visibility", mapped.shape == (60, 17, 3))
check("raw branches retain the historical 230 and 1150 widths",
      branches["engineered"][0].shape == (230,) and branches["segment_bag"][0].shape == (1150,))
check("frozen selected representation is 104 finite values",
      selected.shape == (104,) and np.isfinite(selected).all())
check("adapter names bind each selected index to feature semantics",
      all(
          component["selected_feature_names"]
          == [branches[component["feature_mode"]][1][index]
              for index in component["selected_indices"]]
          for component in adapter["components"]
      ))

try:
    cdp.mediapipe33_to_coco17(np.zeros((60, 17, 3), dtype=np.float32))
    bad_shape_rejected = False
except ValueError:
    bad_shape_rejected = True
check("wrong pose shape is rejected", bad_shape_rejected)
long_body = np.repeat(body, 2, axis=0)
long_branches = cdp.extract_raw_branches(long_body)
check("clips longer than the champion cap are sampled to 64 frames",
      long_branches["engineered"][0][-5] == cdp.MAX_CDP_FRAMES)
try:
    cdp.extract_selected_features(body[:23], adapter)
    short_clip_rejected = False
except ValueError:
    short_clip_rejected = True
check("clips shorter than the champion minimum are rejected", short_clip_rejected)

print("== exporter allow-list ==")
stub_components = []
for mode, dim, count in (("engineered", 230, 40), ("segment_bag", 1150, 64)):
    indices = np.arange(count)
    names = [source_names(mode)[index] for index in indices]
    stub_components.append({
        "name": mode,
        "feature_mode": mode,
        "weight": 0.67 if mode == "engineered" else 0.33,
        "pipeline": StubPipeline(dim, indices),
        "selected_feature_names": names,
    })
stub_bundle = {
    "artifact_version": 5,
    "bundle_kind": "late_fusion",
    "selected_candidate": "test",
    "search_space_version": "test",
    "decision_threshold": 0.45,
    "fusion_components": stub_components,
    "sample_ids": ["PRIVATE_SAMPLE_123"],
    "groups": ["PRIVATE_GROUP_456"],
    "reports": [{"private": "PRIVATE_REPORT_789"}],
}
exported = build_adapter(stub_bundle, "a" * 64)
exported_text = json.dumps(exported)
check("exporter does not copy sample IDs, groups, or reports",
      all(secret not in exported_text for secret in
          ("PRIVATE_SAMPLE_123", "PRIVATE_GROUP_456", "PRIVATE_REPORT_789")))

print("== modality registry and folder ingestion ==")
modality = modalities.get("action_cdp")
with tempfile.TemporaryDirectory() as root:
    os.makedirs(os.path.join(root, "asd"))
    os.makedirs(os.path.join(root, "td"))
    np.savez_compressed(os.path.join(root, "asd", "a.npz"), body=body)
    np.savez_compressed(os.path.join(root, "td", "t.npz"), body=body * 0.9)
    X, y, groups = modality.extract_folder(root)
check("action_cdp ingests one recording per class with stable groups",
      X.shape == (2, 104) and sorted(y.tolist()) == ["ASD", "TD"] and len(groups) == 2)
check("action_cdp lands inside the public DP bounds",
      np.isfinite(X).all() and X.min() >= -1.0 and X.max() <= 1.0)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
