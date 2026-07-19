"""
weight_sensitivity.py
=====================

Reproduces the Trust-Score weight-sensitivity analysis the paper describes.

The old repo could NOT produce this experiment because the Trust Score was a
hardcoded unweighted mean (no weights existed). Now that weights are real and
configurable (auditor.yaml / AIAuditor(weights=...)), this script sweeps the
weights and reports how each model's mean Trust Score — and, crucially, the model
RANKING — responds. A finding is "robust to weighting" only if the ranking is
stable across the sweep.

WHAT IT DOES
    1. Audits every sample in research/samples/<model>/ under the default weights.
    2. Re-scores them under a grid of weight vectors (each phase varied while the
       others stay balanced), plus the corner cases (one phase dominant).
    3. Prints, for each weight vector, every model's mean Trust Score and the
       induced ranking, so you can state precisely whether conclusions hold.

USAGE
    python3 weight_sensitivity.py
    python3 weight_sensitivity.py --step 0.25    # coarser/finer grid

Output is deterministic given the samples, so the numbers are reproducible and
citable. Save the printed table to research/data/weight_sensitivity.csv for the
paper's appendix.
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
from auditor import AIAuditor  # noqa: E402

SAMPLES_ROOT = Path(__file__).parent / "research" / "samples"


def _load_samples():
    samples = {}
    for path in sorted(glob.glob(str(SAMPLES_ROOT / "*" / "*.py"))):
        model = os.path.basename(os.path.dirname(path))
        if model == "benchmark":
            continue
        code = open(path, encoding="utf-8", errors="ignore").read()
        samples.setdefault(model, []).append(code)
    return samples


def _mean_trust(codes, weights):
    total, n = 0, 0
    for code in codes:
        r = AIAuditor(weights=weights).audit(code=code, verbose=False)
        total += r["trust_score"]
        n += 1
    return round(total / n, 2) if n else 0.0


def _ranking(model_scores):
    return [m for m, _ in sorted(model_scores.items(), key=lambda kv: -kv[1])]


def _weight_grid(step: float):
    """Yield (label, weights) vectors: the default, plus each phase dominant, plus
    a symmetric sweep of the hallucination weight with the rest split evenly."""
    yield "equal (1/3,1/3,1/3)", {"hallucination": 1/3, "instruction": 1/3, "quality": 1/3}
    yield "halluc-dominant", {"hallucination": 0.8, "instruction": 0.1, "quality": 0.1}
    yield "instr-dominant", {"hallucination": 0.1, "instruction": 0.8, "quality": 0.1}
    yield "quality-dominant", {"hallucination": 0.1, "instruction": 0.1, "quality": 0.8}
    w = step
    while w <= 1.0 - step + 1e-9:
        rest = (1 - w) / 2
        yield f"halluc={w:.2f}", {"hallucination": w, "instruction": rest, "quality": rest}
        w += step


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", type=float, default=0.25)
    ap.add_argument("--csv", default="research/data/weight_sensitivity.csv",
                    help="where to write the sweep table as CSV")
    args = ap.parse_args()

    samples = _load_samples()
    if not samples:
        print("No samples found under research/samples/. Nothing to sweep.")
        return 1
    models = sorted(samples)

    print("Trust-Score weight-sensitivity sweep")
    print("=" * 72)
    header = f"{'weight vector':<24}" + "".join(f"{m[:8]:>9}" for m in models) + "   ranking"
    print(header)
    print("-" * len(header))

    csv_rows = []  # collected for CSV dump
    baseline_rank = None
    rank_changes = 0
    for label, weights in _weight_grid(args.step):
        scores = {m: _mean_trust(samples[m], weights) for m in models}
        rank = _ranking(scores)
        if baseline_rank is None:
            baseline_rank = rank
        elif rank != baseline_rank:
            rank_changes += 1
        row = f"{label:<24}" + "".join(f"{scores[m]:>9.1f}" for m in models)
        print(row + "   " + " > ".join(r[:6] for r in rank))
        csv_rows.append({
            "weight_vector": label,
            "w_hallucination": round(weights["hallucination"], 4),
            "w_instruction": round(weights["instruction"], 4),
            "w_quality": round(weights["quality"], 4),
            **{f"trust_{m}": scores[m] for m in models},
            "ranking": " > ".join(rank),
        })

    print("-" * len(header))
    print(f"Baseline ranking (equal weights): {' > '.join(baseline_rank)}")
    if rank_changes == 0:
        print("RESULT: model ranking is STABLE across all tested weight vectors")
        print("        -> conclusions are robust to weighting (report this).")
    else:
        print(f"RESULT: ranking changed under {rank_changes} weight vector(s)")
        print("        -> state precisely which conclusions are weight-dependent.")

    # --- write CSV for the paper appendix ---
    import csv as _csv
    out = Path(__file__).parent / args.csv
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        writer = _csv.DictWriter(fh, fieldnames=list(csv_rows[0].keys()))
        writer.writeheader()
        writer.writerows(csv_rows)
    print(f"\nWrote sweep table to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
