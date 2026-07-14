"""Multi-modal ingestion for the federation.

The privacy machinery (secure aggregation + central DP + signed audit) is entirely
modality-agnostic: it only ever sees a fixed-width feature matrix X and labels y. What
changes per modality is the FRONT END — how a partner's folder of raw recordings becomes
that feature matrix. This module is that front end, one plug per signal type:

  eyegaze : eye-tracking gaze traces (CSV per recording)  -> fixation/saccade features
  action  : browser-converted video or MediaPipe .npz per clip -> kinematic features (features.py)
  neuro   : EEG / fMRI multivariate time-series (.npz/.csv) -> spectral + connectivity features

Each modality declares a FIXED feature width, PUBLIC per-feature bounds (declared a-priori,
never derived from participant data — see dp.py), the task's class labels, and two calls:

  extract_folder(path) -> (X, y, groups)   # read raw files a partner actually has
  synth_folder(out, n, seed, classes=...)  # write realistic raw demo files

The demo path runs through the SAME extractor as real data: synth_folder writes raw files,
extract_folder reads them. So a partner pointing the desktop client at their own folder
exercises byte-for-byte the code path the demo does.

HONESTY: the eyegaze and neuro demo generators produce SYNTHETIC recordings with
class-dependent statistics — they exercise and validate the pipeline end to end, they are
NOT a claim of clinical accuracy on real patients. Only the federated privacy mechanism is
the verified contribution; the front-end extractors here are standard, literature-shaped
summaries, not tuned biomarkers.
"""
import csv
import glob
import json
import os
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


# ------------------------------------------------------------------ helpers
def _list(path, exts):
    out = []
    for ext in exts:
        out += glob.glob(os.path.join(path, "**", f"*{ext}"), recursive=True)
    return sorted(set(out))


def _label_of(fpath, root, classes):
    """Label a file by the first path component under `root` that matches a class,
    else by a class token in the filename, else the first class (unlabeled -> class 0)."""
    rel = os.path.relpath(fpath, root)
    parts = [p.lower() for p in rel.replace("\\", "/").split("/")]
    lc = {c.lower(): c for c in classes}
    for p in parts:
        if p in lc:
            return lc[p]
    stem = os.path.basename(fpath).lower()
    for c in classes:
        if c.lower() in stem:
            return c
    return classes[0]




# ================================================================== EYE-GAZE
# A gaze CSV: columns for x, y (screen-normalised 0..1), optional pupil, optional t.
# One recording (one CSV) -> one 32-dim fixation/saccade feature row.
GAZE_DIM = 32
GAZE_CLASSES = ["TD", "ASD"]


def _find_col(header, *names):
    low = [h.strip().lower() for h in header]
    for n in names:
        if n in low:
            return low.index(n)
    return None


