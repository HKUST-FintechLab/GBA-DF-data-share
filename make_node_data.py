"""Turn a partner's local CSV into the data.npz a node needs — and VALIDATE it
against the federation's published schema BEFORE anything leaves the machine.

  uv run python make_node_data.py --csv my_data.csv --label-col activity \
      --coord http://<coordinator-host>:8055 --out nodes/partner/data.npz

CSV: one row per sample; all columns except --label-col are numeric features,
in the SAME order/meaning as the agreed federation feature schema.
This script reads ONLY your local file and (optionally) the public /schema; it
never uploads anything.
"""
import argparse
import csv
import os
import sys

import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="local CSV: features + one label column")
    ap.add_argument("--label-col", required=True)
    ap.add_argument("--out", required=True, help="output .npz (X, y)")
    ap.add_argument("--coord", default=None, help="coordinator URL to validate feature count + labels")
    ap.add_argument("--password", default=None,
                    help="contributor password when the coordinator protects /schema")
    args = ap.parse_args()

    with open(args.csv, newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        sys.exit("empty CSV")
    cols = list(rows[0].keys())
    if args.label_col not in cols:
        sys.exit(f"label column {args.label_col!r} not in CSV columns {cols}")
    feat_cols = [c for c in cols if c != args.label_col]

    try:
        X = np.array([[float(r[c]) for c in feat_cols] for r in rows], dtype=np.float32)
    except ValueError as e:
        sys.exit(f"non-numeric feature value: {e}")
    y = np.array([str(r[args.label_col]) for r in rows])

    print(f"Parsed {X.shape[0]} samples × {X.shape[1]} features.")
    labels, counts = np.unique(y, return_counts=True)
    print("Label distribution:", dict(zip(labels.tolist(), counts.tolist())))

    if args.coord:
        import httpx
        headers = {"X-Fed-Key": args.password} if args.password else {}
        response = httpx.get(args.coord.rstrip("/") + "/schema", timeout=15, headers=headers)
        if response.status_code != 200:
            sys.exit(f"could not read federation schema: {response.status_code} {response.text}")
        sch = response.json()
        if X.shape[1] != sch["n_features"]:
            sys.exit(f"FEATURE MISMATCH: your CSV has {X.shape[1]} features but the federation "
                     f"schema expects {sch['n_features']}. Align your feature pipeline first.")
        unknown = sorted(set(y) - set(sch["classes"]))
        if unknown:
            sys.exit(f"UNKNOWN LABELS {unknown}; federation classes are {sch['classes']}.")
        print(f"✓ validated against {args.coord}: {X.shape[1]} features, labels ⊆ {sch['classes']}")

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    np.savez_compressed(args.out, X=X, y=y)
    print(f"Wrote {args.out}. This file STAYS on your machine — node.py only sends integer leaf-count "
          f"summaries of data-independent trees (the coordinator adds the DP noise).")


if __name__ == "__main__":
    main()
