"""GBA-DF desktop node client (pywebview).

A partner runs this on their own machine. Flow: pick a data modality -> choose the folder of
raw recordings (or convert action videos to pose NPZ locally in the web view) -> enter node +
coordinator info -> connect. From then on it does exactly what node.py does — extracts features
LOCALLY and uploads only masked count vectors — but with live, screen-recordable progress. Raw
data never leaves this machine.

  uv sync --extra client
  uv run python client_app.py                 # opens the desktop window
  uv run python client_app.py --selftest      # headless API smoke test (no GUI)
"""
import argparse
import os
import re
import tempfile
import threading
import time

import numpy as np

import modalities as mods
import node_core as nc

HERE = os.path.dirname(os.path.abspath(__file__))


class Api:
    """Bridge exposed to the web UI as `window.pywebview.api`. Every method returns a
    JSON-safe dict; the node loop runs in a background thread and the UI polls poll()."""

    def __init__(self, default_coord="http://localhost:8055", default_node="node_1"):
        self._lock = threading.Lock()
        self._log = []
        self._state = {"running": False, "done": False, "error": None, "summary": None}
        self._stop = False
        self._thread = None
        self._demo_seed = 100
        self._default_coord = default_coord
        self._default_node = default_node

    # ---- discovery ----
    def list_modalities(self):
        return [m.info() for m in mods.MODALITIES.values()]

    def defaults(self):
        return {"coord": self._default_coord, "node_id": self._default_node}

    def default_node_names(self):
        from node import NAMES
        return NAMES

    # ---- data selection ----
    def pick_folder(self):
        import webview
        win = webview.windows[0]
        res = win.create_file_dialog(webview.FOLDER_DIALOG)
        if not res:
            return {"ok": False, "cancelled": True}
        return {"ok": True, "path": res[0]}

    def scan_folder(self, modality, path):
        try:
            if not path or not os.path.isdir(path):
                return {"ok": False, "error": "folder not found"}
            m = mods.get(modality)
            X, y, g = m.extract_folder(path)
            if len(X) == 0:
                return {"ok": False, "error": "no usable recordings found — check the file "
                        "format and that recordings sit under asd/ and td/ subfolders"}
            y = np.asarray(y).astype(str)
            labels, counts = np.unique(y, return_counts=True)
            return {"ok": True, "path": path, "n_files": len(set(g.tolist())),
                    "n_samples": int(X.shape[0]), "n_features": int(X.shape[1]),
                    "labels": dict(zip(labels.tolist(), counts.tolist()))}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def save_pose_npz(self, root, label, filename, body):
        """Persist browser-extracted MediaPipe pose landmarks as an action-modality NPZ.

        MediaPipe inference stays in the web view; this bridge only validates the numeric
        result and uses the project's existing NumPy dependency to write a compressed,
        atomic ``body: (T, 33, 4)`` file. The source video itself never crosses the bridge.
        """
        tmp = None
        try:
            if not root or not os.path.isdir(root):
                return {"ok": False, "error": "output folder not found"}
            label = str(label).upper()
            if label not in {"ASD", "TD"}:
                return {"ok": False, "error": "label must be ASD or TD"}
            arr = np.asarray(body, dtype=np.float32)
            if arr.ndim != 3 or arr.shape[1:] != (33, 4):
                return {"ok": False, "error": "body must have shape (T, 33, 4)"}
            if not 2 <= arr.shape[0] <= 12000:
                return {"ok": False, "error": "body must contain 2 to 12000 sampled frames"}
            if not np.isfinite(arr).all():
                return {"ok": False, "error": "body contains non-finite values"}

            stem = os.path.splitext(os.path.basename(str(filename)))[0]
            stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-") or "video"
            out_dir = os.path.join(os.path.abspath(root), label.lower())
            os.makedirs(out_dir, exist_ok=True)
            out = os.path.join(out_dir, f"{stem}.npz")
            suffix = 2
            while os.path.exists(out):
                out = os.path.join(out_dir, f"{stem}_{suffix}.npz")
                suffix += 1

            fd, tmp = tempfile.mkstemp(prefix=f".{stem}_", suffix=".npz", dir=out_dir)
            os.close(fd)
            np.savez_compressed(tmp, body=arr)
            os.replace(tmp, out)
            tmp = None
            return {"ok": True, "path": out, "root": os.path.abspath(root),
                    "label": label, "frames": int(arr.shape[0])}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}
        finally:
            if tmp and os.path.exists(tmp):
                try:
                    os.unlink(tmp)
                except OSError:
                    pass

    def generate_demo(self, modality, n_per_class=40):
        """Make a folder of SYNTHETIC demo recordings for partners who want to try the flow
        without real data. Clearly synthetic; same format a real partner's data would take."""
        try:
            m = mods.get(modality)
            out = os.path.join(HERE, "data", "client_demo", modality)
            with self._lock:
                self._demo_seed += 1
                seed = self._demo_seed
            made = m.synth_folder(out, int(n_per_class), seed=seed)
            return {"ok": True, "path": out, "files": made, "synthetic": True}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    # ---- connection ----
    def test_connect(self, coord, modality=None, key=None):
        try:
            sch = nc.fetch_schema(coord, key=key or None)
            fed_mod = sch.get("modality")
            compatible = (fed_mod is None or modality is None or fed_mod == modality)
            return {"ok": True, "modality": fed_mod, "modality_info": sch.get("modality_info"),
                    "n_features": sch["n_features"], "classes": sch["classes"],
                    "cohort": sch["cohort"], "dp": sch["dp"],
                    "epsilon_budget": sch.get("epsilon_budget"),
                    "primary_metric": sch.get("primary_metric"),
                    "next_round": sch.get("next_round", 1), "compatible": compatible,
                    "invitation_required": bool(sch.get("invitation_required"))}
        except Exception as e:
            return {"ok": False, "error": f"cannot reach coordinator: {e}"}

    # ---- run ----
    def start(self, cfg):
        with self._lock:
            if self._state["running"]:
                return {"ok": False, "error": "a run is already in progress"}
            self._log = []
            self._state = {"running": True, "done": False, "error": None, "summary": None}
            self._stop = False
        self._thread = threading.Thread(target=self._run, args=(cfg,), daemon=True)
        self._thread.start()
        return {"ok": True}

    def _log_line(self, m):
        with self._lock:
            self._log.append(m)

    def _run(self, cfg):
        try:
            key = cfg.get("key") or None
            sch = nc.fetch_schema(cfg["coord"], key=key)
            X, y, key_dir = nc.load_local(sch, folder=cfg.get("folder"), data=cfg.get("data"),
                                          modality=cfg.get("modality"), on_log=self._log_line)
            invitation = cfg.get("invitation") or None
            if invitation is not None and not isinstance(invitation, dict):
                raise ValueError("the imported invitation is not a valid JSON object")
            summ = nc.run_node(
                cfg["coord"], cfg["node_id"], cfg.get("name") or cfg["node_id"], X, y, sch,
                rounds=int(cfg.get("rounds", 5)), seed=int(cfg.get("seed", 1)), key_dir=key_dir,
                on_log=self._log_line, should_stop=lambda: self._stop,
                on_round=lambda s: self._set_summary(s), key=key, invitation=invitation)
            with self._lock:
                self._state.update(running=False, done=True, summary=summ,
                                   error=None if summ.get("ok") else summ.get("error"))
        except ValueError as e:                          # validation failure -> friendly
            self._log_line(str(e))
            with self._lock:
                self._state.update(running=False, done=True, error=str(e))
        except Exception as e:
            self._log_line(f"error: {e}")
            with self._lock:
                self._state.update(running=False, done=True, error=f"{type(e).__name__}: {e}")

    def _set_summary(self, s):
        with self._lock:
            self._state["summary"] = s

    def poll(self):
        with self._lock:
            return {"state": dict(self._state), "log": list(self._log)}

    def stop(self):
        self._stop = True
        return {"ok": True}


