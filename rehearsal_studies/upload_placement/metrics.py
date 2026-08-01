"""Is AUC uniquely sensitive to the clips, or do the other headline metrics move too?"""
import json, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(HERE, "sweep2.json")))
KEYS = ["auc", "bacc", "sensitivity", "specificity", "precision", "acc", "brier"]
TRI123 = (1, 2, 3)


def pick(lab, tri=None):
    runs = D[lab]["runs"]
    if tri:
        runs = [r for r in runs if tuple(r["tri"]) == tri]
    return runs


def table(title, base, arm, tri):
    b = pick(base, tri)
    a = pick(arm, tri)
    print(f"\n{title}   (n={len(a)} runs each, paired)")
    print(f"  {'metric':<13}{'baseline':>18}{'with clips':>18}{'delta':>9}"
          f"{'delta/sd':>10}")
    for k in KEYS:
        vb = np.array([r["final"][k] for r in b], float)
        va = np.array([r["final"][k] for r in a], float)
        d = va.mean() - vb.mean()
        sd = vb.std(ddof=1)
        arrow = ""
        if k == "brier":
            arrow = "  (lower is better)"
        print(f"  {k:<13}{vb.mean():>11.3f} +-{sd:>5.3f}{va.mean():>11.3f} +-"
              f"{va.std(ddof=1):>5.3f}{d:>+9.3f}{d/max(sd,1e-9):>+10.1f}{arrow}")


table("A. the demo's actual seeds (1,2,3): base20+0 vs base20 + 11 spread",
      "base20 + 0", "base20 + 11 spread", TRI123)
table("B. pooled over all 12 node-seed triples: base20+0 vs base20 + 11 spread",
      "base20 + 0", "base20 + 11 spread", None)
table("C. the demo's actual seeds (1,2,3): base20+0 vs base20 + 11 all in node_1",
      "base20 + 0", "base20 + 11 all in node_1", TRI123)
table("D. the demo's actual seeds (1,2,3): base30+0 vs base30 + 11 all in node_1",
      "base30 + 0", "base30 + 11 all in node_1", TRI123)
