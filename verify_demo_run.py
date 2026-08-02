"""Rehearse the demo end to end and report what the audience will actually see.

Answers two questions a rehearsal has to settle before it is performed in front of people:
how reliably the federated curve rises and clears the pooled-centralized reference, and whether
uploading the screened clips moves the number by more than the run-to-run noise. Both arms use
the real node path (`node.py` against a real coordinator), just on an isolated port and state
directory so the live demo on :8055 is untouched.

  uv run python verify_demo_run.py                 # 3 repeats per arm
  uv run python verify_demo_run.py --repeats 5
"""
import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

import httpx

HERE = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(HERE, ".venv", "Scripts", "python.exe")
if not os.path.exists(PY):
    PY = sys.executable
CLIPS = os.path.join(HERE, "demo_videos", "npz")

# The on-stage upload plan, mirroring the BATCHES const in static/client_batchimport.js so this
# rehearses the arrangement that will actually be performed. Five of the eleven clips are absent
# deliberately: td_02/td_04/td_05 paint limbs outside the camera frame and must not be shown, and
# asd_06 is 38.7 s. See demo_videos/BATCHES.md and rehearsal_studies/clip_pose_quality/.
BATCHES = {1: ("asd_01", "td_01"), 2: ("asd_03", "td_03"), 3: ("asd_02", "asd_04")}


def stage_arm(root, with_clips):
    """A node tree per arm: the staged baseline, optionally plus the screened clips."""
    shutil.rmtree(root, ignore_errors=True)
    for node in ("node_1", "node_2", "node_3"):
        src = os.path.join(HERE, "demo_nodes", node)
        dst = os.path.join(root, node)
        os.makedirs(dst, exist_ok=True)
        for cls in ("ASD", "TD"):
            source = os.path.join(src, cls)
            if not os.path.isdir(source):
                continue
            os.makedirs(os.path.join(dst, cls), exist_ok=True)
            for name in os.listdir(source):
                if name.startswith("synthetic_") and name.endswith(".npz"):
                    shutil.copy2(os.path.join(source, name), os.path.join(dst, cls, name))
    if not with_clips:
        return
    for node, clips in BATCHES.items():
        for clip in clips:
            cls = clip.split("_")[0]
            src = os.path.join(CLIPS, cls, f"upload_{clip}.npz")
            if not os.path.isfile(src):
                continue
            target = os.path.join(root, f"node_{node}", cls.upper())
            os.makedirs(target, exist_ok=True)
            shutil.copy2(src, os.path.join(target, f"upload_{clip}.npz"))


def run_once(stage, port, state):
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
        nodes = [subprocess.Popen(
            [PY, "node.py", "--node-id", f"node_{n}", "--coord", url,
             "--folder", os.path.join(stage, f"node_{n}"), "--modality", "action",
             "--rounds", "5", "--seed", str(n)], cwd=HERE,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for n in (1, 2, 3)]
        for p in nodes:
            p.wait(timeout=900)
        status = httpx.get(url + "/status", timeout=15).json()
        return [m["auc"] for m in status["metrics"]], status
    finally:
        coord.terminate()
        try:
            coord.wait(timeout=15)
        except Exception:
            coord.kill()
        for path in (stage,):
            for node in ("node_1", "node_2", "node_3"):
                key = os.path.join(path, node, "node_key.pem")
                if os.path.exists(key):
                    os.remove(key)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--port", type=int, default=8410)
    args = ap.parse_args()
    work = tempfile.mkdtemp(prefix="gba-df-verify-")
    n_clips = sum(len(v) for v in BATCHES.values())
    arms = {"baseline only": False, f"baseline + {n_clips} clips": True}
    results = {}
    try:
        for label, with_clips in arms.items():
            stage = os.path.join(work, label.replace(" ", "_").replace("+", "p"))
            stage_arm(stage, with_clips)
            rows = sum(len(os.listdir(os.path.join(stage, n, c)))
                       for n in ("node_1", "node_2", "node_3") for c in ("ASD", "TD")
                       if os.path.isdir(os.path.join(stage, n, c)))
            print(f"\n=== {label} ({rows} files staged) ===")
            curves = []
            for i in range(args.repeats):
                curve, status = run_once(stage, args.port + i, os.path.join(work, f"st_{label}_{i}"))
                curves.append(curve)
                rise = curve[-1] - curve[0]
                dips = sum(1 for a, b in zip(curve, curve[1:]) if b < a - 0.005)
                print(f"  run {i+1}: " + " → ".join(f"{v:.3f}" for v in curve) +
                      f"   rise {rise:+.3f}   visible dips {dips}")
            results[label] = curves
            finals = [c[-1] for c in curves]
            print(f"  final: mean {statistics.mean(finals):.3f}" +
                  (f" ± {statistics.stdev(finals):.3f}" if len(finals) > 1 else ""))
        central = json.load(open(os.path.join(HERE, "data", "meta.json"),
                                 encoding="utf-8"))["centralized"]["auc"]
        print(f"\n=== verdict ===")
        print(f"pooled-centralized reference: {central:.3f}")
        for label, curves in results.items():
            finals = [c[-1] for c in curves]
            above = sum(1 for f in finals if f > central)
            print(f"  {label:<22} final {statistics.mean(finals):.3f} · "
                  f"{above}/{len(finals)} runs above the reference")
        a, b = (results[k] for k in arms)
        fa = [c[-1] for c in a]
        fb = [c[-1] for c in b]
        delta = statistics.mean(fb) - statistics.mean(fa)
        noise = statistics.stdev(fa) if len(fa) > 1 else float("nan")
        print(f"\n  clips move the final AUC by {delta:+.3f}; run-to-run noise is ±{noise:.3f}")
        print("  -> " + ("larger than the noise" if abs(delta) > noise
                         else "SMALLER THAN THE NOISE — do not present the clips as moving the score"))
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
