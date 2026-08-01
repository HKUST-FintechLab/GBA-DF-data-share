import concurrent.futures as cf, time, runner
REPS = range(100, 116)
for r in REPS: runner.ensure_stage(30, r, 3)
jobs = [(t, n, 30, r) for r in REPS for (t, n) in (("p30_n1", 1), ("p30_n2", 2), ("p30_n3", 3))]
t0=time.time(); done=0
with cf.ThreadPoolExecutor(max_workers=6) as ex:
    futs = {ex.submit(runner.run_once, t, n, pc, r): (t, r) for (t, n, pc, r) in jobs}
    for f in cf.as_completed(futs):
        t, r = futs[f]
        try: rec = f.result()
        except Exception as e: rec = {"tag": t, "repeat": r, "ok": False, "error": str(e)}
        runner.append(rec, "ship30.jsonl"); done += 1
        print(f"[{done}/{len(jobs)} {time.time()-t0:5.0f}s] {t} r{r} ok={rec.get('ok')} rows={rec.get('rows')} "
              f"{[round(m['auc'],3) for m in rec.get('metrics',[])]} {rec.get('error') or ''}", flush=True)