def _selftest():
    """Headless check of every API method except the native folder dialog."""
    api = Api()
    print("modalities:", [m["key"] for m in api.list_modalities()])
    d = api.generate_demo("eyegaze", n_per_class=8)
    print("generate_demo:", d)
    print("scan_folder:", api.scan_folder("eyegaze", d["path"]))
    with tempfile.TemporaryDirectory() as out:
        body = np.zeros((8, 33, 4), dtype=np.float32)
        body[..., 3] = 0.9
        saved = api.save_pose_npz(out, "ASD", "sample video.mp4", body.tolist())
        assert saved["ok"] and os.path.exists(saved["path"]), saved
        assert np.load(saved["path"])["body"].shape == (8, 33, 4)
        scanned = api.scan_folder("action", out)
        assert scanned["ok"] and scanned["labels"] == {"ASD": 1}, scanned
        assert not api.save_pose_npz(out, "UNKNOWN", "bad.mp4", body.tolist())["ok"]
        assert not api.save_pose_npz(out, "TD", "bad.mp4", [[[0, 0, 0, 1]]])["ok"]
        print("save_pose_npz:", {"ok": True, "frames": saved["frames"],
                                  "scan": scanned["labels"]})
    print("test_connect(bad):", api.test_connect("http://localhost:1")["ok"])
    print("selftest OK")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true", help="run headless API checks, no GUI")
    ap.add_argument("--coord", default="http://localhost:8055", help="prefill coordinator URL")
    ap.add_argument("--node-id", default="node_1", help="prefill node id")
    args = ap.parse_args()
    if args.selftest:
        _selftest(); return

    import webview
    api = Api(default_coord=args.coord, default_node=args.node_id)
    webview.create_window(
        "GBA-DF Federated Node", url=os.path.join(HERE, "static", "client.html"),
        js_api=api, width=1040, height=760, min_size=(880, 620))
    webview.start()


if __name__ == "__main__":
    main()
