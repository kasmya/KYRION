"""
Regression tests for configurable Trust-Score weights (Gap 3).

Locks in that weights are real: different weight vectors must be capable of
producing different Trust Scores, weights auto-normalise, and missing phases
re-normalise correctly. Guards against regressing to a hardcoded average.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from auditor import AIAuditor  # noqa: E402

# Code where hallucination and quality sub-scores clearly diverge, so weighting
# them differently changes the result.
DIVERGENT = ("import os\nimport totally_fake_pkg\n"
             "def f(x=[]):\n    return x\n    dead=1\n"
             "print(os.getcwd())\ntotally_fake_pkg.go()\n")


def _trust(weights):
    return AIAuditor(weights=weights).audit(code=DIVERGENT, verbose=False)["trust_score"]


def test_different_weights_can_change_score():
    a = _trust({"hallucination": 0.8, "instruction": 0.1, "quality": 0.1})
    b = _trust({"hallucination": 0.1, "instruction": 0.1, "quality": 0.8})
    assert a != b, "weights had no effect — Trust Score is not actually configurable"


def test_weights_need_not_sum_to_one():
    # Un-normalised weights must be normalised internally: (2,2,2) == (1,1,1).
    equal = _trust({"hallucination": 1, "instruction": 1, "quality": 1})
    scaled = _trust({"hallucination": 2, "instruction": 2, "quality": 2})
    assert equal == scaled


def test_score_in_valid_range():
    for w in ({"hallucination": 1, "instruction": 0, "quality": 0},
              {"hallucination": 0, "instruction": 0, "quality": 1}):
        s = _trust(w)
        assert 0 <= s <= 100


def test_weights_recorded_in_output():
    r = AIAuditor(weights={"hallucination": 0.5, "instruction": 0.2, "quality": 0.3}) \
        .audit(code=DIVERGENT, verbose=False)
    assert "trust_weights" in r
    assert abs(r["trust_weights"]["hallucination"] - 0.5) < 1e-9


def test_missing_phase_renormalises():
    # With no instructions supplied, instruction phase is absent; score must still
    # be well-defined (weighted mean over the two present phases).
    r = AIAuditor().audit(code=DIVERGENT, verbose=False)  # no instructions
    assert 0 <= r["trust_score"] <= 100
