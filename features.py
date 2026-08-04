"""Engineered features for action/pose windows (MediaPipe Pose, 33 joints).

One window = (60 frames, 33 joints, 4=[x,y,z,visibility]). We turn it into a
pose-normalised, translation/scale-invariant feature vector (~174 dims) — a
compact, honest stand-in for the CDP-TreeFusion engineered branch.
"""
import glob
import os

import numpy as np

# MediaPipe Pose left/right joint pairs (shoulders, elbows, wrists, hips, knees, ankles)
LEFT_RIGHT = [(11, 12), (13, 14), (15, 16), (23, 24), (25, 26), (27, 28)]


def extract_features(win: np.ndarray) -> np.ndarray:
    """(60,33,4) -> 1-D float32 feature vector."""
    win = np.asarray(win, dtype=np.float64)
    coords = win[..., :3]          # (T,33,3)
    vis = win[..., 3]              # (T,33)
    T = coords.shape[0]

    # translation-invariant: centre on hip midpoint each frame
    hips = (coords[:, 23, :] + coords[:, 24, :]) / 2.0
    coords_c = coords - hips[:, None, :]
    # scale-invariant: divide by torso length (shoulder-mid to hip-mid)
    sh = (coords[:, 11, :] + coords[:, 12, :]) / 2.0
    torso = np.linalg.norm(sh - hips, axis=1)
    scale = np.nanmedian(torso)
    if not np.isfinite(scale) or scale < 1e-3:
        scale = 1.0
    cn = np.nan_to_num(coords_c / scale, nan=0.0, posinf=0.0, neginf=0.0)

    # kinematics
    vel = np.diff(cn, axis=0)                  # (T-1,33,3)
    speed = np.linalg.norm(vel, axis=2)        # (T-1,33)
    sp_mean, sp_std, sp_max = speed.mean(0), speed.std(0), speed.max(0)   # (33,)
    pos_std = cn[..., :2].std(0)               # (33,2)

    sym = np.array([abs(sp_mean[l] - sp_mean[r]) for (l, r) in LEFT_RIGHT])
    energy = float(speed.sum() / T)
    mean_vis = float(np.nanmean(vis))
    active = float((speed.mean(1) > speed.mean() * 0.5).mean())

    feat = np.concatenate(
        [sp_mean, sp_std, sp_max, pos_std[:, 0], pos_std[:, 1], sym,
         [energy, mean_vis, active]]
    )
    return np.nan_to_num(feat, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32)


def load_dataset(asd_dir: str, td_dir: str):
    """Return X (n,d), y (n,), groups (n,) where group = source recording file."""
    X, y, groups = [], [], []
    for label, d in [(1, asd_dir), (0, td_dir)]:
        for f in sorted(glob.glob(os.path.join(d, "*.npz"))):
            body = np.load(f)["body"]              # (N,60,33,4)
            gname = f"{label}:{os.path.basename(f)}"
            for w in body:
                X.append(extract_features(w))
                y.append(label)
                groups.append(gname)
    return np.asarray(X, dtype=np.float32), np.asarray(y, dtype=np.int64), np.asarray(groups)
