"""Live-harness runner: same approach as verify_demo_run.py (isolated FED_STATE_DIR,
real coordinator on a private port, three real node.py processes), but the staging is
configurable so arms can be compared. Ports 8500+. Never touches :8055.

  python run_real.py --spec spec.json --repeats 4 --port 8500 --out results_real.json
"""
import argparse, json, os, shutil, statistics, subprocess, sys, tempfile, time
import httpx

REPO = r"D:\agent\dean\0803\datademo"
SCRATCH = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(REPO, ".venv", "Scripts", "python.exe")
CLIPS = os.path.join(REPO, "demo_videos", "npz")
CLIP_CLASS = {}
for _c in ("asd", "td"):
    for _n in sorted(os.listdir(os.path.join(CLIPS, _c))):
        if _n.endswith(".npz"):
            CLIP_CLASS[_n] = _c


def stage_arm(root, per_class, assign, prefix=""):
    """assign: {node_index: [clip filenames]}. Baseline synthetic comes from base_<pc>."""
    shutil.rmtree(root, ignore_errors=True)
    for n in (1, 2, 3):
        src = os.path.join(SCRATCH, f"base_{per_class}", f"node_{n}")
        dst = os.path.join(root, f"node_{n}")
        for cls in ("ASD", "TD"):
            os.makedirs(os.path.join(dst, cls), exist_ok=True)
            for name in sorted(os.listdir(os.path.join(src, cls))):
                if name.startswith("synthetic_") and name.endswith(".npz"):
                    shutil.copy2(os.path.join(src, cls, name), os.path.join(dst, cls, name))
        for name in assign.get(str(n), assign.get(n, [])):
            cls = CLIP_CLASS[name]
            shutil.copy2(os.path.join(CLIPS, cls, name),
                         os.path.join(dst, cls.upper(), prefix + name))


def run_once(stage, port, state):
    shutil.rmtree(state, ignore_errors=True)
    os.makedirs(state, exist_ok=True)
    env = {**os.environ, "FED_STATE_DIR": state}
    coord = subprocess.Popen([PY, "-m", "uvicorn", "coordinator:app", "--host", "127.0.0.1",
                              "--port", str(port), "--log-level", "warning"],
                             cwd=REPO, env=env,
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
             "--rounds", "5", "--seed", str(n)], cwd=REPO,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for n in (1, 2, 3)]
        for p in procs:
            p.wait(timeout=900)
        status = httpx.get(url + "/status", timeout=15).json()
        return status["metrics"]
    finally:
        coord.terminate()
        try:
            coord.wait(timeout=15)
        except Exception:
            coord.kill()
        for n in ("node_1", "node_2", "node_3"):
            k = os.path.join(stage, n, "node_key.pem")
            if os.path.exists(k):
                os.remove(k)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--repeats", type=int, default=4)
    ap.add_argument("--port", type=int, default=8500)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    spec = json.load(open(args.spec, encoding="utf-8"))
    work = tempfile.mkdtemp(prefix="mit-real-", dir=SCRATCH)
    results = {}
    try:
        for arm in spec:
            label = arm["label"]
            stage = os.path.join(work, label.replace(" ", "_").replace("+", "p").replace("/", "-"))
            stage_arm(stage, arm["per_class"], arm.get("assign", {}), arm.get("prefix", ""))
            files = sum(len(os.listdir(os.path.join(stage, f"node_{n}", c)))
                        for n in (1, 2, 3) for c in ("ASD", "TD"))
            print(f"\n=== {label} ({files} files) ===", flush=True)
            runs = []
            for i in range(args.repeats):
                t0 = time.time()
                try:
                    metrics = run_once(stage, args.port + i, os.path.join(work, f"st_{len(results)}_{i}"))
                    ok = len(metrics) == 5
                except Exception as e:
                    print(f"  run {i+1}: FAILED {type(e).__name__}: {e}", flush=True)
                    runs.append({"ok": False, "error": f"{type(e).__name__}: {e}"})
                    continue
                aucs = [m["auc"] for m in metrics]
                runs.append({"ok": ok, "metrics": metrics})
                print(f"  run {i+1} ({time.time()-t0:.0f}s, {len(metrics)} rounds): "
                      + " -> ".join(f"{v:.3f}" for v in aucs), flush=True)
            results[label] = runs
            fin = [r["metrics"][-1]["auc"] for r in runs if r.get("ok")]
            if fin:
                sd = statistics.stdev(fin) if len(fin) > 1 else 0.0
                print(f"  final AUC {statistics.mean(fin):.3f} +- {sd:.3f}  "
                      f"({sum(1 for f in fin if f > 0.7782143947877431)}/{len(fin)} above ref)",
                      flush=True)
            json.dump(results, open(args.out, "w"), indent=1)
    finally:
        json.dump(results, open(args.out, "w"), indent=1)
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
