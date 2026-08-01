"""Stability analysis of coordinator-reported metrics across 3 stagings x N federations."""
import glob
import json
import math
import os
import statistics as st

WORK = os.path.dirname(os.path.abspath(__file__))
METRICS = ["auc", "acc", "bacc", "sensitivity", "specificity", "precision",
           "f1", "mcc", "brier", "ece"]
COUNTS = ["tn", "fp", "fn", "tp"]
STAGINGS = [10, 20, 30]


def load():
    runs = []
    for path in sorted(glob.glob(os.path.join(WORK, "res_pc*.jsonl"))):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line:
                runs.append(json.loads(line))
    return runs


def sd(xs):
    return st.stdev(xs) if len(xs) > 1 else float("nan")


def cv(xs):
    m = st.mean(xs)
    return sd(xs) / abs(m) * 100 if m else float("nan")


def pearson(a, b):
    n = len(a)
    if n < 3:
        return float("nan")
    ma, mb = st.mean(a), st.mean(b)
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((x - mb) ** 2 for x in b)
    if va <= 1e-15 or vb <= 1e-15:
        return float("nan")
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(va * vb)


def fmt(v, d=3):
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "  n/a"
    return f"{v:.{d}f}"


def main():
    runs = load()
    ok = [r for r in runs if r.get("ok")]
    bad = [r for r in runs if not r.get("ok")]
    print(f"runs collected: {len(runs)}   usable: {len(ok)}   failed: {len(bad)}")
    for r in bad:
        print(f"  FAILED pc{r['per_class']} rep{r['repeat']}: "
              f"{r.get('error', 'incomplete')} rounds={len(r.get('rounds', []))} "
              f"rcs={r.get('node_returncodes')}")
    by = {pc: [r for r in ok if r["per_class"] == pc] for pc in STAGINGS}
    for pc in STAGINGS:
        print(f"  per-class {pc}: n={len(by[pc])} runs, "
              f"median wall {st.median([r['secs'] for r in by[pc]]):.0f}s")

    def final(r, k):
        return r["rounds"][-1][k]

    # ---------- 1. final-round dispersion per staging ----------
    print("\n\n=== 1. FINAL-ROUND (round 5) RUN-TO-RUN DISPERSION, per staging ===")
    hdr = f"{'metric':<12}"
    for pc in STAGINGS:
        hdr += f"| pc{pc}: mean    sd     CV%   "
    print(hdr)
    print("-" * len(hdr))
    cvtab = {}
    for k in METRICS + COUNTS:
        line = f"{k:<12}"
        for pc in STAGINGS:
            xs = [final(r, k) for r in by[pc]]
            xs = [float(x) for x in xs if x is not None]
            c = cv(xs)
            cvtab.setdefault(k, {})[pc] = c
            line += f"| {fmt(st.mean(xs)):>6} {fmt(sd(xs)):>6} {fmt(c,1):>6}   "
        print(line)

    print("\n--- ranking by CV% at each staging (1 = most stable) ---")
    ranks = {}
    for pc in STAGINGS:
        order = sorted(METRICS, key=lambda k: (math.inf if not math.isfinite(cvtab[k][pc])
                                               else cvtab[k][pc]))
        for i, k in enumerate(order, 1):
            ranks.setdefault(k, {})[pc] = i
        print(f"  pc{pc}: " + " < ".join(f"{k}({fmt(cvtab[k][pc],1)})" for k in order))
    print(f"\n{'metric':<12} {'rank10':>7} {'rank20':>7} {'rank30':>7} {'spread':>7} "
          f"{'CVmin':>7} {'CVmax':>7} {'CVmax/CVmin':>12}")
    for k in sorted(METRICS, key=lambda k: st.mean([ranks[k][p] for p in STAGINGS])):
        rs = [ranks[k][p] for p in STAGINGS]
        cs = [cvtab[k][p] for p in STAGINGS if math.isfinite(cvtab[k][p])]
        ratio = max(cs) / min(cs) if cs and min(cs) > 0 else float("nan")
        print(f"{k:<12} {rs[0]:>7} {rs[1]:>7} {rs[2]:>7} {max(rs)-min(rs):>7} "
              f"{fmt(min(cs),1):>7} {fmt(max(cs),1):>7} {fmt(ratio,1):>12}")

    # absolute sd, staging-consistency of sd
    print("\n--- absolute SD (units of the metric) per staging ---")
    print(f"{'metric':<12} " + " ".join(f"{'sd_pc'+str(p):>9}" for p in STAGINGS) +
          f" {'max/min':>9}")
    for k in METRICS:
        sds = []
        for pc in STAGINGS:
            xs = [float(final(r, k)) for r in by[pc]]
            sds.append(sd(xs))
        ratio = max(sds) / min(sds) if min(sds) > 0 else float("nan")
        print(f"{k:<12} " + " ".join(f"{fmt(s):>9}" for s in sds) + f" {fmt(ratio,1):>9}")

    # ---------- 2. within-run shape ----------
    print("\n\n=== 2. WITHIN-RUN BEHAVIOUR ACROSS ROUNDS ===")
    print("r5<r3 = runs whose round-5 value is worse than round-3 (for brier/ece 'worse' = higher)")
    LOWER_BETTER = {"brier", "ece"}
    print(f"{'metric':<12} {'r1mean':>7} {'r3mean':>7} {'r5mean':>7} {'rise r1->r5':>12} "
          f"{'r5<r3 (n/48)':>13} {'r5 worse r3':>12} {'mean |Δ| per round':>19} {'sign flips':>11}")
    for k in METRICS:
        allruns = ok
        r1 = st.mean([r["rounds"][0][k] for r in allruns])
        r3 = st.mean([r["rounds"][2][k] for r in allruns])
        r5 = st.mean([r["rounds"][4][k] for r in allruns])
        below = sum(1 for r in allruns if r["rounds"][4][k] < r["rounds"][2][k])
        worse = sum(1 for r in allruns
                    if (r["rounds"][4][k] > r["rounds"][2][k]) if k in LOWER_BETTER) or below
        if k in LOWER_BETTER:
            worse = sum(1 for r in allruns if r["rounds"][4][k] > r["rounds"][2][k])
        steps = []
        flips = 0
        for r in allruns:
            v = [r["rounds"][i][k] for i in range(5)]
            d = [v[i + 1] - v[i] for i in range(4)]
            steps.extend(abs(x) for x in d)
            flips += sum(1 for i in range(3)
                         if d[i] * d[i + 1] < 0 and abs(d[i]) > 1e-9 and abs(d[i + 1]) > 1e-9)
        print(f"{k:<12} {fmt(r1):>7} {fmt(r3):>7} {fmt(r5):>7} {fmt(r5-r1):>12} "
              f"{below:>13} {worse:>12} {fmt(st.mean(steps)):>19} "
              f"{fmt(flips/len(allruns),2):>11}")

    print("\n--- per staging: fraction of runs with round-5 below round-3 ---")
    print(f"{'metric':<12} " + " ".join(f"{'pc'+str(p):>10}" for p in STAGINGS))
    for k in METRICS:
        cells = []
        for pc in STAGINGS:
            n = len(by[pc])
            b = sum(1 for r in by[pc] if r["rounds"][4][k] < r["rounds"][2][k])
            cells.append(f"{b}/{n}")
        print(f"{k:<12} " + " ".join(f"{c:>10}" for c in cells))

    print("\n--- projector view: does the curve visibly rise, and how far does it fall back? ---")
    print("oriented so 'up' = better (brier/ece negated). dip = a round-to-round fall > 0.010")
    print(f"{'metric':<12} {'rise r1->r5':>11} {'rise/sd_run':>12} {'r5>r1':>8} "
          f"{'runs w/ >=1 dip':>15} {'dips per run':>13} {'max drawdown':>13} "
          f"{'drawdown/sd':>12}")
    for k in METRICS:
        s = -1.0 if k in LOWER_BETTER else 1.0
        sdrun = st.mean([sd([float(final(r, k)) for r in by[pc]]) for pc in STAGINGS])
        rises, dipruns, dips, dds = [], 0, 0, []
        up = 0
        for r in ok:
            v = [s * r["rounds"][i][k] for i in range(5)]
            rises.append(v[4] - v[0])
            up += v[4] > v[0]
            d = [v[i + 1] - v[i] for i in range(4)]
            nd = sum(1 for x in d if x < -0.010)
            dips += nd
            dipruns += nd > 0
            peak, dd = v[0], 0.0
            for x in v:
                peak = max(peak, x)
                dd = max(dd, peak - x)
            dds.append(dd)
        mr = st.mean(rises)
        mdd = st.mean(dds)
        print(f"{k:<12} {fmt(mr):>11} {fmt(mr/sdrun,1):>12} {up:>4}/{len(ok):<3} "
              f"{dipruns:>12}/{len(ok):<2} {fmt(dips/len(ok),2):>13} {fmt(mdd):>13} "
              f"{fmt(mdd/sdrun,1):>12}")

    # ---------- 3. correlation across runs (final round, pooled within staging) ----------
    print("\n\n=== 3. BETWEEN-METRIC CORRELATION ACROSS RUNS (final round) ===")
    print("Pearson r, computed within each staging then averaged (removes between-config signal)")
    keys = METRICS
    corr = {}
    for a in keys:
        for b in keys:
            rs = []
            for pc in STAGINGS:
                xa = [float(final(r, a)) for r in by[pc]]
                xb = [float(final(r, b)) for r in by[pc]]
                v = pearson(xa, xb)
                if math.isfinite(v):
                    rs.append(v)
            corr[(a, b)] = st.mean(rs) if rs else float("nan")
    print(f"{'':<12}" + "".join(f"{k[:6]:>8}" for k in keys))
    for a in keys:
        print(f"{a:<12}" + "".join(f"{fmt(corr[(a,b)],2):>8}" for b in keys))

    print("\n--- strongest anti-correlations (would make a panel see-saw) ---")
    pairs = sorted(((corr[(a, b)], a, b) for i, a in enumerate(keys) for b in keys[i + 1:]
                    if math.isfinite(corr[(a, b)])))
    for v, a, b in pairs[:8]:
        print(f"  {a:<12} vs {b:<12} r = {v:+.3f}")
    print("--- strongest positive (redundant: showing both adds nothing) ---")
    for v, a, b in reversed(pairs[-8:]):
        print(f"  {a:<12} vs {b:<12} r = {v:+.3f}")

    # ---------- 4. signal vs noise between configurations ----------
    print("\n\n=== 4. BETWEEN-CONFIGURATION SIGNAL vs RUN-TO-RUN NOISE (final round) ===")
    print(f"{'metric':<12} {'pc10':>8} {'pc20':>8} {'pc30':>8} {'sd_within':>10} "
          f"{'Δ(30-10)':>9} {'|Δ|/sd':>8} {'eta2':>7} {'F':>8} {'separable?':>12}")
    for k in METRICS:
        groups = [[float(final(r, k)) for r in by[pc]] for pc in STAGINGS]
        means = [st.mean(g) for g in groups]
        grand = st.mean([x for g in groups for x in g])
        ssb = sum(len(g) * (m - grand) ** 2 for g, m in zip(groups, means))
        ssw = sum((x - m) ** 2 for g, m in zip(groups, means) for x in g)
        n = sum(len(g) for g in groups)
        dfb, dfw = len(groups) - 1, n - len(groups)
        eta2 = ssb / (ssb + ssw) if (ssb + ssw) > 0 else float("nan")
        F = (ssb / dfb) / (ssw / dfw) if ssw > 0 else float("inf")
        sw = math.sqrt(ssw / dfw)
        d = means[2] - means[0]
        ratio = abs(d) / sw if sw > 0 else float("inf")
        # overlap test: do pc10 and pc30 run distributions overlap at all?
        lo10, hi10 = min(groups[0]), max(groups[0])
        lo30, hi30 = min(groups[2]), max(groups[2])
        sep = "clean" if (lo30 > hi10 or lo10 > hi30) else ("partial" if ratio > 1 else "NO")
        print(f"{k:<12} {fmt(means[0]):>8} {fmt(means[1]):>8} {fmt(means[2]):>8} "
              f"{fmt(sw):>10} {fmt(d):>9} {fmt(ratio,1):>8} {fmt(eta2,2):>7} {fmt(F,1):>8} "
              f"{sep:>12}")

    print("\n--- pairwise separation: |Δmean| / pooled within-staging sd (Cohen's d) ---")
    print(f"{'metric':<12} {'10 vs 20':>10} {'20 vs 30':>10} {'10 vs 30':>10} "
          f"{'monotonic?':>11} {'Welch t (10v30)':>16}")
    for k in METRICS:
        g = {pc: [float(final(r, k)) for r in by[pc]] for pc in STAGINGS}
        ds = []
        for a, b in ((10, 20), (20, 30), (10, 30)):
            ma, mb = st.mean(g[a]), st.mean(g[b])
            sp = math.sqrt(((len(g[a]) - 1) * st.variance(g[a]) +
                            (len(g[b]) - 1) * st.variance(g[b])) /
                           (len(g[a]) + len(g[b]) - 2))
            ds.append((mb - ma) / sp if sp > 0 else float("nan"))
        ms = [st.mean(g[p]) for p in STAGINGS]
        mono = "yes" if (ms[0] <= ms[1] <= ms[2] or ms[0] >= ms[1] >= ms[2]) else "no"
        a, b = g[10], g[30]
        se = math.sqrt(st.variance(a) / len(a) + st.variance(b) / len(b))
        t = (st.mean(b) - st.mean(a)) / se if se > 0 else float("nan")
        print(f"{k:<12} {fmt(ds[0],2):>10} {fmt(ds[1],2):>10} {fmt(ds[2],2):>10} "
              f"{mono:>11} {fmt(t,2):>16}")

    # ---------- 5. spread of a single displayed digit ----------
    print("\n\n=== 5. WHAT A VIEWER SEES: range of final-round values across runs ===")
    print(f"{'metric':<12} " + " ".join(f"{'pc'+str(p)+' min-max':>18}" for p in STAGINGS))
    for k in METRICS:
        cells = []
        for pc in STAGINGS:
            xs = [float(final(r, k)) for r in by[pc]]
            cells.append(f"{min(xs):.3f}-{max(xs):.3f} ({max(xs)-min(xs):.3f})")
        print(f"{k:<12} " + " ".join(f"{c:>18}" for c in cells))

    # ---------- 6. staging-consistency of the stability ranking ----------
    print("\n\n=== 6. IS THE STABILITY RANKING ITSELF REPRODUCIBLE? ===")
    print("Spearman rho between the CV%-rankings of the three stagings")
    for a, b in ((10, 20), (20, 30), (10, 30)):
        ra = [ranks[k][a] for k in METRICS]
        rb = [ranks[k][b] for k in METRICS]
        print(f"  pc{a} vs pc{b}: rho = {pearson(ra, rb):+.3f}")

    # split-half reliability of the CV estimate itself (n-collapse check)
    print("\n--- CV% estimated from the first half vs the second half of the runs "
          "(does the estimate survive halving n?) ---")
    print(f"{'metric':<12} " + " ".join(f"{'pc'+str(p)+' A/B':>16}" for p in STAGINGS))
    for k in METRICS:
        cells = []
        for pc in STAGINGS:
            rs = sorted(by[pc], key=lambda r: r["repeat"])
            h = len(rs) // 2
            xa = [float(final(r, k)) for r in rs[:h]]
            xb = [float(final(r, k)) for r in rs[h:]]
            cells.append(f"{cv(xa):.1f} / {cv(xb):.1f}")
        print(f"{k:<12} " + " ".join(f"{c:>16}" for c in cells))


if __name__ == "__main__":
    main()
