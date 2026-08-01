"""Paired sweep over stagings using the offline replica. All arms share the same DP-noise
seeds and the same node assign seeds (1,2,3), so arms differ only in staging."""
import json, os, sys
from concurrent.futures import ProcessPoolExecutor
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ASD = [f"asd_0{i}.npz" for i in range(1, 7)]
TD = [f"td_0{i}.npz" for i in range(1, 6)]
ALL = ASD + TD
# verify_demo_run.py's spread: index within each class modulo 3
SPREAD11 = {1: ["asd_01.npz", "asd_04.npz", "td_01.npz", "td_04.npz"],
            2: ["asd_02.npz", "asd_05.npz", "td_02.npz", "td_05.npz"],
            3: ["asd_03.npz", "asd_06.npz", "td_03.npz"]}
LOWSAT = ["asd_02.npz", "td_02.npz", "td_03.npz", "td_04.npz"]   # |x|>=0.999 fraction < 0.20


def spread(names):
    a = {1: [], 2: [], 3: []}
    for i, n in enumerate(names):
        a[i % 3 + 1].append(n)
    return a


ARMS = []


def arm(label, group, per_class, assign):
    ARMS.append({"label": label, "group": group, "per_class": per_class,
                 "assign": {int(k): list(v) for k, v in assign.items()},
                 "n_clips": sum(len(v) for v in assign.values())})


# --- matched baselines -------------------------------------------------------
for pc in (20, 30, 40):
    arm(f"base{pc} + 0", "baseline", pc, {})

# --- 1 dose (per-class 20, spread across nodes) ------------------------------
arm("base20 + 1 (asd_01)", "dose", 20, {1: ["asd_01.npz"]})
arm("base20 + 2 (1A+1T)", "dose", 20, {1: ["asd_01.npz"], 2: ["td_01.npz"]})
arm("base20 + 3 (2A+1T)", "dose", 20, {1: ["asd_01.npz"], 2: ["td_01.npz"], 3: ["asd_02.npz"]})
arm("base20 + 6 (3A+3T)", "dose", 20, spread(["asd_01.npz", "td_01.npz", "asd_02.npz",
                                              "td_02.npz", "asd_03.npz", "td_03.npz"]))
arm("base20 + 11 spread", "dose", 20, SPREAD11)

# --- 2 concentration ---------------------------------------------------------
for n in (1, 2, 3):
    arm(f"base20 + 11 all in node_{n}", "concentration", 20, {n: ALL})
arm("base20 + 6 all in node_1", "concentration", 20,
    {1: ["asd_01.npz", "td_01.npz", "asd_02.npz", "td_02.npz", "asd_03.npz", "td_03.npz"]})
arm("base20 + 3 all in node_1", "concentration", 20,
    {1: ["asd_01.npz", "td_01.npz", "asd_02.npz"]})
arm("base20 + 1 in node_1", "concentration", 20, {1: ["asd_01.npz"]})

# --- 3 dilution --------------------------------------------------------------
for pc in (30, 40):
    arm(f"base{pc} + 11 spread", "dilution", pc, SPREAD11)
    arm(f"base{pc} + 11 all in node_1", "dilution", pc, {1: ALL})
    arm(f"base{pc} + 6 spread", "dilution", pc,
        spread(["asd_01.npz", "td_01.npz", "asd_02.npz", "td_02.npz", "asd_03.npz", "td_03.npz"]))

# --- 4 class balance of the upload (per-class 20) ----------------------------
arm("base20 + 6 ASD only", "balance", 20, spread(ASD))
arm("base20 + 5 TD only", "balance", 20, spread(TD))
arm("base20 + 5A+5T balanced", "balance", 20, spread(ASD[:5] + TD))
arm("base20 + 3A+3T balanced", "balance", 20, spread(ASD[:3] + TD[:3]))
arm("base20 + 6 ASD in node_1", "balance", 20, {1: ASD})
arm("base20 + 5 TD in node_1", "balance", 20, {1: TD})

# --- extra: screen the clips by saturation -----------------------------------
arm("base20 + 4 low-sat spread", "screen", 20, spread(LOWSAT))
arm("base20 + 4 low-sat node_1", "screen", 20, {1: LOWSAT})
arm("base30 + 4 low-sat node_1", "screen", 30, {1: LOWSAT})
arm("base20 + 2 low-sat node_1", "screen", 20, {1: ["asd_02.npz", "td_02.npz"]})

KEYS = ("auc", "bacc", "sensitivity", "specificity", "precision", "brier", "acc")


def work(args):
    idx, n_reps = args
    import sim
    a = ARMS[idx]
    nodes = [sim.assemble(a["per_class"], n, a["assign"].get(n, [])) for n in (1, 2, 3)]
    rows = []
    for s in range(n_reps):
        curve = sim.run(nodes, dp_seed=s)
        rows.append({"dp_seed": s,
                     "final": {k: curve[-1].get(k) for k in KEYS},
                     "auc_curve": [round(m["auc"], 4) for m in curve]})
    return idx, rows


if __name__ == "__main__":
    n_reps = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    out = {}
    with ProcessPoolExecutor(max_workers=10) as ex:
        for idx, rows in ex.map(work, [(i, n_reps) for i in range(len(ARMS))]):
            out[ARMS[idx]["label"]] = {"meta": ARMS[idx], "runs": rows}
            f = [r["final"]["auc"] for r in rows]
            print(f"{ARMS[idx]['label']:<32} {np.mean(f):.3f} +- {np.std(f, ddof=1):.3f}"
                  f"  {sum(1 for v in f if v > 0.7782143947877431)}/{len(f)}", flush=True)
    json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "sweep.json"), "w"), indent=1)
