import argparse
import concurrent.futures as cf
import os
import time

import runner

ARMS = [
    ("s1_n1", 1, 20),   # study 1: each institution ~240 rows, total grows with cohort
    ("s1_n2", 2, 20),
    ("s1_n3", 3, 20),   # doubles as study 2's 3-node arm
    ("s2_n1", 1, 60),   # study 2: total held at ~720 rows, split more ways
    ("s2_n2", 2, 30),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=12)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--out", default=runner.RESULTS)
    args = ap.parse_args()

    reps = range(args.start, args.start + args.repeats)
    # pre-stage serially so concurrent runs never race on generation
    for pc, nodes in ((20, 3), (30, 2), (60, 1)):
        for r in reps:
            s = runner.ensure_stage(pc, r, nodes)
            print("staged", os.path.basename(s), flush=True)

    jobs = [(tag, n, pc, r) for r in reps for (tag, n, pc) in ARMS]
    t0 = time.time()
    done = 0
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(runner.run_once, tag, n, pc, r): (tag, r)
                for (tag, n, pc, r) in jobs}
        for f in cf.as_completed(futs):
            tag, r = futs[f]
            try:
                rec = f.result()
            except Exception as e:
                rec = {"tag": tag, "repeat": r, "ok": False,
                       "error": f"driver {type(e).__name__}: {e}"}
            runner.append(rec, args.out)
            done += 1
            aucs = [round(m["auc"], 3) for m in rec.get("metrics", [])]
            print(f"[{done}/{len(jobs)}  {time.time()-t0:6.0f}s] {tag} r{r} "
                  f"ok={rec.get('ok')} rows={rec.get('rows')} {aucs} {rec.get('error') or ''}",
                  flush=True)


if __name__ == "__main__":
    main()
