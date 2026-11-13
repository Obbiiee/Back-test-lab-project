import sys, json, shutil
sys.path.insert(0, "tools/claude_exp")
from parity import *
n, step, tp, sl, mix, arch = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), sys.argv[5] == "1", sys.argv[6] == "1"
r = run(n, "clean", step_s=step, tp=tp, sl=sl, mix=mix, archive=arch)
shutil.rmtree(r["_work"], ignore_errors=True)
print(json.dumps(dict(n=n, archive=arch, baseline=r["baseline"], claude={k: r["claude"][k] for k in ("cpu", "fills", "balance", "stats")}, parity=r["parity"], archived=r["_cs"].state.get("orderArchive", {}).get("count") if arch else None)))
