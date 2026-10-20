"""
Recompute per-generation stylistic smell flags directly from run*.py files
using the project's own src/quality.py logic, then run Friedman + pairwise
Wilcoxon (Holm-corrected) on the task x model matrices.

Run this from the repo root:
    python3 scripts/pipeline/stylistic_friedman.py
"""
import ast
import glob
import os
import re
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import pandas as pd
import numpy as np
from scipy.stats import friedmanchisquare, wilcoxon

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

LONG_FUNCTION_LINES = 50
LONG_LINE_CHARS = 120

SAMPLES_ROOT = "research/samples"

# canonical model-folder -> short name used in the paper's tables
MODEL_LABELS = {
    "deepseek-ai__deepseek-v4-flash": "deepseek-v4-flash",
    "meta__llama-3-1-70b-instruct": "llama-3.1-70b",
    "meta__llama-3-3-70b-instruct": "llama-3.3-70b",
    "nvidia__llama-3-3-nemotron-super-49b-v1": "nemotron-49b",
    "openai__gpt-oss-120b": "gpt-oss-120b",
}


def flags_for_file(code: str) -> dict:
    """Return per-generation stylistic flags, mirroring src/quality.py logic."""
    flags = {
        "missing_module_docstring": 0,
        "long_function": 0,          # count of long functions in this file
        "long_line": 0,               # 1 if any line exceeds LONG_LINE_CHARS
        "missing_fn_docstring": 0,    # count of functions/classes missing docstrings
        "mutable_default_arg": 0,     # count
        "parse_ok": 0,
    }

    # textual: long line (matches _textual_smells: break on first hit -> presence flag)
    for line in code.split("\n"):
        if len(line) > LONG_LINE_CHARS:
            flags["long_line"] = 1
            break

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return flags  # parse_ok stays 0; everything else 0 (structural checks skipped)

    flags["parse_ok"] = 1

    if ast.get_docstring(tree) is None:
        flags["missing_module_docstring"] = 1

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.end_lineno and node.lineno:
                span = node.end_lineno - node.lineno + 1
                if span > LONG_FUNCTION_LINES:
                    flags["long_function"] += 1
            if ast.get_docstring(node) is None:
                flags["missing_fn_docstring"] += 1
            for default in node.args.defaults + node.args.kw_defaults:
                if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                    flags["mutable_default_arg"] += 1
        elif isinstance(node, ast.ClassDef):
            if ast.get_docstring(node) is None:
                flags["missing_fn_docstring"] += 1

    return flags


def main():
    rows = []
    py_files = sorted(glob.glob(os.path.join(SAMPLES_ROOT, "*", "task*", "run*.py")))
    if not py_files:
        print(f"No files found under {SAMPLES_ROOT}. Run this from the kyrion repo root.")
        sys.exit(1)

    for path in py_files:
        parts = path.split(os.sep)
        model_folder = parts[-3]
        task = parts[-2]
        run = parts[-1].replace(".py", "")
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            code = f.read()
        flags = flags_for_file(code)
        flags.update({"model": model_folder, "task": task, "run": run})
        rows.append(flags)

    df = pd.DataFrame(rows)
    df["model_label"] = df["model"].map(MODEL_LABELS)
    unmapped = df[df["model_label"].isna()]["model"].unique()
    if len(unmapped):
        print("WARNING: unmapped model folders found (excluded from analysis):", unmapped)
    df = df.dropna(subset=["model_label"])

    # aggregate to task-level means per model (mean across the up-to-3 runs in each cell)
    metrics = ["missing_module_docstring", "long_function", "long_line",
               "missing_fn_docstring", "mutable_default_arg"]

    task_level = (
        df.groupby(["task", "model_label"])[metrics]
        .mean()
        .reset_index()
    )

    # drop task14 to keep a complete balanced block across all 5 models
    task_level = task_level[task_level.task != "task14"]

    print("Tasks per model after dropping task14 (should be 19 each):")
    print(task_level.groupby("model_label")["task"].nunique())
    print()

    results_summary = []
    for metric in metrics:
        wide = task_level.pivot(index="task", columns="model_label", values=metric)
        wide = wide.dropna()
        n_tasks = len(wide)
        model_cols = list(wide.columns)

        if wide.values.std() == 0:
            print(f"{metric}: no variance across models, skipping Friedman\n")
            continue

        stat, p = friedmanchisquare(*[wide[m] for m in model_cols])
        print(f"{metric}  (n_tasks={n_tasks})  Friedman chi2={stat:.3f}  p={p:.3e}")

        if p < 0.05:
            pairs = list(combinations(model_cols, 2))
            raw_p = []
            for a, b in pairs:
                diffs = wide[a] - wide[b]
                if (diffs == 0).all():
                    raw_p.append(1.0)
                else:
                    _, pw = wilcoxon(wide[a], wide[b])
                    raw_p.append(pw)
            order = np.argsort(raw_p)
            m = len(raw_p)
            holm = [0.0] * m
            for rank, idx in enumerate(order):
                holm[idx] = min(raw_p[idx] * (m - rank), 1.0)
            for (a, b), pw, ph in zip(pairs, raw_p, holm):
                sig = "Yes" if ph < 0.05 else "No"
                print(f"  {a} vs {b}: p_raw={pw:.4f} p_holm={ph:.4f} sig={sig}")

        print(f"  per-model means: {wide.mean().round(3).to_dict()}")
        print()
        results_summary.append((metric, n_tasks, stat, p))

    print("\n=== SUMMARY TABLE ===")
    print(f"{'Metric':28s} {'n':>4s} {'chi2':>8s} {'p':>12s}")
    for metric, n, stat, p in results_summary:
        print(f"{metric:28s} {n:4d} {stat:8.3f} {p:12.3e}")

    out_path = ROOT / "research" / "data" / "stylistic_task_level_recomputed.csv"
    task_level.to_csv(out_path, index=False)
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
