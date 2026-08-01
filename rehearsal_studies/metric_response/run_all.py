"""Run every arm x seed combination sequentially, appending to results.jsonl.

Seeds are PAIRED across arms: the same seed_base is used in A, B, C and D, so the
node-side assignment randomness is matched and the arms differ only in the clips.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import driver

SEEDS = [int(s) for s in os.environ.get(
    "SEEDS", "10,20,30,40,50,60,70,80,90,100").split(",")]
ARMS = ["A", "B", "C", "D"]


def main():
    t0 = time.time()
    port = 8200
    total = len(SEEDS) * len(ARMS)
    done = 0
    for seed in SEEDS:
        for arm in ARMS:
            res = driver.run_once(arm, seed, port)
            port = 8200 + ((port - 8200 + 3) % 120)
            with open(driver.RESULTS, "a", encoding="utf-8") as f:
                f.write(json.dumps(res) + "\n")
            done += 1
            tail = (res.get("metrics") or [{}])[-1]
            print(f"[{done}/{total}] {arm} seed={seed} ok={res.get('ok')} "
                  f"rounds={res.get('n_rounds')} auc={tail.get('auc')} "
                  f"bacc={tail.get('bacc')} t={res.get('elapsed_s')}s "
                  f"err={res.get('error')} fails={len(res.get('node_failures') or [])}",
                  flush=True)
    print(f"ALL DONE in {round(time.time()-t0,1)}s", flush=True)


if __name__ == "__main__":
    main()
