"""
humaneval_completions.py
========================
Generate HumanEval completions with your five models, then audit them with KYRION.
This is the stronger benchmark evaluation (reviewer's 5-star item): auditing
MODEL-GENERATED code, not just canonical solutions.

Two phases:
  1. generate: call each model on each HumanEval prompt, save completions to
     dataset_outputs_humaneval/<model>/HumanEval_<id>/run<k>.py
  2. audit: run KYRION over the completions and report per-model Trust/Quality/
     security/hallucination/style/dead-code + a Kruskal-Wallis test.

USAGE (run from the repo root):
  # generate (needs api_config.py with your keys, like the main generator)
  python3 scripts/generation/humaneval_completions.py --mode generate --k 1 --limit 40

  # audit whatever has been generated
  python3 scripts/generation/humaneval_completions.py --mode audit

Reuses your existing api_config.py (MODEL_CONFIGS, NVIDIA_BASE_URL) so the same
keys/models are used. Keep --limit modest first; 164 x 5 models is a lot of calls.
"""
from __future__ import annotations
import argparse, glob, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
from auditor import AIAuditor
from quality import analyze_code_quality
from hallucination import detect_hallucinations

HE = Path("research/data/HumanEval.jsonl")
OUT = Path("dataset_outputs_humaneval")
CODE_BLOCK = re.compile(r"```(?:python)?\s*(.*?)```", re.DOTALL)


def load_he(limit):
    problems = [json.loads(l) for l in HE.read_text().splitlines() if l.strip()]
    return problems[:limit] if limit else problems


def slug(m): return m.replace("/", "__").replace(".", "-").replace("_", "-")


def generate(k, limit):
    try:
        from openai import OpenAI
        from api_config import MODEL_CONFIGS, NVIDIA_BASE_URL
    except ImportError as e:
        print("Need openai + api_config.py:", e); return
    problems = load_he(limit)
    for model_id, cfg in MODEL_CONFIGS.items():
        client = OpenAI(api_key=cfg["api_key"], base_url=NVIDIA_BASE_URL)
        for p in problems:
            pid = p["task_id"].replace("/", "_")
            for run in range(1, k + 1):
                folder = OUT / slug(model_id) / pid
                folder.mkdir(parents=True, exist_ok=True)
                target = folder / f"run{run}.py"
                if target.exists():
                    continue
                prompt = ("Complete this Python function. Return only the complete "
                          "function code.\n\n" + p["prompt"])
                try:
                    r = client.chat.completions.create(
                        model=model_id,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=1024, temperature=0.7, timeout=90)
                    text = r.choices[0].message.content or ""
                    blocks = CODE_BLOCK.findall(text)
                    code = blocks[0].strip() if blocks else text.strip()
                    # ensure the prompt (signature) is present
                    if "def " not in code:
                        code = p["prompt"] + code
                    target.write_text(code)
                    print(f"  {slug(model_id)}/{pid}/run{run}")
                except Exception as e:
                    print(f"  ERR {model_id} {pid}: {str(e)[:60]}")
    print("Generation done.")


def audit():
    import numpy as np
    from scipy import stats
    rows = []
    for f in sorted(glob.glob(str(OUT / "*" / "*" / "run*.py"))):
        p = Path(f); model = p.parts[-3]
        code = p.read_text(encoding="utf-8", errors="ignore")
        if not code.strip():
            continue
        a = AIAuditor().audit(code=code, verbose=False)
        q = analyze_code_quality(code); h = detect_hallucinations(code)
        rows.append({"model": model, "trust": a["trust_score"],
                     "quality": q["score"], "security": len(q["security_issues"]),
                     "halluc": h["hallucination_count"],
                     "smells": len(q["code_smells"]), "dead": len(q["dead_code"])})
    if not rows:
        print("No completions found. Run --mode generate first."); return
    models = sorted({r["model"] for r in rows})
    print(f"\nAudited {len(rows)} HumanEval completions across {len(models)} models\n")
    print(f"{'model':<34}{'Trust':>7}{'Qual':>7}{'Sec':>6}{'Hall':>6}{'Smell':>7}{'Dead':>6}")
    for m in models:
        mr = [r for r in rows if r["model"] == m]
        print(f"{m.split('__')[-1]:<34}"
              f"{np.mean([r['trust'] for r in mr]):>7.1f}"
              f"{np.mean([r['quality'] for r in mr]):>7.1f}"
              f"{sum(r['security'] for r in mr):>6}"
              f"{sum(r['halluc'] for r in mr):>6}"
              f"{sum(r['smells'] for r in mr):>7}"
              f"{sum(r['dead'] for r in mr):>6}")
    # Kruskal-Wallis on trust across models
    groups = [[r["trust"] for r in rows if r["model"] == m] for m in models]
    if all(len(g) > 1 for g in groups) and len({v for g in groups for v in g}) > 1:
        H, pv = stats.kruskal(*groups)
        print(f"\nKruskal-Wallis on Trust across models: H={H:.2f}, p={pv:.3f}")
    import csv
    with open("research/data/humaneval_completions.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print("\nWrote research/data/humaneval_completions.csv")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["generate", "audit"], required=True)
    ap.add_argument("--k", type=int, default=1)
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    if a.mode == "generate":
        generate(a.k, a.limit)
    else:
        audit()
