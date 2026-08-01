import json
import os
import numpy as np
from scipy import stats

ROOT = r"C:\Users\chenx\AppData\Local\Temp\claude\D--agent-dean-0803\66483c77-2328-4c98-ab4e-ba05cdf4c932\scratchpad\metric_exp"
METRICS = ["auc", "acc", "bacc", "sensitivity", "specificity", "precision",
           "f1", "mcc", "brier", "ece"]
rows = [json.loads(l) for l in open(os.path.join(ROOT, "results.jsonl"), encoding="utf-8") if l.strip()]
fin, rd1 = {}, {}
for r in rows:
    if r.get("ok"):
        fin.setdefault(r["arm"], {})[r["seed_base"]] = r["metrics"][-1]
        rd1.setdefault(r["arm"], {})[r["seed_base"]] = r["metrics"][0]
seeds = sorted(set(fin["A"]))

print("ARM C (ASD-only) vs ARM B (balanced), paired, n=%d" % len(seeds))
print(f"{'metric':<12}{'C-B':>9}{'t':>8}{'p':>9}{'C>B':>8}")
for m in METRICS:
    b = np.array([fin["B"][s][m] for s in seeds], float)
    c = np.array([fin["C"][s][m] for s in seeds], float)
    t, p = stats.ttest_rel(c, b)
    print(f"{m:<12}{(c-b).mean():>9.3f}{t:>8.2f}{p:>9.3f}{int((c>b).sum()):>5d}/{len(seeds)}")

print("\nROUND-1 (weakest model) A -> B and A -> D, paired")
print(f"{'metric':<12}{'Δ(B-A)':>9}{'p':>8}{'Δ(D-A)':>9}{'p':>8}")
for m in METRICS:
    a = np.array([rd1["A"][s][m] for s in seeds], float)
    b = np.array([rd1["B"][s][m] for s in seeds], float)
    d = np.array([rd1["D"][s][m] for s in seeds], float)
    _, pb = stats.ttest_rel(b, a)
    _, pd_ = stats.ttest_rel(d, a)
    print(f"{m:<12}{(b-a).mean():>9.3f}{pb:>8.3f}{(d-a).mean():>9.3f}{pd_:>8.3f}")

print("\nround-1 vs round-5 within-arm sd (arm A) — is early-round charting even stable?")
for m in ("auc", "bacc", "sensitivity"):
    a1 = np.array([rd1["A"][s][m] for s in seeds], float)
    a5 = np.array([fin["A"][s][m] for s in seeds], float)
    print(f"  {m:<12} r1 sd={a1.std(ddof=1):.3f}  r5 sd={a5.std(ddof=1):.3f}")
