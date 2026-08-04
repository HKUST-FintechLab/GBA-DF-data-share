"""Regression checks for labelled training versus truth-unknown local inference.

Run with: ``uv run python verify_data_contract.py``.
"""
import os
import tempfile

import numpy as np

import modalities
import node_core


def check(label, condition):
    print(("PASS" if condition else "FAIL") + f": {label}")
    if not condition:
        raise SystemExit(1)


def gaze_csv(path):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("t,x,y\\n0,0.1,0.2\\n1,0.2,0.3\\n2,0.3,0.4\\n")


with tempfile.TemporaryDirectory() as root:
    os.makedirs(os.path.join(root, "asd"))
    os.makedirs(os.path.join(root, "unlabeled"))
    os.makedirs(os.path.join(root, "ads"))
    gaze_csv(os.path.join(root, "asd", "case_001.csv"))
    gaze_csv(os.path.join(root, "unlabeled", "case_002.csv"))
    gaze_csv(os.path.join(root, "ads", "case_003.csv"))
    gaze_csv(os.path.join(root, "case_asd_004.csv"))

    X, y, groups = modalities.get("eyegaze").extract_folder(root)
    by_group = dict(zip(groups.tolist(), y.tolist()))
    check("unlabeled directory preserves truth-unavailable label",
          by_group["unlabeled/case_002.csv"] == "")
    check("misspelled label directory does not become TD",
          by_group["ads/case_003.csv"] == "")
    check("explicit filename label remains supported", by_group["case_asd_004.csv"] == "ASD")

    schema = {"classes": ["TD", "ASD"], "n_features": modalities.GAZE_DIM,
              "modality": "eyegaze"}
    try:
        node_core.load_local(schema, folder=root, on_log=lambda _m: None)
    except ValueError as error:
        check("supervised raw-folder training fails closed", "requires an explicit" in str(error))
    else:
        check("supervised raw-folder training fails closed", False)

    # The same feature extractor is valid for inference: callers receive the empty truth
    # marker and can score the local recording without manufacturing an accuracy label.
    check("inference keeps all recordings including truth-unknown ones",
          X.shape[0] == 4 and int(np.count_nonzero(y == "")) == 2)

print("data contract checks passed")
