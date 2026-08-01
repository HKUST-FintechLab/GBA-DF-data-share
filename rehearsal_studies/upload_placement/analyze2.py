import json, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(HERE, "sweep2.json")))
REF = 0.7782143947877431
labels = list(D)
tris = [tuple(r["tri"]) for r in D[labels[0]]["runs"]]
TRIS = sorted(set(tris), key=lambda t: [tuple(r["tri"]) for r in D[labels[0]]["runs"]].index(t))

print("final AUC per node-seed triple (mean over 20 DP seeds)")
head = "arm".ljust(30) + "".join(f"{str(t):>13}" for t in TRIS)
print(head)
for lab in labels:
    runs = D[lab]["runs"]
    cells = []
    for t in TRIS:
        v = [r["final"]["auc"] for r in runs if tuple(r["tri"]) == t]
        cells.append(np.mean(v))
    print(lab.ljust(30) + "".join(f"{c:>13.3f}" for c in cells))

print("\ndelta vs matched baseline, per triple")
BASE = {20: "base20 + 0", 30: "base30 + 0", 40: "base40 + 0"}
print(head)
for lab in labels:
    pc = D[lab]["meta"]["per_class"]
    b = D[BASE[pc]]["runs"]
    runs = D[lab]["runs"]
    cells = []
    for t in TRIS:
        v = np.mean([r["final"]["auc"] for r in runs if tuple(r["tri"]) == t])
        vb = np.mean([r["final"]["auc"] for r in b if tuple(r["tri"]) == t])
        cells.append(v - vb)
    print(lab.ljust(30) + "".join(f"{c:>+13.3f}" for c in cells))
