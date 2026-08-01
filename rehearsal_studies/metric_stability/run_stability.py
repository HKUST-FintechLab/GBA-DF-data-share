"""Repeat federations across stagings and record EVERY per-round metric.

Harness copied from verify_demo_run.py: isolated FED_STATE_DIR, own port (8700+),
three concurrent node.py against a real coordinator, read /status -> metrics[].
Never touches :8055 or data/coordinator_state.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import traceback

import httpx

HERE = r"D:\agent\dean\0803\datademo"
PY = os.path.join(HERE, ".venv", "Scripts", "python.exe")
if not os.path.exists(PY):
    PY = sys.executable
WORK = os.path.dirname(os.path.abspath(__file__))

KEYS = ["auc", "acc", "bacc", "sensitivity", "specificity", "precision",
        "f1", "mcc", "brier", "ece", "n_trees", "n_updates"]


def run_once(stage, port, state, seeds, rounds=5):
    shutil.rmtree(state, ignore_errors=True)
    os.makedirs(state, exist_ok=True)
    env = {**os.environ, "FED_STATE_DIR": state}
    coord = subprocess.Popen([PY, "-m", "uvicorn", "coordinator:app", "--host", "127.0.0.1",
                              "--port", str(port), "--log-level", "warning"],
                             cwd=HERE, env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(120):
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
             "--rounds", str(rounds), "--seed", str(seeds[n - 1])], cwd=HERE,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for n in (1, 2, 3)]
        for p in procs:
            p.wait(timeout=1800)
        rcs = [p.returncode for p in procs]
        status = httpx.get(url + "/status", timeout=30).json()
        rows = []
        for m in status["metrics"]:
            row = {"round": m.get("round")}
            for k in KEYS:
                row[k] = m.get(k)
            conf = m.get("confusion") or {}
            for c in ("tn", "fp", "fn", "tp"):
                row[c] = conf.get(c)
            rows.append(row)
        return {"rounds": rows, "node_returncodes": rcs}
    finally:
        coord.terminate()
        try:
            coord.wait(timeout=15)
        except Exception:
            coord.kill()
        for node in ("node_1", "node_2", "node_3"):
            key = os.path.join(stage, node, "node_key.pem")
            if os.path.exists(key):
                os.remove(key)
        shutil.rmtree(state, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=12)
    ap.add_argument("--start-repeat", type=int, default=0)
    ap.add_argument("--per-class", type=int, nargs="+", default=[10, 20, 30])
    ap.add_argument("--base-port", type=int, default=8700)
    ap.add_argument("--out", default=os.path.join(WORK, "results.jsonl"))
    ap.add_argument("--stage-root", default=WORK,
                    help="directory holding stage_pc<N> trees (use a private copy when "
                         "two waves run concurrently)")
    args = ap.parse_args()

    port = args.base_port
    with open(args.out, "a", encoding="utf-8") as fh:
        for i in range(args.start_repeat, args.start_repeat + args.repeats):
            seeds = [i * 10 + 1, i * 10 + 2, i * 10 + 3]   # paired across stagings
            for pc in args.per_class:
                stage = os.path.join(args.stage_root, f"stage_pc{pc}")
                state = os.path.join(args.stage_root, f"state_pc{pc}_r{i}")
                t0 = time.time()
                rec = {"per_class": pc, "repeat": i, "seeds": seeds, "port": port}
                try:
                    rec.update(run_once(stage, port, state, seeds))
                    rec["ok"] = len(rec["rounds"]) == 5 and all(
                        r.get("auc") is not None for r in rec["rounds"])
                except Exception as e:
                    rec["ok"] = False
                    rec["error"] = f"{type(e).__name__}: {e}"
                    rec["traceback"] = traceback.format_exc()[-1500:]
                rec["secs"] = round(time.time() - t0, 1)
                fh.write(json.dumps(rec) + "\n")
                fh.flush()
                last = rec.get("rounds", [])
                tail = f"auc {last[-1]['auc']:.3f}" if last and last[-1].get("auc") is not None else "FAILED"
                print(f"pc{pc} rep{i} port{port} {rec['secs']}s rounds={len(last)} {tail}",
                      flush=True)
                port += 1


if __name__ == "__main__":
    main()
