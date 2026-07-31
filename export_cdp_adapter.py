#!/usr/bin/env python3
"""One-time, local conversion of a trusted CDP pickle to an allow-listed JSON adapter.

Pickle deserialization can execute code.  This command therefore requires both
an exact SHA-256 pin and an explicit risk acknowledgement.  The generated JSON
does not contain the classifiers, reports, sample IDs, groups, or any executable
object; it contains only scaler parameters, selected feature indices/names,
fusion metadata, and calibration coefficients.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from cdp_features import (
    ADAPTER_FORMAT,
    ADAPTER_VERSION,
    CDP_OUTPUT_DIM,
    DEFAULT_SEGMENT_STRIDE,
    DEFAULT_SEGMENT_WINDOW,
    ENGINEERED_DIM,
    MEDIAPIPE_TO_COCO17,
    SEGMENT_BAG_DIM,
    adapter_payload_sha256,
    validate_adapter,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert one explicitly trusted CDP-TreeFusion pickle into a data-only adapter"
    )
    parser.add_argument("--input", required=True, help="trusted final_model.pkl")
    parser.add_argument("--output", required=True, help="destination JSON adapter")
    parser.add_argument(
        "--trusted-sha256",
        required=True,
        help="expected 64-character SHA-256 of the input pickle",
    )
    parser.add_argument(
        "--acknowledge-pickle-risk",
        action="store_true",
        help="required: acknowledge that loading even a hash-pinned pickle can execute code",
    )
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_floats(value: Any) -> list[float]:
    array = np.asarray(value, dtype=np.float64).reshape(-1)
    if not np.isfinite(array).all():
        raise ValueError("refusing to export non-finite model parameters")
    return [float(item) for item in array]


def _component_payload(component: dict[str, Any], expected_mode: str, expected_dim: int) -> dict:
    if component.get("feature_mode") != expected_mode:
        raise ValueError(f"expected {expected_mode!r} component")
    pipeline = component.get("pipeline")
    steps = getattr(pipeline, "named_steps", {})
    scaler = steps.get("scale")
    selector = steps.get("select")
    if scaler is None or selector is None:
        raise ValueError(f"{expected_mode} pipeline lacks scale/select steps")
    indices = np.asarray(selector.get_support(indices=True), dtype=np.int64)
    names = component.get("selected_feature_names")
    if not isinstance(names, list) or len(names) != len(indices):
        raise ValueError(f"{expected_mode} selected feature names do not match selector")
    input_dim = int(getattr(scaler, "n_features_in_", 0))
    if input_dim != expected_dim:
        raise ValueError(f"{expected_mode} input dimension is {input_dim}, expected {expected_dim}")
    return {
        "name": str(component.get("name", expected_mode)),
        "feature_mode": expected_mode,
        "weight": float(component.get("weight", 0.0)),
        "input_dim": input_dim,
        "output_dim": int(len(indices)),
        "scaler_mean": _json_floats(scaler.mean_),
        "scaler_scale": _json_floats(scaler.scale_),
        "selected_indices": [int(index) for index in indices],
        "selected_feature_names": [str(name) for name in names],
    }


def build_adapter(bundle: Any, source_sha256: str) -> dict[str, Any]:
    if not isinstance(bundle, dict) or bundle.get("bundle_kind") != "late_fusion":
        raise ValueError("expected a late_fusion CDP deployment bundle")
    components = bundle.get("fusion_components")
    if not isinstance(components, list) or len(components) != 2:
        raise ValueError("expected exactly two CDP fusion components")
    exported = [
        _component_payload(components[0], "engineered", ENGINEERED_DIM),
        _component_payload(components[1], "segment_bag", SEGMENT_BAG_DIM),
    ]
    if [component["output_dim"] for component in exported] != [40, 64]:
        raise ValueError("expected CDP champion selectors with 40 and 64 features")

    calibration_payload = None
    calibration = bundle.get("calibration")
    if calibration is not None:
        model = calibration.get("model") if isinstance(calibration, dict) else None
        if model is None:
            raise ValueError("calibration entry is missing its fitted model")
        calibration_payload = {
            "method": str(calibration.get("method", "unknown")),
            "classes": [int(value) for value in np.asarray(model.classes_).reshape(-1)],
            "coef": _json_floats(model.coef_),
            "intercept": _json_floats(model.intercept_),
        }

    payload: dict[str, Any] = {
        "format": ADAPTER_FORMAT,
        "version": ADAPTER_VERSION,
        "purpose": "experimental federated feature adapter; not a deployable CDP classifier",
        "source": {
            "model_sha256": source_sha256,
            "artifact_version": int(bundle.get("artifact_version", 0)),
            "selected_candidate": str(bundle.get("selected_candidate", "")),
            "search_space_version": str(bundle.get("search_space_version", "")),
        },
        "pose": {
            "source_shape": "(T,33,4=[x,y,z,visibility])",
            "target_shape": "(T,17,3=[x,y,visibility])",
            "mediapipe_to_coco17": [int(index) for index in MEDIAPIPE_TO_COCO17],
            "target_fps": 4.0,
            "max_frames": 64,
            "min_sampled_frames": 24,
        },
        "segment": {
            "window_size": DEFAULT_SEGMENT_WINDOW,
            "stride": DEFAULT_SEGMENT_STRIDE,
        },
        "components": exported,
        "output_dim": CDP_OUTPUT_DIM,
        "fusion_weights": [component["weight"] for component in exported],
        "decision_threshold": float(bundle.get("decision_threshold", 0.5)),
        "calibration": calibration_payload,
        "excluded_fields": [
            "sample_ids",
            "groups",
            "reports",
            "pipelines",
            "classifiers",
            "trees",
        ],
    }
    payload["payload_sha256"] = adapter_payload_sha256(payload)
    return validate_adapter(payload)


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
    ) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> None:
    args = parse_args()
    source = Path(args.input).resolve()
    destination = Path(args.output).resolve()
    expected = args.trusted_sha256.lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise SystemExit("--trusted-sha256 must be exactly 64 lowercase hexadecimal characters")
    if not args.acknowledge_pickle_risk:
        raise SystemExit("refusing to load pickle without --acknowledge-pickle-risk")
    actual = sha256_file(source)
    if actual != expected:
        raise SystemExit(f"refusing unpinned pickle: expected {expected}, got {actual}")

    # This is the only executable-deserialization boundary.  Nothing produced by
    # this command is subsequently loaded as pickle by the federated application.
    import pickle

    with source.open("rb") as handle:
        bundle = pickle.load(handle)
    adapter = build_adapter(bundle, actual)
    write_json_atomic(destination, adapter)
    print(f"Wrote {destination}")
    print(f"Adapter payload SHA-256: {adapter['payload_sha256']}")
    print(f"Selected dimensions: {[c['output_dim'] for c in adapter['components']]}")


if __name__ == "__main__":
    main()
