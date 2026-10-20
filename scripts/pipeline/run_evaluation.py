"""
run_evaluation.py  (v2 — repetition-aware)
==========================================

Audit every repetition of every (model, task) and write TWO CSVs:

  1. research/data/results_runs.csv   — one row PER RUN (the raw per-generation data)
  2. research/data/results.csv        — one row PER (model,task) CELL, aggregated
                                        across runs with mean AND standard deviation

The per-run file is the ground truth for statistics (bootstrap CIs, Mann-Whitney,
etc). The per-cell file is what tables and quick summaries read. Crucially, with
k>=2 runs per cell we now get a real standard deviation — turning "DeepSeek = 50.5"
into "50.5 +/- 4.2", which every downstream statistical test depends on.

Reads the canonical structure:  research/samples/<model>/task<NN>/run<K>.py
Empty placeholder run files (not yet collected) are skipped and reported.

USAGE
    python3 scripts/pipeline/run_evaluation.py
    python3 scripts/pipeline/run_evaluation.py --runs-out research/data/results_runs.csv \
                              --cell-out research/data/results.csv
"""
from __future__ import annotations

import argparse
import csv
import glob
import os
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from auditor import AIAuditor            # noqa: E402
from quality import analyze_code_quality  # noqa: E402
from hallucination import detect_hallucinations  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = ROOT / "research" / "samples"

# metrics we aggregate across runs
METRICS = ["trust_score", "quality_score", "hallucination_count",
           "hallucination_rate_pct", "security_issues", "dead_code",
           "code_smells", "unused_imports", "total_issues"]


def audit_one(code: str) -> dict:
    audit = AIAuditor().audit(code=code, verbose=False)
    q = analyze_code_quality(code)
    h = detect_hallucinations(code)
    return {
        "trust_score": audit["trust_score"],
        "quality_score": q["score"],
        "security_issues": len(q["security_issues"]),
        "dead_code": len(q["dead_code"]),
        "code_smells": len(q["code_smells"]),
        "total_issues": q["total_issues"],
        "parse_ok": int(q["parse_ok"]),
        "hallucination_count": h["hallucination_count"],
        "unresolved_local": len(h["unresolved_local_imports"]),
        "unused_imports": len(h["unused_imports"]),
        "imports_total": h["imports_total"],
        "hallucination_rate_pct": h["hallucination_rate_pct"],
    }


def collect_run_rows() -> list[dict]:
    rows = []
    skipped_empty = 0
    for run_path in sorted(glob.glob(str(SAMPLES / "*" / "task*" / "run*.py"))):
        p = Path(run_path)
        model = p.parts[-3]
        task = p.parts[-2]
        run_m = re.match(r"run(\d+)\.py", p.name)
        if not run_m:
            continue
        run_k = int(run_m.group(1))
        code = p.read_text(encoding="utf-8", errors="ignore")
        if not code.strip():
            skipped_empty += 1
            continue  # placeholder not yet filled
        m = audit_one(code)
        m.update({"model": model, "task": task, "run": run_k,
                  "file": os.path.relpath(run_path, ROOT)})
        rows.append(m)
    if skipped_empty:
        print(f"Note: skipped {skipped_empty} empty placeholder run file(s).")
    return rows


def aggregate_cells(run_rows: list[dict]) -> list[dict]:
    # group by (model, task)
    cells: dict[tuple, list[dict]] = {}
    for r in run_rows:
        cells.setdefault((r["model"], r["task"]), []).append(r)

    out = []
    for (model, task), runs in sorted(cells.items()):
        rec = {"model": model, "task": task, "n_runs": len(runs)}
        for metric in METRICS:
            vals = [r[metric] for r in runs]
            rec[f"{metric}_mean"] = round(statistics.mean(vals), 3)
            rec[f"{metric}_sd"] = round(statistics.stdev(vals), 3) if len(vals) > 1 else 0.0
        # convenience aliases used by existing analysis scripts (mean values)
        rec["trust_score"] = rec["trust_score_mean"]
        rec["quality_score"] = rec["quality_score_mean"]
        rec["hallucination_risk"] = rec["hallucination_rate_pct_mean"]
        rec["total_issues"] = rec["total_issues_mean"]
        out.append(rec)
    return out


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs-out", default="research/data/results_runs.csv")
    ap.add_argument("--cell-out", default="research/data/results.csv")
    args = ap.parse_args()

    run_rows = collect_run_rows()
    if not run_rows:
        print("No populated run files found. Collect runs first (collect_runs.py).")
        return 1
    cells = aggregate_cells(run_rows)

    write_csv(ROOT / args.runs_out, run_rows)
    write_csv(ROOT / args.cell_out, cells)
    print(f"Wrote {len(run_rows)} run rows -> {args.runs_out}")
    print(f"Wrote {len(cells)} cell rows -> {args.cell_out}")

    # per-model summary with SD (the whole point of repetitions)
    from statistics import mean
    models = sorted(set(r["model"] for r in run_rows))
    print(f"\n{'model':<10}{'runs':>6}{'trust(mean)':>13}{'trust(sd)':>11}"
          f"{'quality':>10}{'halluc':>8}")
    for m in models:
        mr = [r for r in run_rows if r["model"] == m]
        trust_vals = [r["trust_score"] for r in mr]
        sd = statistics.stdev(trust_vals) if len(trust_vals) > 1 else 0.0
        print(f"{m:<10}{len(mr):>6}{mean(trust_vals):>13.1f}{sd:>11.2f}"
              f"{mean(r['quality_score'] for r in mr):>10.1f}"
              f"{sum(r['hallucination_count'] for r in mr):>8}")

    # variance sanity check: warn if every cell still has n=1 (no repetitions yet)
    max_n = max(c["n_runs"] for c in cells)
    if max_n < 2:
        print("\nWARNING: every cell has only 1 run — SD is 0 and no statistics are")
        print("possible yet. Collect k>=3 with collect_runs.py, then re-run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
