"""Use the federation's trained model as a DATA-USER / central node.

Two ways to consume the model that everyone trained together:

  (A) LOCAL inference (recommended — your query data also stays on your machine):
      download the aggregated model once, then score your own recordings offline.

        uv run python predict.py --coord http://<host>:8062 \
            --folder my_new_cases --out predictions.csv

  (B) HOSTED inference (convenience — sends your feature rows to the coordinator):

        uv run python predict.py --coord http://<host>:8062 \
            --folder my_new_cases --hosted --out predictions.csv

  Just archive the model artifact (pickle-free JSON) for offline / audit use:

        uv run python predict.py --coord http://<host>:8062 --save-model global_model.json

The model is a pickle-free JSON forest ensemble; it carries its provenance (modality, feature
schema, DP budget spent, held-out test metric, and the audit tip you can verify at /pubkey).
"""
import argparse
import csv
import json
import os
import sys

import httpx
import numpy as np

import fed_common as fc
import modalities as mods

HERE = os.path.dirname(os.path.abspath(__file__))


def load_features(meta, folder=None, data=None, modality=None):
    """Turn local recordings into the model's feature matrix — locally, nothing transmitted."""
    if folder:
        folder = folder if os.path.isabs(folder) else os.path.join(HERE, folder)
        mkey = modality or meta.get("modality")
        if not mkey:
            sys.exit("model has no modality; pass --modality or use --data")
        m = mods.get(mkey)
        X, y, groups = m.extract_folder(folder)
        return np.asarray(X, float), np.asarray(y).astype(str), np.asarray(groups).astype(str)
    d = np.load(data if os.path.isabs(data) else os.path.join(HERE, data))
    y = np.asarray(d["y"]).astype(str) if "y" in d else np.array([""] * d["X"].shape[0])
    return np.asarray(d["X"], float), y, np.array([str(i) for i in range(d["X"].shape[0])])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--coord", required=True, help="coordinator URL")
    ap.add_argument("--folder", default=None, help="folder of raw recordings to score (stays local)")
    ap.add_argument("--data", default=None, help="baked features .npz to score")
    ap.add_argument("--modality", choices=list(mods.MODALITIES), default=None)
    ap.add_argument("--hosted", action="store_true", help="send features to /predict instead of local inference")
    ap.add_argument("--save-model", default=None, help="also write the downloaded model JSON here")
    ap.add_argument("--out", default=None, help="write predictions CSV here")
    args = ap.parse_args()

    cli = httpx.Client(base_url=args.coord, timeout=120.0)
    r = cli.get("/model")
    if r.status_code != 200:
        sys.exit(f"could not download model: {r.status_code} {r.text}")
    meta = r.json()
    print(f"Global model — modality={meta.get('modality')} · {len(meta['classes'])} classes "
          f"{meta['classes']} · {meta['n_features']} features · {meta['rounds']} rounds · "
          f"{meta['n_trees']} trees")
    print(f"  held-out {meta['primary_metric']} = {meta.get('test_metric')} · "
          f"DP ε spent {meta['global_eps']}/{meta['epsilon_budget']} · audit tip {meta['audit_tip'][:12]}…")

    if args.save_model:
        with open(args.save_model, "w") as f:
            json.dump(meta, f)
        print(f"  saved model artifact -> {args.save_model}")

    if not (args.folder or args.data):
        if not args.save_model:
            print("Nothing to score (pass --folder or --data). Model downloaded only.")
        return

    X, y, groups = load_features(meta, folder=args.folder, data=args.data, modality=args.modality)
    if X.shape[0] == 0:
        sys.exit("no usable recordings found to score")
    if X.shape[1] != meta["n_features"]:
        sys.exit(f"feature mismatch: local {X.shape[1]} vs model {meta['n_features']} — check the modality")
    print(f"Scoring {X.shape[0]} local samples ({len(set(groups.tolist()))} recordings)…")

    classes = meta["classes"]
    if args.hosted:
        resp = cli.post("/predict", json={"X": X.tolist()}).json()
        if not resp.get("ok"):
            sys.exit(f"hosted predict failed: {resp.get('error')}")
        proba = np.asarray(resp["proba"], float)
        pred = resp["pred"]
        mode = "hosted (/predict)"
    else:
        gm = fc.GlobalModel.from_serialized(meta["model"])     # rebuild locally, run offline
        proba = gm.predict_proba(X)
        pred = [classes[i] for i in proba.argmax(1)]
        mode = "local (data-stays-local)"

    # per-recording aggregate (mean probability over that recording's windows)
    order, seen = [], set()
    for g in groups.tolist():
        if g not in seen:
            seen.add(g); order.append(g)
    print(f"Predictions ({mode}):")
    rows = []
    for g in order:
        sel = groups == g
        mp = proba[sel].mean(0)
        top = classes[int(mp.argmax())]
        conf = float(mp.max())
        truth = y[sel][0] if len(y[sel]) and y[sel][0] else ""
        rows.append({"recording": g, "prediction": top, "confidence": round(conf, 4),
                     **{f"p_{c}": round(float(mp[i]), 4) for i, c in enumerate(classes)},
                     "label": truth})
        mark = "" if not truth else (" ✓" if truth == top else " ✗")
        print(f"  {g:<40} -> {top:<5} ({conf:.2f}){(' [label ' + truth + ']' + mark) if truth else ''}")

    if any(rr["label"] for rr in rows):
        acc = np.mean([rr["prediction"] == rr["label"] for rr in rows if rr["label"]])
        print(f"Accuracy on labelled recordings: {acc:.3f} ({len(rows)} recordings)")

    if args.out:
        with open(args.out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
        print(f"Wrote {args.out}")
    cli.close()


if __name__ == "__main__":
    main()
