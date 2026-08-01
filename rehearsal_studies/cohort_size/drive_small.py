import concurrent.futures as cf, sys, time, runner
PC = int(sys.argv[1]); REPS = int(sys.argv[2]); OUT = sys.argv[3]
ARMS = [(f"p{PC}_n1", 1, PC), (f"p{PC}_n2", 2, PC), (f"p{PC}_n3", 3, PC)]
for r in range(REPS):
    runner.ensure_stage(PC, r, 3)
jobs = [(t, n, pc, r) for r in range(REPS) for (t, n, pc) in ARMS]
t0 = time.time(); done = 0
with cf.ThreadPoolExecutor(max_workers=6) as ex:
    futs = {ex.submit(runner.run_once, t, n, pc, r): (t, r) for (t, n, pc, r) in jobs}
    for f in cf.as_completed(futs):
        t, r = futs[f]
        try: rec = f.result()
        except Exception as e: rec = {"tag": t, "repeat": r, "ok": False, "error": str(e)}
        runner.append(rec, OUT); done += 1
        print(f"[{done}/{len(jobs)} {time.time()-t0:5.0f}s] {t} r{r} ok={rec.get('ok')} rows={rec.get('rows')} "
              f"{[round(m['auc'],3) for m in rec.get('metrics',[])]} {rec.get('error') or ''}", flush=True)
