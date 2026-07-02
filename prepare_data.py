"""Build the POC dataset:
  - load a dataset — a benchmark (har | pose) OR a MODALITY (eyegaze | action | neuro)
  - hold out a TEST set  -> kept ONLY by the coordinator (for evaluation)
  - partition the remaining data across N nodes -> each node's LOCAL data
  - train a centralized baseline on the POOLED training data (comparison only)

  uv run python prepare_data.py --dataset har --nodes 3 --total-trees 600
  uv run python prepare_data.py --modality eyegaze --nodes 3
  uv run python prepare_data.py --modality neuro --nodes 3 --noniid

A modality run synthesizes realistic raw recordings, then extracts features through the
SAME front end (modalities.py) a real partner's folder would use — so the schema the
coordinator publishes is exactly what the desktop client will validate against.
"""
import argparse
import json
import os

import numpy as np
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.metrics import accuracy_score, balanced_accuracy_score, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit, StratifiedShuffleSplit

import data_loaders
import modalities

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
        if auc is not None and not np.isfinite(auc):
            auc = None
    except Exception:
        auc = None
    return {"acc": float(accuracy_score(yte, pred)),
            "bacc": float(balanced_accuracy_score(yte, pred)),
            "auc": auc}


def dp_metrics(fd, Xte, yte, classes):
    from fed_common import JsonForest
    proba = JsonForest(fd).predict_proba(Xte)
    pred = np.array([classes[i] for i in proba.argmax(1)])
    try:
        if len(classes) == 2:
            auc = float(roc_auc_score((np.asarray(yte) == classes[1]).astype(int), proba[:, 1]))
        else:
            auc = float(roc_auc_score(yte, proba, multi_class="ovr", average="macro", labels=classes))
        if auc is not None and not np.isfinite(auc):
            auc = None
    except Exception:
        auc = None
    return {"acc": float(accuracy_score(yte, pred)),
            "bacc": float(balanced_accuracy_score(yte, pred)), "auc": auc}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", choices=["har", "pose"], default="har",
                    help="benchmark dataset (ignored if --modality is given)")
    ap.add_argument("--modality", choices=list(modalities.MODALITIES), default=None,
                    help="signal modality: eyegaze | action | neuro (synthesizes a demo cohort)")
    ap.add_argument("--demo-n", type=int, default=150, help="synth recordings per class (modality)")
    ap.add_argument("--nodes", type=int, default=3)
    ap.add_argument("--test-frac", type=float, default=0.25)
    ap.add_argument("--total-trees", type=int, default=600)
    ap.add_argument("--min-leaf", type=int, default=5, help="match nodes; blunts leakage")
    ap.add_argument("--epsilon", type=float, default=1.0, help="DP epsilon per node per round")
    ap.add_argument("--dp-depth", type=int, default=None,
                    help="DP tree depth (default: 6 for a modality, 9 for HAR/pose benchmark)")
    ap.add_argument("--dp-trees", type=int, default=20, help="DP trees per node per round")
    ap.add_argument("--budget", type=float, default=10.0, help="per-node cumulative epsilon cap")
    ap.add_argument("--noniid", action="store_true", help="skew label mix across nodes")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    if args.dp_depth is None:
        args.dp_depth = 6 if args.modality else 9    # low-dim modalities: shallower = less DP noise

    if args.modality:
        m = modalities.get(args.modality)
        print(f"Modality '{args.modality}' ({m.en}) — synthesizing {args.demo_n}/class, "
              f"extracting features through {args.modality} front end…")
        X, y, groups = modalities.demo_dataset(args.modality, n_per_class=args.demo_n, seed=args.seed)
        ds_label = args.modality
        mod_info = m.info()
    else:
        print(f"Loading benchmark dataset '{args.dataset}'…")
        X, y, groups = data_loaders.load(args.dataset)
        ds_label = args.dataset
        mod_info = None
    y = np.asarray(y).astype(str)          # fixed-width unicode, not object -> npz needs no pickle
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

    print(f"Training NON-PRIVATE ceiling (ExtraTrees, {args.total_trees} trees)…")
    clf = ExtraTreesClassifier(n_estimators=args.total_trees, min_samples_leaf=args.min_leaf,
                               class_weight="balanced", random_state=args.seed, n_jobs=-1)
    clf.fit(Xtr, ytr)
    central_np = {**baseline_metrics(clf, Xte, yte, classes), "n_trees": args.total_trees}
    print(f"  non-private ceiling   acc {central_np['acc']:.3f} | auc {central_np['auc']:.3f}")

    # PUBLIC per-feature bounds (declared a-priori from the dataset's documented range) — DP splits
    # draw from these; they are NOT computed from participant data.
    bounds = (modalities.get(args.modality).bounds() if args.modality
              else data_loaders.public_bounds(args.dataset, X.shape[1]))

    print(f"Training centralized-DP reference (eps={args.epsilon}, depth {args.dp_depth})…")
    import dp as dpmod
    total_dp = args.nodes * args.dp_trees
    cf = dpmod.build_dp_counts(Xtr, ytr, classes, bounds, total_dp, args.dp_depth, seed=args.seed)
    fd = dpmod.add_dp_noise(cf, args.epsilon, np.random.default_rng(args.seed))
    central_dp = {**dp_metrics(fd, Xte, yte, classes), "n_trees": total_dp, "epsilon": args.epsilon}
    _au = central_dp["auc"]
    print(f"  centralized-DP        acc {central_dp['acc']:.3f} | auc {(f'{_au:.3f}' if _au is not None else 'n/a')}")

    meta = {
        "dataset": ds_label,
        "modality": args.modality,          # None for a plain benchmark run
        "modality_info": mod_info,          # {key, zh, en, task_zh, task_en, ...} or None
        "classes": classes,
        "primary_metric": "auc" if len(classes) == 2 else "acc",
        "split": split_kind,
        "partition": "subject-level" if gtr is not None else ("non-IID" if args.noniid else "IID"),
        "nodes": meta_nodes,
        "test_windows": int(Xte.shape[0]),
        "n_features": int(X.shape[1]),
        "feature_bounds": bounds.tolist(),
        "bounds_public": True,                 # declared a-priori, not derived from participant data
        "centralized": central_dp,             # centralized-DP reference (ε per the schema)
        "centralized_nonprivate": central_np,  # non-private ceiling, for context
        "dp": {"epsilon_per_round": args.epsilon, "depth": args.dp_depth,
               "trees_per_round": args.dp_trees, "budget": args.budget,
               "structure_seed": 2024},        # PUBLIC seed for the shared secure-agg forest
        "cohort": args.nodes,                   # secure aggregation needs all enrolled nodes per round
        "seed": args.seed,
    }
    with open(os.path.join(HERE, "data", "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    print("Wrote data/meta.json, data/test.npz, nodes/node_*/data.npz")


if __name__ == "__main__":
    main()
