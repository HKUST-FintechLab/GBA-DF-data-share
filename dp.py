"""Differential privacy for the federated forest — CENTRAL-DP (trusted-curator) model.

Why central-DP: if the node added the noise, the coordinator could never verify the
node used the right noise scale (epsilon would be self-declared and unenforceable).
So instead:
  * NODE  -> builds data-INDEPENDENT random trees (splits drawn from PUBLIC per-feature
    bounds) and ships INTEGER leaf class-histograms (`build_dp_counts`). No noise on the
    node; epsilon is not the node's to choose.
  * CURATOR (coordinator) -> adds Laplace(1/epsilon) to each leaf count with the
    federation's epsilon and meters the per-node budget (`add_dp_noise`). Epsilon is
    therefore ENFORCED by the coordinator, not trusted from the node.

Guarantee: each released node forest is (epsilon, 0)-DP. One record lands in exactly one
leaf per tree -> L1 sensitivity of a tree's count vector = 1 -> per-cell Laplace(1/epsilon)
is the Laplace mechanism. Records are partitioned disjointly across a node's trees ->
PARALLEL composition -> the forest costs epsilon (not epsilon*n_trees). Across rounds the
same data is reused -> SEQUENTIAL (basic) composition -> cumulative node epsilon = sum of
per-round epsilon (the ledger). Advanced/RDP accounting would be tighter (future work).

Trust model: the coordinator is the trusted curator (it adds the noise). Raw records never
leave the node — only data-independent-tree leaf aggregates do, over TLS, to the curator.
Local-DP (node-side noise, untrusted curator) and secure aggregation are future work.
"""
import numpy as np

from fed_common import JsonForest, TREE_LEAF


def build_random_structure(n_features, bounds, depth, rng):
    """Complete binary tree; internal nodes get a random split from PUBLIC bounds."""
    n_internal = 2 ** depth - 1
    n_nodes = 2 ** (depth + 1) - 1
    cl = [TREE_LEAF] * n_nodes
    cr = [TREE_LEAF] * n_nodes
    f = [-2] * n_nodes
    t = [-2.0] * n_nodes
    for i in range(n_internal):
        fi = int(rng.integers(0, n_features))
        lo, hi = bounds[fi]
        f[i] = fi
        t[i] = float(rng.uniform(lo, hi))
        cl[i] = 2 * i + 1
        cr[i] = 2 * i + 2
    return cl, cr, f, t


def _route(cl, cr, f, th, X):
    cl, cr, f, th = map(np.asarray, (cl, cr, f, th))
    n = X.shape[0]
    node = np.zeros(n, dtype=int)
    rows = np.arange(n)
    for _ in range(256):
        leaf = cl[node] == TREE_LEAF
        if leaf.all():
            break
        fi = np.where(f[node] < 0, 0, f[node])
        go_left = X[rows, fi] <= th[node]
        node = np.where(leaf, node, np.where(go_left, cl[node], cr[node]))
    return node


def build_dp_counts(X, y, classes, bounds, n_trees, depth, seed):
    """NODE side: data-independent structure + INTEGER leaf histograms (NO noise).
    Returns a 'count forest' {classes, trees:[{cl,cr,f,t,n}]} for the curator to privatise."""
    rng = np.random.default_rng(seed)
    classes = [str(c) for c in classes]
    cidx = {c: i for i, c in enumerate(classes)}
    C = len(classes)
    y = np.asarray(y).astype(str)
    n = X.shape[0]
    shards = np.array_split(rng.permutation(n), n_trees)   # disjoint -> parallel composition
    trees = []
    for sh in shards:
        cl, cr, f, t = build_random_structure(X.shape[1], bounds, depth, rng)
        counts = np.zeros((len(cl), C), dtype=int)
        if len(sh):
            for node_i, lab in zip(_route(cl, cr, f, t, X[sh]), y[sh]):
                counts[node_i, cidx[lab]] += 1
        trees.append({"cl": [int(x) for x in cl], "cr": [int(x) for x in cr],
                      "f": [int(x) for x in f], "t": [round(float(x), 6) for x in t],
                      "n": counts.tolist()})
    return {"classes": classes, "trees": trees}


def add_dp_noise(count_forest, epsilon, rng=None):
    """CURATOR side: Laplace(1/epsilon) on each leaf count, clamp, normalise -> a
    probability forest {classes, trees:[{cl,cr,f,t,v}]} consumable by JsonForest."""
    rng = rng or np.random.default_rng()
    out = []
    for t in count_forest["trees"]:
        nn = np.asarray(t["n"], dtype=float)
        noisy = np.clip(nn + rng.laplace(0.0, 1.0 / epsilon, size=nn.shape), 0.0, None)
        s = noisy.sum(axis=1, keepdims=True)
        s[s == 0] = 1.0
        v = noisy / s
        out.append({"cl": t["cl"], "cr": t["cr"], "f": t["f"], "t": t["t"],
                    "v": [[round(float(p), 5) for p in row] for row in v]})
    return {"classes": count_forest["classes"], "trees": out}


