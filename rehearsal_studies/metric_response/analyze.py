import json
import math
import os

import numpy as np

ROOT = r"C:\Users\chenx\AppData\Local\Temp\claude\D--agent-dean-0803\66483c77-2328-4c98-ab4e-ba05cdf4c932\scratchpad\metric_exp"
RES = os.path.join(ROOT, "results.jsonl")

METRICS = ["auc", "acc", "bacc", "sensitivity", "specificity",
           "precision", "f1", "mcc", "brier", "ece"]
HIGHER_BETTER = {m: True for m in METRICS}
HIGHER_BETTER["brier"] = False
HIGHER_BETTER["ece"] = False
ARMS = ["A", "B", "C", "D"]

rows = []
with open(RES, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            rows.append(json.loads(line))

bad = [r for r in rows if not r.get("ok")]
print(f"runs loaded: {len(rows)}   failed/incomplete: {len(bad)}")
for r in bad:
    print("  FAILED:", r.get("arm"), r.get("seed_base"), r.get("error"),
          r.get("n_rounds"), r.get("node_failures"))

data = {a: {} for a in ARMS}          # arm -> seed -> final-round metric dict
conf = {a: {} for a in ARMS}
for r in rows:
    if not r.get("ok"):
        continue
    fin = r["metrics"][-1]
    data[r["arm"]][r["seed_base"]] = {m: fin.get(m) for m in METRICS}
    conf[r["arm"]][r["seed_base"]] = fin.get("confusion")

seeds = sorted(set.intersection(*[set(data[a]) for a in ARMS]))
print(f"seeds complete in every arm: {len(seeds)} -> {seeds}\n")


def arr(arm, m):
    return np.array([data[arm][s][m] for s in seeds], float)


print("=" * 96)
print("PER-ARM FINAL-ROUND (round 5) MEAN +/- SD across repeats")
print("=" * 96)
hdr = f"{'metric':<12}" + "".join(f"{a:>21}" for a in ARMS)
print(hdr)
for m in METRICS:
    line = f"{m:<12}"
    for a in ARMS:
        v = arr(a, m)
        line += f"{v.mean():>12.3f} ±{v.std(ddof=1):<8.3f}"
    print(line)

print("\nconfusion (mean tn/fp/fn/tp):")
for a in ARMS:
    c = {k: np.mean([conf[a][s][k] for s in seeds]) for k in ("tn", "fp", "fn", "tp")}
    print(f"  {a}: tn={c['tn']:.1f} fp={c['fp']:.1f} fn={c['fn']:.1f} tp={c['tp']:.1f}")


def compare(x, y, label_from, label_to):
    """y - x, paired by seed."""
    print("\n" + "=" * 96)
    print(f"CHANGE {label_from} -> {label_to}   (paired by seed, n={len(seeds)})")
    print("=" * 96)
    print(f"{'metric':<12}{'mean Δ':>10}{'sd(within-arm)':>16}{'effect Δ/sd':>13}"
          f"{'sd(paired Δ)':>14}{'paired d':>10}{'t':>8}{'worse':>8}{'dir':>6}")
    out = []
    for m in METRICS:
        a = np.array([x[s][m] for s in seeds], float)
        b = np.array([y[s][m] for s in seeds], float)
        d = b - a
        sd_pool = math.sqrt((a.var(ddof=1) + b.var(ddof=1)) / 2)
        eff = d.mean() / sd_pool if sd_pool > 1e-12 else 0.0
        sd_d = d.std(ddof=1)
        eff_p = d.mean() / sd_d if sd_d > 1e-12 else 0.0
        t = d.mean() / (sd_d / math.sqrt(len(d))) if sd_d > 1e-12 else 0.0
        sign = 1.0 if HIGHER_BETTER[m] else -1.0
        worse = int((d * sign < -1e-12).sum())
        out.append((m, d.mean(), sd_pool, eff * sign, sd_d, eff_p * sign, t * sign, worse))
        print(f"{m:<12}{d.mean():>10.3f}{sd_pool:>16.3f}{eff*sign:>13.3f}"
              f"{sd_d:>14.3f}{eff_p*sign:>10.3f}{t*sign:>8.2f}{worse:>4d}/{len(seeds)}"
              f"{'  up=good' if HIGHER_BETTER[m] else '  dn=good':>6}")
    return out


ab = compare(data["A"], data["B"], "A (baseline)", "B (+11 clips)")
ac = compare(data["A"], data["C"], "A (baseline)", "C (+6 ASD only)")
ad = compare(data["A"], data["D"], "A (baseline)", "D (+22 clips)")

print("\n" + "=" * 96)
print("RANKED BY RELIABILITY OF IMPROVEMENT, A -> B  (signed so + = improvement)")
print("=" * 96)
print(f"{'rank':<6}{'metric':<12}{'effect (Δ/sd within-arm)':>26}{'paired effect':>16}{'|t|':>8}")
for i, r in enumerate(sorted(ab, key=lambda r: -r[3]), 1):
    print(f"{i:<6}{r[0]:<12}{r[3]:>26.3f}{r[5]:>16.3f}{abs(r[6]):>8.2f}")

# how often does adding clips hurt, overall
print("\n" + "=" * 96)
print("HOW OFTEN DOES ADDING CLIPS MAKE A METRIC WORSE (paired, per seed)")
print("=" * 96)
for label, other in (("B", "B"), ("C", "C"), ("D", "D")):
    tot = worse = 0
    for m in METRICS:
        a = np.array([data["A"][s][m] for s in seeds], float)
        b = np.array([data[other][s][m] for s in seeds], float)
        sign = 1.0 if HIGHER_BETTER[m] else -1.0
        d = (b - a) * sign
        worse += int((d < -1e-12).sum())
        tot += len(d)
    print(f"  A -> {label}: {worse}/{tot} metric-runs got worse "
          f"({100*worse/tot:.1f}%)")

# B vs C directly
print("\n" + "=" * 96)
print("ARM C (single-class) vs ARM B (balanced), paired")
print("=" * 96)
print(f"{'metric':<12}{'B-A':>10}{'C-A':>10}{'C-B':>10}{'sd(within)':>12}{'(C-B)/sd':>11}")
for m in METRICS:
    a = np.array([data["A"][s][m] for s in seeds], float)
    b = np.array([data["B"][s][m] for s in seeds], float)
    c = np.array([data["C"][s][m] for s in seeds], float)
    sd_pool = math.sqrt((b.var(ddof=1) + c.var(ddof=1)) / 2)
    e = (c - b).mean() / sd_pool if sd_pool > 1e-12 else 0.0
    print(f"{m:<12}{(b-a).mean():>10.3f}{(c-a).mean():>10.3f}{(c-b).mean():>10.3f}"
          f"{sd_pool:>12.3f}{e:>11.3f}")

# ------------------------------------------------------------------ per round
per_round = {a: {} for a in ARMS}     # arm -> round -> seed -> metric dict
for r in rows:
    if not r.get("ok"):
        continue
    for i, mrec in enumerate(r["metrics"]):
        per_round[r["arm"]].setdefault(i + 1, {})[r["seed_base"]] = mrec

print("\n" + "=" * 96)
print("PER-ROUND A -> B EFFECT  (paired Δ / within-arm sd, signed so + = improvement)")
print("=" * 96)
rounds = sorted(per_round["A"])
print(f"{'metric':<12}" + "".join(f"{'r'+str(rd):>11}" for rd in rounds))
for m in METRICS:
    line = f"{m:<12}"
    for rd in rounds:
        a = np.array([per_round["A"][rd][s][m] for s in seeds], float)
        b = np.array([per_round["B"][rd][s][m] for s in seeds], float)
        sd = math.sqrt((a.var(ddof=1) + b.var(ddof=1)) / 2)
        sign = 1.0 if HIGHER_BETTER[m] else -1.0
        line += f"{(b-a).mean()/sd*sign if sd > 1e-12 else 0.0:>11.3f}"
    print(line)

print("\nAUC mean by round (and paired A->B delta):")
for a in ARMS:
    s = f"  {a}: "
    for rd in rounds:
        v = np.array([per_round[a][rd][x]["auc"] for x in seeds], float)
        s += f"r{rd}={v.mean():.3f}±{v.std(ddof=1):.3f} "
    print(s)
s = "  Δ(B-A) auc: "
for rd in rounds:
    a = np.array([per_round["A"][rd][x]["auc"] for x in seeds], float)
    b = np.array([per_round["B"][rd][x]["auc"] for x in seeds], float)
    d = b - a
    t = d.mean() / (d.std(ddof=1) / math.sqrt(len(d)))
    s += f"r{rd}={d.mean():+.3f}(t={t:.2f}) "
print(s)
s = "  Δ(D-A) auc: "
for rd in rounds:
    a = np.array([per_round["A"][rd][x]["auc"] for x in seeds], float)
    b = np.array([per_round["D"][rd][x]["auc"] for x in seeds], float)
    d = b - a
    t = d.mean() / (d.std(ddof=1) / math.sqrt(len(d)))
    s += f"r{rd}={d.mean():+.3f}(t={t:.2f}) "
print(s)
