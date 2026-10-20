"""
step3_missing_list.py
=====================
Print the exact (task, model, run) triples still missing, so you can retry ONLY
those with your NVIDIA generator instead of re-running everything.

Reads provenance.jsonl if present (authoritative), else infers from files on disk.

USAGE:
    python3 scripts/dataset_prep/step3_missing_list.py --k 3
    python3 scripts/dataset_prep/step3_missing_list.py --k 3 --models-out retry_models.txt
"""
import argparse, json, re
from pathlib import Path

SAMPLES = Path("research/samples")
PROV = Path("provenance.jsonl")

def from_disk(k):
    models = sorted([d.name for d in SAMPLES.iterdir() if d.is_dir()])
    tasks = sorted({t.name for m in models for t in (SAMPLES/m).iterdir() if t.is_dir()})
    missing = []
    for m in models:
        for t in tasks:
            have = set()
            d = SAMPLES/m/t
            if d.exists():
                for f in d.glob("run*.py"):
                    mm = re.match(r"run(\d+)\.py", f.name)
                    if mm and f.stat().st_size>0:
                        have.add(int(mm.group(1)))
            for r in range(1,k+1):
                if r not in have:
                    missing.append((t, m, r))
    return missing

def main(k, models_out):
    missing = from_disk(k)
    print(f"Missing runs to reach k={k}: {len(missing)}\n")
    for t,m,r in sorted(missing):
        print(f"  {t} | {m} | run={r}")
    # which models still need work (for the --models flag of your generator)
    need = sorted({m.replace('__','/').replace('-','.',0) for _,m,_ in missing})
    if models_out and need:
        # convert slug back to api id: reverse of slugify is lossy, so just list slugs
        Path(models_out).write_text("\n".join(sorted({m for _,m,_ in missing})))
        print(f"\nModels still needing runs written to {models_out}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--models-out", default=None)
    a = ap.parse_args()
    main(a.k, a.models_out)
