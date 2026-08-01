"""High-n pass at the ONE node-seed triple the demo harness actually uses, (1,2,3).
200 DP-noise draws per arm, paired seed-for-seed across arms."""
import json, os, sys
from concurrent.futures import ProcessPoolExecutor
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sim
from sweep import ASD, TD, ALL, SPREAD11, LOWSAT, spread, KEYS
from sweep3 import assemble

TRI = (1, 2, 3)
NDP = 200
SIX = ["asd_01.npz", "td_01.npz", "asd_02.npz", "td_02.npz", "asd_03.npz", "td_03.npz"]

A = []
def arm(label, pc, assign, prefix=""):
    A.append((label, pc, {int(k): list(v) for k, v in assign.items()}, prefix))


arm("base20 + 0", 20, {})
arm("base20 + 1 (node_1)", 20, {1: ["asd_01.npz"]})
arm("base20 + 2 spread", 20, {1: ["asd_01.npz"], 2: ["td_01.npz"]})
arm("base20 + 3 spread", 20, {1: ["asd_01.npz"], 2: ["td_01.npz"], 3: ["asd_02.npz"]})
arm("base20 + 6 spread (3A+3T)", 20, spread(SIX))
arm("base20 + 11 spread", 20, SPREAD11)
arm("base20 + 11 node_1", 20, {1: ALL})
arm("base20 + 11 node_2", 20, {2: ALL})
arm("base20 + 11 node_3", 20, {3: ALL})
arm("base20 + 11 node_1 sort-last", 20, {1: ALL}, "upload_")
arm("base20 + 11 spread sort-last", 20, SPREAD11, "upload_")
arm("base20 + 6 ASD spread", 20, spread(ASD))
arm("base20 + 5 TD spread", 20, spread(TD))
arm("base20 + 5A+5T spread", 20, spread(ASD[:5] + TD))
arm("base20 + 6 ASD node_1", 20, {1: ASD})
arm("base20 + 5 TD node_1", 20, {1: TD})
arm("base20 + 4 low-sat node_1", 20, {1: LOWSAT})
arm("base30 + 0", 30, {})
arm("base30 + 11 spread", 30, SPREAD11)
arm("base30 + 11 node_1", 30, {1: ALL})
arm("base30 + 11 node_1 sort-last", 30, {1: ALL}, "upload_")
arm("base30 + 6 spread (3A+3T)", 30, spread(SIX))
arm("base40 + 0", 40, {})
arm("base40 + 11 spread", 40, SPREAD11)
arm("base40 + 11 node_1", 40, {1: ALL})
arm("base40 + 11 node_1 sort-last", 40, {1: ALL}, "upload_")


def work(i):
    label, pc, assign, prefix = A[i]
    nodes = [assemble(pc, n, assign.get(n, []), prefix) for n in (1, 2, 3)]
    rows = []
    for s in range(NDP):
        m = sim.run(nodes, dp_seed=s, node_seeds=TRI)[-1]
        rows.append({k: m.get(k) for k in KEYS})
    return i, rows


if __name__ == "__main__":
    out = {}
    with ProcessPoolExecutor(max_workers=4) as ex:
        for i, rows in ex.map(work, range(len(A))):
            out[A[i][0]] = {"per_class": A[i][1], "n_clips": sum(len(v) for v in A[i][2].values()),
                            "prefix": A[i][3], "runs": rows}
    json.dump(out, open(os.path.join(HERE, "focus.json"), "w"))
    REF = sim.CENTRAL
    BASE = {20: "base20 + 0", 30: "base30 + 0", 40: "base40 + 0"}
    print(f"node seeds (1,2,3) — the harness/run_demo configuration — {NDP} DP draws per arm")
    print(f"{'arm':<32}{'clips':>6}{'final AUC':>16}{'>0.778':>9}{'min':>8}"
          f"{'delta vs base':>15}{'paired sd':>11}{'worst run d':>13}")
    for label, pc, assign, prefix in A:
        v = np.array([r["auc"] for r in out[label]["runs"]], float)
        b = np.array([r["auc"] for r in out[BASE[pc]]["runs"]], float)
        d = v - b
        print(f"{label:<32}{out[label]['n_clips']:>6}"
              f"{v.mean():>10.3f} +-{v.std(ddof=1):>4.3f}{int((v > REF).sum()):>6}/{len(v)}"
              f"{v.min():>8.3f}{d.mean():>+15.3f}{d.std(ddof=1):>11.3f}{d.min():>+13.3f}")
