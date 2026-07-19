"""
Regression tests for the AST-based quality analyzer (Gap 2).

Locks in that structural analysis uses real parsing and cannot regress to the old
regex heuristics or silently pass unparseable code.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from quality import (analyze_code_quality, PENALTY_SECURITY,  # noqa: E402
                     PENALTY_DEAD_CODE, PENALTY_CODE_SMELL)


def test_unreachable_after_return_is_dead_code():
    code = "def f():\n    return 1\n    x = 2\n"
    r = analyze_code_quality(code)
    assert any("Unreachable" in d for d in r["dead_code"])


def test_unreachable_after_raise_is_dead_code():
    code = "def f():\n    raise ValueError('x')\n    cleanup()\n"
    r = analyze_code_quality(code)
    assert any("Unreachable" in d for d in r["dead_code"])


def test_reachable_code_not_flagged_dead():
    # A return inside an if must NOT mark the following sibling code dead.
    code = "def f(x):\n    if x:\n        return 1\n    return 2\n"
    r = analyze_code_quality(code)
    assert not any("Unreachable" in d for d in r["dead_code"])


def test_unused_import_detected_via_ast():
    code = "import os\nimport json\nprint(os.getcwd())\n"
    r = analyze_code_quality(code)
    assert any("json" in d for d in r["dead_code"])
    assert not any("'os'" in d for d in r["dead_code"])


def test_used_import_not_flagged():
    code = "import math\nprint(math.pi)\n"
    r = analyze_code_quality(code)
    assert not any("math" in d for d in r["dead_code"])


def test_mutable_default_argument_detected():
    code = "def f(items=[]):\n    '''doc'''\n    return items\n"
    r = analyze_code_quality(code)
    assert any("Mutable default" in s for s in r["code_smells"])


def test_missing_docstring_detected():
    code = "def f():\n    return 1\n"
    r = analyze_code_quality(code)
    assert any("Missing docstring" in s for s in r["code_smells"])


def test_hardcoded_secret_detected():
    code = "password = \"hunter2\"\n"
    r = analyze_code_quality(code)
    assert any("credential" in s.lower() for s in r["security_issues"])


def test_unparseable_code_reports_parse_failure():
    code = "def broken(:\n  nope\n"
    r = analyze_code_quality(code)
    assert r["parse_ok"] is False
    assert "syntax error" in r["summary"].lower()


def test_clean_code_scores_high():
    code = ('"""module doc"""\n'
            "def add(a: int, b: int) -> int:\n"
            '    """Add two numbers."""\n'
            "    return a + b\n")
    r = analyze_code_quality(code)
    assert r["score"] >= 90
    assert r["parse_ok"] is True


def test_scoring_uses_named_constants():
    # One security issue should cost exactly PENALTY_SECURITY points.
    code = 'x = eval("1")\n'  # eval -> one security issue; nothing else structural
    r = analyze_code_quality(code)
    # module docstring missing adds one smell; account for it
    expected = 100 - PENALTY_SECURITY * len(r["security_issues"]) \
                   - PENALTY_DEAD_CODE * len(r["dead_code"]) \
                   - PENALTY_CODE_SMELL * len(r["code_smells"])
    assert r["score"] == max(0, expected)


def test_output_schema_stable():
    r = analyze_code_quality("import os\nprint(os)\n")
    for key in ("security_issues", "dead_code", "code_smells", "score",
                "total_issues", "parse_ok", "summary", "method"):
        assert key in r
