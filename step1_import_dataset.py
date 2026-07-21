"""
step1_import_dataset.py
=======================
Copy your NVIDIA dataset_outputs/ into the auditor's expected layout.

  FROM:  dataset_outputs/<task>/<model>/run<K>.py          (task/model nesting)
  TO:    research/samples/<model>/<task>/run<K>.py         (model/task nesting)

Also writes a run<K>.meta.json beside each file with provenance pulled from
provenance.jsonl (model version, collected_at) so the dataset is citable.

USAGE (edit the two paths at the top if yours differ):
    python3 step1_import_dataset.py
    python3 step1_import_dataset.py --dry-run     # preview only
"""
from __future__ import annotations
import argparse, json, shutil
from pathlib import Path

# ---- EDIT THESE IF YOUR PATHS DIFFER ----
SRC = Path("dataset_outputs")
DST = Path("research/samples")
PROVENANCE = Path("provenance.jsonl")
# -----------------------------------------


def load_provenance() -> dict:
    """Map (task, model_slug, run) -> provenance record, if the file exists."""
    prov = {}
    if not PROVENANCE.exists():
        return prov
    for line in PROVENANCE.read_text().splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "error" in r:
            continue  # skip failed runs
        slug = r["model"].replace("/", "__").replace(".", "-")
        prov[(r["task"], slug, r["run"])] = r
    return prov


def main(dry: bool) -> None:
    if not SRC.exists():
        print(f"ERROR: {SRC} not found. Run this from the folder that contains dataset_outputs/.")
        return
    prov = load_provenance()
    copied = 0
    for run_file in sorted(SRC.rglob("run*.py")):
        # dataset_outputs/<task>/<model>/run<K>.py
        parts = run_file.parts
        task, model, fname = parts[-3], parts[-2], parts[-1]
        run_k = int(fname.replace("run", "").replace(".py", ""))
        # skip empty files (failed generations that left a stub)
        if run_file.stat().st_size == 0:
            print(f"  skip empty: {run_file}")
            continue
        target = DST / model / task / fname
        print(f"  {task}/{model}/{fname}  ->  {model}/{task}/{fname}")
        if not dry:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(run_file, target)
            # write provenance sidecar
            rec = prov.get((task, model, run_k), {})
            meta = {
                "model": model, "task": task, "run": run_k,
                "model_version": rec.get("model_version", "unknown"),
                "collected_at": rec.get("collected_at", "unknown"),
                "source": "nvidia-nim",
            }
            (target.parent / f"{fname.replace('.py', '')}.meta.json").write_text(
                json.dumps(meta, indent=2))
        copied += 1
    verb = "Would copy" if dry else "Copied"
    print(f"\n{verb} {copied} run files into {DST}")
    if dry:
        print("Dry run only. Re-run without --dry-run to actually copy.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    main(ap.parse_args().dry_run)
