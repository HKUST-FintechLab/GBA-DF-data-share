"""GBA-DF federated node (runs on each institution's machine).

Builds data-INDEPENDENT random trees on its OWN local data (splits from the federation's
PUBLIC feature bounds) and uploads INTEGER leaf histograms + a signature. It does NOT add
the privacy noise and does NOT choose epsilon — the coordinator (trusted curator) adds the
Laplace noise at the federation's epsilon and meters the per-node budget. Raw feature/label
arrays are never transmitted.

  uv run python node.py --node-id node_1 --coord http://localhost:8055 \
      --data nodes/node_1/data.npz --rounds 5
"""
import argparse
import os
import time

import httpx
import numpy as np

import dp as dpmod
import fed_common as fc

HERE = os.path.dirname(os.path.abspath(__file__))
NAMES = {"node_1": "HK Children's Hospital", "node_2": "Shenzhen Partner Clinic",
         "node_3": "NGO Screening Centre", "node_4": "University Lab (partner group)",
         "node_5": "Community Clinic"}


def load_or_make_key(node_dir: str):
    p = os.path.join(node_dir, "node_key.pem")          # private key STAYS local, 0600
    if os.path.exists(p):
        try:
            os.chmod(p, 0o600)
        except OSError:
            pass
        return fc.load_priv(open(p, "rb").read())
    k = fc.gen_key()
    os.makedirs(node_dir, exist_ok=True)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(fc.priv_pem(k))
    return k


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--node-id", required=True)
    ap.add_argument("--coord", default="http://localhost:8055")
    ap.add_argument("--data", required=True)
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--trees", type=int, default=None)
    ap.add_argument("--depth", type=int, default=None)
    ap.add_argument("--name", default=None)
    ap.add_argument("--delay", type=float, default=0.8)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    data_path = args.data if os.path.isabs(args.data) else os.path.join(HERE, args.data)
    d = np.load(data_path)
    X, y = d["X"], d["y"].astype(str)                   # LOCAL data — never transmitted
    name = args.name or NAMES.get(args.node_id, args.node_id)
    key = load_or_make_key(os.path.dirname(data_path))
    n_samples = int(X.shape[0])

    cli = httpx.Client(base_url=args.coord, timeout=120.0)
    sch = cli.get("/schema").json()                     # PUBLIC federation schema
    classes = sch["classes"]
    bounds = np.asarray(sch["feature_bounds"], dtype=float)
    dpc = sch["dp"]
    trees = args.trees if args.trees is not None else dpc["trees_per_round"]
    depth = args.depth if args.depth is not None else dpc["depth"]

    cli.post("/register", json={"node_id": args.node_id, "name": name,
                                "pubkey_pem": fc.pub_pem(key).decode(), "samples": n_samples})
    print(f"[{args.node_id}] {name}: {n_samples} local samples — registered. "
          f"mode: DP-counts (depth {depth}, {trees} trees); curator adds Laplace noise at ε={dpc['epsilon_per_round']}/round")

    for r in range(1, args.rounds + 1):
        update = dpmod.build_dp_counts(X, y, classes, bounds, trees, depth, seed=args.seed * 100 + r)
        payload_hash = fc.sha256_hex(fc._canon(update))
        message = f"{args.node_id}|{r}|{n_samples}|{payload_hash}".encode()
        sig = key.sign(message)
        resp = cli.post("/submit", json={"node_id": args.node_id, "round": r, "n_samples": n_samples,
                                         "update": update, "sig_hex": sig.hex()}).json()
        if not resp.get("ok"):
            print(f"[{args.node_id}] round {r}: REJECTED -> {resp.get('error')}")
            break
        kb = len(fc._canon(update)) / 1024
        val = resp.get("fed_primary")
        val_s = f"{val:.3f}" if isinstance(val, (int, float)) else "n/a"
        print(f"[{args.node_id}] round {r}: local={n_samples} | raw arrays sent=0 | leaf counts uploaded "
              f"(curator noised) | ε cum {resp.get('eps_cum'):.2f}/{resp.get('eps_budget')} | "
              f"update={kb:.0f} KB | global {resp.get('primary_metric')}={val_s}")
        time.sleep(args.delay)

    cli.close()
    print(f"[{args.node_id}] done — no raw arrays ever sent.")


if __name__ == "__main__":
    main()
