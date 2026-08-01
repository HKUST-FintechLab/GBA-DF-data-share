import os, statistics, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim

SPREAD = {1: ["asd_01.npz", "asd_04.npz", "td_01.npz", "td_04.npz"],
          2: ["asd_02.npz", "asd_05.npz", "td_02.npz", "td_05.npz"],
          3: ["asd_03.npz", "asd_06.npz", "td_03.npz"]}

base = [sim.assemble(20, n) for n in (1, 2, 3)]
plus = [sim.assemble(20, n, SPREAD[n]) for n in (1, 2, 3)]
N = int(sys.argv[1]) if len(sys.argv) > 1 else 40
for label, nodes in (("baseline only", base), ("baseline + 11 clips", plus)):
    finals = [sim.run(nodes, dp_seed=s)[-1]["auc"] for s in range(N)]
    above = sum(1 for f in finals if f > sim.CENTRAL)
    print(f"{label:<22} {statistics.mean(finals):.3f} +- {statistics.stdev(finals):.3f}"
          f"   {above}/{N} above {sim.CENTRAL:.3f}")
