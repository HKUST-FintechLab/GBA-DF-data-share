import glob, json, os, re, statistics as st

BASE = r"C:\Users\chenx\AppData\Local\Temp\claude\D--agent-dean-0803\66483c77-2328-4c98-ab4e-ba05cdf4c932\scratchpad\baseline_exp"

runs = {}
for p in sorted(glob.glob(os.path.join(BASE, "status_*.json"))):
    rid = re.match(r"status_(.+)\.json", os.path.basename(p)).group(1)
    with open(p, encoding="utf-8-sig") as f:
        d = json.load(f)
    runs[rid] = {"auc": [m["auc"] for m in d["metrics"]],
                 "central": d["centralized"]["auc"],
                 "ceiling": d["centralized_nonprivate"]["auc"],
                 "samples": d["total_samples"]}

def mono(a):
    return all(a[i+1] >= a[i] - 1e-12 for i in range(len(a)-1))

def sd(v):
    return st.stdev(v) if len(v) > 1 else float("nan")

ROWS = {6: (75, 67, 75), 12: (158, 135, 141), 20: (252, 236, 235), 30: (375, 353, 363)}

print("=== MANDATED: 3 runs per per-class setting ===")
for pc in (6, 12, 20, 30):
    ids = [f"pc{pc}_r{r}" for r in (1, 2, 3)]
    finals, nm = [], 0
    for rid in ids:
        a = runs[rid]["auc"]
        finals.append(a[-1]); nm += mono(a)
        print(f"pc{pc:2d} {rid:10s} " + " ".join(f"{x:.3f}" for x in a)
              + f"   final={a[-1]:.3f} mono={mono(a)} rise(r1->r5)={a[-1]-a[0]:+.3f} "
              f"maxdrop={max([0]+[a[i]-a[i+1] for i in range(len(a)-1)]):.3f} n={runs[rid]['samples']}")
    print(f"   -> mean final {st.mean(finals):.3f} sd {sd(finals):.3f} monotone {nm}/3\n")

print("=== EXTENDED: all baseline replicates per setting (identical config) ===")
groups = {6: [], 12: [], 20: [], 30: []}
for rid in runs:
    m = re.match(r"pc(\d+)_r\d+$", rid)
    if m: groups[int(m.group(1))].append(rid)
    m = re.match(r"up(\d+)_base_p\d+$", rid)
    if m: groups[int(m.group(1))].append(rid)
for pc in (6, 12, 20, 30):
    ids = sorted(groups[pc])
    finals = [runs[i]["auc"][-1] for i in ids]
    firsts = [runs[i]["auc"][0] for i in ids]
    nm = sum(mono(runs[i]["auc"]) for i in ids)
    drops = [max([0]+[runs[i]["auc"][k]-runs[i]["auc"][k+1] for k in range(4)]) for i in ids]
    print(f"pc{pc:2d} n={len(ids):2d} rows/node={ROWS[pc]} total={runs[ids[0]]['samples']}  "
          f"final mean {st.mean(finals):.3f} sd {sd(finals):.3f}  "
          f"round1 mean {st.mean(firsts):.3f} sd {sd(firsts):.3f}  "
          f"monotone {nm}/{len(ids)}  mean max-dip {st.mean(drops):.3f}")
    print("     finals: " + " ".join(f"{x:.3f}" for x in finals))

print("\n=== UPLOAD VISIBILITY (+4 rows/node) ===")
for pc in (6, 20):
    b = sorted([r for r in runs if r.startswith(f"up{pc}_base_p")])
    u = sorted([r for r in runs if r.startswith(f"up{pc}_plus4_p")])
    bf = [runs[i]["auc"][-1] for i in b]
    uf = [runs[i]["auc"][-1] for i in u]
    allb = [runs[i]["auc"][-1] for i in sorted(groups[pc])]
    print(f"per-class {pc}:")
    print(f"  paired baselines n={len(bf)}: " + " ".join(f"{x:.3f}" for x in bf)
          + f"  mean {st.mean(bf):.3f} sd {sd(bf):.3f}")
    print(f"  +4 rows/node  n={len(uf)}: " + " ".join(f"{x:.3f}" for x in uf)
          + f"  mean {st.mean(uf):.3f} sd {sd(uf):.3f}")
    print(f"  all baseline replicates n={len(allb)}: mean {st.mean(allb):.3f} sd {sd(allb):.3f}")
    d = [uf[i]-bf[i] for i in range(min(len(uf), len(bf)))]
    print(f"  paired deltas: " + " ".join(f"{x:+.3f}" for x in d)
          + f"  mean {st.mean(d):+.3f} sd {sd(d):.3f}")
    print(f"  delta of means (vs all baselines): {st.mean(uf)-st.mean(allb):+.3f}")

any_id = next(iter(runs))
print(f"\ncentralized-DP reference AUC = {runs[any_id]['central']:.3f}; "
      f"non-private ceiling = {runs[any_id]['ceiling']:.3f}")