def _read_gaze_csv(fpath):
    with open(fpath, newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        return np.zeros((0, 2)), None
    header = rows[0]
    xi = _find_col(header, "x", "gaze_x", "gazex", "norm_x")
    yi = _find_col(header, "y", "gaze_y", "gazey", "norm_y")
    pi = _find_col(header, "pupil", "pupil_diameter", "pupildiameter")
    if xi is None or yi is None:            # no header -> assume first two cols are x,y
        data = rows
        xi, yi, pi = 0, 1, (2 if len(rows[0]) > 2 else None)
    else:
        data = rows[1:]
    xs, ys, ps = [], [], []
    for r in data:
        try:
            xs.append(float(r[xi])); ys.append(float(r[yi]))
            ps.append(float(r[pi]) if pi is not None and pi < len(r) else np.nan)
        except (ValueError, IndexError):
            continue
    xy = np.column_stack([xs, ys]) if xs else np.zeros((0, 2))
    return xy, (np.array(ps) if ps else None)


def _gaze_features(xy, pupil):
    """I-VT-style fixation/saccade + spatial-attention summary -> GAZE_DIM vector."""
    f = np.zeros(GAZE_DIM, dtype=np.float64)
    n = xy.shape[0]
    if n < 3:
        return f.astype(np.float32)
    valid = np.isfinite(xy).all(1)
    xy = xy[valid]
    n = xy.shape[0]
    if n < 3:
        return f.astype(np.float32)
    d = np.linalg.norm(np.diff(xy, axis=0), axis=1)      # per-sample displacement
    vel = d * 30.0                                        # assume ~30 Hz -> velocity proxy
    thr = 0.02                                            # saccade threshold (normalised units)
    is_sacc = vel > thr * 30.0
    # fixation runs = maximal stretches of non-saccade samples
    fix_durs, run = [], 0
    for s in is_sacc:
        if s:
            if run:
                fix_durs.append(run); run = 0
        else:
            run += 1
    if run:
        fix_durs.append(run)
    fix_durs = np.array(fix_durs) if fix_durs else np.array([0])
    sacc_amp = d[is_sacc] if is_sacc.any() else np.array([0.0])

    cx, cy = xy[:, 0], xy[:, 1]
    center = (np.abs(cx - 0.5) < 0.15) & (np.abs(cy - 0.5) < 0.15)   # central AOI dwell
    quad = [
        ((cx < 0.5) & (cy < 0.5)).mean(), ((cx >= 0.5) & (cy < 0.5)).mean(),
        ((cx < 0.5) & (cy >= 0.5)).mean(), ((cx >= 0.5) & (cy >= 0.5)).mean(),
    ]
    vals = [
        len(fix_durs), fix_durs.mean(), fix_durs.std(), fix_durs.max(),
        float((~is_sacc).mean()),                        # fixation-sample fraction
        is_sacc.sum(), sacc_amp.mean(), sacc_amp.std(), sacc_amp.max(),
        vel.mean(), vel.std(), np.percentile(vel, 95),
        d.sum(),                                         # scanpath length
        cx.std(), cy.std(),                              # gaze dispersion
        cx.mean(), cy.mean(), np.median(cx), np.median(cy),
        (cx.max() - cx.min()) * (cy.max() - cy.min()),  # bounding-box area
        center.mean(), *quad,
        float(np.isnan(pupil).mean()) if pupil is not None else 0.0,
        np.nanmean(pupil) if pupil is not None and np.isfinite(pupil).any() else 0.0,
        np.nanstd(pupil) if pupil is not None and np.isfinite(pupil).any() else 0.0,
        n,                                              # samples (valid)
    ]
    vals = np.array(vals[:GAZE_DIM - 3], dtype=np.float64)
    f[:len(vals)] = np.nan_to_num(vals)
    # transitions between AOIs (re-fixation / attention shifting)
    aoi = (cx > 0.5).astype(int) * 2 + (cy > 0.5).astype(int)
    f[-3] = np.count_nonzero(np.diff(aoi))
    f[-2] = float((d < 0.005).mean())                   # micro-movement fraction
    f[-1] = float((d > 0.1).mean())                     # long-jump fraction
    return np.nan_to_num(f).astype(np.float32)


def _gaze_extract(path):
    files = _list(path, [".csv"])
    X, y, g = [], [], []
    for fp in files:
        xy, pup = _read_gaze_csv(fp)
        X.append(_gaze_features(xy, pup))
        y.append(_label_of(fp, path, GAZE_CLASSES))
        g.append(os.path.relpath(fp, path))
    if not X:
        return np.zeros((0, GAZE_DIM), np.float32), np.array([], object), np.array([], object)
    return np.vstack(X), np.array(y, object), np.array(g, object)


def _gaze_synth(out, n_per_class, seed, classes=None):
    classes = classes or GAZE_CLASSES
    rng = np.random.default_rng(seed)
    made = 0
    for c in classes:
        d = os.path.join(out, c)
        os.makedirs(d, exist_ok=True)
        asd = c.upper() == "ASD"
        for k in range(n_per_class):
            T = int(rng.integers(600, 1200))             # ~20-40 s at 30 Hz
            # graded, OVERLAPPING severity so the classes are separable but not trivially
            # so (realistic ~0.85 ceiling, leaving room for DP to cost something).
            sev = np.clip(rng.normal(0.68 if asd else 0.32, 0.22), 0, 1)
            # higher sev -> fewer, shorter fixations, more scattered (reduced central attention)
            n_fix = int(round(18 - 9 * sev + rng.normal(0, 2)))
            n_fix = max(4, n_fix)
            xy = np.zeros((T, 2))
            t = 0
            for _ in range(n_fix):
                dur = int(max(6, rng.normal(45 - 30 * sev, 8)))
                spread = 0.10 + 0.30 * sev               # central (low sev) -> scattered (high)
                cx = np.clip(rng.normal(0.5, spread), 0, 1)
                cy = np.clip(rng.normal(0.5, spread), 0, 1)
                seg = min(dur, T - t)
                if seg <= 0:
                    break
                jit = 0.012 + 0.012 * sev
                xy[t:t + seg] = [cx, cy] + rng.normal(0, jit, (seg, 2))
                t += seg
            if t < T:
                xy[t:] = xy[max(t - 1, 0)]
            xy = np.clip(xy, 0, 1)
            pupil = rng.normal(3.5, 0.4, T)
            path_csv = os.path.join(d, f"{c.lower()}_{seed}_{k:03d}.csv")
            with open(path_csv, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["t", "x", "y", "pupil"])
                for i in range(T):
                    w.writerow([round(i / 30.0, 3), round(xy[i, 0], 4),
                                round(xy[i, 1], 4), round(pupil[i], 3)])
            made += 1
    return made


# ==================================================================== ACTION
# Body-pose windows in the project's native format: .npz with key 'body' (T,33,4).
# Reuses the engineered kinematic extractor (features.py) -> 174-dim.
from features import extract_features as _pose_features        # noqa: E402

ACTION_DIM = 174
ACTION_CLASSES = ["TD", "ASD"]


def _action_extract(path):
    files = _list(path, [".npz"])
    X, y, g = [], [], []
    for fp in files:
        try:
            z = np.load(fp)
            body = z["body"] if "body" in z else z[z.files[0]]
        except Exception:
            continue
        body = np.asarray(body)
        if body.ndim == 3:                                # single window (T,33,4)
            body = body[None]
        lab = _label_of(fp, path, ACTION_CLASSES)
        gid = os.path.relpath(fp, path)
        for w in body:
            if w.shape[-2:] != (33, 4):
                continue
            X.append(_pose_features(w)); y.append(lab); g.append(gid)
    if not X:
        return np.zeros((0, ACTION_DIM), np.float32), np.array([], object), np.array([], object)
    return np.vstack(X).astype(np.float32), np.array(y, object), np.array(g, object)


def _action_synth(out, n_per_class, seed, classes=None):
    classes = classes or ACTION_CLASSES
    rng = np.random.default_rng(seed + 7)
    made = 0
    for c in classes:
        d = os.path.join(out, c)
        os.makedirs(d, exist_ok=True)
        asd = c.upper() == "ASD"
        for k in range(n_per_class):
            W = int(rng.integers(4, 9))                  # windows per clip file
            # graded overlapping severity: ASD-like clips tend to higher repetitive-motion
            # frequency + limb asymmetry, but the distributions overlap.
            sev = np.clip(rng.normal(0.72 if asd else 0.28, 0.20), 0, 1)
            body = np.zeros((W, 60, 33, 4), dtype=np.float32)
            for wi in range(W):
                base = rng.normal(0, 0.05, (33, 3))
                base[:, 1] += np.linspace(-0.4, 0.4, 33)  # rough vertical layout
                freq = rng.uniform(0.7, 1.3) * (1.0 + 1.3 * sev)
                amp = rng.uniform(0.03, 0.06) * (1.0 + 1.0 * sev)
                t = np.linspace(0, 2 * np.pi * freq, 60)
                for j in range(33):
                    phase = rng.uniform(0, 2 * np.pi)
                    asym = 1.0 + 0.7 * sev if j % 2 == 0 else 1.0
                    xyz = base[j][None] + amp * asym * np.column_stack(
                        [np.sin(t + phase), np.cos(t + phase), 0.3 * np.sin(2 * t)])
                    xyz += rng.normal(0, 0.006, xyz.shape)    # sensor noise -> overlap
                    body[wi, :, j, :3] = xyz
                    body[wi, :, j, 3] = np.clip(rng.normal(0.9, 0.05, 60), 0, 1)
            np.savez_compressed(os.path.join(d, f"{c.lower()}_{seed}_{k:03d}.npz"), body=body)
            made += 1
    return made


# ==================================================================== NEURO
# EEG or fMRI: a multivariate time-series file (.npz with key 'ts' shape (C,T) or (T,C),
# or a CSV of channels x time). One recording -> spectral + functional-connectivity vector.
NEURO_DIM = 48
NEURO_CLASSES = ["TD", "ASD"]
_BANDS = [(1, 4), (4, 8), (8, 13), (13, 30), (30, 45)]     # delta theta alpha beta gamma
_CORR_BINS = np.linspace(-1, 1, 13)                        # 12 histogram bins


def _read_neuro(fpath):
    if fpath.endswith(".npz"):
        try:
            z = np.load(fpath)
            ts = z["ts"] if "ts" in z else z[z.files[0]]
        except Exception:
            return None
    else:
        try:
            ts = np.loadtxt(fpath, delimiter=",")
        except Exception:
            return None
    ts = np.asarray(ts, dtype=np.float64)
    if ts.ndim != 2 or min(ts.shape) < 2:
        return None
    if ts.shape[0] > ts.shape[1]:      # want (channels, time); more time than channels
        ts = ts.T
    return ts


def _neuro_features(ts):
    """Spectral band-power ratios (channel-averaged) + functional-connectivity summary."""
    C, T = ts.shape
    ts = ts - ts.mean(1, keepdims=True)
    # spectral: FFT per channel, average band power across channels, normalise to ratios
    freqs = np.fft.rfftfreq(T, d=1.0 / 128.0)              # assume 128 Hz (EEG-ish)
    psd = (np.abs(np.fft.rfft(ts, axis=1)) ** 2).mean(0)
    band_p = np.array([psd[(freqs >= lo) & (freqs < hi)].sum() for lo, hi in _BANDS])
    band_ratio = band_p / (band_p.sum() + 1e-9)
    slope = np.polyfit(np.log(freqs[1:20] + 1e-9), np.log(psd[1:20] + 1e-9), 1)[0] \
        if T > 40 else 0.0
    # functional connectivity: correlation matrix off-diagonal distribution + graph stats
    if C >= 2:
        corr = np.corrcoef(ts)
        iu = np.triu_indices(C, 1)
        off = np.nan_to_num(corr[iu])
    else:
        off = np.zeros(1)
    hist, _ = np.histogram(off, bins=_CORR_BINS, density=False)
    hist = hist / (hist.sum() + 1e-9)
    graph = [np.abs(off).mean(), off.std(), float((np.abs(off) > 0.5).mean()),
             off.mean(), np.percentile(off, 90), np.percentile(off, 10)]
    chan = [ts.var(1).mean(), ts.var(1).std(), C, T]      # signal-scale summary
    vec = np.concatenate([band_ratio, [slope], hist, graph, chan])
    out = np.zeros(NEURO_DIM, dtype=np.float64)
    out[:min(len(vec), NEURO_DIM)] = np.nan_to_num(vec[:NEURO_DIM])
    return out.astype(np.float32)


def _neuro_extract(path):
    files = _list(path, [".npz", ".csv"])
    X, y, g = [], [], []
    for fp in files:
        ts = _read_neuro(fp)
        if ts is None:
            continue
        X.append(_neuro_features(ts))
        y.append(_label_of(fp, path, NEURO_CLASSES))
        g.append(os.path.relpath(fp, path))
    if not X:
        return np.zeros((0, NEURO_DIM), np.float32), np.array([], object), np.array([], object)
    return np.vstack(X), np.array(y, object), np.array(g, object)


def _neuro_synth(out, n_per_class, seed, classes=None):
    classes = classes or NEURO_CLASSES
    rng = np.random.default_rng(seed + 19)
    C, T, fs = 19, 1024, 128.0                            # 19-channel, 8 s @128 Hz
    made = 0
    for c in classes:
        d = os.path.join(out, c)
        os.makedirs(d, exist_ok=True)
        asd = c.upper() == "ASD"
        for k in range(n_per_class):
            tvec = np.arange(T) / fs
            # graded overlapping severity: ASD-like -> weaker long-range connectivity +
            # relatively elevated high-freq power, but distributions overlap.
            sev = np.clip(rng.normal(0.66 if asd else 0.34, 0.24), 0, 1)
            base = rng.normal(0, 1, (1, T))               # shared component -> connectivity
            share = 0.72 - 0.34 * sev                     # high sev -> less shared -> weaker FC
            a_alpha, a_beta, a_gamma = 1.2 - 0.5 * sev, 0.6 + 0.4 * sev, 0.3 + 0.4 * sev
            ts = np.zeros((C, T))
            for ch in range(C):
                indep = rng.normal(0, 1, T)
                osc = sum(a * np.sin(2 * np.pi * fq * tvec + rng.uniform(0, 6.28))
                          for fq, a in [(3, 1.0), (10, a_alpha), (22, a_beta), (38, a_gamma)])
                ts[ch] = share * base[0] + (1 - share) * indep + 0.5 * osc
            np.savez_compressed(os.path.join(d, f"{c.lower()}_{seed}_{k:03d}.npz"),
                                ts=ts.astype(np.float32))
            made += 1
    return made


# ================================================================== REGISTRY
# Public normalization: raw features are heterogeneous (counts, fractions, lengths), so a
# single declared [lo, hi] can't bracket them and random-split DP trees would miss the data.
# We instead squash every feature with tanh(raw / scale) into [-1, 1], where `scale` is a
# SHIPPED PUBLIC CONSTANT (public_scales.json) computed ONCE from a published synthetic
# REFERENCE cohort (fixed seed below) — never from any participant's data. tanh is monotone,
# so it preserves every axis-aligned split (tree accuracy is unchanged) while giving the DP
# forest a genuinely public [-1, 1] range to draw thresholds from. Analogous to shipping
# ImageNet mean/std: public constants, data-independent of participants.
_SCALE_FILE = os.path.join(HERE, "public_scales.json")   # committed public artifact (not under data/)
_REF_SEED = 20240601
_REF_N = 80


class Modality:
    def __init__(self, key, zh, en, task_zh, task_en, dim, classes, file_hint, extract, synth):
        self.key, self.zh, self.en = key, zh, en
        self.task_zh, self.task_en = task_zh, task_en
        self.dim, self.classes = dim, classes
        self.file_hint = file_hint
        self._extract, self._synth = extract, synth
        self.scale = np.ones(dim)                        # set by _ensure_scales()

    def bounds(self):
        """PUBLIC per-feature [lo, hi] = [-1, 1] after the public tanh normalization."""
        return np.tile([-1.0, 1.0], (self.dim, 1)).astype(float)

    def normalize(self, X):
        return np.tanh(np.asarray(X, float) / self.scale).astype(np.float32)

    def extract_folder(self, path):
        X, y, g = self._extract(path)                    # RAW features
        if len(X):
            X = self.normalize(X)                        # -> [-1, 1] via public scale
        return X, y, g

    def synth_folder(self, out, n_per_class, seed, classes=None):
        os.makedirs(out, exist_ok=True)
        return self._synth(out, n_per_class, seed, classes)

    def info(self):
        return {"key": self.key, "zh": self.zh, "en": self.en,
                "task_zh": self.task_zh, "task_en": self.task_en,
                "n_features": self.dim, "classes": self.classes,
                "file_hint": self.file_hint}


MODALITIES = {
    "eyegaze": Modality(
        "eyegaze", "眼动数据", "Eye-tracking",
        "社交注意力筛查 (ASD/TD)", "Social-attention screening (ASD/TD)",
        GAZE_DIM, GAZE_CLASSES,
        "每段录制一个 CSV（列含 x, y[, pupil]），放入 asd/ 与 td/ 子文件夹 · one CSV per recording (x, y[, pupil]) under asd/ and td/",
        _gaze_extract, _gaze_synth),
    "action": Modality(
        "action", "动作/姿态数据", "Body action / pose",
        "行为动作筛查 (ASD/TD)", "Behavioural-action screening (ASD/TD)",
        ACTION_DIM, ACTION_CLASSES,
        "选择现有 body:(T,33,4) NPZ，或在桌面客户端本地转换原始视频 · choose existing body:(T,33,4) NPZ files or convert raw video locally in the desktop client",
        _action_extract, _action_synth),
    "neuro": Modality(
        "neuro", "EEG / fMRI 神经影像", "EEG / fMRI",
        "神经影像筛查 (ASD/TD)", "Neuroimaging screening (ASD/TD)",
        NEURO_DIM, NEURO_CLASSES,
        "每次扫描一个 .npz(键 'ts',通道×时间)或 CSV,放入 asd/ 与 td/ · one .npz (key 'ts', channels×time) or CSV per scan under asd/ and td/",
        _neuro_extract, _neuro_synth),
}


def _compute_scale(m):
    """Per-feature public scale from a fixed-seed synthetic REFERENCE cohort (public,
    participant-independent). Robust magnitude -> tanh keeps the bulk within [-0.9, 0.9]."""
    with tempfile.TemporaryDirectory() as tmp:
        m.synth_folder(tmp, _REF_N, _REF_SEED)
        R, _, _ = m._extract(tmp)                        # RAW
    if len(R) == 0:
        return np.ones(m.dim)
    s = np.percentile(np.abs(R), 90, axis=0)
    return np.maximum(s, 1e-3)


def _ensure_scales():
    cache = {}
    if os.path.exists(_SCALE_FILE):
        try:
            cache = json.load(open(_SCALE_FILE))
        except Exception:
            cache = {}
    changed = False
    for key, m in MODALITIES.items():
        v = cache.get(key)
        if isinstance(v, list) and len(v) == m.dim:
            m.scale = np.asarray(v, float)
        else:
            m.scale = _compute_scale(m)
            cache[key] = m.scale.tolist()
            changed = True
    if changed:
        try:
            with open(_SCALE_FILE, "w") as f:
                json.dump(cache, f, indent=0)
        except OSError:
            pass


_ensure_scales()


def get(key):
    if key not in MODALITIES:
        raise ValueError(f"unknown modality {key!r} (use {list(MODALITIES)})")
    return MODALITIES[key]


def demo_dataset(key, n_per_class=80, seed=0, cache_root=None):
    """Synthesize a raw demo folder for `key`, then run it through the REAL extractor.
    Returns (X, y, groups) — the exact path real partner data takes."""
    m = get(key)
    root = cache_root or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                      "data", "demo_raw", key)
    if not (os.path.isdir(root) and _list(root, [".csv", ".npz"])):
        m.synth_folder(root, n_per_class, seed)
    return m.extract_folder(root)


if __name__ == "__main__":               # quick self-check across all modalities
    import tempfile
    for key, m in MODALITIES.items():
        with tempfile.TemporaryDirectory() as tmp:
            made = m.synth_folder(tmp, 10, 0)
            X, y, g = m.extract_folder(tmp)
            u, c = np.unique(y, return_counts=True)
            assert X.shape[1] == m.dim, (key, X.shape, m.dim)
            print(f"{key:8s} files={made:3d} -> X{X.shape} dim={m.dim} "
                  f"classes={dict(zip(u.tolist(), c.tolist()))}")
