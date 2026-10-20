"""
step3_quality_gate.py
=====================
Before statistics, check the dataset is clean and decide how to handle incomplete
cells. Runs three checks and writes a filtered run-list you can feed to stats.

CHECKS:
  1. Truncation: files whose last line looks cut off (no newline / ends mid-token)
     — a symptom of max_tokens being too small. These should be regenerated.
  2. Parse failures: files that don't parse as Python (often truncation).
  3. Coverage: cells below the k threshold you choose.

OUTPUTS:
  - Prints a report.
  - Writes research/data/excluded_cells.json listing cells to drop (n < min_k),
    which run_evaluation / stats can honor.

USAGE:
    python3 scripts/dataset_prep/step3_quality_gate.py --min-k 2
    python3 scripts/dataset_prep/step3_quality_gate.py --min-k 2 --drop-model deepseek-ai__deepseek-v4-flash
"""
from __future__ import annotations
import argparse, ast, json, re
from pathlib import Path

SAMPLES = Path("research/samples")

def check_truncation(code: str) -> bool:
    """Heuristic: likely truncated if it doesn't parse AND ends without a clear
    statement terminator, or ends inside an obvious open construct."""
    stripped = code.rstrip()
    if not stripped:
        return True
    # ends mid-line with an opening bracket/colon and no body is suspicious
    last = stripped.splitlines()[-1]
    if last.rstrip().endswith(("(", "[", "{", ",", "=", "+")):
        return True
    return False

def main(min_k: int, drop_models: list[str]):
    models = sorted([d.name for d in SAMPLES.iterdir() if d.is_dir()])
    tasks = sorted({t.name for m in models for t in (SAMPLES/m).iterdir() if t.is_dir()})

    truncated, parse_fail = [], []
    cell_counts = {}
    for m in models:
        for t in tasks:
            d = SAMPLES/m/t
            if not d.exists():
                cell_counts[(m,t)] = 0
                continue
            good = 0
            for f in sorted(d.glob("run*.py")):
                if f.stat().st_size == 0:
                    continue
                code = f.read_text(encoding="utf-8", errors="ignore")
                is_trunc = check_truncation(code)
                try:
                    ast.parse(code)
                    parses = True
                except SyntaxError:
                    parses = False
                    parse_fail.append(str(f.relative_to(SAMPLES)))
                if is_trunc:
                    truncated.append(str(f.relative_to(SAMPLES)))
                if parses and not is_trunc:
                    good += 1
            cell_counts[(m,t)] = good

    print("QUALITY GATE REPORT")
    print("="*60)
    print(f"Truncated files (regenerate these): {len(truncated)}")
    for x in truncated[:15]: print(f"   {x}")
    print(f"\nParse-failure files: {len(parse_fail)}")
    for x in parse_fail[:15]: print(f"   {x}")

    # cells to exclude
    excluded = []
    for (m,t), n in sorted(cell_counts.items()):
        if m in drop_models:
            excluded.append({"model": m, "task": t, "reason": "model dropped"})
        elif n < min_k:
            excluded.append({"model": m, "task": t, "n": n,
                             "reason": f"below min_k={min_k}"})
    print(f"\nCells excluded (n < {min_k} or dropped model): {len(excluded)}")

    out = Path("research/data/excluded_cells.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(excluded, indent=2))
    print(f"Wrote exclusion list -> {out}")

    kept = [(m,t) for (m,t),n in cell_counts.items()
            if n >= min_k and m not in drop_models]
    print(f"\nCells KEPT for statistics: {len(kept)}")
    kept_models = sorted({m for m,_ in kept})
    print(f"Models retained: {len(kept_models)}")
    for m in kept_models:
        c = sum(1 for mm,_ in kept if mm==m)
        print(f"   {m.split('__')[-1]}: {c} complete cells")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-k", type=int, default=2)
    ap.add_argument("--drop-model", action="append", default=[])
    a = ap.parse_args()
    main(a.min_k, a.drop_model)
