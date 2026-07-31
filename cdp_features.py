"""CDP-TreeFusion feature adapter for MediaPipe Pose windows.

This module ports the dependency-light feature front end from the historical
CDP-TreeFusion project.  It does not load or execute the historical pickle and
does not contain the ExtraTrees classifiers.  A small, allow-listed JSON
adapter supplies only the frozen StandardScaler parameters and selected feature
indices needed to expose the champion's 40 + 64 dimensional representation to
the existing federated DP forest.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import numpy as np


HERE = Path(__file__).resolve().parent
DEFAULT_ADAPTER_PATH = HERE / "assets" / "cdp_adapter_v1.json"
ADAPTER_FORMAT = "gba-df-cdp-adapter"
ADAPTER_VERSION = 1
# `action_cdp` is a schema, not merely a dimension.  Pinning this adapter
# prevents two nodes from silently training on different 104-feature meanings.
EXPECTED_ADAPTER_PAYLOAD_SHA256 = "be56fc8ca5b775ff9a8a944a35b13bdfe5bfdf131c97dbdf6906cd41d6378c42"
CDP_OUTPUT_DIM = 104
ENGINEERED_DIM = 230
SEGMENT_BAG_DIM = 1150
DEFAULT_SEGMENT_WINDOW = 32
DEFAULT_SEGMENT_STRIDE = 16
MIN_CDP_FRAMES = 24
MAX_CDP_FRAMES = 64

# Mapping used by the historical MediaPipe training run:
# nose, eyes, ears, shoulders, elbows, wrists, hips, knees, ankles.
MEDIAPIPE_TO_COCO17 = np.asarray(
    [0, 2, 5, 7, 8, 11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28],
    dtype=np.int64,
)

LEFT_RIGHT_PAIRS = (
    (5, 6),
    (7, 8),
    (9, 10),
    (11, 12),
    (13, 14),
    (15, 16),
)
CORE_JOINTS = (0, 5, 6, 11, 12)
AGGREGATIONS = ("mean", "std", "max", "min", "slope")
_FORBIDDEN_ADAPTER_KEYS = {
    "sample_ids",
    "groups",
    "reports",
    "pipeline",
    "model",
    "estimators",
    "trees",
}


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def adapter_payload_sha256(payload: dict[str, Any]) -> str:
    body = {key: value for key, value in payload.items() if key != "payload_sha256"}
    return hashlib.sha256(_canonical_json(body)).hexdigest()


def mediapipe33_to_coco17(body: np.ndarray) -> np.ndarray:
    """Map ``(T,33,4=[x,y,z,visibility])`` to ``(T,17,3=[x,y,visibility])``."""
    body = np.asarray(body, dtype=np.float32)
    if body.ndim != 3 or body.shape[1:] != (33, 4):
        raise ValueError("expected MediaPipe body with shape (T,33,4)")
    if body.shape[0] < 1:
        raise ValueError("pose sequence must contain at least one frame")
    mapped = np.stack(
        [
            body[:, MEDIAPIPE_TO_COCO17, 0],
            body[:, MEDIAPIPE_TO_COCO17, 1],
            body[:, MEDIAPIPE_TO_COCO17, 3],
        ],
        axis=-1,
    )
    return np.nan_to_num(mapped, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32)


def prepare_cdp_body(body: np.ndarray) -> np.ndarray:
    """Validate a CDP clip and reproduce the champion's 64-frame cap."""
    body = np.asarray(body, dtype=np.float32)
    if body.ndim != 3 or body.shape[1:] != (33, 4):
        raise ValueError("expected MediaPipe body with shape (T,33,4)")
    if body.shape[0] < MIN_CDP_FRAMES:
        raise ValueError(f"CDP input requires at least {MIN_CDP_FRAMES} sampled frames")
    if body.shape[0] > MAX_CDP_FRAMES:
        indices = np.linspace(0, body.shape[0] - 1, num=MAX_CDP_FRAMES, dtype=np.int64)
        body = body[indices]
    return body


def normalize_keypoints(keypoints: np.ndarray) -> np.ndarray:
    """Reproduce the historical video-level min/max pose normalization."""
    normalized = np.asarray(keypoints, dtype=np.float32).copy()
    if normalized.ndim != 3 or normalized.shape[1:] != (17, 3):
        raise ValueError("expected CDP keypoints with shape (T,17,3)")

    valid = normalized[:, :, 2] > 0.1
    if valid.any():
        x = normalized[:, :, 0]
        y = normalized[:, :, 1]
        x_min, x_max = x[valid].min(), x[valid].max()
        y_min, y_max = y[valid].min(), y[valid].max()
        normalized[:, :, 0] = (x - x_min) / max(float(x_max - x_min), 1e-6)
        normalized[:, :, 1] = (y - y_min) / max(float(y_max - y_min), 1e-6)

    return np.nan_to_num(normalized, nan=0.0, posinf=0.0, neginf=0.0)


