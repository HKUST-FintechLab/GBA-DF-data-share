"""Run federations for the metric-responsiveness experiment.

One run = isolated coordinator (own FED_STATE_DIR, own port >= 8200) + three concurrent
nodes for 5 rounds. Results (all per-round metric dicts) are appended to results.jsonl.

  python driver.py <arm> <seed_base> <port>
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

REPO = r"D:\agent\dean\0803\datademo"
PY = os.path.join(REPO, ".venv", "Scripts", "python.exe")
ROOT = r"C:\Users\chenx\AppData\Local\Temp\claude\D--agent-dean-0803\66483c77-2328-4c98-ab4e-ba05cdf4c932\scratchpad\metric_exp"
ARMS = os.path.join(ROOT, "arms")
RUNS = os.path.join(ROOT, "runs")
RESULTS = os.path.join(ROOT, "results.jsonl")

ENV_BASE = dict(os.environ)
ENV_BASE.update({"OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1",
                 "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1",
                 "PYTHONUNBUFFERED": "1"})


def free_port(start):
    p = start
    while p < start + 200:
        if p == 8055:
            p += 1
            continue
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                p += 1
    raise RuntimeError("no free port")


def get(url, timeout=10):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


def run_once(arm, seed_base, port_hint, rounds=5, log=print):
    arm_dir = os.path.join(ARMS, arm)
    run_tag = f"{arm}_s{seed_base}"
    state = os.path.join(RUNS, run_tag)
    if os.path.exists(state):
        shutil.rmtree(state)
    os.makedirs(state, exist_ok=True)
    # fresh node identities every run
    for n in (1, 2, 3):
        pem = os.path.join(arm_dir, f"node_{n}", "node_key.pem")
        if os.path.exists(pem):
            os.remove(pem)

    port = free_port(port_hint)
    env = dict(ENV_BASE)
    env["FED_STATE_DIR"] = state
    coord = subprocess.Popen(
        [PY, "-m", "uvicorn", "coordinator:app", "--host", "127.0.0.1",
         "--port", str(port), "--log-level", "warning"],
        cwd=REPO, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    base = f"http://127.0.0.1:{port}"
    t0 = time.time()
    try:
        ready = False
        while time.time() - t0 < 120:
            if coord.poll() is not None:
                err = coord.stderr.read().decode(errors="replace")[-2000:]
                return {"ok": False, "error": "coordinator exited", "stderr": err}
            try:
                sch = get(base + "/schema", timeout=3)
                ready = True
                break
            except Exception:
                time.sleep(0.5)
        if not ready:
            return {"ok": False, "error": "coordinator never became ready"}

        procs = []
        for n in (1, 2, 3):
            procs.append(subprocess.Popen(
                [PY, "node.py", "--node-id", f"node_{n}", "--coord", base,
                 "--folder", os.path.join(arm_dir, f"node_{n}"),
                 "--modality", "action", "--rounds", str(rounds), "--seed", str(seed_base + n)],
                cwd=REPO, env=dict(ENV_BASE),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT))
        outs = []
        deadline = time.time() + 900
        for p in procs:
            try:
                o, _ = p.communicate(timeout=max(10, deadline - time.time()))
            except subprocess.TimeoutExpired:
                p.kill()
                o, _ = p.communicate()
                outs.append(("TIMEOUT", o.decode(errors="replace")))
                continue
            outs.append((p.returncode, o.decode(errors="replace")))

        status = get(base + "/status", timeout=20)
        metrics = status.get("metrics", [])
        node_fail = [(rc, o[-600:]) for rc, o in outs if rc != 0]
        return {"ok": len(metrics) >= rounds and not node_fail,
                "arm": arm, "seed_base": seed_base, "port": port,
                "n_rounds": len(metrics), "metrics": metrics,
                "node_returncodes": [rc for rc, _ in outs],
                "node_failures": node_fail,
                "cohort": sch.get("cohort"), "n_features": sch.get("n_features"),
                "elapsed_s": round(time.time() - t0, 1)}
    finally:
        coord.terminate()
        try:
            coord.wait(timeout=15)
        except subprocess.TimeoutExpired:
            coord.kill()
        try:
            coord.stderr.close()
        except Exception:
            pass
        shutil.rmtree(state, ignore_errors=True)
        for n in (1, 2, 3):
            pem = os.path.join(arm_dir, f"node_{n}", "node_key.pem")
            if os.path.exists(pem):
                os.remove(pem)


def main():
    arm, seed_base, port_hint = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    res = run_once(arm, seed_base, port_hint)
    with open(RESULTS, "a", encoding="utf-8") as f:
        f.write(json.dumps(res) + "\n")
    last = res.get("metrics", [])
    tail = last[-1] if last else {}
    print(json.dumps({"arm": arm, "seed": seed_base, "ok": res.get("ok"),
                      "rounds": res.get("n_rounds"), "elapsed": res.get("elapsed_s"),
                      "auc": tail.get("auc"), "bacc": tail.get("bacc"),
                      "error": res.get("error"), "fails": res.get("node_failures")}))


if __name__ == "__main__":
    main()
