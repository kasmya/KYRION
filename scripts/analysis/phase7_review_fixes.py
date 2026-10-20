"""
phase7_review_fixes.py
======================
Zero-new-data analyses for reviewer items #3 and #6. Runs on CSVs you already have.

  #3 Multiple-comparisons correction across metrics: the 7 omnibus tests were run
     without correcting for testing 7 metrics. Apply Benjamini-Hochberg (FDR) and
     Bonferroni to the omnibus p-values; report which survive.

  #6 n=3 reliability: for each significant metric, compute within-cell dispersion
     (mean per-cell SD and range across the 3 runs) to show the 3-run estimates
     are stable.

USAGE:
    python3 scripts/analysis/phase7_review_fixes.py
Reads research/data/results_runs.csv (per-run) — no new generation needed.
"""
import csv, statistics
from pathlib import Path
import numpy as np
from scipy import stats

DATA = Path("research/data")

def load():
    return list(csv.DictReader(open(DATA/"results_runs.csv")))

def task_means(rows, metric):
    cell = {}
    for r in rows:
        cell.setdefault((r["model"], r["task"]), []).append(float(r[metric]))
    by = {}
    for (m,_), v in cell.items():
        by.setdefault(m, []).append(np.mean(v))
    return by

def bh_correction(pvals):
    """Benjamini-Hochberg FDR. Returns adjusted p-values in original order."""
    n = len(pvals)
    order = sorted(range(n), key=lambda i: pvals[i])
    adj = [0.0]*n
    prev = 1.0
    for rank, i in enumerate(reversed(order)):
        k = n - rank
        val = min(prev, pvals[i]*n/k)
        adj[i] = val
        prev = val
    return adj

def main():
    rows = load()
    metrics = ["trust_score","quality_score","code_smells","total_issues",
               "security_issues","dead_code","hallucination_count"]

    # ---- #3 multiple-comparisons correction on omnibus p-values ----
    print("="*70)
    print("#3 MULTIPLE-COMPARISONS CORRECTION (7 omnibus tests)")
    print("="*70)
    results = []
    for m in metrics:
        by = task_means(rows, m)
        models = sorted(by.keys())
        groups = [by[mm] for mm in models]
        allv = [v for g in groups for v in g]
        if len(set(allv)) <= 1:
            results.append((m, float('nan'), float('nan')))
            continue
        H, p = stats.kruskal(*groups)
        results.append((m, H, p))

    valid = [(m,H,p) for m,H,p in results if p==p]  # drop nan
    pvals = [p for _,_,p in valid]
    bh = bh_correction(pvals)
    bonf = [min(1.0, p*len(pvals)) for p in pvals]

    print(f"\n{'metric':<20}{'H':>8}{'p_raw':>10}{'p_BH':>10}{'p_Bonf':>10}{'sig(BH)':>9}")
    print("-"*67)
    for (m,H,p),b,bf in zip(valid, bh, bonf):
        sig = "yes" if b < 0.05 else "no"
        print(f"{m:<20}{H:>8.2f}{p:>10.4f}{b:>10.4f}{bf:>10.4f}{sig:>9}")
    print("\nMetrics with no variance (all identical), excluded from correction:")
    for m,H,p in results:
        if p!=p: print(f"  {m}")

    # ---- #6 n=3 reliability ----
    print("\n"+"="*70)
    print("#6 n=3 RELIABILITY (within-cell dispersion across 3 runs)")
    print("="*70)
    print(f"\n{'metric':<20}{'mean cell SD':>14}{'mean cell range':>16}")
    print("-"*50)
    for m in ["trust_score","quality_score","code_smells","dead_code"]:
        cell = {}
        for r in rows:
            cell.setdefault((r["model"],r["task"]), []).append(float(r[m]))
        sds, ranges = [], []
        for k, v in cell.items():
            if len(v) >= 2:
                sds.append(statistics.stdev(v))
                ranges.append(max(v)-min(v))
        print(f"{m:<20}{np.mean(sds):>14.2f}{np.mean(ranges):>16.2f}")
    print("\nInterpretation: low mean within-cell SD/range => 3 runs give stable")
    print("per-cell estimates; the task-level means are not driven by run-to-run noise.")

if __name__ == "__main__":
    main()
