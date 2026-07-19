"""
Code Quality Analysis Module for AI Auditor  (v2 — AST-based)
=============================================================

WHAT CHANGED AND WHY (Gap 2 fix)
--------------------------------
The previous version did every structural check with regular expressions,
including the widely-mocked dead-code line:

    if imp not in code.replace('import','').replace('from',''):

Regex cannot reliably tell an unreachable statement from a reachable one, a real
function boundary from text that merely looks like one, or a decorated/typed
function from a plain one. This rewrite performs all *structural* analysis on the
Abstract Syntax Tree (AST), which is what the paper's Figure 1 caption claims.

WHAT USES AST NOW (structural — needs real parsing):
    - unused imports            (import bound but never referenced)
    - unreachable / dead code   (statements after return/raise/continue/break)
    - long functions            (real line span of a FunctionDef)
    - missing docstrings         (ast.get_docstring on defs/classes/module)
    - mutable default arguments  (list/dict/set literal as a default)

WHAT STAYS REGEX (genuinely textual — AST would not help):
    - hardcoded secrets, weak crypto (md5/sha1), eval/exec, shell calls,
      SQL string-concatenation, pickle.load, unvalidated input, long lines,
      TODO/FIXME markers.
    These are lexical/textual smells; matching them on source text is appropriate
    and we say so explicitly rather than dressing them up as "AST analysis".

SCORING
-------
The penalty coefficients are defined ONCE, as named constants, and are the single
source of truth. The paper's Equation (1) must quote THESE numbers. (They are also
exposed so the paper's coefficient-sensitivity analysis can vary them.)

The analyzer degrades safely: if the code does not parse, structural checks are
skipped and the result records parse_ok=False rather than silently scoring it clean.
"""

from __future__ import annotations

import ast
import re
from typing import Any, Dict, List

# --------------------------------------------------------------------------
# Scoring coefficients — SINGLE SOURCE OF TRUTH.
# The paper's Equation (1) must use exactly these values.
#   quality = max(0, 100 - SEC*sec - DEAD*dead - SMELL*smell)
# --------------------------------------------------------------------------
PENALTY_SECURITY = 15
PENALTY_DEAD_CODE = 5
PENALTY_CODE_SMELL = 3

LONG_FUNCTION_LINES = 50      # hard threshold: "long function"
REFACTOR_FUNCTION_LINES = 30  # soft threshold: "consider refactoring"
LONG_LINE_CHARS = 120


