"""
Professional report generator for AI Auditor
"""
import datetime
from typing import Dict, Any, List


def generate_report(results: Dict[str, Any], filename: str) -> str:
    """
    Generate a clean, informative text report.
    """
    # Extract data with safe defaults
    trust_score = results.get('trust_score', 0)
    summary = results.get('summary', 'No summary available')
    
    hallucination = results.get('hallucination', {})
    instruction = results.get('instruction_adherence', {})
    quality = results.get('quality', {})
    
    # --- Hallucination data (with safe defaults) ---
    halu_llm = hallucination.get('llmauditor', {})
    halu_data = halu_llm.get('hallucination', {})
    halu_risk = halu_data.get('risk_level', 'UNKNOWN')
    halu_risk_pct = halu_data.get('risk_score_pct', 0)
    
    # If halu_risk_pct is 0 but risk_level is not UNKNOWN, it might be valid
    # But we'll use safe defaults
    if halu_risk_pct == 0 and halu_risk == 'UNKNOWN':
        halu_risk_pct = 0
    
    # Safe extraction for dependency_check
    dep_check = hallucination.get('dependency_check', {})
    halu_imports = dep_check.get('hallucinated_imports', [])
    halu_patterns = dep_check.get('anti_patterns', [])
    
    # --- Instruction data ---
    instr_score = instruction.get('score', 0)
    instr_violations = instruction.get('violations', [])
    
    # --- Quality data ---
    qual_score = quality.get('score', 0)
    qual_security = quality.get('security_issues', [])
    qual_dead = quality.get('dead_code', [])
    qual_smells = quality.get('code_smells', [])
    qual_total = quality.get('total_issues', 0)
    
    # Calculate trust score from individual scores
    halu_score = max(0, 100 - halu_risk_pct) if halu_risk_pct is not None else 70
    instr_score_val = instr_score if instr_score else 70
    qual_score_val = qual_score if qual_score else 70
    
    # Calculate overall trust score
    if trust_score == 0:
        trust_score = int((halu_score + instr_score_val + qual_score_val) / 3)
        # Ensure trust_score is between 0 and 100
        trust_score = max(0, min(100, trust_score))
    
    # Count total issues
    total_issues = (
        len(halu_imports) + len(halu_patterns) +
        len(instr_violations) +
        len(qual_security) + len(qual_dead) + len(qual_smells)
    )
    
    # Determine status emoji
    if trust_score >= 80:
        status_emoji = "✅"
        status_text = "PASSED"
    elif trust_score >= 50:
        status_emoji = "⚠️"
        status_text = "REVIEW NEEDED"
    else:
        status_emoji = "❌"
        status_text = "FAILED"
    
    # Severity classification
    high_issues = []
    medium_issues = []
    low_issues = []
    
    for issue in qual_security:
        high_issues.append(f"🔴 {issue}")
    for issue in halu_imports:
        high_issues.append(f"🔴 Hallucinated import: {issue}")
    for issue in instr_violations:
        medium_issues.append(f"🟡 Instruction violation: {issue}")
    for issue in qual_dead:
        medium_issues.append(f"🟡 {issue}")
    for issue in halu_patterns:
        low_issues.append(f"🟢 {issue}")
    for issue in qual_smells:
        low_issues.append(f"🟢 {issue}")
    
    # Build report
    report = f"""
╔══════════════════════════════════════════════════════════════════════╗
║                      AI AUDITOR REPORT                              ║
╚══════════════════════════════════════════════════════════════════════╝

📁 File: {filename}
📅 Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
📊 Status: {status_emoji} {status_text}

┌──────────────────────────────────────────────────────────────────────┐
│                         OVERALL SCORE                              │
│                                                                     │
│                    ╔═══════════════════════════╗                    │
│                    ║         {trust_score}/100          ║                    │
│                    ╚═══════════════════════════╝                    │
│                                                                     │
│  {summary[:80]}                                           │
└──────────────────────────────────────────────────────────────────────┘

┌─────────────┬─────────────┬─────────────┬──────────────────────────┐
│   METRIC    │    SCORE    │   STATUS    │        ISSUES            │
├─────────────┼─────────────┼─────────────┼──────────────────────────┤
│ Hallucination │ {halu_risk_pct:>3}%      │ {halu_risk:<10} │ {len(halu_imports) + len(halu_patterns):>3} found      │
│ Instructions  │ {instr_score:>3}/100   │ {'✅' if instr_score >= 80 else '⚠️':<10} │ {len(instr_violations):>3} violations  │
│ Code Quality  │ {qual_score:>3}/100   │ {'✅' if qual_score >= 80 else '⚠️':<10} │ {qual_total:>3} issues       │
└─────────────┴─────────────┴─────────────┴──────────────────────────┘

{'━' * 70}

📋 DETAILED ISSUES

{'🔴 HIGH SEVERITY' if high_issues else '✅ No high severity issues'}
{chr(10).join(high_issues) if high_issues else '   None found'}

{'🟡 MEDIUM SEVERITY' if medium_issues else '✅ No medium severity issues'}
{chr(10).join(medium_issues) if medium_issues else '   None found'}

{'🟢 LOW SEVERITY' if low_issues else '✅ No low severity issues'}
{chr(10).join(low_issues) if low_issues else '   None found'}

{'━' * 70}

💡 RECOMMENDATIONS

"""
    
    # Generate recommendations
    recommendations = []
    
    if trust_score >= 80:
        recommendations.append("✅ Code looks good! Continue monitoring.")
    else:
        if halu_imports:
            recommendations.append("🔴 Remove hallucinated imports (packages that don't exist)")
        if halu_patterns:
            recommendations.append("🟡 Fix AI anti-patterns (mutable defaults, JS leakage)")
        if instr_violations:
            recommendations.append("📝 Update code to follow all instructions")
        if qual_security:
            recommendations.append("🔴 Fix security vulnerabilities immediately")
        if qual_dead:
            recommendations.append("🗑️ Remove unreachable dead code")
        if qual_smells:
            recommendations.append("📏 Refactor code smells (long functions, missing docs)")
    
    if not recommendations:
        recommendations.append("✅ No issues found! Code is clean.")
    
    for rec in recommendations:
        report += f"   {rec}\n"
    
    report += f"""
{'━' * 70}
📊 SUMMARY

   Total Issues Found: {total_issues}
   Trust Score: {trust_score}/100
   Status: {status_emoji} {status_text}

{'═' * 70}
   Generated by AI Auditor • https://github.com/kasmya/AI-Auditor
{'═' * 70}
"""
    
    return report
