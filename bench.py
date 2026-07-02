"""Robustness benchmark: federated-DP vs centralized-DP vs non-private ceiling,
over multiple seeds and BOTH IID and non-IID partitions, across an epsilon sweep.

Emits data/benchmark.json (mean +/- std) and data/epsilon_utility.png (the privacy dial).

  uv run python bench.py --seeds 5 --nodes 3
"""
import argparse
import json
import os

import numpy as np
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.metrics import accuracy_score
from sklearn.model_selection import StratifiedShuffleSplit

import data_loaders
import dp as dpmod
from fed_common import JsonForest

HERE = os.path.dirname(os.path.abspath(__file__))
EPS_GRID = [0.5, 1.0, 2.0, 5.0, 1e9]   # 1e9 == effectively no DP noise


def partition(y, n_nodes, mode, rng, alpha=0.4):
    """Return list of index arrays per node. iid = stratified round-robin;
    noniid = Dirichlet(alpha) label skew (standard FL non-IID)."""
    buckets = [[] for _ in range(n_nodes)]
    for lbl in np.unique(y):
        idx = np.where(y == lbl)[0]
        rng.shuffle(idx)
        if mode == "iid":
            for i, j in enumerate(idx):
                buckets[i % n_nodes].append(int(j))
        else:
            props = rng.dirichlet([alpha] * n_nodes)
            cuts = (np.cumsum(props)[:-1] * len(idx)).astype(int)
            for b, chunk in enumerate(np.split(idx, cuts)):
                buckets[b].extend(int(j) for j in chunk)
    return [np.array(sorted(b), dtype=int) for b in buckets]


def fed_dp_acc(Xtr, ytr, Xte, yte, classes, bounds, parts, n_trees, depth, eps, seed):
    gp = np.zeros((len(Xte), len(classes)))
    for ni, idx in enumerate(parts):
        if not len(idx):
            continue
        cf = dpmod.build_dp_counts(Xtr[idx], ytr[idx], classes, bounds, n_trees, depth, seed=seed * 13 + ni)
        fd = dpmod.add_dp_noise(cf, eps, np.random.default_rng(seed * 17 + ni))
        gp += JsonForest(fd).predict_proba(Xte) * len(idx)
    pred = np.array([classes[i] for i in gp.argmax(1)])
    return accuracy_score(yte, pred)


def secure_agg_acc(Xtr, ytr, Xte, yte, classes, bounds, parts, total_trees, depth, eps, seed):
    """Secure-aggregation flow: shared trees, sum node counts (masks cancel), central noise."""
    trees = dpmod.build_shared_structure(seed + 999, Xtr.shape[1], bounds, depth, total_trees)
    summed = None
    for ni, idx in enumerate(parts):
        if not len(idx):
            continue
        flat = dpmod.flatten_counts(dpmod.count_on_shared(trees, Xtr[idx], ytr[idx], classes, seed * 31 + ni))
        summed = flat if summed is None else summed + flat
    fd = dpmod.forest_from_summed_counts(trees, summed, classes, eps, np.random.default_rng(seed * 5 + 2))
    pred = np.array([classes[i] for i in JsonForest(fd).predict_proba(Xte).argmax(1)])
    return accuracy_score(yte, pred)


def central_dp_acc(Xtr, ytr, Xte, yte, classes, bounds, total_trees, depth, eps, seed):
    cf = dpmod.build_dp_counts(Xtr, ytr, classes, bounds, total_trees, depth, seed=seed)
    fd = dpmod.add_dp_noise(cf, eps, np.random.default_rng(seed * 3 + 1))
    pred = np.array([classes[i] for i in JsonForest(fd).predict_proba(Xte).argmax(1)])
    return accuracy_score(yte, pred)


