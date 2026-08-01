import concurrent.futures as cf, time, runner
# pc16 repeats 14..27 (extend to n=28) + same-total control: 1 node holding ~580 rows
ARMS = [("p16_n1", 1, 16), ("p16_n2", 2, 16), ("p16_n3", 3, 16)]
jobs = [(t, n, pc, r) for r in range(14, 28) for (t, n, pc) in ARMS]
jobs += [("p16ctl_n1", 1, 48, r) for r in range(28)]
for pc, nodes in ((16, 3), (48, 1)):
    for r in range(28):
        runner.ensure_stage(pc, r, nodes)
t0 = time.time(); done = 0
with cf.ThreadPoolExecutor(max_workers=6) as ex:
    futs = {ex.submit(runner.run_once, t, n, pc, r): (t, r) for (t, n, pc, r) in jobs}
    for f in cf.as_completed(futs):
        t, r = futs[f]
        try: rec = f.result()
        except Exception as e: rec = {"tag": t, "repeat": r, "ok": False, "error": str(e)}
        out = "small16.jsonl" if t.startswith("p16_") else "ctl16.jsonl"
        runner.append(rec, out); done += 1
        print(f"[{done}/{len(jobs)} {time.time()-t0:5.0f}s] {t} r{r} ok={rec.get('ok')} rows={rec.get('rows')} "
              f"{[round(m['auc'],3) for m in rec.get('metrics',[])]} {rec.get('error') or ''}", flush=True)
