import json
import math
import os

import numpy as np
from scipy import stats

ROOT = r"C:\Users\chenx\AppData\Local\Temp\claude\D--agent-dean-0803\66483c77-2328-4c98-ab4e-ba05cdf4c932\scratchpad\metric_exp"
METRICS = ["auc", "acc", "bacc", "sensitivity", "specificity",
           "precision", "f1", "mcc", "brier", "ece"]
HB = {m: True for m in METRICS}
HB["brier"] = HB["ece"] = False
ARMS = ["A", "B", "C", "D"]

rows = [json.loads(l) for l in open(os.path.join(ROOT, "results.jsonl"), encoding="utf-8") if l.strip()]
data = {a: {} for a in ARMS}
for r in rows:
    if r.get("ok"):
        data[r["arm"]][r["seed_base"]] = {m: r["metrics"][-1].get(m) for m in METRICS}
seeds = sorted(set.intersection(*[set(data[a]) for a in ARMS]))
n = len(seeds)
print(f"n = {n} paired repeats per arm; {len(rows)} runs total, "
      f"{sum(1 for r in rows if not r.get('ok'))} failed\n")


def col(a, m):
    return np.array([data[a][s][m] for s in seeds], float)


print("NOISE FLOOR: within-arm sd of the final-round value (arm A, no clips)")
print(f"{'metric':<12}{'mean':>8}{'sd':>8}{'cv%':>8}{'sd/(range seen)':>18}")
for m in METRICS:
    v = col("A", m)
    print(f"{m:<12}{v.mean():>8.3f}{v.std(ddof=1):>8.3f}"
          f"{100*v.std(ddof=1)/max(abs(v.mean()),1e-9):>8.1f}"
          f"{v.max()-v.min():>18.3f}")

for arm in ("B", "C", "D"):
    print("\n" + "=" * 90)
    print(f"A -> {arm}: paired test, exact p, Bonferroni over 10 metrics")
    print("=" * 90)
    print(f"{'metric':<12}{'Δ':>9}{'95% CI':>20}{'d(paired)':>11}{'t':>8}"
          f"{'p':>9}{'p_bonf':>9}{'win rate':>10}")
    res = []
    for m in METRICS:
        a, b = col("A", m), col(arm, m)
        d = b - a
        sign = 1.0 if HB[m] else -1.0
        sd = d.std(ddof=1)
        t, p = stats.ttest_rel(b, a)
        se = sd / math.sqrt(n)
        crit = stats.t.ppf(0.975, n - 1)
        lo, hi = d.mean() - crit * se, d.mean() + crit * se
        win = int((d * sign > 1e-12).sum())
        res.append((m, d.mean() * sign, sign * d.mean() / sd if sd > 1e-12 else 0, p, win))
        print(f"{m:<12}{d.mean():>9.3f}  [{lo:>7.3f},{hi:>7.3f}]"
              f"{sign*d.mean()/sd if sd>1e-12 else 0:>11.3f}{sign*t:>8.2f}"
              f"{p:>9.3f}{min(1.0, p*10):>9.3f}{win:>7d}/{n}")
    best = max(res, key=lambda r: r[1] / 1.0)
    print(f"  -> largest improvement: {best[0]} Δ={best[1]:+.3f}, "
          f"smallest p = {min(r[3] for r in res):.3f} "
          f"(Bonferroni {min(1.0, 10*min(r[3] for r in res)):.3f})")

print("\n" + "=" * 90)
print("DOSE-RESPONSE of AUC (the only metric with a monotone trend)")
print("=" * 90)
for arm, added in (("A", 0), ("B", 11), ("C", 6), ("D", 22)):
    v = col(arm, "auc")
    print(f"  {arm} (+{added:>2} clip rows, {217+added} total rows): "
          f"auc = {v.mean():.3f} ± {v.std(ddof=1):.3f}   "
          f"[min {v.min():.3f}, max {v.max():.3f}]")
a, d_ = col("A", "auc"), col("D", "auc")
print(f"  A vs D: Δ={d_.mean()-a.mean():+.3f}, within-arm sd≈{a.std(ddof=1):.3f} "
      f"-> a single run's noise is {a.std(ddof=1)/max(d_.mean()-a.mean(),1e-9):.1f}x the effect")

print("\nHow many clips would be needed for +11 clips' AUC effect to clear 1 sd of noise?")
per_clip = (col("D", "auc").mean() - col("A", "auc").mean()) / 22
print(f"  observed AUC gain per added clip row ≈ {per_clip:+.5f}")
print(f"  1 within-arm sd of AUC = {col('A','auc').std(ddof=1):.3f} "
      f"-> needs ≈ {col('A','auc').std(ddof=1)/max(per_clip,1e-9):.0f} clip rows")
