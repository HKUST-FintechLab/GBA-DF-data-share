import os
import sys
import collections

sys.path.insert(0, r"D:\agent\dean\0803\datademo")
import numpy as np
import modalities as mods

ROOT = r"C:\Users\chenx\AppData\Local\Temp\claude\D--agent-dean-0803\66483c77-2328-4c98-ab4e-ba05cdf4c932\scratchpad\metric_exp"
mod = mods.get("action")

d = np.load(r"D:\agent\dean\0803\datademo\data\test.npz")
Xt, yt = d["X"], np.asarray(d["y"]).astype(str)
print("TEST set:", Xt.shape, dict(collections.Counter(yt.tolist())))
print("  test feature range", float(Xt.min()), float(Xt.max()))

Xc, yc, _ = mod.extract_folder(os.path.join(ROOT, "clips"))
Xb, yb, _ = mod.extract_folder(os.path.join(ROOT, "stage", "node_1"))
print("CLIPS:", Xc.shape, "  BASELINE node_1:", Xb.shape)

for name, X in (("test", Xt), ("baseline", Xb), ("clips", Xc)):
    sat = float((np.abs(X) >= 0.999).mean())
    print(f"  {name:9s} mean={X.mean():.4f} sd={X.std():.4f} "
          f"frac at |x|>=0.999 = {sat:.4f}")

# how far are the clip rows from the test manifold, per class?
for cls in ("ASD", "TD"):
    ct = Xt[yt == cls]
    cc = Xc[np.asarray(yc).astype(str) == cls]
    cb = Xb[np.asarray(yb).astype(str) == cls]
    # nearest-neighbour distance from each clip row to the test cloud vs baseline rows
    dc = np.sqrt(((cc[:, None, :] - ct[None, :, :]) ** 2).sum(-1)).min(1)
    db = np.sqrt(((cb[:, None, :] - ct[None, :, :]) ** 2).sum(-1)).min(1)
    print(f"  {cls}: NN-dist to test  clips mean={dc.mean():.3f} "
          f"| baseline mean={db.mean():.3f}")
