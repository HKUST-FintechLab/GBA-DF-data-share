"""Per-FILE feature blocks so any staging can be reassembled in exactly the order
modalities._list() (sorted full path) would produce inside a node folder."""
import os, pickle, shutil, sys, tempfile
import numpy as np

HERE = r"D:\agent\dean\0803\datademo"
sys.path.insert(0, HERE)
os.chdir(HERE)
import modalities as mods

SCRATCH = r"C:\Users\chenx\AppData\Local\Temp\claude\D--agent-dean-0803\66483c77-2328-4c98-ab4e-ba05cdf4c932\scratchpad\mitigate"
MOD = mods.get("action")

tmp = tempfile.mkdtemp(prefix="blk-")


def block(src_file, cls):
    """Features for one npz file, extracted alone under <cls>/ so the label is right."""
    work = os.path.join(tmp, "one")
    shutil.rmtree(work, ignore_errors=True)
    d = os.path.join(work, cls)
    os.makedirs(d, exist_ok=True)
    shutil.copy2(src_file, os.path.join(d, os.path.basename(src_file)))
    X, y, g = MOD.extract_folder(work)
    return np.asarray(X, np.float32), np.asarray(y).astype(str)


cache = {"base": {}, "clips": {}}
for pc in (20, 30, 40):
    for n in (1, 2, 3):
        folder = os.path.join(SCRATCH, f"base_{pc}", f"node_{n}")
        rows = []
        for cls in ("ASD", "TD"):
            for name in sorted(os.listdir(os.path.join(folder, cls))):
                if not name.endswith(".npz"):
                    continue
                X, y = block(os.path.join(folder, cls, name), cls)
                rows.append((cls, name, X, y))
        cache["base"][(pc, n)] = rows
        print(f"base{pc} node_{n}: {len(rows)} files, {sum(r[2].shape[0] for r in rows)} rows")

for cls in ("asd", "td"):
    src = os.path.join(HERE, "demo_videos", "npz", cls)
    for name in sorted(os.listdir(src)):
        if not name.endswith(".npz"):
            continue
        X, y = block(os.path.join(src, name), cls.upper())
        assert X.shape[0] == 1
        cache["clips"][name] = (cls.upper(), X, y)
        print(f"clip {name}: {y[0]}")

shutil.rmtree(tmp, ignore_errors=True)
with open(os.path.join(SCRATCH, "cache.pkl"), "wb") as f:
    pickle.dump(cache, f)
print("saved")
