"""Pluggable datasets for the federated POC.

  har  : UCI Human Activity Recognition (real action data, 6 activities, 561
         features, 10299 windows) — the canonical federated-learning benchmark.
  pose : the project's own ASD action/pose seeds (real, on-brand, but a small
         65-subject seed set → weaker signal; kept as an option).

Each loader returns (X float32, y str-labels, groups or None).
"""
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SEEDS = os.path.normpath(os.path.join(HERE, "..", "..", "synthesis_seeds"))

HAR_NAMES = {
    "1": "WALKING", "2": "WALKING_UPSTAIRS", "3": "WALKING_DOWNSTAIRS",
    "4": "SITTING", "5": "STANDING", "6": "LAYING",
}


def load_har():
    """UCI HAR via OpenML (cached locally to data/har_cache.npz after first fetch)."""
    cache = os.path.join(HERE, "data", "har_cache.npz")
    if os.path.exists(cache):
        z = np.load(cache, allow_pickle=True)
        return z["X"].astype(np.float32), z["y"].astype(str), None
    from sklearn.datasets import fetch_openml
    d = fetch_openml(data_id=1478, as_frame=True)
    X = d.data.to_numpy(dtype=np.float32)
    y = np.array([HAR_NAMES[str(v)] for v in d.target], dtype=object).astype(str)
    os.makedirs(os.path.join(HERE, "data"), exist_ok=True)
    np.savez_compressed(cache, X=X, y=y)
    return X, y, None


def load_pose():
    """Project ASD pose seeds -> ('ASD'/'TD') labels, subject-level groups."""
    from features import load_dataset
    X, y_int, groups = load_dataset(os.path.join(SEEDS, "asd"), os.path.join(SEEDS, "td"))
    y = np.where(y_int == 1, "ASD", "TD").astype(str)
    return X.astype(np.float32), y, groups


def load(name: str):
    if name == "har":
        return load_har()
    if name == "pose":
        return load_pose()
    raise ValueError(f"unknown dataset {name!r} (use 'har' or 'pose')")
