"""Offline replica of the coordinator's federated round loop.

Mirrors coordinator.py exactly for the secure-aggregation path:
  trees = dp.build_shared_structure(STRUCT_SEED + rd, ...)          (public, per round)
  per node: dp.count_on_shared(trees, X, y, CLASSES, seed*100 + rd) (integer leaf counts)
  summed   = plain sum of the count vectors (pairwise masks cancel exactly)
  forest   = dp.forest_from_summed_counts(trees, summed, CLASSES, EPS_ROUND, rng)
  model.add(forest, weight=total samples); metrics = model.evaluate(X_TEST, Y_TEST)

The only stochastic element per repeat is the curator's Laplace draw, which is what the
live harness randomises too (node assign seeds are fixed at 1/2/3 there).
"""
import os, pickle, sys
import numpy as np

HERE = r"D:\agent\dean\0803\datademo"
sys.path.insert(0, HERE)
SCRATCH = os.path.dirname(os.path.abspath(__file__))
_cwd = os.getcwd()
os.chdir(HERE)
import json
import dp as dpmod
import fed_common as fc
os.chdir(_cwd)

_t = np.load(os.path.join(HERE, "data", "test.npz"))
X_TEST, Y_TEST = _t["X"], _t["y"].astype(str)
META = json.load(open(os.path.join(HERE, "data", "meta.json"), encoding="utf-8"))
CLASSES = [str(c) for c in META["classes"]]
BOUNDS = np.asarray(META["feature_bounds"], float)
DP = META["dp"]
EPS_ROUND = float(DP["epsilon_per_round"])
N_TREES, DEPTH = int(DP["trees_per_round"]), int(DP["depth"])
STRUCT_SEED = int(DP.get("structure_seed", 2024))
N_FEATURES = int(X_TEST.shape[1])
CENTRAL = META["centralized"]["auc"]

with open(os.path.join(SCRATCH, "cache.pkl"), "rb") as f:
    CACHE = pickle.load(f)

_TREES = {rd: dpmod.build_shared_structure(STRUCT_SEED + rd, N_FEATURES, BOUNDS, DEPTH, N_TREES)
          for rd in range(1, 6)}


def assemble(per_class, node, clips=()):
    """X, y for one node folder = baseline files + named clips, in sorted-path order
    (ASD/ before TD/, and inside each class dir clip names sort before 'synthetic_')."""
    blocks = list(CACHE["base"][(per_class, node)])
    for name in clips:
        cls, X, y = CACHE["clips"][name]
        blocks.append((cls, name, X, y))
    blocks.sort(key=lambda b: (b[0], b[1]))
    X = np.vstack([b[2] for b in blocks]).astype(np.float32)
    y = np.concatenate([b[3] for b in blocks])
    return X, y


def run(nodes, dp_seed, node_seeds=(1, 2, 3), rounds=5):
    """nodes: list of (X, y). Returns list of per-round metric dicts."""
    model = fc.GlobalModel(CLASSES)
    total = float(sum(X.shape[0] for X, _ in nodes))
    rng = np.random.default_rng(dp_seed)
    out = []
    for rd in range(1, rounds + 1):
        trees = _TREES[rd]
        summed = None
        for (X, y), s in zip(nodes, node_seeds):
            flat = dpmod.flatten_counts(dpmod.count_on_shared(trees, X, y, CLASSES,
                                                              assign_seed=s * 100 + rd))
            summed = flat if summed is None else summed + flat
        fd = dpmod.forest_from_summed_counts(trees, summed, CLASSES, EPS_ROUND, rng)
        model.add(fc.JsonForest(fd), total, "secure-agg", rd)
        out.append(model.evaluate(X_TEST, Y_TEST))
    return out
