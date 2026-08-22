import pandas as pd
from scipy.stats import friedmanchisquare, wilcoxon
from itertools import combinations
import numpy as np

df = pd.read_csv("results.csv")

metric_cols = {
    "trust": "trust_score_mean",
    "quality": "quality_score_mean",
    "security": "security_issues_mean",
    "dead_code": "dead_code_mean",
    "code_smells": "code_smells_mean",
    "total_issues": "total_issues_mean",
    "hallucination": "hallucination_count_mean",
}

# drop task14 (missing entirely for gpt-oss-120b) to keep a complete block design
df = df[df.task != "task14"]

results_summary = []

for label, col in metric_cols.items():
    wide = df.pivot(index="task", columns="model", values=col)
    wide = wide.dropna()  # safety: only fully-populated tasks
    n_tasks = len(wide)
    models = list(wide.columns)

    if wide.nunique(axis=0).sum() == 0 or wide.values.std() == 0:
        print(f"{label}: no variance, skipping Friedman")
        continue

    stat, p = friedmanchisquare(*[wide[m] for m in models])
    print(f"\n{label}  (n_tasks={n_tasks})  Friedman chi2={stat:.3f}  p={p:.5f}")

    if p < 0.05:
        pairs = list(combinations(models, 2))
        raw_p, deltas = [], []
        for a, b in pairs:
            diffs = wide[a] - wide[b]
            if (diffs == 0).all():
                raw_p.append(1.0)
            else:
                _, pw = wilcoxon(wide[a], wide[b])
                raw_p.append(pw)
        order = np.argsort(raw_p)
        m = len(raw_p)
        holm = [0.0]*m
        for rank, idx in enumerate(order):
            holm[idx] = min(raw_p[idx] * (m - rank), 1.0)
        for (a, b), pw, ph in zip(pairs, raw_p, holm):
            sig = "Yes" if ph < 0.05 else "No"
            print(f"  {a} vs {b}: p_raw={pw:.4f} p_holm={ph:.4f} sig={sig}")

    results_summary.append((label, n_tasks, stat, p))

print("\n\n=== SUMMARY TABLE ===")
print(f"{'Metric':15s} {'n':>4s} {'chi2':>8s} {'p':>10s}")
for label, n, stat, p in results_summary:
    print(f"{label:15s} {n:4d} {stat:8.3f} {p:10.5f}")
