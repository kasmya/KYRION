"""
stats_analysis.py
=================
Inferential statistics for the model comparison. Reads the PER-RUN data
(results_runs.csv) so it uses the real repetition variance, not collapsed means.

Produces everything the paper needs to defend "model A differs from model B":

  1. Descriptive table with bootstrap 95% confidence intervals per model.
  2. Kruskal-Wallis omnibus test — are the models different at all? (non-parametric,
     right for small n and non-normal scores).
  3. Pairwise Mann-Whitney U with Holm-Bonferroni correction — WHICH pairs differ.
  4. Cliff's delta effect size for each pair — HOW BIG the difference is
     (negligible/small/medium/large), independent of significance.

Why non-parametric: with ~3 runs/cell and bounded 0-100 scores, normality can't be
assumed. Kruskal-Wallis + Mann-Whitney + Cliff's delta make no normality assumption
and are the standard defensible choice for this design.

USAGE:
    python3 scripts/pipeline/stats_analysis.py                       # metric = trust_score
    python3 scripts/pipeline/stats_analysis.py --metric quality_score
    python3 scripts/pipeline/stats_analysis.py --metric hallucination_count
    python3 scripts/pipeline/stats_analysis.py --unit run            # per-run (default)
    python3 scripts/pipeline/stats_analysis.py --unit cell           # per-cell means (task-level)

Writes a CSV of pairwise results to research/data/stats_<metric>.csv.
"""
from __future__ import annotations

import argparse
import csv
import itertools
from pathlib import Path

import numpy as np
from scipy import stats

RUNS_CSV = Path("research/data/results_runs.csv")
OUT_DIR = Path("research/data")

VALID_METRICS = ["trust_score", "quality_score", "hallucination_count",
                 "hallucination_rate_pct", "security_issues", "dead_code",
                 "code_smells", "total_issues"]


# --------------------------------------------------------------------------
def load(metric: str, unit: str):
    """Return {model: [values]}. unit='run' uses every run; unit='cell' averages
    runs within each (model,task) first (task-level analysis)."""
    rows = list(csv.DictReader(open(RUNS_CSV)))
    if metric not in rows[0]:
        raise SystemExit(f"metric '{metric}' not in CSV. Available: "
                         f"{[c for c in rows[0] if c in VALID_METRICS]}")
    by_model: dict[str, list[float]] = {}
    if unit == "run":
        for r in rows:
            by_model.setdefault(r["model"], []).append(float(r[metric]))
    else:  # cell
        cell: dict[tuple, list[float]] = {}
        for r in rows:
            cell.setdefault((r["model"], r["task"]), []).append(float(r[metric]))
        for (m, _), vals in cell.items():
            by_model.setdefault(m, []).append(float(np.mean(vals)))
    return by_model


def short(name: str) -> str:
    return name.split("__")[-1]


# --------------------------------------------------------------------------
def bootstrap_ci(values, n_boot=10000, ci=95, seed=42):
    rng = np.random.default_rng(seed)
    arr = np.asarray(values, dtype=float)
    boot = rng.choice(arr, size=(n_boot, len(arr)), replace=True).mean(axis=1)
    lo, hi = np.percentile(boot, [(100 - ci) / 2, 100 - (100 - ci) / 2])
    return float(arr.mean()), float(lo), float(hi)


def cliffs_delta(a, b):
    """Cliff's delta effect size in [-1, 1]. Positive => a tends to exceed b."""
    a = np.asarray(a); b = np.asarray(b)
    gt = sum((x > b).sum() for x in a)
    lt = sum((x < b).sum() for x in a)
    d = (gt - lt) / (len(a) * len(b))
    ad = abs(d)
    mag = ("negligible" if ad < 0.147 else "small" if ad < 0.33
           else "medium" if ad < 0.474 else "large")
    return d, mag


def holm_correction(pairs):
    """Holm-Bonferroni: sort p asc, adjust. pairs = list of dicts with 'p_raw'."""
    ordered = sorted(pairs, key=lambda x: x["p_raw"])
    m = len(ordered)
    prev = 0.0
    for i, rec in enumerate(ordered):
        adj = min(1.0, rec["p_raw"] * (m - i))
        adj = max(adj, prev)  # enforce monotonicity
        rec["p_holm"] = adj
        prev = adj
    return pairs


