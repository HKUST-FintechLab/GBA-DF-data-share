"""Is the drop caused by the clips' out-of-distribution features, or merely by WHERE the
clip files land in the sorted file list?

Inside a node folder modalities._list() sorts by path, so 'asd_01.npz' sorts BEFORE
'synthetic_*.npz' while 'td_01.npz' sorts AFTER it. dp.count_on_shared draws
rng.integers(0, 20, size=n_rows) and zips it against the rows in that order, so inserting
a file at the FRONT re-rolls which of the 20 shared trees every later row is counted into.

Three arms, all inserted at exactly the same sorted position with exactly the same names:
  clips     - the 6 real ASD clips                        (OOD data + re-roll)
  donor     - 6 ASD rows from an unrelated synthetic node (in-distribution data + re-roll)
  reorder   - 6 of the node's OWN ASD synthetic files, merely renamed so they sort first
              (IDENTICAL data, re-roll only)
"""
import os, pickle, shutil, sys, tempfile
from concurrent.futures import ProcessPoolExecutor
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, r"D:\agent\dean\0803\datademo")
import sim
from sweep2 import TRIPLES, DP_SEEDS

ASD_CLIPS = [f"asd_0{i}.npz" for i in range(1, 7)]
SPREAD6 = {1: ["asd_01.npz", "asd_04.npz"], 2: ["asd_02.npz", "asd_05.npz"],
           3: ["asd_03.npz", "asd_06.npz"]}

# donor blocks: 6 ASD synthetic files from unrelated nodes 4/5/6
_donor_cache = os.path.join(HERE, "donor_blocks.pkl")
if not os.path.exists(_donor_cache):
    import modalities as mods
    M = mods.get("action")
    tmp = tempfile.mkdtemp(prefix="donor-")
    blocks = {}
    for dn in (4, 5, 6):
        src = os.path.join(HERE, "donor", f"node_{dn}", "ASD")
        names = sorted(n for n in os.listdir(src) if n.endswith(".npz"))[:2]
        got = []
        for nm in names:
            work = os.path.join(tmp, "one", "ASD")
            shutil.rmtree(os.path.join(tmp, "one"), ignore_errors=True)
            os.makedirs(work, exist_ok=True)
            shutil.copy2(os.path.join(src, nm), os.path.join(work, nm))
            X, y, _ = M.extract_folder(os.path.join(tmp, "one"))
            got.append((np.asarray(X, np.float32), np.asarray(y).astype(str)))
        blocks[dn] = got
    shutil.rmtree(tmp, ignore_errors=True)
    pickle.dump(blocks, open(_donor_cache, "wb"))
DONOR = pickle.load(open(_donor_cache, "rb"))


def nodes_clips():
    return [sim.assemble(20, n, SPREAD6[n]) for n in (1, 2, 3)]


def nodes_donor():
    out = []
    for n in (1, 2, 3):
        blocks = list(sim.CACHE["base"][(20, n)])
        for i, (X, y) in enumerate(DONOR[n + 3]):
            blocks.append(("ASD", f"asd_0{i+1}.npz", X, y))
        blocks.sort(key=lambda b: (b[0], b[1]))
        out.append((np.vstack([b[2] for b in blocks]).astype(np.float32),
                    np.concatenate([b[3] for b in blocks])))
    return out


def nodes_reorder():
    """Same rows, same count — only two ASD files per node renamed so they sort first."""
    out = []
    for n in (1, 2, 3):
        blocks = list(sim.CACHE["base"][(20, n)])
        asd = [i for i, b in enumerate(blocks) if b[0] == "ASD"]
        for k, i in enumerate(asd[:2]):
            c, _nm, X, y = blocks[i]
            blocks[i] = (c, f"asd_0{k+1}.npz", X, y)
        blocks.sort(key=lambda b: (b[0], b[1]))
        out.append((np.vstack([b[2] for b in blocks]).astype(np.float32),
                    np.concatenate([b[3] for b in blocks])))
    return out


ARMS = {"base20 + 0 (no insert)": lambda: [sim.assemble(20, n) for n in (1, 2, 3)],
        "6 real ASD clips": nodes_clips,
        "6 donor SYNTHETIC rows": nodes_donor,
        "reorder only (same data)": nodes_reorder}


def work(label):
    nodes = ARMS[label]()
    rows = {}
    for tri in TRIPLES:
        rows[tri] = [sim.run(nodes, dp_seed=s, node_seeds=tri)[-1]["auc"] for s in DP_SEEDS]
    return label, rows


if __name__ == "__main__":
    res = {}
    with ProcessPoolExecutor(max_workers=4) as ex:
        for label, rows in ex.map(work, list(ARMS)):
            res[label] = rows
    base = res["base20 + 0 (no insert)"]
    print("final AUC per node-seed triple (mean over 20 DP seeds)")
    print("arm".ljust(26) + "".join(f"{str(t):>13}" for t in TRIPLES) + "     all")
    for label in ARMS:
        cells = [np.mean(res[label][t]) for t in TRIPLES]
        allv = np.concatenate([res[label][t] for t in TRIPLES])
        print(label.ljust(26) + "".join(f"{c:>13.3f}" for c in cells) + f"  {allv.mean():.3f}")
    print("\ndelta vs no-insert baseline")
    for label in ARMS:
        cells = [np.mean(res[label][t]) - np.mean(base[t]) for t in TRIPLES]
        print(label.ljust(26) + "".join(f"{c:>+13.3f}" for c in cells)
              + f"   mean {np.mean(cells):+.3f} sd {np.std(cells, ddof=1):.3f}")
