"""
phase2_smell_breakdown.py
=========================
Your one significant finding is "gpt-oss produces fewer code smells." This answers
the essential follow-up: WHICH smells? It re-audits every run, categorises each
code-smell by type, and reports per-model rates + a Kruskal-Wallis test per smell
type — so you can say "gpt-oss produces fewer <specific smell>" instead of a vague
aggregate.

Smell types tracked (from quality.py):
  - Missing docstring (function/class)
  - Missing module-level docstring
  - Long function
  - Mutable default argument
  - Long line
  - TODO/FIXME markers

USAGE:
    python3 scripts/analysis/phase2_smell_breakdown.py
Writes research/data/smell_breakdown.csv (per-model mean count per smell type)
and prints a significance test for each type.
"""
from __future__ import annotations
import csv, glob, re
from collections import defaultdict
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from quality import analyze_code_quality  # noqa: E402
import numpy as np
from scipy import stats

SAMPLES = Path("research/samples")

# map a raw smell string to a coarse category
def categorise(smell: str) -> str:
    s = smell.lower()
    if "module-level docstring" in s: return "missing_module_docstring"
    if "docstring" in s:              return "missing_docstring"
    if "long function" in s:          return "long_function"
    if "mutable default" in s:        return "mutable_default"
    if "long line" in s:              return "long_line"
    if "todo" in s or "fixme" in s:   return "todo_fixme"
    return "other"

CATEGORIES = ["missing_docstring","missing_module_docstring","long_function",
              "mutable_default","long_line","todo_fixme","other"]

def short(m): return m.split("__")[-1]

def main():
    # per (model, run) counts per category
    per_run = []  # list of (model, task, {cat: count})
    for run_path in sorted(glob.glob(str(SAMPLES / "*" / "task*" / "run*.py"))):
        p = Path(run_path)
        model, task = p.parts[-3], p.parts[-2]
        code = p.read_text(encoding="utf-8", errors="ignore")
        if not code.strip():
            continue
        q = analyze_code_quality(code)
        counts = defaultdict(int)
        for smell in q["code_smells"]:
            counts[categorise(smell)] += 1
        per_run.append((model, task, counts))

    models = sorted({m for m,_,_ in per_run})

    # aggregate to per-cell (task-mean) per category, for stats at task level
    print("="*78)
    print("CODE-SMELL TYPE BREAKDOWN  (which smells separate the models?)")
    print("="*78)

    # per-model mean count per category (over runs)
    print(f"\nMean smells per generation, by type:\n")
    header = f"{'smell type':<26}" + "".join(f"{short(m)[:9]:>11}" for m in models)
    print(header); print("-"*len(header))
    model_cat_runs = {m: {c: [] for c in CATEGORIES} for m in models}
    for m, t, counts in per_run:
        for c in CATEGORIES:
            model_cat_runs[m][c].append(counts.get(c, 0))

    csv_rows = []
    for c in CATEGORIES:
        row = f"{c:<26}"
        for m in models:
            row += f"{np.mean(model_cat_runs[m][c]):>11.2f}"
        print(row)
        csv_rows.append({"smell_type": c,
                         **{short(m): round(np.mean(model_cat_runs[m][c]),3) for m in models}})

    # significance test per category (task-level: average runs within task first)
    print(f"\nKruskal-Wallis per smell type (task-level):\n")
    print(f"{'smell type':<26}{'H':>9}{'p':>12}{'sig?':>6}")
    print("-"*53)
    # build task-level samples: for each (model), list of task-mean counts
    cellmap = defaultdict(lambda: defaultdict(list))  # cat -> model -> [task means]
    taskcell = defaultdict(lambda: defaultdict(list))  # (model,task) -> cat -> [run counts]
    for m, t, counts in per_run:
        for c in CATEGORIES:
            taskcell[(m,t)][c].append(counts.get(c,0))
    for (m,t), catcounts in taskcell.items():
        for c in CATEGORIES:
            cellmap[c][m].append(np.mean(catcounts[c]))

    for c in CATEGORIES:
        groups = [cellmap[c][m] for m in models if len(cellmap[c][m])>0]
        # skip if all zeros (no variance)
        if all(all(v==0 for v in g) for g in groups):
            print(f"{c:<26}{'--':>9}{'all zero':>12}{'':>6}")
            continue
        try:
            h, p = stats.kruskal(*groups)
            sig = "***" if p<0.001 else "**" if p<0.01 else "*" if p<0.05 else "ns"
            print(f"{c:<26}{h:>9.3f}{p:>12.3e}{sig:>6}")
        except ValueError:
            print(f"{c:<26}{'--':>9}{'n/a':>12}{'':>6}")

    out = Path("research/data/smell_breakdown.csv")
    with open(out,"w",newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(csv_rows[0].keys()))
        w.writeheader(); w.writerows(csv_rows)
    print(f"\nWrote per-type means -> {out}")
    print("\nFor the paper: report which smell type(s) are significant, then state")
    print("e.g. 'gpt-oss-120b produces significantly fewer <type> than <model>'.")

if __name__ == "__main__":
    main()
