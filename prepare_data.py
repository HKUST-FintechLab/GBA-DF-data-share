"""Build the POC dataset:
  - load a dataset (har | pose)
  - hold out a TEST set  -> kept ONLY by the coordinator (for evaluation)
  - partition the remaining data across N nodes -> each node's LOCAL data
  - train a centralized baseline on the POOLED training data (comparison only)

  uv run python prepare_data.py --dataset har --nodes 3 --total-trees 600
  uv run python prepare_data.py --dataset pose --nodes 3
"""
import argparse
import json
import os

import numpy as np
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.metrics import accuracy_score, balanced_accuracy_score, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit, StratifiedShuffleSplit

import data_loaders

HERE = os.path.dirname(os.path.abspath(__file__))
NODE_NAMES = [
    "HK Children's Hospital", "Shenzhen Partner Clinic", "NGO Screening Centre",
    "University Lab (partner group)", "Community Clinic",
]


def baseline_metrics(clf, Xte, yte, classes):
    proba = clf.predict_proba(Xte)
    pred = clf.predict(Xte)
    cols = {c: i for i, c in enumerate(clf.classes_)}
    P = np.zeros((len(yte), len(classes)))
    for i, c in enumerate(classes):
        if c in cols:
            P[:, i] = proba[:, cols[c]]
    try:
        if len(classes) == 2:
            auc = float(roc_auc_score((np.asarray(yte) == classes[1]).astype(int), P[:, 1]))
        else:
            auc = float(roc_auc_score(yte, P, multi_class="ovr", average="macro", labels=classes))
    except Exception:
        auc = float("nan")
    return {"acc": float(accuracy_score(yte, pred)),
            "bacc": float(balanced_accuracy_score(yte, pred)),
            "auc": auc}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", choices=["har", "pose"], default="har")
    ap.add_argument("--nodes", type=int, default=3)
    ap.add_argument("--test-frac", type=float, default=0.25)
    ap.add_argument("--total-trees", type=int, default=600)
    ap.add_argument("--min-leaf", type=int, default=5, help="match nodes; blunts leakage")
    ap.add_argument("--noniid", action="store_true", help="skew label mix across nodes")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    print(f"Loading dataset '{args.dataset}'…")
    X, y, groups = data_loaders.load(args.dataset)
    classes = sorted(np.unique(y).tolist())
    print(f"  {X.shape[0]} samples, {X.shape[1]} features, classes={classes}")

    # ---- hold-out test set ----
    if groups is not None:
        tr, te = next(GroupShuffleSplit(1, test_size=args.test_frac,
                                        random_state=args.seed).split(X, y, groups))
        split_kind = "subject-level (grouped)"
    else:
        tr, te = next(StratifiedShuffleSplit(1, test_size=args.test_frac,
                                             random_state=args.seed).split(X, y))
        split_kind = "stratified sample-level"
    Xtr, ytr = X[tr], y[tr]
    Xte, yte = X[te], y[te]
    gtr = groups[tr] if groups is not None else None
    print(f"  split: {split_kind} | train {len(tr)} | test {len(te)}")

    rng = np.random.default_rng(args.seed)

    # ---- partition train across nodes ----
    buckets = [[] for _ in range(args.nodes)]   # lists of TRAIN-relative indices
    if gtr is not None:
        subj = np.unique(gtr)
        per_class = {}
        for s in subj:
            lbl = ytr[np.where(gtr == s)[0][0]]
            per_class.setdefault(lbl, []).append(s)
        assign = {}
        for lbl, slist in per_class.items():
            slist = list(slist); rng.shuffle(slist)
            for i, s in enumerate(slist):
                assign[s] = i % args.nodes
        for i, s in enumerate(gtr):
            buckets[assign[s]].append(i)
    elif args.noniid:
        order = np.argsort(ytr, kind="stable")   # group by label, then shard contiguously
        shards = np.array_split(order, args.nodes * 2)
        rng.shuffle(shards)
        for i, sh in enumerate(shards):
            buckets[i % args.nodes].extend(sh.tolist())
    else:
        for lbl in classes:                      # IID: round-robin within each class
            idx = np.where(ytr == lbl)[0]; rng.shuffle(idx)
            for i, j in enumerate(idx):
                buckets[i % args.nodes].append(int(j))

    os.makedirs(os.path.join(HERE, "data"), exist_ok=True)
    np.savez_compressed(os.path.join(HERE, "data", "test.npz"), X=Xte, y=yte)

    meta_nodes = []
    for n in range(args.nodes):
        idx = np.array(sorted(buckets[n]), dtype=int)
        Xn, yn = Xtr[idx], ytr[idx]
        nd = os.path.join(HERE, "nodes", f"node_{n+1}")
        os.makedirs(nd, exist_ok=True)
        np.savez_compressed(os.path.join(nd, "data.npz"), X=Xn, y=yn)
        dist = {c: int((yn == c).sum()) for c in classes}   # printed only, NOT persisted
        name = NODE_NAMES[n % len(NODE_NAMES)]
        meta_nodes.append({"node_id": f"node_{n+1}", "name": name, "samples": int(Xn.shape[0])})
        print(f"  node_{n+1} [{name}]: {Xn.shape[0]} samples  {dist}")

    print(f"Training centralized baseline (ExtraTrees, {args.total_trees} trees)…")
    clf = ExtraTreesClassifier(n_estimators=args.total_trees, min_samples_leaf=args.min_leaf,
                               class_weight="balanced", random_state=args.seed, n_jobs=-1)
    clf.fit(Xtr, ytr)
    central = {**baseline_metrics(clf, Xte, yte, classes), "n_trees": args.total_trees}
    print(f"  centralized  acc {central['acc']:.3f} | auc {central['auc']:.3f} | "
          f"bacc {central['bacc']:.3f}")

    meta = {
        "dataset": args.dataset,
        "classes": classes,
        "primary_metric": "auc" if len(classes) == 2 else "acc",
        "split": split_kind,
        "partition": "subject-level" if gtr is not None else ("non-IID" if args.noniid else "IID"),
        "nodes": meta_nodes,
        "test_windows": int(Xte.shape[0]),
        "n_features": int(X.shape[1]),
        "centralized": central,
        "seed": args.seed,
    }
    with open(os.path.join(HERE, "data", "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    print("Wrote data/meta.json, data/test.npz, nodes/node_*/data.npz")


if __name__ == "__main__":
    main()