# ==========================================================================
# AST-based structural analysis
# ==========================================================================
class _StructuralVisitor(ast.NodeVisitor):
    def __init__(self, source_lines: int) -> None:
        self.source_lines = source_lines
        self.imported: Dict[str, int] = {}     # bound name -> line
        self.used_names: set[str] = set()
        self.dead_code: List[str] = []
        self.long_functions: List[str] = []
        self.missing_docstrings: List[str] = []
        self.mutable_defaults: List[str] = []

    # ---- imports & usage (for unused-import detection) ----
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            bound = (alias.asname or alias.name).split(".")[0]
            self.imported[bound] = node.lineno
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            if alias.name == "*":
                continue
            bound = alias.asname or alias.name
            self.imported[bound] = node.lineno
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        self.used_names.add(node.id)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        cur = node
        while isinstance(cur, ast.Attribute):
            cur = cur.value
        if isinstance(cur, ast.Name):
            self.used_names.add(cur.id)
        self.generic_visit(node)

    # ---- functions: length, docstring, mutable defaults, dead code ----
    def _check_function(self, node) -> None:
        # length via real line span
        if node.end_lineno and node.lineno:
            span = node.end_lineno - node.lineno + 1
            if span > LONG_FUNCTION_LINES:
                self.long_functions.append(
                    f"Long function '{node.name}' ({span} lines) at line {node.lineno}"
                )
        # docstring
        if ast.get_docstring(node) is None:
            self.missing_docstrings.append(
                f"Missing docstring for function '{node.name}' (line {node.lineno})"
            )
        # mutable default args
        for default in node.args.defaults + node.args.kw_defaults:
            if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                self.mutable_defaults.append(
                    f"Mutable default argument in '{node.name}' (line {node.lineno})"
                )
                break
        # dead code inside this function body
        self._check_dead_code(node.body)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_function(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_function(node)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if ast.get_docstring(node) is None:
            self.missing_docstrings.append(
                f"Missing docstring for class '{node.name}' (line {node.lineno})"
            )
        self.generic_visit(node)

    def _check_dead_code(self, body: List[ast.stmt]) -> None:
        """Any statement in the same block AFTER a return/raise/break/continue is
        unreachable. This is a true control-flow fact from the AST — not a guess."""
        TERMINATORS = (ast.Return, ast.Raise, ast.Break, ast.Continue)
        for i, stmt in enumerate(body):
            if isinstance(stmt, TERMINATORS) and i + 1 < len(body):
                nxt = body[i + 1]
                self.dead_code.append(
                    f"Unreachable code after {type(stmt).__name__.lower()} "
                    f"(line {nxt.lineno})"
                )
            # recurse into nested blocks
            for attr in ("body", "orelse", "finalbody"):
                inner = getattr(stmt, attr, None)
                if isinstance(inner, list) and inner and isinstance(inner[0], ast.stmt):
                    self._check_dead_code(inner)


# ==========================================================================
# Regex-based textual smells (appropriate for lexical patterns)
# ==========================================================================
def _textual_security(code: str) -> List[str]:
    issues: List[str] = []
    if re.search(r'(password|pwd|secret|token|api_key|key)\s*=\s*["\'][^"\']+["\']',
                 code, re.IGNORECASE):
        issues.append("Hardcoded credential detected (password, token, or key)")
    if re.search(r'(execute|query)\s*\(\s*["\'][^"\']*\+', code, re.IGNORECASE):
        issues.append("Potential SQL injection — string concatenation in query")
    if re.search(r'\beval\s*\(', code):
        issues.append("eval() used — arbitrary code execution risk")
    if re.search(r'\bexec\s*\(', code):
        issues.append("exec() used — arbitrary code execution risk")
    if re.search(r'\binput\s*\(', code) and "validate" not in code.lower():
        issues.append("User input used without validation")
    if "pickle" in code and "load" in code:
        issues.append("pickle.load() used — potential deserialization risk")
    if "os.system" in code or "subprocess" in code:
        issues.append("Shell command execution — ensure input is sanitized")
    if re.search(r'\b(md5|sha1)\b', code):
        issues.append("Weak cryptographic hash (MD5/SHA1) detected")
    return issues


def _textual_smells(code: str) -> List[str]:
    smells: List[str] = []
    for i, line in enumerate(code.split("\n"), start=1):
        if len(line) > LONG_LINE_CHARS:
            smells.append(f"Long line ({len(line)} chars) at line {i}")
            break
    todos = re.findall(r'#\s*TODO', code, re.IGNORECASE)
    if todos:
        smells.append(f"{len(todos)} TODO comment(s) — incomplete code")
    fixmes = re.findall(r'#\s*FIXME', code, re.IGNORECASE)
    if fixmes:
        smells.append(f"{len(fixmes)} FIXME comment(s) — known issues")
    return smells


# ==========================================================================
# Public API
# ==========================================================================
def analyze_code_quality(code: str, language: str = "python") -> Dict[str, Any]:
    """Analyse code for security, dead code, and quality issues.

    Structural checks use the AST; lexical smells use regex. Returns a dict with
    security_issues, dead_code, code_smells, score, total_issues, summary,
    parse_ok, and method.
    """
    result: Dict[str, Any] = {
        "security_issues": [],
        "dead_code": [],
        "code_smells": [],
        "score": 0,
        "total_issues": 0,
        "parse_ok": False,
        "summary": "",
        "method": "ast(structural)+regex(lexical)",
    }

    if language != "python":
        result["summary"] = f"unsupported language: {language}"
        return result

    # --- lexical checks always run (work on raw text) ---
    security = _textual_security(code)
    smells = _textual_smells(code)
    dead_code: List[str] = []

    # --- structural checks require a parse ---
    try:
        tree = ast.parse(code)
        result["parse_ok"] = True
    except SyntaxError as exc:
        # Report honestly; do not pretend structurally-clean.
        result["security_issues"] = security
        result["code_smells"] = smells
        result["summary"] = f"syntax error — structural checks skipped: {exc}"
        # score only on what we could measure
        score = 100 - PENALTY_SECURITY * len(security) - PENALTY_CODE_SMELL * len(smells)
        result["score"] = max(0, score)
        result["total_issues"] = len(security) + len(smells)
        return result

    module_lines = code.count("\n") + 1
    visitor = _StructuralVisitor(module_lines)
    visitor.visit(tree)

    # unused imports (structural, via AST)
    for bound, line in visitor.imported.items():
        if bound not in visitor.used_names:
            dead_code.append(f"Unused import '{bound}' (line {line})")
    dead_code.extend(visitor.dead_code)

    # module docstring
    if ast.get_docstring(tree) is None:
        smells.append("Missing module-level docstring")
    smells.extend(visitor.long_functions)
    smells.extend(visitor.missing_docstrings)
    smells.extend(visitor.mutable_defaults)

    # --- scoring (coefficients from named constants; paper Eq.(1) must match) ---
    score = 100
    score -= PENALTY_SECURITY * len(security)
    score -= PENALTY_DEAD_CODE * len(dead_code)
    score -= PENALTY_CODE_SMELL * len(smells)
    score = max(0, score)

    total = len(security) + len(dead_code) + len(smells)
    if total == 0:
        summary = "Code quality is excellent. No issues found."
    elif score >= 80:
        summary = f"Good quality. Score: {score}/100. {total} minor issue(s)."
    elif score >= 50:
        summary = f"Fair quality. Score: {score}/100. {total} issue(s) need attention."
    else:
        summary = f"Poor quality. Score: {score}/100. {total} serious issue(s)."

    result.update({
        "security_issues": security,
        "dead_code": dead_code,
        "code_smells": smells,
        "score": score,
        "total_issues": total,
        "summary": summary,
    })
    return result


if __name__ == "__main__":
    demo = (
        "import os\n"
        "import json\n"                       # unused -> dead code
        "def f(x=[]):\n"                       # mutable default + missing docstring
        "    return x\n"
        "    print('unreachable')\n"           # dead code after return
        "password = \"admin123\"\n"            # security
    )
    from pprint import pprint
    pprint(analyze_code_quality(demo))
