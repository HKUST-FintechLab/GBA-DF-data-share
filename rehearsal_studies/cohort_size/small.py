import itertools, json, math, statistics as st, sys
C = 0.7782143947877431
rows = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8") if l.strip()]
bad = [r for r in rows if not r.get("ok")]
good = [r for r in rows if r.get("ok")]
print(f"{len(rows)} runs, {len(good)} ok, {len(bad)} failed")
for r in bad: print("  FAILED", r.get("tag"), r.get("repeat"), r.get("error"))
by = {}
for r in good: by.setdefault(r["tag"], []).append(r)
tags = sorted(by)
print(f"{'arm':<10}{'rows':>6}{'final AUC':>18}{'range':>16}{'>0.778':>9}{'rise':>8}   per-round mean")
for t in tags:
    rs = sorted(by[t], key=lambda r: r["repeat"])
    fin = [r["metrics"][-1]["auc"] for r in rs]
    fi = [r["metrics"][0]["auc"] for r in rs]
    pr = [st.mean([r["metrics"][i]["auc"] for r in rs]) for i in range(5)]
    print(f"{t:<10}{rs[0]['rows']:>6}  {st.mean(fin):.3f} +- {st.stdev(fin):.3f} (n={len(fin)}) "
          f"{min(fin):.3f}-{max(fin):.3f}{sum(1 for f in fin if f>C):>5}/{len(fin):<4}"
          f"{st.mean(fin)-st.mean(fi):+7.3f}   " + " ".join(f"{v:.3f}" for v in pr))
fb = {t: {r["repeat"]: r["metrics"][-1]["auc"] for r in by[t]} for t in tags}
print(f"\n{'contrast':<20}{'delta':>8}{'sd(diff)':>10}{'dz':>7}{'welch t':>9}{'1-run win':>12}{'>=0.02':>8}")
for a, b in itertools.combinations(tags, 2):
    ks = sorted(set(fb[a]) & set(fb[b])); d = [fb[b][k]-fb[a][k] for k in ks]
    va, vb = list(fb[a].values()), list(fb[b].values())
    se = math.sqrt(st.variance(va)/len(va) + st.variance(vb)/len(vb))
    wins = sum(1 for x, y in itertools.product(va, vb) if y > x)
    big = sum(1 for x, y in itertools.product(va, vb) if y-x >= 0.02)
    tot = len(va)*len(vb)
    print(f"{a+' -> '+b:<20}{st.mean(d):+8.3f}{st.stdev(d):10.3f}{st.mean(d)/st.stdev(d):7.2f}"
          f"{(st.mean(vb)-st.mean(va))/se:9.2f}{wins/tot:11.0%}{big/tot:8.0%}")
# monotone 1<2<3 over independent single runs
if len(tags) >= 3:
    a, b, c = tags[0], tags[1], tags[2]
    va, vb, vc = (list(fb[x].values()) for x in (a, b, c))
    mono = sum(1 for x, y, z in itertools.product(va, vb, vc) if x < y < z)
    print(f"\nP(one live 1->2->3 sequence rises at every step) = {mono/(len(va)*len(vb)*len(vc)):.0%}")
