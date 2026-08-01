"""Same sweep, but each arm is sampled over BOTH sources of run randomness:
  * the node assign seeds (which of the 20 shared trees each row is counted into), and
  * the curator's Laplace draw.
Arms are paired cell-by-cell: every arm sees the identical (node_seed_triple, dp_seed) grid.

Sampling node seeds matters because inserting a clip file shifts every later row's
tree assignment, so a single fixed seed triple measures one draw of that lottery rather
than the effect of the data.
"""
import json, os, sys
from concurrent.futures import ProcessPoolExecutor
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sweep import ARMS as _A, spread, ASD, TD, ALL, SPREAD11, LOWSAT, KEYS  # noqa: E402

# 12 node-seed triples: the live paths use (1,2,3) (run_demo.py / verify_demo_run.py)
# and (1,1,1) (desktop client default), the rest probe the lottery.
TRIPLES = [(1, 2, 3), (1, 1, 1), (0, 0, 0), (0, 1, 2), (2, 3, 4), (5, 5, 5),
           (7, 8, 9), (11, 12, 13), (42, 43, 44), (101, 102, 103), (3, 1, 2), (23, 24, 25)]
DP_SEEDS = list(range(20))

KEEP = [
    "base20 + 0", "base30 + 0", "base40 + 0",
    "base20 + 1 (asd_01)", "base20 + 2 (1A+1T)", "base20 + 3 (2A+1T)",
    "base20 + 6 (3A+3T)", "base20 + 11 spread",
    "base20 + 11 all in node_1", "base20 + 6 all in node_1", "base20 + 3 all in node_1",
    "base30 + 11 spread", "base30 + 11 all in node_1",
    "base40 + 11 spread", "base40 + 11 all in node_1",
    "base20 + 6 ASD only", "base20 + 5 TD only", "base20 + 5A+5T balanced",
    "base20 + 6 ASD in node_1", "base20 + 5 TD in node_1",
    "base20 + 4 low-sat spread", "base20 + 4 low-sat node_1", "base30 + 4 low-sat node_1",
]
ARMS = [a for a in _A if a["label"] in KEEP]
assert len(ARMS) == len(KEEP), set(KEEP) - {a["label"] for a in ARMS}


def work(idx):
    import sim
    a = ARMS[idx]
    nodes = [sim.assemble(a["per_class"], n, a["assign"].get(n, [])) for n in (1, 2, 3)]
    rows = []
    for tri in TRIPLES:
        for s in DP_SEEDS:
            curve = sim.run(nodes, dp_seed=s, node_seeds=tri)
            rows.append({"tri": list(tri), "dp_seed": s,
                         "final": {k: curve[-1].get(k) for k in KEYS},
                         "auc_curve": [round(m["auc"], 4) for m in curve]})
    return idx, rows


if __name__ == "__main__":
    out = {}
    with ProcessPoolExecutor(max_workers=6) as ex:
        for idx, rows in ex.map(work, range(len(ARMS))):
            out[ARMS[idx]["label"]] = {"meta": ARMS[idx], "runs": rows}
            f = [r["final"]["auc"] for r in rows]
            print(f"{ARMS[idx]['label']:<30} {np.mean(f):.3f} +- {np.std(f, ddof=1):.3f}"
                  f"  above {sum(1 for v in f if v > 0.7782143947877431)}/{len(f)}", flush=True)
    json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "sweep2.json"), "w"), indent=1)
