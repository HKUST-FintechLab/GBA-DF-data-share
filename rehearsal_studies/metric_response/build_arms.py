"""Build the four experiment arms as independent node-folder trees.

A = baseline only
B = baseline + all 11 clips, ASD/TD balanced per node
C = baseline + only the 6 ASD clips, node_3 gets none
D = baseline + the 11 clips copied twice (22 rows)
"""
import os
import shutil
import sys
import collections

sys.path.insert(0, r"D:\agent\dean\0803\datademo")
import numpy as np
import modalities as mods

ROOT = r"C:\Users\chenx\AppData\Local\Temp\claude\D--agent-dean-0803\66483c77-2328-4c98-ab4e-ba05cdf4c932\scratchpad\metric_exp"
STAGE = os.path.join(ROOT, "stage")
CLIPS = os.path.join(ROOT, "clips")
ARMS = os.path.join(ROOT, "arms")

ASD = [f"asd_0{i}" for i in range(1, 7)]
TD = [f"td_0{i}" for i in range(1, 6)]

# node -> (asd clips, td clips)
PLAN = {
    "A": {1: ([], []), 2: ([], []), 3: ([], [])},
    # 6 ASD -> 2/2/2 ; 5 TD -> 2/2/1  (balanced as evenly as 11 clips allow)
    "B": {1: (ASD[0:2], TD[0:2]), 2: (ASD[2:4], TD[2:4]), 3: (ASD[4:6], TD[4:5])},
    # single-class contribution: node_3 contributes nothing
    "C": {1: (ASD[0:3], []), 2: (ASD[3:6], []), 3: ([], [])},
    "D": {1: (ASD[0:2], TD[0:2]), 2: (ASD[2:4], TD[2:4]), 3: (ASD[4:6], TD[4:5])},
}
COPIES = {"A": 0, "B": 1, "C": 1, "D": 2}


def build():
    if os.path.exists(ARMS):
        shutil.rmtree(ARMS)
    mod = mods.get("action")
    report = {}
    for arm, plan in PLAN.items():
        report[arm] = {}
        for n in (1, 2, 3):
            dst = os.path.join(ARMS, arm, f"node_{n}")
            shutil.copytree(os.path.join(STAGE, f"node_{n}"), dst)
            asd_c, td_c = plan[n]
            for cls, names in (("asd", asd_c), ("td", td_c)):
                for name in names:
                    src = os.path.join(CLIPS, cls, f"{name}.npz")
                    out_dir = os.path.join(dst, cls.upper())
                    os.makedirs(out_dir, exist_ok=True)
                    for k in range(COPIES[arm]):
                        tag = f"clip_{name}" if k == 0 else f"clip_{name}_dup{k}"
                        shutil.copy2(src, os.path.join(out_dir, f"{tag}.npz"))
            X, y, g = mod.extract_folder(dst)
            cnt = dict(collections.Counter(map(str, y)))
            n_clip = sum(1 for gi in g if os.path.basename(str(gi)).startswith("clip_"))
            report[arm][n] = (X.shape, cnt, n_clip)
            print(f"{arm} node_{n}: {X.shape[0]} rows ({n_clip} from clips) x {X.shape[1]}  {cnt}")
        tot = sum(report[arm][n][0][0] for n in (1, 2, 3))
        print(f"{arm} TOTAL rows: {tot}\n")


if __name__ == "__main__":
    build()