def ms(vals):
    a = np.array(vals, dtype=float)
    return {"mean": round(float(a.mean()), 4), "std": round(float(a.std()), 4), "n": len(a)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="har")
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--nodes", type=int, default=3)
    ap.add_argument("--trees", type=int, default=20)
    ap.add_argument("--depth", type=int, default=9)
    args = ap.parse_args()

    X, y, _ = data_loaders.load(args.dataset)
    classes = sorted(np.unique(y).tolist())
    bounds = data_loaders.public_bounds(args.dataset, X.shape[1])
    total_trees = args.nodes * args.trees
    print(f"{args.dataset} · {args.seeds} seeds · {args.nodes} nodes × {args.trees} trees(d{args.depth})")

    central = {e: [] for e in EPS_GRID}
    fed = {"iid": {e: [] for e in EPS_GRID}, "noniid": {e: [] for e in EPS_GRID}}
    sagg = {"iid": {e: [] for e in EPS_GRID}, "noniid": {e: [] for e in EPS_GRID}}
    ceil_vals = []

    for s in range(args.seeds):
        tr, te = next(StratifiedShuffleSplit(1, test_size=0.25, random_state=s).split(X, y))
        Xtr, ytr, Xte, yte = X[tr], y[tr], X[te], y[te]
        clf = ExtraTreesClassifier(n_estimators=total_trees, min_samples_leaf=5,
                                   class_weight="balanced", random_state=s, n_jobs=-1).fit(Xtr, ytr)
        ceil_vals.append(accuracy_score(yte, clf.predict(Xte)))
        rng = np.random.default_rng(s)
        parts = {m: partition(ytr, args.nodes, m, rng) for m in ("iid", "noniid")}
        for e in EPS_GRID:
            central[e].append(central_dp_acc(Xtr, ytr, Xte, yte, classes, bounds, total_trees, args.depth, e, s))
            for m in ("iid", "noniid"):
                fed[m][e].append(fed_dp_acc(Xtr, ytr, Xte, yte, classes, bounds, parts[m],
                                            args.trees, args.depth, e, s))
                sagg[m][e].append(secure_agg_acc(Xtr, ytr, Xte, yte, classes, bounds, parts[m],
                                                  total_trees, args.depth, e, s))
        print(f"  seed {s}: ceiling {ceil_vals[-1]:.3f} | "
              f"fed-DP(ε=1,iid) {fed['iid'][1.0][-1]:.3f} | fed-DP(ε=1,non-iid) {fed['noniid'][1.0][-1]:.3f}")

    def lbl(e):
        return "inf" if e > 1e8 else str(e)
    result = {
        "dataset": args.dataset, "seeds": args.seeds, "nodes": args.nodes,
        "trees_per_node": args.trees, "depth": args.depth,
        "non_private_ceiling": ms(ceil_vals),
        "centralized_dp": {lbl(e): ms(central[e]) for e in EPS_GRID},
        "federated_ensemble_iid": {lbl(e): ms(fed["iid"][e]) for e in EPS_GRID},
        "federated_ensemble_noniid": {lbl(e): ms(fed["noniid"][e]) for e in EPS_GRID},
        "federated_secureagg_iid": {lbl(e): ms(sagg["iid"][e]) for e in EPS_GRID},
        "federated_secureagg_noniid": {lbl(e): ms(sagg["noniid"][e]) for e in EPS_GRID},
    }
    with open(os.path.join(HERE, "data", "benchmark.json"), "w") as f:
        json.dump(result, f, indent=2)

    print("\n=== mean ± std over seeds ===")
    print(f"non-private ceiling: {result['non_private_ceiling']['mean']:.3f} ± {result['non_private_ceiling']['std']:.3f}")
    print(f"{'eps':>5} {'central':>11} {'ens-IID':>11} {'ens-nonIID':>12} {'secAgg-nonIID':>14}")
    for e in EPS_GRID:
        c, fi, fn, sn = central[e], fed["iid"][e], fed["noniid"][e], sagg["noniid"][e]
        print(f"{lbl(e):>5} {np.mean(c):>6.3f}±{np.std(c):.2f} {np.mean(fi):>6.3f}±{np.std(fi):.2f} "
              f"{np.mean(fn):>7.3f}±{np.std(fn):.2f} {np.mean(sn):>9.3f}±{np.std(sn):.2f}")

    make_figure(result)
    print("\nWrote data/benchmark.json and data/epsilon_utility.png")


def make_figure(r):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    eps = [0.5, 1.0, 2.0, 5.0]
    x = list(range(len(eps)))
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11})
    fig, ax = plt.subplots(figsize=(6.6, 4.2), dpi=150)

    def series(d, color, label, marker):
        m = [d[str(e)]["mean"] for e in eps]
        s = [d[str(e)]["std"] for e in eps]
        ax.plot(x, m, marker=marker, color=color, label=label, lw=2)
        ax.fill_between(x, np.array(m) - np.array(s), np.array(m) + np.array(s), color=color, alpha=0.15)

    series(r["centralized_dp"], "#2e7d6b", "Centralized-DP", "^")
    series(r["federated_ensemble_iid"], "#d97757", "Fed ensemble (IID)", "o")
    series(r["federated_ensemble_noniid"], "#c2683f", "Fed ensemble (non-IID) — collapses", "s")
    series(r["federated_secureagg_noniid"], "#6a9ccd", "Fed secure-agg (non-IID) — recovers", "D")
    ceil = r["non_private_ceiling"]["mean"]
    ax.axhline(ceil, ls="--", color="#867f74", lw=1.6, label=f"Non-private ceiling ({ceil:.2f})")

    ax.set_xticks(x); ax.set_xticklabels([f"ε={e}" for e in eps])
    ax.set_ylabel("Test accuracy"); ax.set_ylim(0.45, 1.0)
    ax.set_title(f"Privacy–utility tradeoff · {r['dataset'].upper()} · "
                 f"{r['nodes']} nodes · {r['seeds']} seeds (mean ± std)")
    ax.legend(loc="lower right", fontsize=9, framealpha=0.95)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "data", "epsilon_utility.png"))


if __name__ == "__main__":
    main()