class CDPEngineeredExtractor:
    """Historical 230-dimensional CDP engineered feature branch."""

    def __init__(self, visibility_threshold: float = 0.1) -> None:
        self.visibility_threshold = visibility_threshold

    @staticmethod
    def _safe_series(values: np.ndarray) -> np.ndarray:
        values = np.asarray(values, dtype=np.float32).reshape(-1)
        if values.size == 0:
            return np.zeros(1, dtype=np.float32)
        return np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)

    def _add_stats(
        self,
        values: np.ndarray,
        prefix: str,
        names: list[str],
        features: list[float],
    ) -> None:
        series = self._safe_series(values)
        percentiles = np.percentile(series, [10, 25, 50, 75, 90])
        stats = (
            ("mean", series.mean()),
            ("std", series.std()),
            ("min", series.min()),
            ("max", series.max()),
            ("p10", percentiles[0]),
            ("p25", percentiles[1]),
            ("p50", percentiles[2]),
            ("p75", percentiles[3]),
            ("p90", percentiles[4]),
        )
        for suffix, value in stats:
            names.append(f"{prefix}_{suffix}")
            features.append(float(value))

    def extract(self, keypoints: np.ndarray) -> tuple[np.ndarray, list[str]]:
        keypoints = normalize_keypoints(keypoints)
        valid = keypoints[:, :, 2] > self.visibility_threshold
        coords = keypoints[:, :, :2]
        visibility = keypoints[:, :, 2]
        center = coords[:, CORE_JOINTS, :].mean(axis=1)
        velocity = np.diff(coords, axis=0, prepend=coords[:1])
        speed = np.linalg.norm(velocity, axis=2)
        acceleration = np.diff(speed, axis=0, prepend=speed[:1])
        bbox_width = coords[:, :, 0].max(axis=1) - coords[:, :, 0].min(axis=1)
        bbox_height = coords[:, :, 1].max(axis=1) - coords[:, :, 1].min(axis=1)
        bbox_area = bbox_width * bbox_height
        frame_visibility_ratio = valid.mean(axis=1)
        joint_visibility_ratio = valid.mean(axis=0)

        symmetry = [
            np.abs(coords[:, left, :] - coords[:, right, :]).mean(axis=1)
            for left, right in LEFT_RIGHT_PAIRS
        ]
        symmetry_matrix = np.vstack(symmetry)

        names: list[str] = []
        features: list[float] = []
        self._add_stats(center[:, 0], "center_x", names, features)
        self._add_stats(center[:, 1], "center_y", names, features)
        self._add_stats(speed.mean(axis=1), "global_speed", names, features)
        self._add_stats(speed.std(axis=1), "joint_speed_dispersion", names, features)
        self._add_stats(acceleration.mean(axis=1), "global_acceleration", names, features)
        self._add_stats(acceleration.std(axis=1), "joint_acceleration_dispersion", names, features)
        self._add_stats(bbox_width, "bbox_width", names, features)
        self._add_stats(bbox_height, "bbox_height", names, features)
        self._add_stats(bbox_area, "bbox_area", names, features)
        self._add_stats(frame_visibility_ratio, "frame_visibility", names, features)
        self._add_stats(visibility.mean(axis=1), "mean_confidence", names, features)
        self._add_stats(symmetry_matrix.mean(axis=0), "left_right_gap", names, features)

        for joint_index in (0, 5, 6, 9, 10, 15, 16):
            self._add_stats(speed[:, joint_index], f"joint_{joint_index:02d}_speed", names, features)

        for pair_index, (left, right) in enumerate(LEFT_RIGHT_PAIRS):
            pair_distance = np.linalg.norm(coords[:, left, :] - coords[:, right, :], axis=1)
            self._add_stats(pair_distance, f"pair_{pair_index:02d}_distance", names, features)

        names.extend(
            [
                "num_frames",
                "num_joints",
                "visibility_ratio_overall",
                "joint_visibility_mean",
                "joint_visibility_std",
            ]
        )
        features.extend(
            [
                float(keypoints.shape[0]),
                float(keypoints.shape[1]),
                float(valid.mean()),
                float(joint_visibility_ratio.mean()),
                float(joint_visibility_ratio.std()),
            ]
        )
        feature_vector = np.nan_to_num(
            np.asarray(features, dtype=np.float32), nan=0.0, posinf=0.0, neginf=0.0
        )
        if feature_vector.shape != (ENGINEERED_DIM,):
            raise RuntimeError(f"CDP engineered feature width changed: {feature_vector.shape}")
        return feature_vector, names


