"""One-click showcase: coordinator + dashboard + N desktop client windows.

Presentation helper only. It shells out to the existing entry points and adds no
protocol, privacy or aggregation behaviour of its own:

  * `prepare_data.py`  — only when the dataset is missing, or with --prepare
  * `coordinator:app`  — started with uvicorn, exactly as run_demo.py does
  * `client_app.py`    — one desktop window per partner institution

    uv run python run_showcase.py                       # 3 clients, fresh state
    uv run python run_showcase.py --clients 2 --port 8080
    uv run python run_showcase.py --keep-state          # continue a previous run
    uv run python run_showcase.py --headless            # nodes instead of windows

Ctrl+C stops the coordinator and every window it started.
"""
import argparse
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import webbrowser

import httpx

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
DEFAULT_NAMES = ["HK Children's Hospital", "Shenzhen Partner Clinic", "NGO Screening Centre",
                 "Macau Paediatric Centre", "Guangzhou Rehab Centre"]


def wait_health(url, tries=80):
    for _ in range(tries):
        try:
            if httpx.get(url + "/health", timeout=2).status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def free_port(port):
    """True when nothing is already listening — run_demo.py's default port is often taken."""
    import socket
    with socket.socket() as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", port)) != 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clients", type=int, default=3, help="desktop client windows to open")
    ap.add_argument("--port", type=int, default=8070)
    ap.add_argument("--rounds", type=int, default=6)
    ap.add_argument("--trees", type=int, default=40)
    ap.add_argument("--modality", default=None, help="eyegaze | action | neuro")
    ap.add_argument("--prepare", action="store_true", help="force re-prepare the dataset")
    ap.add_argument("--keep-state", action="store_true",
                    help="reuse the previous coordinator state instead of starting clean")
    ap.add_argument("--headless", action="store_true",
                    help="run CLI nodes instead of desktop windows (no GUI needed)")
    ap.add_argument("--no-browser", action="store_true", help="do not open the dashboard")
    args = ap.parse_args()

    if not free_port(args.port):
        sys.exit(f"port {args.port} is already in use — pass --port with a free one.\n"
                 f"On this machine 8055-8057 belong to a different checkout.")

    url = f"http://localhost:{args.port}"
    env = dict(os.environ)

    # A clean state directory means the demo always starts at round 1 with a full epsilon
    # budget — the usual reason a rehearsed demo looks wrong is a half-spent leftover ledger.
    state_dir = None
    if not args.keep_state:
        state_dir = tempfile.mkdtemp(prefix="gba-df-showcase-")
        env["FED_STATE_DIR"] = state_dir
        print(f"== Fresh coordinator state: {state_dir}")

    if args.prepare or not os.path.exists(os.path.join(HERE, "data", "meta.json")):
        total = max(1, args.clients) * args.rounds * args.trees
        print("== Preparing dataset + centralized baseline ==")
        cmd = [PY, "prepare_data.py", "--nodes", str(args.clients), "--total-trees", str(total)]
        if args.modality:
            cmd += ["--modality", args.modality]
        subprocess.run(cmd, cwd=HERE, check=True)

    print("== Starting coordinator ==")
    coord = subprocess.Popen(
        [PY, "-m", "uvicorn", "coordinator:app", "--host", "127.0.0.1",
         "--port", str(args.port), "--log-level", "warning"], cwd=HERE, env=env)
    if not wait_health(url):
        coord.terminate()
        sys.exit("coordinator failed to start")
    print(f"   dashboard: {url}")
    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    procs = []
    if args.headless:
        print(f"== Launching {args.clients} CLI nodes ==")
        for n in range(1, args.clients + 1):
            procs.append(subprocess.Popen(
                [PY, "node.py", "--node-id", f"node_{n}", "--coord", url,
                 "--data", f"nodes/node_{n}/data.npz", "--rounds", str(args.rounds),
                 "--seed", str(n)], cwd=HERE, env=env))
            time.sleep(0.4)
    else:
        print(f"== Opening {args.clients} client windows ==")
        print("   In each window: pick the data type, choose its nodes/node_N folder,")
        print(f"   confirm the coordinator is {url}, then Connect & start.")
        print("   Suggested display names, one per window:")
        for n in range(1, args.clients + 1):
            print(f"     node_{n}  {DEFAULT_NAMES[(n - 1) % len(DEFAULT_NAMES)]}")
        for n in range(1, args.clients + 1):
            # client_app.py takes --coord and --node-id only; the display name is typed in
            # the window, so no flag is invented here.
            procs.append(subprocess.Popen(
                [PY, "client_app.py", "--coord", url, "--node-id", f"node_{n}"],
                cwd=HERE, env=env))
            time.sleep(1.2)

    print(f"\n== Running. Dashboard live at {url} (Ctrl+C to stop everything) ==")
    try:
        if args.headless:
            for p in procs:
                p.wait()
            print("\n== Nodes finished. Dashboard still live; Ctrl+C to stop. ==")
        coord.wait()
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs + [coord]:
            try:
                p.send_signal(signal.SIGTERM)
            except Exception:
                pass
        for p in procs + [coord]:
            try:
                p.wait(timeout=5)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass
        if state_dir:
            print(f"   showcase state left in {state_dir} (delete when finished)")


if __name__ == "__main__":
    main()
