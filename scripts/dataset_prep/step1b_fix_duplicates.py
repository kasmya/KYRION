"""
step1b_fix_duplicates.py
========================
Fix the slugify duplication where the SAME model got two folder names differing
only by dash-vs-underscore in the version number, e.g.:

    meta__llama-3-1-70b-instruct   <-- canonical (dashes)
    meta__llama-3_1-70b-instruct   <-- duplicate (underscore) -- MERGE INTO canonical

It merges every underscore-variant folder into its dash-variant twin, moving run
files across without overwriting, then removes the empty duplicate folders.

Also lets you drop models that barely generated (e.g. mistral) so they don't
pollute the stats.

USAGE:
    python3 scripts/dataset_prep/step1b_fix_duplicates.py --dry-run
    python3 scripts/dataset_prep/step1b_fix_duplicates.py
    python3 scripts/dataset_prep/step1b_fix_duplicates.py --drop mistralai__mistral-large-3-675b-instruct-2512
"""
from __future__ import annotations
import argparse, re, shutil
from pathlib import Path

SAMPLES = Path("research/samples")

def canonical(name: str) -> str:
    # normalise version underscores to dashes ONLY inside the model part:
    # meta__llama-3_1-70b -> meta__llama-3-1-70b
    # keep the '__' separator between vendor and model intact
    if "__" not in name:
        return name.replace("_", "-")
    vendor, model = name.split("__", 1)
    model = model.replace("_", "-")
    return f"{vendor}__{model}"

def main(dry: bool, drop: list[str]):
    if not SAMPLES.exists():
        print("research/samples not found."); return
    dirs = sorted([d.name for d in SAMPLES.iterdir() if d.is_dir()])

    # group by canonical name
    groups: dict[str, list[str]] = {}
    for d in dirs:
        groups.setdefault(canonical(d), []).append(d)

    moved, removed = 0, 0
    for canon, variants in sorted(groups.items()):
        if canon in drop:
            continue
        # pick the canonical-named folder as target if present, else the first
        target_name = canon if canon in variants else variants[0]
        target = SAMPLES / target_name
        for v in variants:
            if v == target_name:
                continue
            src = SAMPLES / v
            print(f"MERGE {v}  ->  {target_name}")
            for run_file in src.rglob("run*.py"):
                task = run_file.parent.name
                dest_dir = target / task
                dest = dest_dir / run_file.name
                if not dry:
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    if dest.exists():
                        # keep both: rename incoming to next free run number
                        n = 1
                        while (dest_dir / f"run{n}.py").exists():
                            n += 1
                        dest = dest_dir / f"run{n}.py"
                    shutil.move(str(run_file), str(dest))
                    # move meta sidecar too if present
                    meta = run_file.with_suffix("").with_suffix(".meta.json")
                    if meta.exists():
                        shutil.move(str(meta), str(dest.with_suffix("").with_suffix(".meta.json")))
                moved += 1
            if not dry and src.exists() and not any(src.rglob("*.py")):
                shutil.rmtree(src); removed += 1

    # drop unwanted models entirely
    for d in drop:
        p = SAMPLES / d
        if p.exists():
            print(f"DROP  {d}")
            if not dry:
                shutil.rmtree(p); removed += 1

    verb = "Would move" if dry else "Moved"
    print(f"\n{verb} {moved} run files; removed {removed} folder(s).")
    if not dry:
        print("Remaining model folders:")
        for d in sorted([x.name for x in SAMPLES.iterdir() if x.is_dir()]):
            n = len(list((SAMPLES/d).rglob("run*.py")))
            print(f"   {d}: {n} runs")
    if dry:
        print("Dry run only. Re-run without --dry-run to apply.")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--drop", action="append", default=[])
    a = ap.parse_args()
    main(a.dry_run, a.drop)
