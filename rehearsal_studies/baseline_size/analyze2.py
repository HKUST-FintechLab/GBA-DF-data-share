import glob, json, os, re, statistics as st, itertools, math

BASE = r"C:\Users\chenx\AppData\Local\Temp\claude\D--agent-dean-0803\66483c77-2328-4c98-ab4e-ba05cdf4c932\scratchpad\baseline_exp"
runs = {}
for p in sorted(glob.glob(os.path.join(BASE, "status_*.json"))):
    rid = re.match(r"status_(.+)\.json", os.path.basename(p)).group(1)
    with open(p, encoding="utf-8-sig") as f:
        d = json.load(f)
    runs[rid] = [m["auc"] for m in d["metrics"]]

groups = {6: [], 12: [], 20: [], 30: []}
for rid in runs:
    m = re.match(r"pc(\d+)_r\d+$", rid) or re.match(r"up(\d+)_base_p\d+$", rid)
    if m:
        groups[int(m.group(1))].append(rid)

def dips(a):
    return [a[i] - a[i+1] for i in range(len(a)-1) if a[i] > a[i+1]]

print("=== wobble structure (all baseline replicates) ===")
print("pc | n  | mono5 | mono r2-5 | any dip>0.005 | mean max-dip | max max-dip | mean rise r1->r5 | final sd | r1 sd")
for pc in (6, 12, 20, 30):
    ids = sorted(groups[pc]); A = [runs[i] for i in ids]
    mono5 = sum(all(a[i+1] >= a[i] for i in range(4)) for a in A)
    mono25 = sum(all(a[i+1] >= a[i] for i in range(1, 4)) for a in A)
    md = [max(dips(a), default=0.0) for a in A]
    big = sum(x > 0.005 for x in md)
    rise = [a[-1]-a[0] for a in A]
    print(f"{pc:2d} | {len(ids):2d} | {mono5}/{len(ids):<3} | {mono25}/{len(ids):<7} | {big}/{len(ids):<11} | "
          f"{st.mean(md):.3f}        | {max(md):.3f}      | {st.mean(rise):+.3f}           | "
          f"{st.stdev([a[-1] for a in A]):.3f}    | {st.stdev([a[0] for a in A]):.3f}")

def welch(a, b):
    na, nb = len(a), len(b)
    va, vb = st.variance(a), st.variance(b)
    se = math.sqrt(va/na + vb/nb)
    t = (st.mean(a) - st.mean(b)) / se
    df = (va/na + vb/nb)**2 / ((va/na)**2/(na-1) + (vb/nb)**2/(nb-1))
    return t, df, se

print("\n=== upload visibility, all-pairs view ===")
for pc in (6, 20):
    b = [runs[i][-1] for i in sorted(groups[pc])]
    u = [runs[i][-1] for i in sorted(r for r in runs if r.startswith(f"up{pc}_plus4_p"))]
    t, df, se = welch(u, b)
    wins = sum(x > y for x, y in itertools.product(u, b))
    tot = len(u)*len(b)
    print(f"per-class {pc}: baseline n={len(b)} mean {st.mean(b):.3f} sd {st.stdev(b):.3f} "
          f"[{min(b):.3f}-{max(b):.3f}]")
    print(f"              +4rows  n={len(u)} mean {st.mean(u):.3f} sd {st.stdev(u):.3f} "
          f"[{min(u):.3f}-{max(u):.3f}]")
    print(f"              delta {st.mean(u)-st.mean(b):+.3f}  (SE {se:.3f}, Welch t={t:.2f}, df={df:.1f})")
    print(f"              |delta| / baseline sd = {abs(st.mean(u)-st.mean(b))/st.stdev(b):.2f}")
    print(f"              P(one upload run beats one baseline run) = {wins}/{tot} = {wins/tot:.2f}")

print("\n=== round-by-round means (all baseline replicates) ===")
for pc in (6, 12, 20, 30):
    A = [runs[i] for i in sorted(groups[pc])]
    means = [st.mean([a[r] for a in A]) for r in range(5)]
    sds = [st.stdev([a[r] for a in A]) for r in range(5)]
    print(f"pc{pc:2d} mean " + " ".join(f"{m:.3f}" for m in means)
          + "   sd " + " ".join(f"{s:.3f}" for s in sds))
