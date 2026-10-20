"""
phase4_paper_exhibits.py
========================
Generate the paper's core exhibits from the frozen results:
  1. Master results table (LaTeX) — per-model mean +/- 95% CI for every metric.
  2. A per-metric significance summary table (LaTeX).
  3. A bar chart (PNG) of mean scores with CI error bars, per metric.

These are the skeleton the Results prose wraps around — build them first.

USAGE:
    python3 scripts/analysis/phase4_paper_exhibits.py
Writes to research/data/paper_exhibits/:
    master_results_table.tex
    significance_summary.tex
    fig_<metric>.png
"""
from __future__ import annotations
import csv
from pathlib import Path
import numpy as np
from scipy import stats

DATA = Path("research/data")
OUT = DATA / "paper_exhibits"

METRICS = [("trust_score","Trust"), ("quality_score","Quality"),
           ("code_smells","Code Smells"), ("total_issues","Total Issues"),
           ("hallucination_count","Halluc.")]

def load():
    return list(csv.DictReader(open(DATA/"results_runs.csv")))

def short(m): return m.split("__")[-1]

def boot_ci(vals, n=10000, seed=42):
    rng = np.random.default_rng(seed)
    a = np.asarray(vals,float)
    b = rng.choice(a, size=(n,len(a)), replace=True).mean(1)
    return a.mean(), np.percentile(b,2.5), np.percentile(b,97.5)

def cell_means(runs, metric):
    """task-level means per model, for the significance test."""
    cell = {}
    for r in runs:
        cell.setdefault((r["model"],r["task"]),[]).append(float(r[metric]))
    by = {}
    for (m,_),v in cell.items():
        by.setdefault(m,[]).append(np.mean(v))
    return by

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    runs = load()
    models = sorted({r["model"] for r in runs})

    # ---------- 1. master results table ----------
    lines = [r"\begin{table*}[t]", r"\centering",
             r"\caption{Per-model performance across 20 tasks "
             r"(mean $\pm$ 95\% bootstrap CI, $n\approx60$ generations per model). "
             r"Best value per column in bold.}",
             r"\label{tab:master}",
             r"\begin{tabular}{l" + "c"*len(METRICS) + "}", r"\toprule",
             "Model & " + " & ".join(l for _,l in METRICS) + r" \\", r"\midrule"]

    # compute for bolding
    metric_means = {}
    for mk,_ in METRICS:
        metric_means[mk] = {m: np.mean([float(r[mk]) for r in runs if r["model"]==m])
                            for m in models}
    for m in sorted(models, key=lambda x:-metric_means["trust_score"][x]):
        cells = []
        for mk,_ in METRICS:
            vals = [float(r[mk]) for r in runs if r["model"]==m]
            mean, lo, hi = boot_ci(vals)
            # bold if best (max for scores, min for smells/issues/halluc)
            better_low = mk in ("code_smells","total_issues","hallucination_count")
            best_val = (min if better_low else max)(metric_means[mk].values())
            is_best = abs(metric_means[mk][m]-best_val) < 1e-9
            cell = f"{mean:.1f}"
            if is_best: cell = r"\textbf{"+cell+"}"
            cells.append(cell)
        lines.append(f"{short(m)} & " + " & ".join(cells) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table*}"]
    (OUT/"master_results_table.tex").write_text("\n".join(lines))

    # ---------- 2. significance summary ----------
    sig_lines = [r"\begin{table}[t]", r"\centering",
                 r"\caption{Kruskal--Wallis omnibus test per metric (task-level, "
                 r"$n=20$ tasks per model).}", r"\label{tab:significance}",
                 r"\begin{tabular}{lccc}", r"\toprule",
                 r"Metric & $H$ & $p$ & Significant? \\", r"\midrule"]
    for mk,label in METRICS:
        by = cell_means(runs, mk)
        groups = [by[m] for m in models]
        try:
            if all(all(v==0 for v in g) for g in groups):
                h,p = float("nan"), float("nan")
            else:
                h,p = stats.kruskal(*groups)
        except ValueError:
            h,p = float("nan"), float("nan")
        sig = "Yes" if (p==p and p<0.05) else "No"
        pstr = "--" if p!=p else f"{p:.3f}"
        hstr = "--" if h!=h else f"{h:.2f}"
        sig_lines.append(f"{label} & {hstr} & {pstr} & {sig} " + r"\\")
    sig_lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    (OUT/"significance_summary.tex").write_text("\n".join(sig_lines))

    # ---------- 3. figures ----------
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        for mk,label in METRICS:
            fig, ax = plt.subplots(figsize=(7,4))
            ms = sorted(models, key=lambda x:-metric_means[mk][x])
            means, los, his = [], [], []
            for m in ms:
                vals=[float(r[mk]) for r in runs if r["model"]==m]
                mn,lo,hi = boot_ci(vals)
                means.append(mn); los.append(mn-lo); his.append(hi-mn)
            ax.bar(range(len(ms)), means, yerr=[los,his], capsize=4,
                   color="#4C72B0", alpha=0.85)
            ax.set_xticks(range(len(ms)))
            ax.set_xticklabels([short(m) for m in ms], rotation=30, ha="right", fontsize=8)
            ax.set_ylabel(label); ax.set_title(f"{label} by model (95% CI)")
            fig.tight_layout()
            fig.savefig(OUT/f"fig_{mk}.png", dpi=150)
            plt.close(fig)
        figs = f"{len(METRICS)} figures"
    except ImportError:
        figs = "matplotlib not installed — skipped figures (pip install matplotlib)"

    print("Wrote exhibits to", OUT)
    print("  master_results_table.tex")
    print("  significance_summary.tex")
    print(" ", figs)
    print("\nDrop the .tex files straight into your paper; regenerate anytime the")
    print("frozen dataset changes.")

if __name__ == "__main__":
    main()
