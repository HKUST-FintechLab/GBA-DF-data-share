"""Extract feature matrices once: synthetic baselines (per-class 20/30/40) and each clip alone."""
import os, shutil, sys, tempfile
import numpy as np

HERE = r"D:\agent\dean\0803\datademo"
sys.path.insert(0, HERE)
os.chdir(HERE)
import modalities as mods

SCRATCH = r"C:\Users\chenx\AppData\Local\Temp\claude\D--agent-dean-0803\66483c77-2328-4c98-ab4e-ba05cdf4c932\scratchpad\mitigate"
MOD = mods.get("action")

out = {}
for pc in (20, 30, 40):
    for n in (1, 2, 3):
        folder = os.path.join(SCRATCH, f"base_{pc}", f"node_{n}")
        X, y, g = MOD.extract_folder(folder)
        out[f"base{pc}_n{n}_X"] = np.asarray(X, float)
        out[f"base{pc}_n{n}_y"] = np.asarray(y).astype(str)
        print(f"base{pc} node_{n}: {X.shape}")

# clips, one at a time -> one row each
clip_names, clip_X, clip_y = [], [], []
tmp = tempfile.mkdtemp(prefix="clip-")
for cls in ("asd", "td"):
    src = os.path.join(HERE, "demo_videos", "npz", cls)
    for name in sorted(os.listdir(src)):
        if not name.endswith(".npz"):
            continue
        d = os.path.join(tmp, "one", cls.upper())
        shutil.rmtree(os.path.join(tmp, "one"), ignore_errors=True)
        os.makedirs(d, exist_ok=True)
        shutil.copy2(os.path.join(src, name), os.path.join(d, name))
        X, y, g = MOD.extract_folder(os.path.join(tmp, "one"))
        assert X.shape[0] == 1, (name, X.shape)
        clip_names.append(f"{cls}/{name}")
        clip_X.append(X[0])
        clip_y.append(str(y[0]))
        print(f"clip {cls}/{name}: y={y[0]} sat={np.mean(np.abs(X[0])>=0.999):.3f}")
shutil.rmtree(tmp, ignore_errors=True)
out["clip_X"] = np.asarray(clip_X, float)
out["clip_y"] = np.asarray(clip_y)
out["clip_names"] = np.asarray(clip_names)
np.savez_compressed(os.path.join(SCRATCH, "cache.npz"), **out)
print("saved", out["clip_X"].shape)
