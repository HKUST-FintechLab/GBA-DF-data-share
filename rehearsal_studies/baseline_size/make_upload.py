"""Copy a staged node set and add exactly 4 extra feature rows per node.

Each added file is a synthetic action clip generated with a DIFFERENT seed from the
baseline stage, trimmed to a single 60-frame window so one file == one feature row.
2 rows go to TD/, 2 to ASD/, per node.
"""
import os, shutil, sys, tempfile
sys.path.insert(0, r"D:\agent\dean\0803\datademo")
import numpy as np
import modalities as mods

src, dst, base_seed = sys.argv[1], sys.argv[2], int(sys.argv[3])
if os.path.exists(dst):
    shutil.rmtree(dst)
shutil.copytree(src, dst)
for root, _d, files in os.walk(dst):
    for f in files:
        if f == "node_key.pem":
            os.remove(os.path.join(root, f))

mod = mods.get("action")
for n in (1, 2, 3):
    node = os.path.join(dst, f"node_{n}")
    tmp = tempfile.mkdtemp()
    mods._action_synth(tmp, 2, seed=base_seed + n * 31)   # 2 per class, fresh seed
    for cls in ("TD", "ASD"):
        srcs = sorted(os.listdir(os.path.join(tmp, cls)))[:2]
        for i, name in enumerate(srcs):
            with np.load(os.path.join(tmp, cls, name)) as z:
                body = np.asarray(z["body"])[:1]          # exactly ONE window -> ONE row
            out = os.path.join(node, cls, f"synthetic_upload_{base_seed}_{i}.npz")
            np.savez_compressed(out, body=body)
    shutil.rmtree(tmp)
    X, y, _g = mod.extract_folder(node)
    Xs, ys, _ = mod.extract_folder(os.path.join(src, f"node_{n}"))
    print(f"  node_{n}: {Xs.shape[0]} -> {X.shape[0]} rows (+{X.shape[0]-Xs.shape[0]})")