def compute_window_starts(num_frames: int, window_size: int, stride: int) -> list[int]:
    if window_size < 1 or stride < 1:
        raise ValueError("window_size and stride must be positive")
    if num_frames <= window_size:
        return [0]
    starts = list(range(0, num_frames - window_size + 1, stride))
    last_start = max(num_frames - window_size, 0)
    if starts[-1] != last_start:
        starts.append(last_start)
    return starts


def build_segment_feature_names(base_feature_names: list[str]) -> list[str]:
    return [
        f"segment_{aggregation}_{feature_name}"
        for aggregation in AGGREGATIONS
        for feature_name in base_feature_names
    ]


def extract_segment_bag(
    keypoints: np.ndarray,
    *,
    window_size: int = DEFAULT_SEGMENT_WINDOW,
    stride: int = DEFAULT_SEGMENT_STRIDE,
    extractor: CDPEngineeredExtractor | None = None,
) -> tuple[np.ndarray, list[str]]:
    """Historical five-statistic segment bag (230 × 5 = 1150 dimensions)."""
    extractor = extractor or CDPEngineeredExtractor()
    normalized = normalize_keypoints(keypoints)
    starts = compute_window_starts(normalized.shape[0], window_size, stride)
    window_features: list[np.ndarray] = []
    base_names: list[str] | None = None
    for start in starts:
        clip = normalized[start : min(start + window_size, normalized.shape[0])]
        features, names = extractor.extract(clip)
        window_features.append(features)
        if base_names is None:
            base_names = names

    window_matrix = np.vstack(window_features)
    stats = [
        window_matrix.mean(axis=0),
        window_matrix.std(axis=0),
        window_matrix.max(axis=0),
        window_matrix.min(axis=0),
    ]
    if len(window_matrix) > 1:
        x_axis = np.arange(len(window_matrix), dtype=np.float32)
        slope = np.polyfit(x_axis, window_matrix, 1)[0]
    else:
        slope = np.zeros(window_matrix.shape[1], dtype=np.float32)
    stats.append(np.asarray(slope, dtype=np.float32))
    bag = np.nan_to_num(np.concatenate(stats), nan=0.0, posinf=0.0, neginf=0.0)
    names = build_segment_feature_names(base_names or [])
    if bag.shape != (SEGMENT_BAG_DIM,) or len(names) != SEGMENT_BAG_DIM:
        raise RuntimeError(f"CDP segment-bag feature width changed: {bag.shape}")
    return bag.astype(np.float32), names


def extract_raw_branches(
    body: np.ndarray,
    *,
    window_size: int = DEFAULT_SEGMENT_WINDOW,
    stride: int = DEFAULT_SEGMENT_STRIDE,
) -> dict[str, tuple[np.ndarray, list[str]]]:
    keypoints = mediapipe33_to_coco17(prepare_cdp_body(body))
    extractor = CDPEngineeredExtractor()
    engineered = extractor.extract(keypoints)
    segment_bag = extract_segment_bag(
        keypoints, window_size=window_size, stride=stride, extractor=extractor
    )
    return {"engineered": engineered, "segment_bag": segment_bag}


def _walk_keys(value: Any):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def _finite_vector(value: Any, length: int, name: str, *, positive: bool = False) -> np.ndarray:
    array = np.asarray(value, dtype=np.float64)
    if array.shape != (length,) or not np.isfinite(array).all():
        raise ValueError(f"{name} must contain {length} finite numbers")
    if positive and np.any(array <= 0):
        raise ValueError(f"{name} must be strictly positive")
    return array


