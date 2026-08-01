import collections
import sys
sys.path.insert(0, r"D:\agent\dean\0803\datademo")
import numpy as np
import modalities as mods

d = r"C:\Users\chenx\AppData\Local\Temp\claude\D--agent-dean-0803\66483c77-2328-4c98-ab4e-ba05cdf4c932\scratchpad\metric_exp\clips"
X, y, g = mods.get("action").extract_folder(d)
print("X", X.shape, X.dtype, "finite", bool(np.isfinite(X).all()))
print("labels", dict(collections.Counter(map(str, y))))
for gi, yi in zip(g, y):
    print("  ", gi, "->", yi)
print("range", float(X.min()), float(X.max()))
