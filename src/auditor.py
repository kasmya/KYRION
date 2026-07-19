"""
Unified Orchestrator - Combines all three audit phases

Trust Score is a WEIGHTED, CONFIGURABLE mean of the three phase sub-scores.
Weights are read from auditor.yaml (or passed explicitly), auto-normalised, and
re-normalised when a phase is unavailable. This is what makes the paper's
weight-sensitivity analysis reproducible.
"""
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from hallucination import detect_hallucinations
from instruction import audit_instruction_adherence
from quality import analyze_code_quality

# Default weights used if no config file is present. Equal thirds = neutral prior.
DEFAULT_WEIGHTS = {"hallucination": 1 / 3, "instruction": 1 / 3, "quality": 1 / 3}
DEFAULT_HALLUC_PENALTY = 25


def _load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load weights/penalties from auditor.yaml if available, else defaults.

    PyYAML is optional: if it is not installed or the file is absent, we fall back
    to DEFAULT_WEIGHTS so the tool always runs. The chosen weights are returned so
    the caller (and the report) can record exactly what was used.
    """
    cfg = {"weights": dict(DEFAULT_WEIGHTS),
           "hallucination_penalty": DEFAULT_HALLUC_PENALTY,
           "source": "defaults"}
    if config_path is None:
        # look for auditor.yaml at repo root (parent of src/)
        candidate = Path(__file__).parent.parent / "auditor.yaml"
        config_path = str(candidate) if candidate.exists() else None
    if config_path and os.path.exists(config_path):
        try:
            import yaml  # optional dependency
            with open(config_path, "r", encoding="utf-8") as fh:
                raw = yaml.safe_load(fh) or {}
            w = raw.get("trust_score_weights", {})
            if w:
                cfg["weights"] = {
                    "hallucination": float(w.get("hallucination", DEFAULT_WEIGHTS["hallucination"])),
                    "instruction": float(w.get("instruction", DEFAULT_WEIGHTS["instruction"])),
                    "quality": float(w.get("quality", DEFAULT_WEIGHTS["quality"])),
                }
            cfg["hallucination_penalty"] = int(raw.get("hallucination_penalty", DEFAULT_HALLUC_PENALTY))
            cfg["source"] = config_path
        except ImportError:
            cfg["source"] = "defaults (pyyaml not installed)"
        except Exception as exc:  # malformed yaml -> defaults, but say so
            cfg["source"] = f"defaults (config error: {exc})"
    return cfg


class AIAuditor:
    """
    Unified AI Auditor that runs all three phases together.

    Usage:
        auditor = AIAuditor()                       # uses auditor.yaml if present
        auditor = AIAuditor(weights={"hallucination":0.5,"instruction":0.2,"quality":0.3})
        results = auditor.audit(code="...", prompt="...", instructions=[...])
        print(results['trust_score'], results['trust_weights'])
    """

    def __init__(self, config_path: Optional[str] = None,
                 weights: Optional[Dict[str, float]] = None):
        self.results: Dict[str, Any] = {}
        self.trust_score = 0
        cfg = _load_config(config_path)
        # explicit weights override config file
        self.weights = dict(weights) if weights else cfg["weights"]
        self.hallucination_penalty = cfg["hallucination_penalty"]
        self.config_source = "explicit weights" if weights else cfg["source"]
    
    def audit(
        self,
        code: str,
        prompt: Optional[str] = None,
        instructions: Optional[List[str]] = None,
        verbose: bool = False
    ) -> Dict[str, Any]:
        """
        Run all three audit phases.
        
        Args:
            code: AI-generated code to audit
            prompt: Original prompt given to AI
            instructions: Custom instructions to check
            verbose: Print progress messages
        
        Returns:
            dict: Combined audit results with trust score
        """
        if verbose:
            print("🔍 Running complete audit...")
        
        # Phase 1: Hallucination Detection
        if verbose:
            print("  📋 Phase 1: Hallucination Detection")
        self.results['hallucination'] = detect_hallucinations(code)
        
        # Phase 2: Instruction Adherence
        if prompt and instructions:
            if verbose:
                print("  📋 Phase 2: Instruction Adherence")
            self.results['instruction_adherence'] = audit_instruction_adherence(
                prompt, code, instructions
            )
        elif prompt and not instructions:
            self.results['instruction_adherence'] = {
                "skipped": True,
                "message": "No instructions provided, skipping instruction adherence"
            }
        
        # Phase 3: Code Quality Analysis
        if verbose:
            print("  📋 Phase 3: Code Quality Analysis")
        self.results['quality'] = analyze_code_quality(code)
        
        # Calculate overall trust score
        self._calculate_trust_score()
        self.results['trust_score'] = self.trust_score
        self.results['summary'] = self._generate_summary()
        
        if verbose:
            print(f"  ✅ Audit complete! Trust Score: {self.trust_score}/100")
        
        return self.results
    
    def _calculate_trust_score(self):
        """Compute the Trust Score as a WEIGHTED mean of available phase sub-scores.

        Each present phase contributes (weight, sub_score). Weights are normalised
        over only the phases that are actually available for this sample, so the
        score is well-defined even when a phase is skipped. This replaces the old
        unweighted `sum(scores)/len(scores)` and makes the weights genuinely
        configurable (and the paper's weight-sensitivity analysis reproducible).
        """
        contributions = []  # list of (weight, sub_score)

        # --- Hallucination sub-score (AST + frozen oracle detector) ---
        if 'hallucination' in self.results:
            halu = self.results['hallucination']
            if isinstance(halu, dict) and halu.get('parse_ok'):
                penalty = self.hallucination_penalty * halu.get('hallucination_count', 0)
                sub = max(0, 100 - penalty)
                contributions.append((self.weights.get('hallucination', 0.0), sub))
            # parse failed -> contribute nothing (do not invent a number)

        # --- Instruction-adherence sub-score ---
        if 'instruction_adherence' in self.results:
            instr = self.results['instruction_adherence']
            if isinstance(instr, dict) and 'score' in instr:
                contributions.append((self.weights.get('instruction', 0.0), instr['score']))

        # --- Quality sub-score ---
        if 'quality' in self.results:
            quality = self.results['quality']
            if isinstance(quality, dict) and 'score' in quality:
                contributions.append((self.weights.get('quality', 0.0), quality['score']))

        # --- weighted, normalised aggregation ---
        total_w = sum(w for w, _ in contributions)
        if contributions and total_w > 0:
            weighted = sum(w * s for w, s in contributions) / total_w
            self.trust_score = int(round(weighted))
        elif contributions:
            # weights summed to zero but phases exist -> fall back to plain mean
            self.trust_score = int(round(sum(s for _, s in contributions) / len(contributions)))
        else:
            self.trust_score = 50

        # record exactly what was used, for transparency/reporting
        self.results['trust_weights'] = dict(self.weights)
        self.results['trust_config_source'] = self.config_source
    
    def _generate_summary(self) -> str:
        """Generate a human-readable summary"""
        trust = self.trust_score
        total_issues = 0
        
        for key in ['hallucination', 'instruction_adherence', 'quality']:
            if key in self.results and isinstance(self.results[key], dict):
                if 'total_issues' in self.results[key]:
                    total_issues += self.results[key].get('total_issues', 0)
                elif 'violations' in self.results[key]:
                    total_issues += len(self.results[key].get('violations', []))
        
        if trust >= 90:
            return f"✅ Excellent! Trust Score: {trust}/100. Only {total_issues} minor issues found."

        elif trust >= 70:
            return f"🟢 Good! Trust Score: {trust}/100. {total_issues} issues found that need review."
        elif trust >= 50:
            return f"🟡 Fair! Trust Score: {trust}/100. {total_issues} issues found that need attention."
        else:
            return f"🔴 Poor! Trust Score: {trust}/100. {total_issues} serious issues found that need fixing."
