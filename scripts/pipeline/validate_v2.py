"""
validate_v2.py — self-contained hallucination-detector validation.
Builds a properly-sized labelled test set from ALL clean corpus files and
computes precision/recall/F1 against known ground truth.

Run from the KYRION root:
    python3 scripts/pipeline/validate_v2.py --n-positive 60 --seed 42
"""
from __future__ import annotations
import argparse, glob, random, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from hallucination import detect_hallucinations

SAMPLES = Path(__file__).resolve().parents[2] / "research" / "samples"

# Realistic typosquats (hard positives) — do not exist on PyPI => hallucination.
TYPOSQUATS = [
    "import nunpy as np\nnp.array([1])\n",
    "import reqeusts\nreqeusts.get('x')\n",
    "import pandsa as pd\npd.DataFrame()\n",
    "import tensorflwo as tf\ntf.constant(1)\n",
    "import beatifulsoup\nbeatifulsoup.parse('x')\n",
    "import matplotlibb.pyplot as plt\nplt.plot([1])\n",
]
# Import-name != package-name (hard negatives) — all REAL => clean.
MISMATCH_NEG = [
    "from PIL import Image\nImage.open('a.png')\n",
    "import bs4\nbs4.BeautifulSoup('<a>')\n",
    "import cv2\ncv2.imread('x.png')\n",
    "import jwt\njwt.encode({'a':1},'k')\n",
    "import yaml\nyaml.safe_load('a: 1')\n",
    "from dateutil import parser\nparser.parse('2020')\n",
    "import sklearn\nsklearn.__version__\n",
    "from flask_sqlalchemy import SQLAlchemy\nSQLAlchemy()\n",
]
FAKES = ["zxqw_pkg", "notarealmod", "fakelib99", "imaginary_util", "nonexistent_xyz"]

def load_corpus():
    files = sorted(glob.glob(str(SAMPLES / "*" / "task*" / "run*.py")))
    out = []
    for f in files:
        try:
            c = open(f, encoding="utf-8", errors="ignore").read()
            if c.strip():
                out.append(c)
        except Exception:
            pass
    return out

def main(n_positive, seed):
    rng = random.Random(seed)
    corpus = load_corpus()
    print(f"Corpus files available: {len(corpus)}")
    if len(corpus) < 20:
        print("WARNING: corpus too small — check SAMPLES path.")

    dataset = []  # (code, label)  label 1 = hallucination
    # Easy positives: inject a guaranteed-fake import into real samples
    for code in rng.sample(corpus, min(n_positive, len(corpus))):
        fake = rng.choice(FAKES) + str(rng.randint(100, 999))
        dataset.append((f"import {fake}\n{code}\n{fake}.run()\n", 1))
    # Hard positives: typosquats
    for t in TYPOSQUATS:
        dataset.append((t, 1))
    # Easy negatives: unmodified real samples
    for code in rng.sample(corpus, min(n_positive, len(corpus))):
        dataset.append((code, 0))
    # Hard negatives: name mismatches
    for m in MISMATCH_NEG:
        dataset.append((m, 0))
    rng.shuffle(dataset)

    tp = fp = tn = fn = 0
    for code, label in dataset:
        r = detect_hallucinations(code)
        pred = 1 if (r["parse_ok"] and r["hallucination_count"] >= 1) else 0
        if label == 1 and pred == 1: tp += 1
        elif label == 1 and pred == 0: fn += 1
        elif label == 0 and pred == 1: fp += 1
        else: tn += 1

    prec = tp/(tp+fp) if (tp+fp) else 0.0
    rec = tp/(tp+fn) if (tp+fn) else 0.0
    f1 = 2*prec*rec/(prec+rec) if (prec+rec) else 0.0
    print("="*56)
    print(f"Dataset size: {len(dataset)}  (positives={sum(1 for _,l in dataset if l==1)}, "
          f"negatives={sum(1 for _,l in dataset if l==0)})")
    print(f"TP={tp}  FP={fp}  TN={tn}  FN={fn}")
    print(f"Precision: {prec:.3f}")
    print(f"Recall:    {rec:.3f}")
    print(f"F1-score:  {f1:.3f}")
    print("="*56)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-positive", type=int, default=60)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    main(a.n_positive, a.seed)