def validate_adapter(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("CDP adapter must be a JSON object")
    if payload.get("format") != ADAPTER_FORMAT or payload.get("version") != ADAPTER_VERSION:
        raise ValueError("unsupported CDP adapter format/version")
    if any(key in _FORBIDDEN_ADAPTER_KEYS for key in _walk_keys(payload)):
        raise ValueError("CDP adapter contains a forbidden model or participant field")
    expected_hash = payload.get("payload_sha256")
    if not isinstance(expected_hash, str) or expected_hash != adapter_payload_sha256(payload):
        raise ValueError("CDP adapter payload hash mismatch")
    if payload.get("output_dim") != CDP_OUTPUT_DIM:
        raise ValueError(f"CDP adapter output_dim must be {CDP_OUTPUT_DIM}")

    segment = payload.get("segment")
    if not isinstance(segment, dict):
        raise ValueError("CDP adapter is missing segment configuration")
    if segment.get("window_size") != DEFAULT_SEGMENT_WINDOW:
        raise ValueError(f"CDP adapter window_size must be {DEFAULT_SEGMENT_WINDOW}")
    if segment.get("stride") != DEFAULT_SEGMENT_STRIDE:
        raise ValueError(f"CDP adapter stride must be {DEFAULT_SEGMENT_STRIDE}")

    components = payload.get("components")
    if not isinstance(components, list) or len(components) != 2:
        raise ValueError("CDP adapter must contain two components")
    expected = (("engineered", ENGINEERED_DIM, 40), ("segment_bag", SEGMENT_BAG_DIM, 64))
    total = 0
    weights = []
    for component, (mode, input_dim, output_dim) in zip(components, expected):
        if not isinstance(component, dict) or component.get("feature_mode") != mode:
            raise ValueError(f"CDP adapter component order must be {[item[0] for item in expected]}")
        if component.get("input_dim") != input_dim or component.get("output_dim") != output_dim:
            raise ValueError(f"invalid dimensions for CDP component {mode}")
        indices = np.asarray(component.get("selected_indices"), dtype=np.int64)
        if (
            indices.shape != (output_dim,)
            or len(np.unique(indices)) != output_dim
            or np.any(indices < 0)
            or np.any(indices >= input_dim)
        ):
            raise ValueError(f"invalid selected_indices for CDP component {mode}")
        names = component.get("selected_feature_names")
        if not isinstance(names, list) or len(names) != output_dim or not all(
            isinstance(name, str) for name in names
        ):
            raise ValueError(f"invalid selected_feature_names for CDP component {mode}")
        _finite_vector(component.get("scaler_mean"), input_dim, f"{mode}.scaler_mean")
        _finite_vector(
            component.get("scaler_scale"), input_dim, f"{mode}.scaler_scale", positive=True
        )
        weight = float(component.get("weight", -1))
        if not np.isfinite(weight) or weight < 0:
            raise ValueError(f"invalid fusion weight for CDP component {mode}")
        weights.append(weight)
        total += output_dim
    if total != CDP_OUTPUT_DIM or not np.isclose(sum(weights), 1.0, atol=1e-9):
        raise ValueError("CDP adapter output width or fusion weights are inconsistent")
    return payload


def load_adapter(path: str | os.PathLike[str] = DEFAULT_ADAPTER_PATH) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        payload = validate_adapter(json.load(handle))
    if payload["payload_sha256"] != EXPECTED_ADAPTER_PAYLOAD_SHA256:
        raise ValueError(
            "CDP adapter is valid JSON but does not match the action_cdp v1 schema pin"
        )
    return payload


def extract_selected_features(
    body: np.ndarray,
    adapter: dict[str, Any] | None = None,
) -> np.ndarray:
    """Return the champion's frozen 40 + 64 selected, standardized features."""
    adapter = validate_adapter(adapter) if adapter is not None else load_adapter()
    segment = adapter["segment"]
    branches = extract_raw_branches(
        body, window_size=segment["window_size"], stride=segment["stride"]
    )
    selected: list[np.ndarray] = []
    for component in adapter["components"]:
        mode = component["feature_mode"]
        raw, feature_names = branches[mode]
        indices = np.asarray(component["selected_indices"], dtype=np.int64)
        expected_names = [feature_names[index] for index in indices]
        if expected_names != component["selected_feature_names"]:
            raise ValueError(f"CDP adapter feature-name binding failed for {mode}")
        mean = np.asarray(component["scaler_mean"], dtype=np.float64)
        scale = np.asarray(component["scaler_scale"], dtype=np.float64)
        standardized = (raw.astype(np.float64) - mean) / scale
        selected.append(standardized[indices])
    output = np.nan_to_num(
        np.concatenate(selected), nan=0.0, posinf=0.0, neginf=0.0
    ).astype(np.float32)
    if output.shape != (CDP_OUTPUT_DIM,):
        raise RuntimeError(f"CDP selected feature width changed: {output.shape}")
    return output
