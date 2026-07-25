"""GBA-DF federated node (CLI) — SECURE AGGREGATION.

Builds the federation's SHARED data-independent trees (from a public seed), counts its
LOCAL data into the leaves, then uploads a PAIRWISE-MASKED integer count vector. The
coordinator can only recover the SUM across all nodes (masks cancel) — it never sees this
node's own counts — and adds the DP noise to that sum. Raw data never leaves the machine.

  # baked features (fast CLI demo):
  uv run python node.py --node-id node_1 --coord http://localhost:8055 \
      --data nodes/node_1/data.npz --rounds 5
  # raw folder ingested LOCALLY via the modality front end (what a partner actually does):
  uv run python node.py --node-id node_1 --coord http://localhost:8055 \
      --folder /path/to/my/eyegaze_recordings --modality eyegaze --rounds 5
  # invited pilot node: everything but the data comes from the issued configuration file
  uv run python node.py --config invite-node_1.json \
      --folder /path/to/my/recordings --rounds 5

The shared node loop lives in node_core.py (also used by the desktop client).
"""
import argparse

import node_core as nc

NAMES = {"node_1": "HK Children's Hospital", "node_2": "Shenzhen Partner Clinic",
         "node_3": "NGO Screening Centre", "node_4": "University Lab (partner group)",
         "node_5": "Community Clinic"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None,
                    help="administrator-issued connection config (URL, password, node id, "
                         "and signed invitation); explicit flags below override it")
    ap.add_argument("--node-id", default=None)
    ap.add_argument("--coord", default=None)
    ap.add_argument("--data", default=None, help="baked features .npz (X, y)")
    ap.add_argument("--folder", default=None, help="raw recordings folder (ingested locally)")
    ap.add_argument("--modality", choices=list(nc.mods.MODALITIES), default=None,
                    help="modality of --folder (defaults to the federation's published modality)")
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--name", default=None)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--password", default=None, help="shared access token if the federation is protected")
    args = ap.parse_args()
    if not args.data and not args.folder:
        ap.error("provide --data (baked .npz) or --folder (raw recordings)")

    issued = {}
    if args.config:
        try:
            issued = nc.load_client_config(args.config)
        except (OSError, ValueError) as e:
            ap.error(f"could not read --config: {e}")
    coord = args.coord or issued.get("coord") or "http://localhost:8055"
    node_id = args.node_id or issued.get("node_id")
    password = args.password or issued.get("password")
    invitation = issued.get("invitation")
    if not node_id:
        ap.error("provide --node-id (or a --config that carries one)")

    tag = f"[{node_id}] "
    log = lambda m: print(tag + m)                      # noqa: E731
    try:
        sch = nc.fetch_schema(coord, key=password)
    except Exception as e:
        log(f"cannot reach coordinator: {e}"); return
    try:
        X, y, key_dir = nc.load_local(sch, data=args.data, folder=args.folder,
                                      modality=args.modality, on_log=log)
    except ValueError as e:
        log(str(e)); return
    name = args.name or issued.get("name") or NAMES.get(node_id, node_id)
    nc.run_node(coord, node_id, name, X, y, sch, rounds=args.rounds,
                seed=args.seed, key_dir=key_dir, on_log=log, key=password,
                invitation=invitation)


if __name__ == "__main__":
    main()
