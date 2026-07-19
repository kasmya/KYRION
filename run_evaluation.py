"""
run_evaluation.py
=================

Audit every sample in research/samples/<model>/ and write a per-sample results
CSV. This is the file the analysis scripts and the paper's tables are built from.
The old repo referenced research/data/results.csv but never shipped it, so no
table could be reproduced. This script generates it deterministically.

USAGE:
    python3 run_evaluation.py
    python3 run_evaluation.py --out research/data/results.csv

OUTPUT columns (one row per audited sample):
    model, task, file,
    trust_score,
    quality_score, security_issues, dead_code, code_smells, parse_ok,
    hallucination_count, unresolved_local, unused_imports, imports_total,
    hallucination_rate_pct
"""
from __future__ import annotations

import argparse
import csv
import glob
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
from auditor import AIAuditor          # noqa: E402
from quality import analyze_code_quality  # noqa: E402
from hallucination import detect_hallucinations  # noqa: E402

SAMPLES_ROOT = Path(__file__).parent / "research" / "samples"


def _task_id(filename: str) -> str:
    """Best-effort extraction of a task identifier from varied filename schemes."""
    base = os.path.splitext(os.path.basename(filename))[0]
    return base


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="research/data/results.csv")
    args = ap.parse_args()

    files = sorted(glob.glob(str(SAMPLES_ROOT / "*" / "*.py")))
    files = [f for f in files if os.path.basename(os.path.dirname(f)) != "benchmark"]
    if not files:
        print("No samples found under research/samples/.")
        return 1

    rows = []
    for path in files:
        model = os.path.basename(os.path.dirname(path))
        code = open(path, encoding="utf-8", errors="ignore").read()

        # full audit (trust score with default weights from auditor.yaml)
        audit = AIAuditor().audit(code=code, verbose=False)
        q = analyze_code_quality(code)
        h = detect_hallucinations(code)

        rows.append({
            "model": model,
            "task": _task_id(path),
            "file": os.path.relpath(path, Path(__file__).parent),
            "trust_score": audit["trust_score"],
            "quality_score": q["score"],
            "security_issues": len(q["security_issues"]),
            "dead_code": len(q["dead_code"]),
            "code_smells": len(q["code_smells"]),
            "parse_ok": int(q["parse_ok"]),
            "hallucination_count": h["hallucination_count"],
            "unresolved_local": len(h["unresolved_local_imports"]),
            "unused_imports": len(h["unused_imports"]),
            "imports_total": h["imports_total"],
            "hallucination_rate_pct": h["hallucination_rate_pct"],
            # aliases consumed by research/analysis/*.py (kept for compatibility)
            "hallucination_risk": h["hallucination_rate_pct"],
            "total_issues": q["total_issues"],
        })

    out = Path(__file__).parent / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {out}")
    # quick per-model summary to stdout
    from statistics import mean
    models = sorted(set(r["model"] for r in rows))
    print(f"\n{'model':<10}{'n':>4}{'mean_trust':>12}{'mean_quality':>14}{'halluc':>8}")
    for m in models:
        mr = [r for r in rows if r["model"] == m]
        print(f"{m:<10}{len(mr):>4}{mean(r['trust_score'] for r in mr):>12.1f}"
              f"{mean(r['quality_score'] for r in mr):>14.1f}"
              f"{sum(r['hallucination_count'] for r in mr):>8}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