# --------------------------------------------------------------------------
def main(metric: str, unit: str):
    data = load(metric, unit)
    models = sorted(data.keys())
    n_unit = "runs" if unit == "run" else "task-means"

    print("=" * 74)
    print(f"STATISTICAL ANALYSIS — metric: {metric}   (unit: 1 sample = 1 {unit})")
    print("=" * 74)

    # 1. Descriptives + bootstrap CI
    print(f"\n1) DESCRIPTIVES with 95% bootstrap CI ({n_unit} per model)\n")
    print(f"{'model':<28}{'n':>5}{'mean':>9}{'95% CI':>20}{'median':>9}")
    print("-" * 71)
    desc = {}
    for m in sorted(models, key=lambda x: -np.mean(data[x])):
        vals = data[m]
        mean, lo, hi = bootstrap_ci(vals)
        desc[m] = (mean, lo, hi)
        print(f"{short(m):<28}{len(vals):>5}{mean:>9.2f}"
              f"{f'[{lo:.1f}, {hi:.1f}]':>20}{np.median(vals):>9.1f}")

    # 2. Kruskal-Wallis omnibus
    print(f"\n2) KRUSKAL-WALLIS omnibus test (are the {len(models)} models different?)\n")
    all_vals = [v for m in models for v in data[m]]
    if len(set(all_vals)) <= 1:
        print("   All values identical across models (no variance).")
        print("   => Models are trivially indistinguishable on this metric.")
        print(f"   (Every model scored {all_vals[0] if all_vals else 0} on every task.)")
        return
    h, p_kw = stats.kruskal(*[data[m] for m in models])
    print(f"   H = {h:.3f},  p = {p_kw:.3e}")
    if p_kw < 0.05:
        print("   => Significant: at least one model differs. Proceed to pairwise.")
    else:
        print("   => NOT significant: no evidence models differ on this metric.")
        print("      (Report this honestly; pairwise tests would be post-hoc noise.)")

    # 3 + 4. Pairwise Mann-Whitney + Cliff's delta
    print(f"\n3+4) PAIRWISE Mann-Whitney U (Holm-corrected) + Cliff's delta\n")
    pairs = []
    for a, b in itertools.combinations(models, 2):
        u, p_raw = stats.mannwhitneyu(data[a], data[b], alternative="two-sided")
        d, mag = cliffs_delta(data[a], data[b])
        pairs.append({"a": a, "b": b, "U": u, "p_raw": p_raw,
                      "cliffs_delta": d, "magnitude": mag})
    holm_correction(pairs)

    print(f"{'pair':<46}{'p(Holm)':>10}{'sig':>5}{'delta':>8}{'size':>12}")
    print("-" * 81)
    for rec in sorted(pairs, key=lambda x: x["p_holm"]):
        sig = "***" if rec["p_holm"] < 0.001 else "**" if rec["p_holm"] < 0.01 \
              else "*" if rec["p_holm"] < 0.05 else "ns"
        label = f"{short(rec['a'])} vs {short(rec['b'])}"
        print(f"{label:<46}{rec['p_holm']:>10.3e}{sig:>5}"
              f"{rec['cliffs_delta']:>8.2f}{rec['magnitude']:>12}")

    # write CSV
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"stats_{metric}.csv"
    with open(out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["model_a", "model_b", "U", "p_raw", "p_holm",
                    "cliffs_delta", "magnitude"])
        for r in pairs:
            w.writerow([r["a"], r["b"], r["U"], r["p_raw"], r["p_holm"],
                        round(r["cliffs_delta"], 4), r["magnitude"]])
    print(f"\nWrote pairwise results -> {out}")

    # interpretation helper
    sig_pairs = [r for r in pairs if r["p_holm"] < 0.05]
    print(f"\nSUMMARY: {len(sig_pairs)} of {len(pairs)} pairs differ significantly "
          f"(Holm p<0.05) on {metric}.")
    print("For the paper: report H, p from Kruskal-Wallis; then the significant")
    print("pairs with their Cliff's delta. Non-significant pairs => 'statistically")
    print("indistinguishable', which is a finding, not a failure.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--metric", default="trust_score", choices=VALID_METRICS)
    ap.add_argument("--unit", default="run", choices=["run", "cell"])
    main(ap.parse_args().metric, ap.parse_args().unit)
