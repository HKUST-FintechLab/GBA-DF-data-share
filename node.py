"""GBA-DF federated node (runs on each institution's machine).

Loads its OWN local data, trains Extra-Trees locally each round, and submits a
constrained JSON tree schema (no pickle) — raw feature/label arrays are never
transmitted. The model itself is NOT privacy-protected (no DP); see README.

  uv run python node.py --node-id node_1 --coord http://localhost:8055 \
      --data nodes/node_1/data.npz --rounds 5 --trees 40
"""
import argparse
import json
import os
import time

import httpx
import numpy as np
from sklearn.ensemble import ExtraTreesClassifier

import fed_common as fc

HERE = os.path.dirname(os.path.abspath(__file__))
NAMES = {"node_1": "HK Children's Hospital", "node_2": "Shenzhen Partner Clinic",
         "node_3": "NGO Screening Centre", "node_4": "University Lab (partner group)",
         "node_5": "Community Clinic"}


def load_or_make_key(node_dir: str):
    """Private key STAYS local, written 0600 (never world-readable, never sent)."""
    p = os.path.join(node_dir, "node_key.pem")
    if os.path.exists(p):
        try:
            os.chmod(p, 0o600)        # repair perms on keys created by an older path
        except OSError:
            pass
        return fc.load_priv(open(p, "rb").read())
    k = fc.gen_key()
    os.makedirs(node_dir, exist_ok=True)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(fc.priv_pem(k))
    return k


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--node-id", required=True)
    ap.add_argument("--coord", default="http://localhost:8055")
    ap.add_argument("--data", required=True)
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--trees", type=int, default=40)
    ap.add_argument("--min-leaf", type=int, default=5, help=">=K samples per leaf (blunts leakage)")
    ap.add_argument("--name", default=None)
    ap.add_argument("--delay", type=float, default=0.8)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    data_path = args.data if os.path.isabs(args.data) else os.path.join(HERE, args.data)
    d = np.load(data_path)
    X, y = d["X"], d["y"].astype(str)               # LOCAL data — never transmitted
    name = args.name or NAMES.get(args.node_id, args.node_id)
    key = load_or_make_key(os.path.dirname(data_path))
    n_samples = int(X.shape[0])

    labels, counts = np.unique(y, return_counts=True)
    cli = httpx.Client(base_url=args.coord, timeout=60.0)
    cli.post("/register", json={"node_id": args.node_id, "name": name,
                                "pubkey_pem": fc.pub_pem(key).decode(), "samples": n_samples})
    print(f"[{args.node_id}] {name}: {n_samples} local samples "
          f"({', '.join(f'{l}:{c}' for l, c in zip(labels, counts))}) — registered.")

    for r in range(1, args.rounds + 1):
        clf = ExtraTreesClassifier(n_estimators=args.trees, min_samples_leaf=args.min_leaf,
                                   class_weight="balanced", random_state=args.seed * 100 + r, n_jobs=-1)
        clf.fit(X, y)                               # trains on LOCAL data only
        update = fc.serialize_forest(clf)           # JSON tree schema — no raw X/y, no pickle
        payload = fc._canon(update)
        payload_hash = fc.sha256_hex(payload)
        message = f"{args.node_id}|{r}|{n_samples}|{payload_hash}".encode()
        sig = key.sign(message)
        resp = cli.post("/submit", json={"node_id": args.node_id, "round": r,
                                         "n_samples": n_samples, "update": update,
                                         "sig_hex": sig.hex()}).json()
        if not resp.get("ok"):
            print(f"[{args.node_id}] round {r}: REJECTED -> {resp.get('error')}")
            break
        kb = len(payload) / 1024
        metric = resp.get("primary_metric", "metric")
        val = resp.get("fed_primary")
        val_s = f"{val:.3f}" if isinstance(val, (int, float)) else "n/a"
        print(f"[{args.node_id}] round {r}: local samples={n_samples} | "
              f"raw feature/label arrays sent=0 | model update={kb:.0f} KB | "
              f"global {metric}={val_s} ({resp.get('global_trees')} trees)")
        time.sleep(args.delay)

    cli.close()
    print(f"[{args.node_id}] done — {args.rounds} rounds, no raw feature/label arrays ever sent.")


if __name__ == "__main__":
    main()
