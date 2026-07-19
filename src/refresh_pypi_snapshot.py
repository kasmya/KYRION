"""
refresh_pypi_snapshot.py
========================

Regenerate the frozen package oracle used by hallucination.py by verifying each
candidate import name against LIVE PyPI, then writing a dated snapshot.

WHY A FROZEN SNAPSHOT (and not a live check at audit time):
    Live PyPI lookups make results non-reproducible — a package that exists today
    might be yanked tomorrow, silently changing your hallucination numbers. For an
    archival research result you want a *dated, frozen* registry so the same code
    yields the same verdict forever. You refresh the snapshot deliberately (and
    record its date in the paper), not on every run.

USAGE:
    python3 refresh_pypi_snapshot.py                # verify current snapshot names
    python3 refresh_pypi_snapshot.py --add pkg1 pkg2  # add & verify new names

This script is OPTIONAL tooling; the committed snapshot is the source of truth.
It requires network access; hallucination.py itself never touches the network.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
import urllib.request
from pathlib import Path

_DATA = Path(__file__).parent / "data"
_SNAPSHOT = _DATA / "known_pypi_snapshot.json"


def pypi_exists(package: str, timeout: float = 5.0) -> bool:
    """Return True iff `package` resolves on PyPI (JSON API 200)."""
    url = f"https://pypi.org/pypi/{package}/json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ai-auditor-oracle"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--add", nargs="*", default=[], help="new package names to verify & add")
    args = ap.parse_args()

    snap = json.loads(_SNAPSHOT.read_text())
    packages = set(snap["packages"]) | set(args.add)

    print(f"Verifying {len(packages)} package names against live PyPI...")
    verified, dropped = [], []
    for pkg in sorted(packages):
        if pypi_exists(pkg):
            verified.append(pkg)
        else:
            dropped.append(pkg)
            print(f"  ! not found on PyPI (dropped): {pkg}")

    snap["packages"] = sorted(verified)
    snap["_version"] = _dt.date.today().isoformat()
    snap["_count"] = len(verified)
    snap["_source"] = "verified against live PyPI JSON API"
    _SNAPSHOT.write_text(json.dumps(snap, indent=1))

    print(f"\nWrote {len(verified)} verified packages "
          f"({len(dropped)} dropped) to {_SNAPSHOT.name}")
    print(f"Snapshot dated {snap['_version']}. "
          f"Cite this date in the paper for reproducibility.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
