"""GBA-DF desktop node client (pywebview).

A partner runs this on their own machine. Flow: pick a data modality -> choose the folder of
raw recordings (or convert action videos to pose NPZ locally in the web view) -> enter node +
coordinator info -> connect. From then on it does exactly what node.py does — extracts features
LOCALLY and uploads only masked count vectors — but with live, screen-recordable progress. Raw
data never leaves this machine.

  uv sync --extra client
  uv run python client_app.py                 # opens the town desktop window
  uv run python client_app.py --ui classic    # opens the classic sharing window
  uv run python client_app.py --selftest      # headless API smoke test (no GUI)
"""
import argparse
import os
import re
import tempfile
import threading
import time
from pathlib import Path

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
        # Browser-extracted pose files default to one private, per-process workspace.
        # TemporaryDirectory removes it when the desktop client exits; users can opt
        # into a persistent folder explicitly through the advanced video settings.
        self._video_temp = tempfile.TemporaryDirectory(prefix="gba-df-video-")
        self._video_output = self._video_temp.name

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
        dialog_kind = (webview.FileDialog.FOLDER if hasattr(webview, "FileDialog")
                       else webview.FOLDER_DIALOG)
        res = win.create_file_dialog(dialog_kind)
        if not res:
            return {"ok": False, "cancelled": True}
        return {"ok": True, "path": res[0]}

    def video_output(self):
        path = os.path.abspath(self._video_output)
        return {"ok": True, "path": path,
                "temporary": path == os.path.abspath(self._video_temp.name)}

    def pick_video_output(self):
        selected = self.pick_folder()
        if not selected.get("ok"):
            return selected
        self._video_output = os.path.abspath(selected["path"])
        return self.video_output()

    def reset_video_output(self):
        os.makedirs(self._video_temp.name, exist_ok=True)
        self._video_output = self._video_temp.name
        return self.video_output()

    def scan_folder(self, modality, path):
        try:
            if not path or not os.path.isdir(path):
                return {"ok": False, "error": "folder not found"}
            m = mods.get(modality)
            X, y, g = m.extract_folder(path)
            if len(X) == 0:
                return {"ok": False, "error": "no usable recordings found — check the file "
                        "format"}
            y = np.asarray(y).astype(str)
            g = np.asarray(g).astype(str)
            labels, counts = np.unique(y, return_counts=True)
            label_files = {str(label): int(len(np.unique(g[y == label]))) for label in labels}
            unlabeled = int(label_files.pop("", 0))
            label_counts = dict(zip(labels.tolist(), counts.tolist()))
            label_counts.pop("", None)
            return {"ok": True, "path": path, "n_files": len(set(g.tolist())),
                    "n_samples": int(X.shape[0]), "n_features": int(X.shape[1]),
                    "labels": label_counts,
                    "label_files": label_files, "unlabeled_files": unlabeled,
                    "training_ready": unlabeled == 0}
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
                    "label": label, "frames": int(arr.shape[0]),
                    "points": int(arr.shape[1]), "bytes": os.path.getsize(out)}
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
    def test_connect(self, coord, modality=None, key=None, invitation=None):
        try:
            sch = nc.fetch_schema(coord, key=key or None)
            identity = {}
            if isinstance(invitation, dict):
                # Surface a wrong coordinator here, at "Test connection", rather than at the
                # first upload. A mismatch is a hard failure, not a warning.
                try:
                    identity = nc.check_coordinator_identity(coord, invitation, key=key or None)
                except RuntimeError as e:
                    return {"ok": False, "error": str(e)}
            fed_mod = sch.get("modality")
            compatible = (fed_mod is None or modality is None or fed_mod == modality)
            return {"ok": True, "modality": fed_mod, "modality_info": sch.get("modality_info"),
                    "pinned": bool(identity.get("pinned")),
                    "pin_warning": identity.get("warning", ""),
                    "n_features": sch["n_features"], "classes": sch["classes"],
                    "cohort": sch["cohort"], "dp": sch["dp"],
                    "secure_aggregation": bool(sch.get("secure_aggregation")),
                    "privacy_mode": sch.get("privacy_mode"),
                    "solo_shared": bool(sch.get("solo_shared")),
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
    temporary_output = api.video_output()
    assert temporary_output["ok"] and temporary_output["temporary"]
    assert os.path.isdir(temporary_output["path"])
    print("video_output:", {"temporary": True, "exists": True})
    print("modalities:", [m["key"] for m in api.list_modalities()])
    d = api.generate_demo("eyegaze", n_per_class=8)
    print("generate_demo:", d)
    print("scan_folder:", api.scan_folder("eyegaze", d["path"]))
    with tempfile.TemporaryDirectory() as out:
        body = np.zeros((8, 33, 4), dtype=np.float32)
        body[..., 3] = 0.9
        saved = api.save_pose_npz(temporary_output["path"], "ASD",
                                  "sample video.mp4", body.tolist())
        assert saved["ok"] and os.path.exists(saved["path"]), saved
        assert saved["root"] == temporary_output["path"]
        assert saved["points"] == 33 and saved["bytes"] > 0
        assert np.load(saved["path"])["body"].shape == (8, 33, 4)
        scanned = api.scan_folder("action", temporary_output["path"])
        assert scanned["ok"] and scanned["labels"] == {"ASD": 1}, scanned
        api._video_output = out
        assert not api.video_output()["temporary"]
        assert api.reset_video_output()["temporary"]
        assert not api.save_pose_npz(out, "UNKNOWN", "bad.mp4", body.tolist())["ok"]
        assert not api.save_pose_npz(out, "TD", "bad.mp4", [[[0, 0, 0, 1]]])["ok"]
        print("save_pose_npz:", {"ok": True, "frames": saved["frames"],
                                  "scan": scanned["labels"]})
    game_index = Path(HERE, "static", "game", "index.html")
    game_shell = game_index.read_text(encoding="utf-8")
    assert "GBA-DF · 联邦小镇" in game_shell and "game-root" in game_shell
    assert Path(HERE, "static", "client.html").is_file()
    print("game_shell:", {"ok": True, "client_mode": True})
    print("test_connect(bad):", api.test_connect("http://localhost:1")["ok"])
    print("selftest OK")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true", help="run headless API checks, no GUI")
    ap.add_argument("--coord", default="http://localhost:8055", help="prefill coordinator URL")
    ap.add_argument("--node-id", default="node_1", help="prefill node id")
    ap.add_argument("--ui", choices=("town", "classic"), default="town",
                    help="desktop interface: town game (default) or classic sharing wizard")
    args = ap.parse_args()
    if args.selftest:
        _selftest(); return

    import webview
    api = Api(default_coord=args.coord, default_node=args.node_id)
    if args.ui == "classic":
        window_title = "GBA-DF Federated Node"
        window_url = Path(HERE, "static", "client.html").resolve().as_uri() + "?theme=classic"
    else:
        window_title = "GBA-DF Federated Town"
        window_url = Path(HERE, "static", "game", "index.html").resolve().as_uri() + "?mode=client"
    webview.create_window(
        window_title, url=window_url,
        js_api=api, width=1180, height=780, min_size=(920, 640))
    webview.start()


if __name__ == "__main__":
    main()
