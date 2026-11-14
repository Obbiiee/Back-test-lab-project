import sys, json, shutil
sys.path.insert(0, ".")
from parity import *
pair, month, n, step, tp, sl, mix, arch = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6]), sys.argv[7] == "1", sys.argv[8] == "1"
offset = int(sys.argv[9]) if len(sys.argv) > 9 else 0
set_instrument(5, "0.00040")
z = rf"C:\Users\kuchi\OneDrive\Dokumen\mix data\HistData-UTC\{pair}\HISTDATA_UTC_{pair}_T{month}.zip"
r = run(n, "clean", step_s=step, tp=tp, sl=sl, mix=mix, archive=arch, offset=offset, hd=dict(zip=z, pair=pair, month=month))
shutil.rmtree(r["_work"], ignore_errors=True)
print(json.dumps(dict(pair=pair, n=n, archive=arch, mismatches=r["admission_reconstruction_mismatches"], baseline=r["baseline"], claude={k: r["claude"][k] for k in ("cpu", "fills", "balance", "stats")}, parity=r["parity"], firstDiff=r.get("firstDiff"))))
