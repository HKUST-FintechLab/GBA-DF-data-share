"""Cohort-size measurement harness. Copies the verify_demo_run.py pattern.

Never touches :8055, demo_nodes/, data/. Ports 8600-8699 only.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time

import httpx

REPO = r"D:\agent\dean\0803\datademo"
PY = os.path.join(REPO, ".venv", "Scripts", "python.exe")
if not os.path.exists(PY):
    PY = sys.executable
WORK = r"C:\Users\chenx\AppData\Local\Temp\claude\D--agent-dean-0803\66483c77-2328-4c98-ab4e-ba05cdf4c932\scratchpad\cohort"
STAGES = os.path.join(WORK, "stages")
RUNS = os.path.join(WORK, "runs")
RESULTS = os.path.join(WORK, "results.jsonl")

_PORT_LOCK = threading.Lock()
_PORTS = list(range(8600, 8700))
_IN_USE = set()


def _free_port():
    with _PORT_LOCK:
        for p in _PORTS:
            if p in _IN_USE:
                continue
            s = socket.socket()
            try:
                s.bind(("127.0.0.1", p))
            except OSError:
                s.close()
                continue
            s.close()
            _IN_USE.add(p)
            return p
    raise RuntimeError("no free port in 8600-8699")


def _release(p):
    with _PORT_LOCK:
        _IN_USE.discard(p)


def stage_key(per_class, repeat, nodes=None):
    return f"pc{per_class}_r{repeat}"


_STAGE_LOCK = threading.Lock()


def ensure_stage(per_class, repeat, nodes):
    """One synthetic stage per (per_class, repeat). Node k data depends only on
    (base_seed, k, per_class), so arms with different cohort sizes share node_1..node_k."""
    out = os.path.join(STAGES, stage_key(per_class, repeat))
    done = os.path.join(out, ".staged")
    with _STAGE_LOCK:
        if os.path.exists(done):
            return out
        return _build_stage(out, done, per_class, repeat, nodes)


def _build_stage(out, done, per_class, repeat, nodes):
    shutil.rmtree(out, ignore_errors=True)
    base = 100 + 1000 * repeat
    cmd = [PY, "stage_demo_nodes.py", "--modality", "action", "--nodes", str(nodes),
           "--per-class", str(per_class), "--out", out, "--seed", str(base), "--force"]
    r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=1800)
    if r.returncode != 0:
        raise RuntimeError(f"stage failed: {r.stdout}\n{r.stderr}")
    rows = {}
    for line in r.stdout.splitlines():
        line = line.strip()
        if line.startswith("node_") and "rows x" in line:
            nid = line.split(":")[0]
            rows[nid] = int(line.split("->")[1].split("rows")[0].strip().split()[0])
    with open(done, "w") as f:
        json.dump(rows, f)
    return out


def stage_rows(stage, node_ids):
    with open(os.path.join(stage, ".staged")) as f:
        rows = json.load(f)
    return sum(rows[n] for n in node_ids)


def run_once(tag, n_nodes, per_class, repeat, rounds=5, timeout=1800):
    """One federation run: fresh state dir, fresh port, n concurrent nodes, 5 rounds."""
    stage = ensure_stage(per_class, repeat, n_nodes)
    node_ids = [f"node_{k}" for k in range(1, n_nodes + 1)]
    run_dir = os.path.join(RUNS, f"{tag}_r{repeat}_{os.getpid()}_{int(time.time()*1000)%100000}")
    shutil.rmtree(run_dir, ignore_errors=True)
    data_dir = os.path.join(run_dir, "data")
    state = os.path.join(run_dir, "state")
    os.makedirs(state, exist_ok=True)
    for nid in node_ids:
        shutil.copytree(os.path.join(stage, nid), os.path.join(data_dir, nid))
    port = _free_port()
    env = {**os.environ, "FED_STATE_DIR": state, "FED_COHORT": str(n_nodes)}
    if n_nodes == 1:
        # cohort=1 is central-DP-only. SOLO_SHARED keeps the single room readable through
        # /status; without it each node gets a private per-session room we cannot address.
        env["FED_SOLO_SHARED"] = "1"
    coord = subprocess.Popen([PY, "-m", "uvicorn", "coordinator:app", "--host", "127.0.0.1",
                              "--port", str(port), "--log-level", "warning"],
                             cwd=REPO, env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    rec = {"tag": tag, "n_nodes": n_nodes, "per_class": per_class, "repeat": repeat,
           "port": port, "rows": stage_rows(stage, node_ids), "ok": False, "error": None}
    t0 = time.time()
    try:
        for _ in range(180):
            try:
                if httpx.get(url + "/health", timeout=2).status_code == 200:
                    break
            except Exception:
                pass
            time.sleep(0.5)
        else:
            raise RuntimeError("coordinator never became ready")
        procs = [subprocess.Popen(
            [PY, "node.py", "--node-id", nid, "--coord", url,
             "--folder", os.path.join(data_dir, nid), "--modality", "action",
             "--rounds", str(rounds), "--seed", str(k)], cwd=REPO,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for k, nid in enumerate(node_ids, start=1)]
        codes = []
        for p in procs:
            try:
                codes.append(p.wait(timeout=timeout))
            except subprocess.TimeoutExpired:
                p.kill()
                codes.append(-9)
        rec["node_exit_codes"] = codes
        status = httpx.get(url + "/status", timeout=30).json()
        ms = status["metrics"]
        rec["metrics"] = [{k: m.get(k) for k in
                           ("round", "auc", "bacc", "acc", "sensitivity", "specificity", "n_trees")}
                          for m in ms]
        rec["cohort_reported"] = status.get("cohort")
        rec["secure_aggregation"] = status.get("secure_aggregation")
        rec["privacy_mode"] = status.get("privacy_mode")
        rec["n_rounds_done"] = len(ms)
        rec["ok"] = len(ms) == rounds and all(c == 0 for c in codes)
        if not rec["ok"]:
            rec["error"] = f"rounds={len(ms)} codes={codes}"
    except Exception as e:
        rec["error"] = f"{type(e).__name__}: {e}"
    finally:
        rec["seconds"] = round(time.time() - t0, 1)
        try:
            coord.terminate()
            coord.wait(timeout=20)
        except Exception:
            try:
                coord.kill()
            except Exception:
                pass
        _release(port)
        shutil.rmtree(run_dir, ignore_errors=True)
    return rec


def append(rec, path=RESULTS):
    with _PORT_LOCK:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
