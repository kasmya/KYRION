"""
validate_detector.py
====================

Measure the hallucination detector's precision/recall against a LABELLED ground
truth — not against another paper's number. This kills the circularity critique
("calibrated to reproduce Tian et al.'s 2.04%") by giving the detector a set of
inputs whose correct labels we KNOW by construction.

GROUND TRUTH CONSTRUCTION
    Positive controls (label = hallucination):
        Real corpus samples into which we INJECT an import of a package that does
        not exist (randomly generated non-existent names). We know these are
        hallucinations because we created them.
    Negative controls (label = clean):
        (a) Real corpus samples left unmodified — their imports are real packages
            or local/stdlib modules (verified: corpus true-hallucination count = 0).
        (b) Hand-picked snippets using real-but-uncommon packages and
            import-name/package-name mismatches (PIL, bs4, jwt, ...), which a naive
            detector would wrongly flag.

We then run the detector on every item and compute precision, recall, F1, and a
confusion matrix at the FILE level (a file is "predicted hallucination" iff the
detector reports >=1 true hallucination).

USAGE
    python3 validate_detector.py
    python3 validate_detector.py --n-positive 40 --seed 42

Deterministic given the seed, so the reported precision/recall are reproducible
and citable in the paper.
"""
from __future__ import annotations

import argparse
import glob
import os
import random
import string
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
from hallucination import detect_hallucinations  # noqa: E402

SAMPLES_ROOT = Path(__file__).parent / "research" / "samples"


def _random_fake_module(rng: random.Random) -> str:
    """Generate a plausible-looking but non-existent package name."""
    parts = []
    for _ in range(rng.randint(2, 3)):
        parts.append("".join(rng.choice(string.ascii_lowercase)
                             for _ in range(rng.randint(4, 8))))
    return "_".join(parts)


def _load_corpus():
    files = sorted(glob.glob(str(SAMPLES_ROOT / "*" / "*.py")))
    files = [f for f in files if os.path.basename(os.path.dirname(f)) != "benchmark"]
    return [(f, open(f, encoding="utf-8", errors="ignore").read()) for f in files]


# Negative controls that stress import-name != package-name resolution.
# A correct detector must label ALL of these as clean (0 hallucinations).
MISMATCH_NEGATIVES = [
    "from PIL import Image\nImage.open('a.png')\n",
    "import bs4\nsoup = bs4.BeautifulSoup('<a>')\n",
    "import sklearn\nfrom sklearn.linear_model import LinearRegression\nLinearRegression()\n",
    "import jwt\ntok = jwt.encode({'a': 1}, 'k')\n",
    "import yaml\nyaml.safe_load('a: 1')\n",
    "from dateutil import parser\nparser.parse('2020')\n",
    "import cv2\ncv2.imread('x.png')\n",
    "from flask_sqlalchemy import SQLAlchemy\ndb = SQLAlchemy()\n",
]

# HARD positive controls: typosquats of real packages — the realistic form of
# import hallucination LLMs actually emit. Each is a misspelling of a real
# package and does NOT exist on PyPI, so the correct label is "hallucination".
TYPOSQUAT_POSITIVES = [
    "import nunpy as np\nnp.array([1])\n",          # numpy
    "import reqeusts\nreqeusts.get('x')\n",         # requests
    "import pandsa as pd\npd.DataFrame()\n",         # pandas
    "from flask import Flask\nFlask(__name__)\n",    # flask
    "import tensorflwo as tf\ntf.constant(1)\n",     # tensorflow
    "import beatifulsoup\nbeatifulsoup.parse('x')\n",  # beautifulsoup(4)
]


def build_dataset(n_positive: int, seed: int):
    """Return list of (code, label) where label 1 = hallucination, 0 = clean."""
    rng = random.Random(seed)
    corpus = _load_corpus()
    dataset = []

    # Positive controls (easy): inject an obviously-fake random import.
    chosen = rng.sample(corpus, min(n_positive, len(corpus)))
    for _, code in chosen:
        fake = _random_fake_module(rng)
        injected = f"import {fake}\n{code}\n{fake}.run()\n"
        dataset.append((injected, 1))

    # Positive controls (HARD): typosquats of real packages. These are the
    # realistic hallucinations LLMs actually produce (nunpy, reqeusts, ...).
    # A detector that only catches obvious junk would miss these.
    for typo in TYPOSQUAT_POSITIVES:
        dataset.append((typo, 1))

    # Negative controls (a): unmodified real samples.
    remaining = [c for c in corpus if c not in chosen] or corpus
    for _, code in rng.sample(remaining, min(n_positive, len(remaining))):
        dataset.append((code, 0))

    # Negative controls (b): import-name mismatches.
    for code in MISMATCH_NEGATIVES:
        dataset.append((code, 0))

    rng.shuffle(dataset)
    return dataset


def evaluate(dataset):
    tp = fp = tn = fn = 0
    for code, label in dataset:
        r = detect_hallucinations(code)
        pred = 1 if (r["parse_ok"] and r["hallucination_count"] >= 1) else 0
        if label == 1 and pred == 1:
            tp += 1
        elif label == 1 and pred == 0:
            fn += 1
        elif label == 0 and pred == 1:
            fp += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return dict(tp=tp, fp=fp, tn=tn, fn=fn,
                precision=precision, recall=recall, f1=f1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-positive", type=int, default=40)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    dataset = build_dataset(args.n_positive, args.seed)
    if not dataset:
        print("No samples available to build a validation set.")
        return 1
    m = evaluate(dataset)

    print("Hallucination Detector — Ground-Truth Validation")
    print("=" * 56)
    print(f"Dataset size:            {len(dataset)} "
          f"(positives + negatives, seed={args.seed})")
    print(f"Confusion matrix:")
    print(f"  True Positives (TP):   {m['tp']}")
    print(f"  False Positives (FP):  {m['fp']}   <- real packages wrongly flagged")
    print(f"  True Negatives (TN):   {m['tn']}")
    print(f"  False Negatives (FN):  {m['fn']}   <- injected fakes missed")
    print("-" * 56)
    print(f"  Precision:  {m['precision']:.3f}")
    print(f"  Recall:     {m['recall']:.3f}")
    print(f"  F1-score:   {m['f1']:.3f}")
    print("-" * 56)
    print("These numbers are measured against a constructed ground truth, so they")
    print("are independent of any external paper's reported rate (no circularity).")

    # persist for the paper appendix
    import csv as _csv
    out = Path(__file__).parent / "research" / "data" / "detector_validation.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = _csv.writer(fh)
        w.writerow(["metric", "value"])
        for k in ("tp", "fp", "tn", "fn", "precision", "recall", "f1"):
            w.writerow([k, round(m[k], 4) if isinstance(m[k], float) else m[k]])
    print(f"\nWrote metrics to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
