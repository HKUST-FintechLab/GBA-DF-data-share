import argparse
import itertools
import json
import math
import statistics as st

CENTRAL = 0.7782143947877431
LABEL = {"s1_n1": "S1 1 node  (240 rows)", "s1_n2": "S1 2 nodes (480 rows)",
         "s1_n3": "S1 3 nodes (720 rows)", "s2_n1": "S2 1 node  (720 rows)",
         "s2_n2": "S2 2 nodes (720 rows)"}
ORDER = ["s1_n1", "s1_n2", "s1_n3", "s2_n1", "s2_n2"]


def load(path):
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    good = [r for r in rows if r.get("ok")]
    bad = [r for r in rows if not r.get("ok")]
    return rows, good, bad


def ms(v):
    return st.mean(v), (st.stdev(v) if len(v) > 1 else float("nan"))


def welch(a, b):
    ma, mb = st.mean(a), st.mean(b)
    va, vb = st.variance(a), st.variance(b)
    se = math.sqrt(va / len(a) + vb / len(b))
    return (mb - ma), (0.0 if se == 0 else (mb - ma) / se)


def paired(a_by_r, b_by_r):
    keys = sorted(set(a_by_r) & set(b_by_r))
    d = [b_by_r[k] - a_by_r[k] for k in keys]
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default="results.jsonl")
    a = ap.parse_args()
    rows, good, bad = load(a.path)
    print(f"runs: {len(rows)} total, {len(good)} ok, {len(bad)} failed")
    for r in bad:
        print(f"  FAILED {r.get('tag')} r{r.get('repeat')}: {r.get('error')}")

    by = {}
    for r in good:
        by.setdefault(r["tag"], []).append(r)
    for t in by:
        by[t].sort(key=lambda r: r["repeat"])

    print("\n== per-arm summary (final round, n=5 rounds) ==")
    hdr = f"{'arm':<22}{'n':>3}{'rows':>6}  {'AUC final':>16}  {'range':>15}  {'>0.778':>7}  {'rise r1->r5':>13}  {'monotone-ish':>12}"
    print(hdr)
    for t in ORDER:
        rs = by.get(t, [])
        if not rs:
            continue
        fin = [r["metrics"][-1]["auc"] for r in rs]
        first = [r["metrics"][0]["auc"] for r in rs]
        rise = [b - a2 for a2, b in zip(first, fin)]
        m, s = ms(fin)
        above = sum(1 for f in fin if f > CENTRAL)
        # a curve counts as "rises" if final > first and no drop larger than 0.005 after r2
        nice = sum(1 for r in rs
                   if r["metrics"][-1]["auc"] > r["metrics"][0]["auc"]
                   and all(b["auc"] >= a2["auc"] - 0.005
                           for a2, b in zip(r["metrics"][1:], r["metrics"][2:])))
        print(f"{LABEL[t]:<22}{rs[0]['n_nodes']:>3}{rs[0]['rows']:>6}  "
              f"{m:.3f} ± {s:.3f} (n={len(fin):>2})  {min(fin):.3f}-{max(fin):.3f}  "
              f"{above:>3}/{len(fin):<3}  {st.mean(rise):+.3f}       {nice:>3}/{len(fin)}")

    print("\n== other metrics at final round (mean ± sd) ==")
    print(f"{'arm':<22}{'auc':>14}{'bacc':>14}{'acc':>14}{'sens':>14}{'spec':>14}")
    for t in ORDER:
        rs = by.get(t, [])
        if not rs:
            continue
        cells = []
        for k in ("auc", "bacc", "acc", "sensitivity", "specificity"):
            v = [r["metrics"][-1][k] for r in rs]
            m, s = ms(v)
            cells.append(f"{m:.3f}±{s:.3f}")
        print(f"{LABEL[t]:<22}" + "".join(f"{c:>14}" for c in cells))

    print("\n== per-round mean AUC ==")
    print(f"{'arm':<22}" + "".join(f"{'r'+str(i+1):>9}" for i in range(5)))
    for t in ORDER:
        rs = by.get(t, [])
        if not rs:
            continue
        cells = [st.mean([r["metrics"][i]["auc"] for r in rs]) for i in range(5)]
        print(f"{LABEL[t]:<22}" + "".join(f"{c:>9.3f}" for c in cells))

    print("\n== contrasts (final AUC) ==")
    fin_by = {t: {r["repeat"]: r["metrics"][-1]["auc"] for r in by.get(t, [])} for t in ORDER}
    pairs = [("s1_n1", "s1_n2"), ("s1_n2", "s1_n3"), ("s1_n1", "s1_n3"),
             ("s2_n1", "s2_n2"), ("s2_n2", "s1_n3"), ("s2_n1", "s1_n3"),
             ("s1_n1", "s2_n1"), ("s1_n2", "s2_n2")]
    print(f"{'contrast':<34}{'delta':>8}{'sd(diff)':>10}{'d(paired)':>11}{'welch t':>9}{'P(single win)':>15}")
    for a1, b1 in pairs:
        A, B = fin_by.get(a1, {}), fin_by.get(b1, {})
        if not A or not B:
            continue
        d = paired(A, B)
        va, vb = list(A.values()), list(B.values())
        delta, tt = welch(va, vb)
        sd_d = st.stdev(d) if len(d) > 1 else float("nan")
        dz = st.mean(d) / sd_d if sd_d else float("nan")
        # every unpaired single-run comparison an audience could see
        wins = sum(1 for x, y in itertools.product(va, vb) if y > x)
        tot = len(va) * len(vb)
        name = f"{LABEL[a1].split('(')[0].strip()} -> {LABEL[b1].split('(')[0].strip()}"
        print(f"{name:<34}{st.mean(d):+8.3f}{sd_d:10.3f}{dz:11.2f}{tt:9.2f}"
              f"{wins}/{tot} = {wins/tot:.0%}".rjust(15))

    print("\n== single-run visibility (unpaired, what an audience sees) ==")
    for a1, b1 in [("s1_n1", "s1_n2"), ("s1_n2", "s1_n3"), ("s1_n1", "s1_n3")]:
        va = list(fin_by[a1].values())
        vb = list(fin_by[b1].values())
        pooled_sd = math.sqrt((st.variance(va) + st.variance(vb)) / 2)
        delta = st.mean(vb) - st.mean(va)
        wins = sum(1 for x, y in itertools.product(va, vb) if y > x)
        tot = len(va) * len(vb)
        big = sum(1 for x, y in itertools.product(va, vb) if y - x >= 0.02)
        print(f"  {a1} -> {b1}: delta {delta:+.3f}, run-to-run sd {pooled_sd:.3f}, "
              f"effect size {delta/pooled_sd:+.2f}; single 2-run comparison favours the "
              f"bigger cohort {wins}/{tot} = {wins/tot:.0%}; visibly (>=0.02) {big/tot:.0%}")


if __name__ == "__main__":
    main()
