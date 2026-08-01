"""Robustness of each candidate to the node-seed lottery (12 triples x 20 DP draws)."""
import json, os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REF = 0.7782143947877431
S2 = json.load(open(os.path.join(HERE, "sweep2.json")))
S3 = json.load(open(os.path.join(HERE, "sweep3.json")))
TRIS = [(1, 2, 3), (1, 1, 1), (0, 0, 0), (0, 1, 2), (2, 3, 4), (5, 5, 5),
        (7, 8, 9), (11, 12, 13), (42, 43, 44), (101, 102, 103), (3, 1, 2), (23, 24, 25)]
BASE = {20: "base20 + 0", 30: "base30 + 0", 40: "base40 + 0"}

WANT = [(S2, "base20 + 0"), (S2, "base20 + 11 spread"), (S2, "base20 + 11 all in node_1"),
        (S3, "base20 + 11 node_1 [renamed to sort last]"),
        (S2, "base20 + 6 ASD only"), (S2, "base20 + 5 TD only"),
        (S2, "base30 + 0"), (S2, "base30 + 11 spread"), (S2, "base30 + 11 all in node_1"),
        (S3, "base30 + 11 node_1 [renamed to sort last]"),
        (S2, "base40 + 0"), (S2, "base40 + 11 spread"), (S2, "base40 + 11 all in node_1")]

print(f"{'arm':<44}{'AUC (240 runs)':>18}{'>ref':>9}{'d mean':>9}{'d sd':>7}"
      f"{'worst tri d':>13}")
for src, lab in WANT:
    runs = src[lab]["runs"]
    pc = src[lab]["meta"]["per_class"]
    b = (S2 if BASE[pc] in S2 else S3)[BASE[pc]]["runs"]
    v = np.array([r["final"]["auc"] for r in runs], float)
    ds = []
    for t in TRIS:
        ds.append(np.mean([r["final"]["auc"] for r in runs if tuple(r["tri"]) == t])
                  - np.mean([r["final"]["auc"] for r in b if tuple(r["tri"]) == t]))
    print(f"{lab:<44}{v.mean():>11.3f} +-{v.std(ddof=1):>5.3f}{int((v > REF).sum()):>6}/{len(v)}"
          f"{np.mean(ds):>+9.3f}{np.std(ds, ddof=1):>7.3f}{min(ds):>+13.3f}")
