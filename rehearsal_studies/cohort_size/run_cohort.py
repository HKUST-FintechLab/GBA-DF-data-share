"""Cohort-size measurement harness. Copies the verify_demo_run.py pattern:
isolated FED_STATE_DIR, real node.py processes, read /status -> metrics[].

Never touches port 8055, demo_nodes/, or data/.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

import httpx

HERE = r"D:\agent\dean\0803\datademo"
PY = os.path.join(HERE, ".venv", "Scripts", "python.exe")
WORK = r"C:\Users\chenx\AppData\Local\Temp\claude\D--agent-dean-0803\66483c77-2328-4c98-ab4e-ba05cdf4c932\scratchpad\cohort"


def run_once(stage, n_nodes, port, state, rounds=5, seed_base=0, timeout=1200):
    shutil.rmtree(state, ignore_errors=True)
    os.makedirs(state, exist_ok=True)
    env = {**os.environ, "FED_STATE_DIR": state, "FED_COHORT": str(n_nodes)}
    if n_nodes == 1:
        # cohort=1 isolates each session into a private room by default; share the room so
        # /status reports it. cohort=1 is CENTRAL DP ONLY - never secure aggregation.
        env["FED_SOLO_SHARED"] = "1"
    coord = subprocess.Popen([PY, "-m", "uvicorn", "coordinator:app", "--host", "127.0.0.1",
                              "--port", str(port), "--log-level", "warning"],
                             cwd=HERE, env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(240):
            try:
                if httpx.get(url + "/health", timeout=2).status_code == 200:
                    break
            except Exception:
                pass
            time.sleep(0.5)
        else:
            raise RuntimeError("coordinator never became ready")
        procs = [subprocess.Popen(
            [PY, "node.py", "--node-id", f"node_{n}", "--coord", url,
             "--folder", os.path.join(stage, f"node_{n}"), "--modality", "action",
             "--rounds", str(rounds), "--seed", str(seed_base * 10 + n)], cwd=HERE,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for n in range(1, n_nodes + 1)]
        rcs = []
        for p in procs:
            try:
                rcs.append(p.wait(timeout=timeout))
            except Exception:
                p.kill()
                rcs.append(-9)
        status = httpx.get(url + "/status", timeout=20).json()
        return {"metrics": status["metrics"], "rcs": rcs,
                "total_samples": status.get("total_samples"),
                "cohort": status.get("cohort"),
                "secure_aggregation": status.get("secure_aggregation"),
                "privacy_mode": status.get("privacy_mode"),
                "global_eps": status.get("global_eps"),
                "rejected": status.get("rejected_payloads")}
    finally:
        coord.terminate()
        try:
            coord.wait(timeout=20)
        except Exception:
            coord.kill()
        for n in range(1, n_nodes + 1):
            key = os.path.join(stage, f"node_{n}", "node_key.pem")
            if os.path.exists(key):
                os.remove(key)
        shutil.rmtree(state, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True)
    ap.add_argument("--nodes", type=int, required=True)
    ap.add_argument("--arm", required=True)
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--seed-start", type=int, default=1)
    ap.add_argument("--port", type=int, default=8600)
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    stage = os.path.join(WORK, args.stage)
    with open(args.out, "a", encoding="utf-8") as fh:
        for i in range(args.repeats):
            seed = args.seed_start + i
            t0 = time.time()
            rec = {"arm": args.arm, "nodes": args.nodes, "stage": args.stage,
                   "repeat": i, "seed": seed}
            try:
                res = run_once(stage, args.nodes, args.port,
                               os.path.join(WORK, f"state_{args.arm}_{i}"),
                               rounds=args.rounds, seed_base=seed)
                rec.update(res)
                rec["ok"] = (len(res["metrics"]) == args.rounds
                             and all(r == 0 for r in res["rcs"]))
            except Exception as e:
                rec["ok"] = False
                rec["error"] = f"{type(e).__name__}: {e}"
            rec["seconds"] = round(time.time() - t0, 1)
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            curve = [round(m["auc"], 3) for m in rec.get("metrics", [])]
            print(f"{args.arm} run {i+1}/{args.repeats} seed={seed} ok={rec['ok']} "
                  f"{rec['seconds']}s  auc={curve}", flush=True)


if __name__ == "__main__":
    main()
