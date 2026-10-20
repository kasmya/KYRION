"""
phase3_claims_table.py
======================
Builds a claims-to-evidence table: every factual claim the paper will make, paired
with the exact file + number that backs it. This is the single best defense against
the original paper's disease (claims the code could not support). If a claim has no
backing, it shows UNBACKED so you either generate the evidence or cut the claim.

It auto-reads the CSVs you've generated and fills in the real numbers where it can,
so the table is pre-populated with your actual results.

USAGE:
    python3 scripts/analysis/phase3_claims_table.py
Writes research/data/claims_evidence.md (the table) — review it before writing.
"""
from __future__ import annotations
import csv
from pathlib import Path
import numpy as np

DATA = Path("research/data")

def read_csv(name):
    p = DATA / name
    if not p.exists():
        return None
    return list(csv.DictReader(open(p)))

def model_means(runs, metric):
    if not runs: return {}
    by = {}
    for r in runs:
        by.setdefault(r["model"], []).append(float(r[metric]))
    return {m: np.mean(v) for m,v in by.items()}

def short(m): return m.split("__")[-1]

def kw_result(name):
    """Pull H,p from a stats_<metric>.csv is not stored; recompute note instead."""
    return None

def main():
    runs = read_csv("results_runs.csv")
    claims = []  # (section, claim, evidence_file, value_or_status)

    def add(section, claim, ev, val):
        claims.append((section, claim, ev, val))

    # ---- dataset claims ----
    if runs:
        n = len(runs)
        models = sorted({r["model"] for r in runs})
        add("Dataset", f"We evaluate {len(models)} models across 20 tasks",
            "results_runs.csv", f"{len(models)} models, {n} runs")
        counts = {m: sum(1 for r in runs if r["model"]==m) for m in models}
        bal = "balanced ~60/model" if min(counts.values())>=57 else f"UNBALANCED {counts}"
        add("Dataset", "Each cell has multiple repetitions (k>=3)",
            "results_runs.csv", bal)
    else:
        add("Dataset", "We evaluate N models across 20 tasks", "results_runs.csv", "UNBACKED - run run_evaluation.py")

    # ---- detector validation ----
    val = read_csv("detector_validation.csv")
    if val:
        d = {r["metric"]: r["value"] for r in val}
        add("Method", "Hallucination detector validated against ground truth",
            "detector_validation.csv",
            f"P={d.get('precision','?')}, R={d.get('recall','?')}, F1={d.get('f1','?')}")
    else:
        add("Method", "Hallucination detector validated against ground truth",
            "detector_validation.csv", "UNBACKED - run validate_detector.py")

    # ---- per-metric descriptive claims ----
    if runs:
        for metric, label in [("trust_score","Trust Score"),
                              ("quality_score","Quality Score"),
                              ("code_smells","code smells"),
                              ("hallucination_count","true hallucinations")]:
            mm = model_means(runs, metric)
            best = max(mm, key=mm.get) if "hallucination" not in metric and "smell" not in metric else min(mm, key=mm.get)
            add("Results", f"Model ranking on {label} (best: {short(best)})",
                f"stats_{metric}.csv",
                "; ".join(f"{short(m)}={v:.1f}" for m,v in sorted(mm.items(), key=lambda x:-x[1])))

    # ---- significance claims (these must come from stats output) ----
    add("Results", "Models are statistically indistinguishable on Trust/Quality",
        "stats_trust_score.csv, stats_quality_score.csv",
        "VERIFY: Kruskal-Wallis p>0.05 at task level (you reported p=0.36, 0.32)")
    add("Results", "Models differ significantly on code smells",
        "stats_code_smells.csv",
        "VERIFY: H=12.65, p=0.013; gpt-oss vs llama-3.1 & deepseek significant (delta=0.52)")
    add("Results", "Which specific smell types differ",
        "smell_breakdown.csv",
        "FILL after running phase2_smell_breakdown.py")

    # ---- robustness ----
    ws = read_csv("weight_sensitivity.csv")
    add("Results", "Conclusions robust to Trust-Score weighting",
        "weight_sensitivity.csv",
        "backed" if ws else "UNBACKED - run weight_sensitivity.py")

    # ---- claims you must NOT make ----
    nono = [
        "Do NOT claim any model is 'unsafe' or 'dangerous' - not statistically supported",
        "Do NOT claim 'execution-based' detection - detector is static (AST)",
        "Do NOT claim significant Trust/Quality differences - they are tied",
        "Do NOT claim 'hallucination in every sample' - true rate is near zero",
        "Do NOT drop Holm correction to manufacture significance",
    ]

    # ---- write markdown ----
    out = DATA / "claims_evidence.md"
    lines = ["# Claims-to-Evidence Table",
             "",
             "Every claim below must trace to the listed file. `UNBACKED`/`VERIFY`/`FILL`",
             "means do that before writing the sentence.",
             "",
             "| Section | Claim | Evidence file | Value / Status |",
             "|---------|-------|---------------|----------------|"]
    for s,c,ev,val in claims:
        lines.append(f"| {s} | {c} | `{ev}` | {val} |")
    lines += ["", "## Claims you must NOT make (write-time guardrails)", ""]
    for x in nono:
        lines.append(f"- {x}")
    out.write_text("\n".join(lines))
    print(f"Wrote claims table -> {out}")
    print(f"\n{len(claims)} claims mapped. Open the file and resolve every")
    print("UNBACKED / VERIFY / FILL before writing that section.")

if __name__ == "__main__":
    main()
