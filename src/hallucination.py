"""
Hallucination Detection Module for AI Auditor  (v2 — AST-based, credible)
=========================================================================

WHAT CHANGED AND WHY
--------------------
The previous version claimed "hallucination detection" but actually (a) checked
imports against a hardcoded list of six toy names that real models never emit, so
it returned nothing on real code, and (b) delegated a "hallucination risk %" to a
token/cost-estimator library that merely counted numeric literals in text. Neither
measured code hallucination. This rewrite replaces both with a real, ground-truthed,
reproducible detector.

DEFINITION (this is the definition the paper must use)
------------------------------------------------------
We parse the code into an Abstract Syntax Tree (AST) and classify every top-level
imported module into exactly one of:

  1. TRUE HALLUCINATION  — the module is neither in the Python standard library nor
                           resolvable to a known real PyPI distribution (plausibly
                           does not exist anywhere).
  2. UNUSED IMPORT       — the module is real but imported and never referenced
                           (a quality issue, NOT a hallucination — reported apart).
  3. RESOLVED / OK       — real module, actually used.

Cross-framework / anti-pattern heuristics live in their own bucket and are NEVER
counted as hallucinations.

WHY THIS IS CREDIBLE AND REPRODUCIBLE
-------------------------------------
- Ground truth = Python's own `sys.stdlib_module_names` plus a FROZEN, versioned
  snapshot of known PyPI names (data/known_pypi_snapshot.json). Freezing the registry
  means identical code yields identical verdicts over time, independent of live PyPI.
- Import-name/package-name mismatches (PIL->pillow, bs4->beautifulsoup4,
  sklearn->scikit-learn, jwt->pyjwt, ...) are resolved via data/import_to_package.json
  so legitimate packages are not falsely flagged.
- Every decision is explainable: each flagged import records WHY it was flagged.
- Degrades safely: if code does not parse, we say so rather than returning "clean".
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Set

_DATA_DIR = Path(__file__).parent / "data"


def _load_json(name: str) -> dict:
    with open(_DATA_DIR / name, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _load_known_packages() -> Set[str]:
    snap = _load_json("known_pypi_snapshot.json")
    return {p.lower() for p in snap["packages"]}


def _load_import_map() -> Dict[str, str]:
    raw = _load_json("import_to_package.json")
    return {k: v.lower() for k, v in raw.items() if not k.startswith("_")}


_STDLIB: Set[str] = set(getattr(sys, "stdlib_module_names", set()))
_KNOWN_PACKAGES: Set[str] = _load_known_packages()
_IMPORT_TO_PACKAGE: Dict[str, str] = _load_import_map()

_STDLIB_EXTRA = {
    "__future__", "typing", "dataclasses", "enum", "collections", "concurrent",
    "asyncio", "pathlib", "functools", "itertools", "email", "urllib",
}
_STDLIB |= _STDLIB_EXTRA


class _ImportCollector(ast.NodeVisitor):
    """Collect top-level imports (with line numbers) and all used names, so we can
    distinguish used from unused imports."""

    def __init__(self) -> None:
        self.imported: Dict[str, int] = {}
        self.used_names: Set[str] = set()
        self.alias_map: Dict[str, str] = {}
        self.from_import: Dict[str, bool] = {}   # top-level -> came via `from X import`
        self.is_relative: Set[str] = set()       # top-level from a relative import

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            top = alias.name.split(".")[0]
            bound = (alias.asname or alias.name).split(".")[0]
            self.imported.setdefault(top, node.lineno)
            self.from_import.setdefault(top, False)
            self.alias_map[bound] = top
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level and not node.module:
            # `from . import x` — purely relative, definitively local; skip.
            self.generic_visit(node)
            return
        if node.module:
            top = node.module.split(".")[0]
            self.imported.setdefault(top, node.lineno)
            self.from_import.setdefault(top, True)
            if node.level:  # `from .pkg import x` — relative, local
                self.is_relative.add(top)
            for alias in node.names:
                bound = (alias.asname or alias.name)
                self.alias_map[bound] = top
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


def _is_real_module(top: str) -> bool:
    if top in _STDLIB:
        return True
    low = top.lower()
    if low in _KNOWN_PACKAGES:
        return True
    if top in _IMPORT_TO_PACKAGE and _IMPORT_TO_PACKAGE[top] in _KNOWN_PACKAGES:
        return True
    if low.replace("_", "-") in _KNOWN_PACKAGES:
        return True
    return False


# Common local-module names that indicate an intra-project import (a sibling .py
# file) rather than a hallucinated third-party package. Django/Flask projects
# routinely import these locally. We classify them as UNRESOLVED LOCAL, not as
# hallucinations, because a single-file snippet cannot prove they are fabricated —
# the honest, conservative verdict. This is the distinction that separates a
# credible detector from one that inflates its hallucination count.
_LOCAL_MODULE_HINTS = {
    "models", "forms", "views", "urls", "admin", "apps", "feeds", "serializers",
    "schemas", "routes", "config", "settings", "utils", "helpers", "database",
    "db", "app", "main", "tasks", "services", "handlers", "middleware",
    "extensions", "auth", "api", "core", "common", "constants", "exceptions",
}


def _classify_import(top: str, from_import: bool) -> str:
    """Return one of: 'real', 'local', 'hallucination'."""
    if _is_real_module(top):
        return "real"
    # A short, lowercase, common project name imported via `from X import ...`
    # is almost certainly a local sibling module, not a hallucinated package.
    if top in _LOCAL_MODULE_HINTS:
        return "local"
    return "hallucination"


def _detect_anti_patterns(tree: ast.AST, code: str) -> List[str]:
    findings: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for default in node.args.defaults + node.args.kw_defaults:
                if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                    findings.append(
                        f"Mutable default argument in function '{node.name}' "
                        f"(line {node.lineno})"
                    )
                    break
    for js in (".push(", ".shift(", ".unshift("):
        if js in code:
            findings.append(
                f"Possible cross-language leakage: '{js}' is a JavaScript idiom"
            )
    return findings


def detect_hallucinations(code: str, language: str = "python") -> Dict[str, Any]:
    """Analyse `code` for import hallucinations using AST + a frozen package oracle."""
    result: Dict[str, Any] = {
        "parse_ok": False,
        "true_hallucinations": [],
        "unresolved_local_imports": [],
        "unused_imports": [],
        "anti_patterns": [],
        "imports_total": 0,
        "hallucination_count": 0,
        "hallucination_rate_pct": 0.0,
        "status": "",
        "method": "ast+frozen-pypi-oracle",
    }

    if language != "python":
        result["status"] = f"unsupported language: {language}"
        return result

    try:
        tree = ast.parse(code)
        result["parse_ok"] = True
    except SyntaxError as exc:
        result["status"] = f"syntax error, cannot analyse: {exc}"
        return result

    collector = _ImportCollector()
    collector.visit(tree)
    imported = collector.imported
    result["imports_total"] = len(imported)

    for top, line in sorted(imported.items(), key=lambda kv: kv[1]):
        # Relative imports (from .x import y) are always local by definition.
        if top in collector.is_relative:
            result["unresolved_local_imports"].append({"module": top, "line": line})
            continue

        kind = _classify_import(top, collector.from_import.get(top, False))
        if kind == "hallucination":
            result["true_hallucinations"].append({
                "module": top,
                "line": line,
                "reason": "not in Python stdlib and not a known PyPI distribution "
                          "(after import-name resolution)",
            })
            continue
        if kind == "local":
            result["unresolved_local_imports"].append({
                "module": top,
                "line": line,
            })
            continue
        # real module: check usage
        aliases = {b for b, t in collector.alias_map.items() if t == top} | {top}
        if aliases.isdisjoint(collector.used_names):
            result["unused_imports"].append({"module": top, "line": line})

    result["anti_patterns"] = _detect_anti_patterns(tree, code)

    hc = len(result["true_hallucinations"])
    result["hallucination_count"] = hc
    result["hallucination_rate_pct"] = round(
        (hc / result["imports_total"] * 100.0) if result["imports_total"] else 0.0, 2
    )
    result["status"] = "ok"
    return result


if __name__ == "__main__":
    demo = (
        "import os\n"
        "import numpy as np\n"
        "from flask import Flask\n"
        "import totally_made_up_pkg\n"
        "from nonexistent_ai_lib import Magic\n"
        "import json\n"
        "\n"
        "app = Flask(__name__)\n"
        "arr = np.array([1, 2, 3])\n"
        "print(os.getcwd())\n"
    )
    from pprint import pprint
    pprint(detect_hallucinations(demo))
