"""
step2_status.py
===============
Show coverage of runs per (model, task) toward a target k. Auto-detects whatever
models exist under research/samples/ (no hardcoded model list), so it works with
your NVIDIA models directly.

USAGE:
    python3 scripts/dataset_prep/step2_status.py            # target k=3
    python3 scripts/dataset_prep/step2_status.py --k 3
"""
import argparse, re
from pathlib import Path

SAMPLES = Path("research/samples")

def runs_present(model_dir: Path, task: str) -> int:
    d = model_dir / task
    if not d.exists():
        return 0
    n = 0
    for f in d.glob("run*.py"):
        if re.match(r"run\d+\.py", f.name) and f.stat().st_size > 0:
            n += 1
    return n

def main(k: int):
    models = sorted([d.name for d in SAMPLES.iterdir() if d.is_dir()])
    tasks = sorted({t.name for m in models for t in (SAMPLES/m).iterdir() if t.is_dir()})
    if not models:
        print("No models found under research/samples/. Run step1 first.")
        return

    print(f"Coverage toward k={k}  (* = incomplete)\n")
    # short labels for header
    short = {m: m.split("__")[-1][:10] for m in models}
    header = f"{'task':<9}" + "".join(f"{short[m]:>12}" for m in models)
    print(header); print("-"*len(header))

    missing_total = 0
    incomplete_cells = []
    for t in tasks:
        row = f"{t:<9}"
        for m in models:
            n = runs_present(SAMPLES/m, t)
            missing_total += max(0, k-n)
            if n < k:
                incomplete_cells.append((t, m, n))
            row += f"{str(n)+'/'+str(k)+('*' if n<k else ''):>12}"
        print(row)
    print("-"*len(header))
    print(f"Runs still needed to reach k={k}: {missing_total}")
    print(f"Incomplete cells: {len(incomplete_cells)} of {len(models)*len(tasks)}")

    # also flag cells with n<2 (cannot compute variance)
    novar = [(t,m,n) for t,m,n in incomplete_cells if n < 2]
    if novar:
        print(f"\n⚠ {len(novar)} cell(s) have <2 runs — no variance possible, must retry or drop:")
        for t,m,n in novar[:20]:
            print(f"    {t} | {m.split('__')[-1]} | has {n}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--k", type=int, default=3)
    main(ap.parse_args().k)
