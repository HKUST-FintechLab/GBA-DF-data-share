"""Does the uploaded clips' FILENAME (hence their position in the sorted file list) matter?

'asd_01.npz' sorts before 'synthetic_*.npz' and re-rolls every later row's tree assignment;
'upload_asd_01.npz' sorts after it and perturbs nothing but the 11 added rows.
Same data, same nodes, same seeds — only the name differs.
"""
import json, os, sys
from concurrent.futures import ProcessPoolExecutor
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sim
from sweep2 import TRIPLES, DP_SEEDS
from sweep import ASD, TD, ALL, SPREAD11, spread, KEYS

REF = sim.CENTRAL


def assemble(per_class, node, clips=(), prefix=""):
    blocks = list(sim.CACHE["base"][(per_class, node)])
    for name in clips:
        cls, X, y = sim.CACHE["clips"][name]
        blocks.append((cls, prefix + name, X, y))
    blocks.sort(key=lambda b: (b[0], b[1]))
    return (np.vstack([b[2] for b in blocks]).astype(np.float32),
            np.concatenate([b[3] for b in blocks]))


ARMS = []
def arm(label, group, pc, assign, prefix):
    ARMS.append({"label": label, "group": group, "per_class": pc,
                 "assign": {int(k): list(v) for k, v in assign.items()}, "prefix": prefix,
                 "n_clips": sum(len(v) for v in assign.values())})


for pc in (20, 30):
    arm(f"base{pc} + 0", "baseline", pc, {}, "")
    for pref, tag in (("", "as-is names"), ("upload_", "renamed to sort last")):
        arm(f"base{pc} + 11 spread [{tag}]", "spread", pc, SPREAD11, pref)
        arm(f"base{pc} + 11 node_1 [{tag}]", "one node", pc, {1: ALL}, pref)
        arm(f"base{pc} + 6 ASD spread [{tag}]", "asd only", pc, spread(ASD), pref)
        arm(f"base{pc} + 6 spread [{tag}]", "dose 6", pc,
            spread(["asd_01.npz", "td_01.npz", "asd_02.npz", "td_02.npz",
                    "asd_03.npz", "td_03.npz"]), pref)
        arm(f"base{pc} + 3 spread [{tag}]", "dose 3", pc,
            {1: ["asd_01.npz"], 2: ["td_01.npz"], 3: ["asd_02.npz"]}, pref)
        arm(f"base{pc} + 1 node_1 [{tag}]", "dose 1", pc, {1: ["asd_01.npz"]}, pref)


def work(i):
    a = ARMS[i]
    nodes = [assemble(a["per_class"], n, a["assign"].get(n, []), a["prefix"]) for n in (1, 2, 3)]
    rows = []
    for tri in TRIPLES:
        for s in DP_SEEDS:
            m = sim.run(nodes, dp_seed=s, node_seeds=tri)[-1]
            rows.append({"tri": list(tri), "dp_seed": s, "final": {k: m.get(k) for k in KEYS}})
    return i, rows


if __name__ == "__main__":
    out = {}
    with ProcessPoolExecutor(max_workers=6) as ex:
        for i, rows in ex.map(work, range(len(ARMS))):
            out[ARMS[i]["label"]] = {"meta": ARMS[i], "runs": rows}
    json.dump(out, open(os.path.join(HERE, "sweep3.json"), "w"), indent=1)

    BASE = {20: "base20 + 0", 30: "base30 + 0"}
    print(f"{'arm':<44}{'(1,2,3)':>10}{'d123':>8}{'all 12 tri':>12}{'d_all':>8}"
          f"{'sd_d':>7}{'worst d':>9}{'>ref':>9}")
    for a in ARMS:
        lab = a["label"]
        runs = out[lab]["runs"]
        bruns = out[BASE[a["per_class"]]]["runs"]
        f123 = [r["final"]["auc"] for r in runs if tuple(r["tri"]) == (1, 2, 3)]
        b123 = [r["final"]["auc"] for r in bruns if tuple(r["tri"]) == (1, 2, 3)]
        ds = []
        for t in TRIPLES:
            v = np.mean([r["final"]["auc"] for r in runs if tuple(r["tri"]) == t])
            vb = np.mean([r["final"]["auc"] for r in bruns if tuple(r["tri"]) == t])
            ds.append(v - vb)
        allv = [r["final"]["auc"] for r in runs]
        above = sum(1 for r in runs if tuple(r["tri"]) == (1, 2, 3) and r["final"]["auc"] > REF)
        print(f"{lab:<44}{np.mean(f123):>10.3f}{np.mean(f123)-np.mean(b123):>+8.3f}"
              f"{np.mean(allv):>12.3f}{np.mean(ds):>+8.3f}{np.std(ds, ddof=1):>7.3f}"
              f"{min(ds):>+9.3f}{above:>6}/{len(f123)}")
