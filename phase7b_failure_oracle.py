"""
phase7b_failure_oracle.py
=========================
Reviewer items #4 (parse-failure breakdown) and #5 (oracle staleness check).
Runs on files you already have — no new generation.

  #4: tabulate quarantined parse-failures by model (from _excluded_parsefail/ if you
      moved them there, else re-scan). Answers "are failures concentrated in one model?"

  #5: list every package the oracle currently flags in your REAL corpus (should be
      none after your fix) AND list the newest packages in your snapshot so you can
      eyeball staleness risk.

USAGE:
    python3 phase7b_failure_oracle.py
"""
import glob, json, ast
from pathlib import Path
from collections import Counter

def parse_failures():
    print("="*60)
    print("#4 PARSE-FAILURE BREAKDOWN BY MODEL")
    print("="*60)
    # check quarantine folder first
    quar = glob.glob("_excluded_parsefail/*/task*/run*.py") + \
           glob.glob("_excluded_parsefail/*/*/run*.py")
    counts = Counter()
    if quar:
        for f in quar:
            parts = Path(f).parts
            model = parts[1] if len(parts) > 3 else "unknown"
            counts[model] += 1
        print(f"\nFrom _excluded_parsefail/ ({len(quar)} files):")
    else:
        # re-scan live corpus for any that still fail
        for f in glob.glob("research/samples/*/task*/run*.py"):
            try:
                ast.parse(open(f, encoding="utf-8", errors="ignore").read())
            except SyntaxError:
                counts[Path(f).parts[-3]] += 1
        print(f"\nRe-scanned live corpus:")
    if counts:
        for model, n in counts.most_common():
            print(f"  {model.split('__')[-1]:<38} {n}")
        total = sum(counts.values())
        print(f"  {'TOTAL':<38} {total}")
        top = counts.most_common(1)[0]
        print(f"\nInterpretation: {top[1]}/{total} failures were {top[0].split('__')[-1]}.")
        print("State whether failures concentrate in specific models (a data-quality")
        print("note) or are spread evenly (random truncation).")
    else:
        print("  No parse failures found (all quarantined or none exist).")

def oracle_check():
    print("\n"+"="*60)
    print("#5 ORACLE STALENESS CHECK")
    print("="*60)
    snap = json.load(open("src/data/known_pypi_snapshot.json"))
    print(f"\nOracle version: {snap.get('_version','?')}")
    print(f"Oracle package count: {snap.get('_count', len(snap.get('packages',[])))}")
    # anything still flagged in real corpus?
    import sys
    sys.path.insert(0, "src")
    from hallucination import detect_hallucinations
    flagged = Counter()
    for f in glob.glob("research/samples/*/task*/run*.py"):
        code = open(f, encoding="utf-8", errors="ignore").read()
        if not code.strip(): continue
        r = detect_hallucinations(code)
        if r["parse_ok"] and r["hallucination_count"] >= 1:
            for h in r.get("true_hallucinations", []):
                flagged[h["module"]] += 1
    if flagged:
        print(f"\nStill flagged in real corpus (check these are truly fake):")
        for mod, n in flagged.most_common():
            print(f"  {mod}: {n}")
    else:
        print("\nNo real-corpus imports flagged — oracle covers all packages your")
        print("models actually used. State the oracle date and note that packages")
        print("released after that date could be misflagged (staleness risk), which")
        print("the refreshable snapshot addresses.")

if __name__ == "__main__":
    parse_failures()
    oracle_check()