# ---------------- shared-forest path (for SECURE AGGREGATION) ----------------
# Every node builds the SAME trees from a PUBLIC structure_seed, so their per-leaf count
# vectors are aligned and can be securely summed; the coordinator adds the DP noise to the SUM.

def build_shared_structure(structure_seed, n_features, bounds, depth, n_trees):
    rng = np.random.default_rng(structure_seed)
    return [build_random_structure(n_features, bounds, depth, rng) for _ in range(n_trees)]


def count_on_shared(trees, X, y, classes, assign_seed):
    """Assign each record to ONE tree (disjoint -> sensitivity 1), route, integer counts.
    Returns a list of (n_nodes, C) int arrays, one per shared tree."""
    rng = np.random.default_rng(assign_seed)
    cidx = {c: i for i, c in enumerate(classes)}
    C = len(classes)
    y = np.asarray(y).astype(str)
    tree_of = rng.integers(0, len(trees), size=X.shape[0])
    out = []
    for ti, (cl, cr, f, t) in enumerate(trees):
        c = np.zeros((len(cl), C), dtype=np.int64)
        sel = np.where(tree_of == ti)[0]
        if len(sel):
            for li, lab in zip(_route(cl, cr, f, t, X[sel]), y[sel]):
                c[li, cidx[lab]] += 1
        out.append(c)
    return out


def flatten_counts(per_tree):
    return np.concatenate([c.reshape(-1) for c in per_tree]).astype(np.int64)


def forest_from_summed_counts(trees, flat_counts, classes, eps, rng=None):
    """CURATOR side: take the securely-summed integer leaf counts, add Laplace(1/eps),
    normalise, and assemble a probability forest for JsonForest."""
    rng = rng or np.random.default_rng()
    C = len(classes)
    out, off = [], 0
    for (cl, cr, f, t) in trees:
        m = len(cl)
        block = np.asarray(flat_counts[off:off + m * C], dtype=float).reshape(m, C)
        off += m * C
        noisy = np.clip(block + rng.laplace(0.0, 1.0 / eps, size=block.shape), 0.0, None)
        s = noisy.sum(axis=1, keepdims=True)
        s[s == 0] = 1.0
        v = noisy / s
        out.append({"cl": list(cl), "cr": list(cr), "f": list(f),
                    "t": [round(float(x), 6) for x in t],
                    "v": [[round(float(p), 5) for p in row] for row in v]})
    return {"classes": [str(c) for c in classes], "trees": out}


# ---------------- calibration (run directly) ----------------
if __name__ == "__main__":
    import argparse
    from sklearn.metrics import accuracy_score
    from sklearn.model_selection import StratifiedShuffleSplit
    import data_loaders

    ap = argparse.ArgumentParser()
    ap.add_argument("--nodes", type=int, default=3)
    ap.add_argument("--trees", type=int, default=20)
    ap.add_argument("--depth", type=int, default=9)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    X, y, _ = data_loaders.load("har")
    classes = sorted(np.unique(y).tolist())
    tr, te = next(StratifiedShuffleSplit(1, test_size=0.25, random_state=42).split(X, y))
    Xtr, ytr, Xte, yte = X[tr], y[tr], X[te], y[te]
    bounds = data_loaders.public_bounds("har", X.shape[1])   # PUBLIC, not derived from data
    rng = np.random.default_rng(args.seed)
    parts = np.array_split(rng.permutation(len(Xtr)), args.nodes)

    print(f"HAR {len(Xtr)}/{len(Xte)} · {args.nodes} nodes × {args.trees} trees(d{args.depth}) · public bounds")
    print(f"{'eps/round':>10} {'fed acc':>9}")
    for eps in [0.5, 1.0, 2.0, 5.0, 1e9]:
        gp = np.zeros((len(Xte), len(classes)))
        for ni, idx in enumerate(parts):
            cf = build_dp_counts(Xtr[idx], ytr[idx], classes, bounds, args.trees, args.depth,
                                 seed=args.seed * 10 + ni)
            fd = add_dp_noise(cf, eps, np.random.default_rng(args.seed * 7 + ni))
            gp += JsonForest(fd).predict_proba(Xte) * len(idx)
        pred = np.array([classes[i] for i in gp.argmax(1)])
        tag = "inf (no noise)" if eps > 1e8 else f"{eps:.1f}"
        print(f"{tag:>10} {accuracy_score(yte, pred):>9.3f}")
