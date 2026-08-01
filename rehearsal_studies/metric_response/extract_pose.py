"""Sample demo clips at 4 fps, run MediaPipe Pose, write body:(T,33,4) float32 NPZ.

Matches the contract enforced by client_app.py::save_pose_npz:
  - float32, shape (T, 33, 4) = (x, y, z, visibility)
  - 2 <= T <= 12000
  - all values finite
Output layout mirrors the input: <out>/asd/<stem>.npz, <out>/td/<stem>.npz
"""
import os
import sys
import glob

import cv2
import numpy as np
import mediapipe as mp

TARGET_FPS = 4.0
MAX_FRAMES = 12000


def extract(video_path, pose):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None, "cannot open"
    src_fps = cap.get(cv2.CAP_PROP_FPS)
    if not src_fps or not np.isfinite(src_fps) or src_fps <= 0:
        src_fps = 30.0
    step = max(1, int(round(src_fps / TARGET_FPS)))
    frames = []
    last = None
    idx = 0
    read_total = 0
    detected = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % step == 0:
            read_total += 1
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            res = pose.process(rgb)
            if res.pose_landmarks is not None:
                lm = np.array([[p.x, p.y, p.z, p.visibility]
                               for p in res.pose_landmarks.landmark], dtype=np.float32)
                last = lm
                detected += 1
                frames.append(lm)
            elif last is not None:
                # carry the last valid pose forward so the time base stays uniform
                frames.append(last.copy())
            # frames before the first detection are dropped
        idx += 1
        if len(frames) >= MAX_FRAMES:
            break
    cap.release()
    if len(frames) < 2:
        return None, f"only {len(frames)} usable frames (sampled {read_total}, detected {detected})"
    arr = np.asarray(frames, dtype=np.float32)
    arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32)
    meta = {"src_fps": round(float(src_fps), 3), "step": step,
            "sampled": read_total, "detected": detected,
            "duration_s": round(idx / src_fps, 2), "T": int(arr.shape[0])}
    return arr, meta


def main():
    src_root = sys.argv[1]
    out_root = sys.argv[2]
    mp_pose = mp.solutions.pose
    rows = []
    with mp_pose.Pose(static_image_mode=False, model_complexity=1,
                      min_detection_confidence=0.5, min_tracking_confidence=0.5) as pose:
        for cls in ("asd", "td"):
            in_dir = os.path.join(src_root, cls)
            out_dir = os.path.join(out_root, cls)
            os.makedirs(out_dir, exist_ok=True)
            for vp in sorted(glob.glob(os.path.join(in_dir, "*.mp4"))):
                stem = os.path.splitext(os.path.basename(vp))[0]
                arr, meta = extract(vp, pose)
                if arr is None:
                    print(f"FAIL {cls}/{stem}: {meta}", flush=True)
                    rows.append((cls, stem, None))
                    continue
                assert arr.dtype == np.float32 and arr.ndim == 3 and arr.shape[1:] == (33, 4)
                assert 2 <= arr.shape[0] <= 12000
                assert np.isfinite(arr).all()
                out = os.path.join(out_dir, f"{stem}.npz")
                np.savez_compressed(out, body=arr)
                print(f"OK   {cls}/{stem}: {meta}", flush=True)
                rows.append((cls, stem, meta["T"]))
    print("\nwrote", sum(1 for r in rows if r[2] is not None), "of", len(rows))


if __name__ == "__main__":
    main()
