"""Reset a demo federation to round 1 without touching the coordinator's identity.

A run is meant to be repeatable on stage. The coordinator persists its signed state — the audit
chain, the global model, the metrics and the epsilon ledger — so a restart resumes where it left
off. That is correct for a pilot and wrong for a rehearsal, where you want round 1 and epsilon 0
again. This deletes the room state and leaves `coordinator_key.pem` in place, so the federation
keeps its identity and any issued invitation stays valid.

  uv run python reset_demo.py                 # stop the coordinator, clear rooms, restart it
  uv run python reset_demo.py --no-start      # clear only; start the coordinator yourself
  uv run python reset_demo.py --purge-videos  # also drop clips extracted into demo_nodes/
  uv run python reset_demo.py --export audit.zip   # archive the chain before clearing it

Node private keys under demo_nodes/ and nodes/ are removed too: a cleared coordinator has no
record of them, and a stale key only produces a confusing re-enrolment.
"""
import argparse
import glob
import os
import shutil
import subprocess
import sys
import time

import httpx

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.environ.get("FED_STATE_DIR") or os.path.join(HERE, "data", "coordinator_state")


def coordinator_pids(port):
    """Find our own coordinator processes without depending on psutil or pkill."""
    if sys.platform == "win32":
        # single quotes only: double quotes do not survive the hand-off to powershell.exe
        script = ("Get-CimInstance Win32_Process | Where-Object { "
                  "$_.Name -like 'python*' -and $_.CommandLine -like '*coordinator:app*' "
                  f"-and $_.CommandLine -like '*{port}*' }} | ForEach-Object {{ $_.ProcessId }}")
        out = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                             capture_output=True, text=True)
        return [int(line) for line in out.stdout.split() if line.strip().isdigit()]
    out = subprocess.run(["pgrep", "-f", f"coordinator:app.*{port}"], capture_output=True, text=True)
    return [int(line) for line in out.stdout.split() if line.strip().isdigit()]


def stop_coordinator(port):
    pids = coordinator_pids(port)
    for pid in pids:
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
            else:
                os.kill(pid, 15)
        except OSError:
            pass
    return pids


def port_is_free(port):
    """A stale coordinator answering on this port is the failure this whole script exists to
    avoid: it keeps its state in memory, rewrites the file we just deleted, and the reset
    silently does nothing."""
    import socket
    with socket.socket() as sock:
        sock.settimeout(1.0)
        return sock.connect_ex(("127.0.0.1", port)) != 0


def export_bundle(port, out_path, password=None):
    headers = {"X-Fed-Key": password} if password else {}
    url = f"http://localhost:{port}/audit/bundle"
    try:
        response = httpx.get(url, headers=headers, timeout=30.0)
        response.raise_for_status()
    except Exception as e:
        return f"could not export {url}: {e}"
    with open(out_path, "wb") as f:
        f.write(response.content)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8055)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--no-start", action="store_true", help="clear only; do not restart")
    ap.add_argument("--purge-videos", action="store_true",
                    help="also delete clips extracted into demo_nodes/ (keeps synthetic_* files)")
    ap.add_argument("--export", default=None, metavar="PATH",
                    help="download /audit/bundle to PATH before clearing")
    ap.add_argument("--password", default=None, help="read/operator password, if the demo sets one")
    args = ap.parse_args()

    if args.export:
        problem = export_bundle(args.port, args.export, args.password)
        print(f"  export FAILED: {problem}" if problem else f"  exported audit bundle -> {args.export}")
        if problem:
            raise SystemExit("refusing to clear state after a failed export")

    print(f"== stopping coordinator on :{args.port} ==")
    pids = stop_coordinator(args.port)
    print(f"   stopped {len(pids)} process(es)" + (f" {pids}" if pids else ""))
    for _ in range(20):
        if port_is_free(args.port):
            break
        time.sleep(0.5)
    else:
        raise SystemExit(
            f"something is still listening on :{args.port}. It holds the federation state in "
            f"memory and would rewrite the files this script deletes, so the reset would be a "
            f"no-op. Stop it and re-run.")

    print(f"== clearing room state in {STATE_DIR} ==")
    rooms = glob.glob(os.path.join(STATE_DIR, "audit-*.json"))
    for path in rooms:
        os.remove(path)
        print(f"   removed {os.path.basename(path)}")
    if not rooms:
        print("   already clean")
    key = os.path.join(STATE_DIR, "coordinator_key.pem")
    print(f"   kept {os.path.basename(key)}" if os.path.exists(key) else "   no coordinator key yet")

    removed_keys = 0
    for root in ("demo_nodes", "nodes"):
        for path in glob.glob(os.path.join(HERE, root, "**", "node_key.pem"), recursive=True):
            os.remove(path)
            removed_keys += 1
    print(f"   removed {removed_keys} stale node key(s)")

    if args.purge_videos:
        stage = os.path.join(HERE, "demo_nodes")
        dropped = 0
        for path in glob.glob(os.path.join(stage, "**", "*.npz"), recursive=True):
            if not os.path.basename(path).startswith("synthetic_"):
                os.remove(path)
                dropped += 1
        print(f"== purged {dropped} extracted clip(s) from demo_nodes/ (synthetic baseline kept) ==")

    if args.no_start:
        print("\nState cleared. Start the coordinator when you are ready:")
        print(f"  uv run python -m uvicorn coordinator:app --host {args.host} --port {args.port}")
        return

    print("== restarting coordinator ==")
    creation = subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
    subprocess.Popen([sys.executable, "-m", "uvicorn", "coordinator:app",
                      "--host", args.host, "--port", str(args.port), "--log-level", "warning"],
                     cwd=HERE, creationflags=creation)
    url = f"http://localhost:{args.port}"
    for _ in range(60):
        try:
            if httpx.get(url + "/health", timeout=2).status_code == 200:
                schema = httpx.get(url + "/schema", timeout=5).json()
                nxt = schema.get("next_round")
                print(f"   up: {url} · modality {schema.get('modality')} · "
                      f"{schema['n_features']} features · cohort {schema['cohort']} · "
                      f"next round {nxt}")
                if nxt != 1:
                    raise SystemExit(f"the coordinator came back at round {nxt}, not 1 — its state "
                                     f"was not actually cleared. Check FED_STATE_DIR.")
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise SystemExit("coordinator did not come back up")


if __name__ == "__main__":
    main()
