"""Null distribution for "insert 6 ASD rows at the front of each node", at the ONE node-seed
triple the demo harness actually uses, (1,2,3).

Two nulls, both leaving the data in-distribution:
  donor_k   - 6 ASD rows taken from unrelated synthetic nodes 4/5/6 (24 different draws)
  reorder_k - the node's OWN rows, 2 ASD files per node renamed so they sort first
              (24 different choices; IDENTICAL data, only the order changes)
The real-clip arm is scored against those.
"""
import os, pickle, shutil, sys, tempfile
from concurrent.futures import ProcessPoolExecutor
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, r"D:\agent\dean\0803\datademo")
import sim

TRI = (1, 2, 3)
DP_SEEDS = list(range(20))
SPREAD6 = {1: ["asd_01.npz", "asd_04.npz"], 2: ["asd_02.npz", "asd_05.npz"],
           3: ["asd_03.npz", "asd_06.npz"]}
CACHE_P = os.path.join(HERE, "donor_all.pkl")

if not os.path.exists(CACHE_P):
    import modalities as mods
    M = mods.get("action")
    tmp = tempfile.mkdtemp(prefix="donorall-")
    blocks = {}
    for dn in (4, 5, 6):
        src = os.path.join(HERE, "donor", f"node_{dn}", "ASD")
        got = []
        for nm in sorted(n for n in os.listdir(src) if n.endswith(".npz")):
            work = os.path.join(tmp, "one", "ASD")
            shutil.rmtree(os.path.join(tmp, "one"), ignore_errors=True)
            os.makedirs(work, exist_ok=True)
            shutil.copy2(os.path.join(src, nm), os.path.join(work, nm))
            X, y, _ = M.extract_folder(os.path.join(tmp, "one"))
            got.append((np.asarray(X, np.float32), np.asarray(y).astype(str)))
        blocks[dn] = got
    shutil.rmtree(tmp, ignore_errors=True)
    pickle.dump(blocks, open(CACHE_P, "wb"))
DONOR = pickle.load(open(CACHE_P, "rb"))


def _finish(blocks):
    blocks = sorted(blocks, key=lambda b: (b[0], b[1]))
    return (np.vstack([b[2] for b in blocks]).astype(np.float32),
            np.concatenate([b[3] for b in blocks]))


def nodes_donor(k):
    rng = np.random.default_rng(1000 + k)
    out = []
    for n in (1, 2, 3):
        blocks = list(sim.CACHE["base"][(20, n)])
        pool = DONOR[n + 3]
        pick = rng.choice(len(pool), size=2, replace=False)
        for i, p in enumerate(pick):
            X, y = pool[p]
            blocks.append(("ASD", f"asd_0{i+1}.npz", X, y))
        out.append(_finish(blocks))
    return out


def nodes_reorder(k):
    rng = np.random.default_rng(2000 + k)
    out = []
    for n in (1, 2, 3):
        blocks = list(sim.CACHE["base"][(20, n)])
        asd = [i for i, b in enumerate(blocks) if b[0] == "ASD"]
        pick = rng.choice(asd, size=2, replace=False)
        for i, idx in enumerate(sorted(pick)):
            c, _nm, X, y = blocks[idx]
            blocks[idx] = (c, f"asd_0{i+1}.npz", X, y)
        out.append(_finish(blocks))
    return out


def job(spec):
    kind, k = spec
    if kind == "donor":
        nodes = nodes_donor(k)
    elif kind == "reorder":
        nodes = nodes_reorder(k)
    elif kind == "clips":
        nodes = [sim.assemble(20, n, SPREAD6[n]) for n in (1, 2, 3)]
    else:
        nodes = [sim.assemble(20, n) for n in (1, 2, 3)]
    return kind, k, [sim.run(nodes, dp_seed=s, node_seeds=TRI)[-1]["auc"] for s in DP_SEEDS]


if __name__ == "__main__":
    K = 24
    specs = [("base", 0), ("clips", 0)] + [("donor", k) for k in range(K)] \
        + [("reorder", k) for k in range(K)]
    res = {}
    with ProcessPoolExecutor(max_workers=6) as ex:
        for kind, k, v in ex.map(job, specs):
            res.setdefault(kind, {})[k] = float(np.mean(v))
    base = res["base"][0]
    clip = res["clips"][0]
    print(f"node seeds {TRI}, 20 DP seeds per point, per-class-20 baseline")
    print(f"  no insert                : {base:.3f}")
    print(f"  6 REAL ASD clips inserted: {clip:.3f}   delta {clip-base:+.3f}")
    for kind in ("donor", "reorder"):
        vals = np.array([res[kind][k] for k in range(K)])
        d = vals - base
        worse = int((vals <= clip).sum())
        print(f"\n  null '{kind}' ({K} draws): mean {vals.mean():.3f}  sd {vals.std(ddof=1):.3f}"
              f"  range {vals.min():.3f}..{vals.max():.3f}")
        print(f"    deltas: mean {d.mean():+.3f}  range {d.min():+.3f}..{d.max():+.3f}")
        print(f"    draws at or below the real-clip arm: {worse}/{K}"
              f"  -> one-sided p = {(worse+1)/(K+1):.3f}")
        print("    sorted deltas: " + " ".join(f"{v:+.3f}" for v in np.sort(d)))
