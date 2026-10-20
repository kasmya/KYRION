"""
phase6_humaneval.py
===================
PRIORITY 2 -- evaluate KYRION on a recognized benchmark (HumanEval).

Purpose: reviewers want to see the tool applied to a standard benchmark, not only
a custom dataset. This does two things:

  1. Runs KYRION's auditor over HumanEval canonical solutions (and, optionally,
     model-generated completions) to show the tool works on standard data.

  2. CONSTRUCT VALIDITY: correlates KYRION's Trust Score with functional
     correctness (whether the code passes HumanEval's own unit tests). A positive
     correlation is evidence that the Trust Score captures something real; a null
     correlation is still reportable ("KYRION measures non-functional quality
     orthogonal to correctness").

HumanEval provides, per problem: a prompt, a canonical_solution, and a `test`
function plus an entry_point. We build the full program (prompt + solution),
audit it with KYRION, optionally execute the tests to get a pass/fail label, then
report the correlation between Trust Score and pass rate.

USAGE:
    # audit canonical solutions only (no execution) -- safe, fast
    python3 scripts/analysis/phase6_humaneval.py --mode audit

    # audit + execute tests to get correctness labels (runs code in a subprocess)
    python3 scripts/analysis/phase6_humaneval.py --mode validate --limit 50

SAFETY: executing benchmark code runs third-party code. We run each problem in a
separate subprocess with a timeout. Use --mode audit if you don't want execution.

DATA: expects human-eval's JSONL. If not present, the script prints how to get it.
"""
from __future__ import annotations
import argparse, json, subprocess, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from auditor import AIAuditor                    # noqa: E402
from quality import analyze_code_quality         # noqa: E402
from hallucination import detect_hallucinations  # noqa: E402

DATA = Path("research/data")
HUMANEVAL = Path("research/data/HumanEval.jsonl")


def load_humaneval():
    if not HUMANEVAL.exists():
        print("HumanEval.jsonl not found. Get it with ONE of:")
        print("  pip install human-eval    # then find HumanEval.jsonl.gz in the package")
        print("  # or download from https://github.com/openai/human-eval")
        print(f"  Place the JSONL at: {HUMANEVAL}")
        return None
    problems = []
    for line in HUMANEVAL.read_text().splitlines():
        if line.strip():
            problems.append(json.loads(line))
    return problems


def audit_program(code: str) -> dict:
    audit = AIAuditor().audit(code=code, verbose=False)
    q = analyze_code_quality(code)
    h = detect_hallucinations(code)
    return {"trust_score": audit["trust_score"], "quality_score": q["score"],
            "security_issues": len(q["security_issues"]),
            "code_smells": len(q["code_smells"]),
            "hallucination_count": h["hallucination_count"],
            "total_issues": q["total_issues"]}


def run_tests(problem: dict, solution: str) -> int:
    """Execute HumanEval's own tests for one problem in a subprocess.
    Returns 1 if all tests pass, 0 otherwise."""
    program = (problem["prompt"] + solution + "\n" +
               problem["test"] + "\n" +
               f"check({problem['entry_point']})\n")
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as tf:
        tf.write(program); tmp = tf.name
    try:
        r = subprocess.run([sys.executable, tmp], capture_output=True,
                           timeout=10, text=True)
        return 1 if r.returncode == 0 else 0
    except Exception:
        return 0
    finally:
        Path(tmp).unlink(missing_ok=True)


def main(mode: str, limit: int | None):
    problems = load_humaneval()
    if problems is None:
        return 1
    if limit:
        problems = problems[:limit]

    import numpy as np
    rows = []
    for i, p in enumerate(problems):
        full = p["prompt"] + p["canonical_solution"]
        a = audit_program(full)
        a["task_id"] = p["task_id"]
        if mode == "validate":
            a["passes"] = run_tests(p, p["canonical_solution"])
        rows.append(a)
        if (i + 1) % 20 == 0:
            print(f"  audited {i+1}/{len(problems)}...")

    # write CSV
    DATA.mkdir(parents=True, exist_ok=True)
    import csv
    keys = list(rows[0].keys())
    with open(DATA / "humaneval_results.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys); w.writeheader(); w.writerows(rows)

    print("\n" + "=" * 64)
    print(f"KYRION on HumanEval  ({len(rows)} problems)")
    print("=" * 64)
    trust = [r["trust_score"] for r in rows]
    qual = [r["quality_score"] for r in rows]
    print(f"Mean Trust Score : {np.mean(trust):.1f}  (SD {np.std(trust):.1f})")
    print(f"Mean Quality     : {np.mean(qual):.1f}")
    print(f"Total hallucinations: {sum(r['hallucination_count'] for r in rows)}")
    print(f"Total code smells   : {sum(r['code_smells'] for r in rows)}")

    if mode == "validate":
        from scipy import stats
        passes = [r["passes"] for r in rows]
        pass_rate = np.mean(passes)
        print(f"\nCanonical-solution pass rate: {pass_rate:.1%}")
        # correlation: does higher Trust Score associate with passing?
        if len(set(passes)) > 1:
            # point-biserial correlation (continuous Trust vs binary pass)
            r_pb, p_pb = stats.pointbiserialr(passes, trust)
            print(f"\nCONSTRUCT VALIDITY:")
            print(f"  Point-biserial correlation (Trust vs pass): r={r_pb:.3f}, p={p_pb:.3f}")
            if p_pb < 0.05 and r_pb > 0:
                print("  => Trust Score significantly predicts correctness. Strong result.")
            elif p_pb < 0.05 and r_pb < 0:
                print("  => Negative correlation -- investigate before reporting.")
            else:
                print("  => No significant correlation. Report honestly: KYRION measures")
                print("     non-functional quality, orthogonal to functional correctness.")
        else:
            print("  (All solutions passed -- no variance to correlate. Use model")
            print("   completions instead of canonical solutions for variance.)")

    print(f"\nWrote research/data/humaneval_results.csv")
    print("\nFor the paper: report mean Trust on HumanEval + the correlation. Even a")
    print("null correlation is a legitimate finding about what the tool measures.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["audit", "validate"], default="audit")
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    sys.exit(main(a.mode, a.limit))
