"""One-command recordable demo: prepare data -> start coordinator -> run all nodes.

  uv run python run_demo.py                          # HAR benchmark, 3 nodes, 5 rounds
  uv run python run_demo.py --modality eyegaze       # eye-tracking federation
  uv run python run_demo.py --modality neuro --noniid --prepare
Open the dashboard URL it prints, then start your screen recorder.
"""
import argparse
import os
import subprocess
import sys
import time

import httpx

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def wait_health(url, tries=60):
    for _ in range(tries):
        try:
            if httpx.get(url + "/health", timeout=2).status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nodes", type=int, default=3)
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--trees", type=int, default=40)
    ap.add_argument("--port", type=int, default=8055)
    ap.add_argument("--modality", default=None,
                    help="eyegaze | action | neuro (default: HAR benchmark)")
    ap.add_argument("--noniid", action="store_true", help="skew label mix across nodes")
    ap.add_argument("--prepare", action="store_true", help="force re-prepare the dataset")
    args = ap.parse_args()
    url = f"http://localhost:{args.port}"

    if args.prepare or not os.path.exists(os.path.join(HERE, "data", "meta.json")):
        total = args.nodes * args.rounds * args.trees
        print("== Preparing dataset + centralized baseline ==")
        cmd = [PY, "prepare_data.py", "--nodes", str(args.nodes), "--total-trees", str(total)]
        if args.modality:
            cmd += ["--modality", args.modality]
        if args.noniid:
            cmd += ["--noniid"]
        subprocess.run(cmd, cwd=HERE, check=True)

    print("== Starting coordinator ==")
    coord = subprocess.Popen(
        [PY, "-m", "uvicorn", "coordinator:app", "--host", "0.0.0.0",
         "--port", str(args.port), "--log-level", "warning"], cwd=HERE)
    if not wait_health(url):
        coord.terminate(); sys.exit("coordinator failed to start")
    print(f"   coordinator up — dashboard: {url}")

    print("== Launching nodes (each trains on its OWN local data) ==")
    procs = []
    for n in range(1, args.nodes + 1):
        p = subprocess.Popen(
            [PY, "node.py", "--node-id", f"node_{n}", "--coord", url,
             "--data", f"nodes/node_{n}/data.npz", "--rounds", str(args.rounds),
             "--seed", str(n)], cwd=HERE)
        procs.append(p)
        time.sleep(0.4)
    for p in procs:
        p.wait()

    print(f"\n== Done. Dashboard live at {url} (Ctrl+C to stop) ==")
    print("   Federated vs centralized AUC, signed audit chain, and the")
    print("   exact JSON payload accounting and the 'raw data transferred: 0 bytes' invariant")
    print("   are all on screen.")
    try:
        coord.wait()
    except KeyboardInterrupt:
        coord.terminate()


if __name__ == "__main__":
    main()
