"""
Regression tests for the AST-based hallucination detector.

PURPOSE: lock in correct behaviour so the "fake detector" gap can NEVER silently
return. These tests fail loudly if the detector regresses to a state where it:
  - misses real hallucinations (false negatives), or
  - flags real packages / stdlib / local imports as hallucinations (false positives), or
  - silently passes code that does not parse.

Run:  pytest tests/test_hallucination.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from hallucination import detect_hallucinations  # noqa: E402


# ---------- POSITIVE CONTROLS: must be caught as true hallucinations ----------
def test_obvious_fake_package_is_caught():
    code = "import totally_made_up_xyz_pkg\nx = totally_made_up_xyz_pkg.run()\n"
    r = detect_hallucinations(code)
    mods = [h["module"] for h in r["true_hallucinations"]]
    assert "totally_made_up_xyz_pkg" in mods
    assert r["hallucination_count"] == 1


def test_fake_from_import_is_caught():
    code = "from nonexistent_ai_lib import Magic\nm = Magic()\n"
    r = detect_hallucinations(code)
    mods = [h["module"] for h in r["true_hallucinations"]]
    assert "nonexistent_ai_lib" in mods


def test_multiple_fakes_counted():
    code = "import faketed_pkg_a\nimport faketed_pkg_b\n"
    r = detect_hallucinations(code)
    assert r["hallucination_count"] == 2


# ---------- NEGATIVE CONTROLS: must NOT be flagged (no false positives) -------
def test_stdlib_not_flagged():
    code = "import os\nimport sys\nimport json\nprint(os, sys, json)\n"
    r = detect_hallucinations(code)
    assert r["hallucination_count"] == 0


def test_real_pypi_not_flagged():
    code = "import numpy as np\nimport pandas as pd\narr = np.array([1]); df = pd.DataFrame()\n"
    r = detect_hallucinations(code)
    assert r["hallucination_count"] == 0


def test_import_name_mismatch_not_flagged():
    # These import names differ from their PyPI package names and are a classic
    # source of false positives. They must resolve as real.
    for code in [
        "from PIL import Image\nImage.open('x')\n",           # pillow
        "import bs4\nbs4.BeautifulSoup('')\n",                # beautifulsoup4
        "import sklearn\nsklearn.base\n",                     # scikit-learn
        "import jwt\njwt.encode({}, 'k')\n",                  # pyjwt
    ]:
        r = detect_hallucinations(code)
        assert r["hallucination_count"] == 0, f"false positive on: {code!r}"


def test_local_module_not_flagged_as_hallucination():
    # Local sibling imports common in Django/Flask projects must be classified as
    # unresolved-local, NOT hallucination.
    code = "from models import User\nfrom forms import LoginForm\nu = User(); f = LoginForm()\n"
    r = detect_hallucinations(code)
    assert r["hallucination_count"] == 0
    locals_ = [h["module"] for h in r["unresolved_local_imports"]]
    assert "models" in locals_ and "forms" in locals_


def test_relative_import_is_local():
    code = "from .services import handler\nhandler()\n"
    r = detect_hallucinations(code)
    assert r["hallucination_count"] == 0


# ---------- STRUCTURAL GUARANTEES ----------
def test_unparseable_code_is_not_silently_clean():
    # The old detector returned "no hallucinations" on junk. This must not happen:
    # a parse failure must be reported, not masked as a clean result.
    code = "def broken(:\n    this is not python\n"
    r = detect_hallucinations(code)
    assert r["parse_ok"] is False
    assert "syntax error" in r["status"].lower()


def test_unused_import_is_separate_from_hallucination():
    code = "import os\nimport json\nprint(os.getcwd())\n"  # json unused, both real
    r = detect_hallucinations(code)
    assert r["hallucination_count"] == 0
    assert any(u["module"] == "json" for u in r["unused_imports"])


def test_output_schema_is_stable():
    # Downstream code (auditor.py, report.py) depends on these keys existing.
    r = detect_hallucinations("import os\n")
    for key in ("parse_ok", "true_hallucinations", "unresolved_local_imports",
                "unused_imports", "anti_patterns", "imports_total",
                "hallucination_count", "hallucination_rate_pct", "status", "method"):
        assert key in r, f"missing output key: {key}"


# ---------- CORPUS-LEVEL SANITY: no false-positive explosion on real samples ----
def test_no_false_positive_explosion_on_corpus():
    """If the detector ever starts flagging real packages, the corpus hallucination
    count will spike. This guard fails if true-hallucination count across all
    samples exceeds a sane ceiling (indicating the oracle/mapping broke)."""
    import glob
    total_halluc = 0
    sample_root = Path(__file__).parent.parent / "research" / "samples"
    files = glob.glob(str(sample_root / "*" / "*.py"))
    if not files:
        return  # samples not present in this checkout; skip
    for f in files:
        if "benchmark" in f:
            continue
        code = open(f, encoding="utf-8", errors="ignore").read()
        r = detect_hallucinations(code)
        if r["parse_ok"]:
            total_halluc += r["hallucination_count"]
    # Real frontier-model output rarely fabricates packages. A sudden spike above
    # this ceiling means the oracle regressed (e.g. snapshot failed to load).
    assert total_halluc <= 15, (
        f"Corpus true-hallucination count = {total_halluc}, which is implausibly "
        f"high. The package oracle or import map likely regressed."
    )


# ---------- GROUND-TRUTH VALIDATION GUARD ----------
def test_detector_meets_precision_recall_floor():
    """Run the ground-truth validation harness and assert the detector stays above
    a quality floor. Guards against silent regressions in precision/recall."""
    import subprocess, sys as _sys
    from pathlib import Path as _P
    root = _P(__file__).parent.parent
    # import the harness directly for speed
    _sys.path.insert(0, str(root))
    import validate_detector as vd
    dataset = vd.build_dataset(n_positive=40, seed=42)
    m = vd.evaluate(dataset)
    assert m["precision"] >= 0.95, f"precision regressed to {m['precision']}"
    assert m["recall"] >= 0.90, f"recall regressed to {m['recall']}"
    assert m["fp"] == 0, f"detector produced {m['fp']} false positives on real packages"
