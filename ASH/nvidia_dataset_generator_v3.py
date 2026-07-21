"""
NVIDIA NIM Multi-Model Dataset Generator — Per-Key Edition
============================================================
Each model in api_config.py uses its OWN dedicated API key, so quota
and rate limits are isolated per model instead of shared. Output goes
into clean, separate folders per task/model as before.

Setup:
    pip install openai
    Edit api_config.py to set/update model -> API key mappings.

Run all configured models, k=3 runs each:
    python nvidia_dataset_generator.py --tasks tasks.json

Resume after interruption:
    python nvidia_dataset_generator.py --tasks tasks.json --resume

Retry only failed runs:
    python nvidia_dataset_generator.py --tasks tasks.json --retry-failed

Run only specific models (subset of api_config.py):
    python nvidia_dataset_generator.py --tasks tasks.json --models "deepseek-ai/deepseek-v4-pro,openai/gpt-oss-120b"
"""

import argparse
import json
import os
import re
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI, APIStatusError

from api_config import MODEL_CONFIGS, NVIDIA_BASE_URL

SYSTEM_PROMPT = (
    "You are a Python code generator. "
    "Output ONLY the code inside a single ```python ... ``` fenced block. "
    "No explanations, no prose, no text outside the code block."
)

OUTPUT_ROOT     = Path("dataset_outputs")
PROVENANCE_FILE = Path("provenance.jsonl")
SUMMARY_FILE    = Path("summary.json")
SKIPPED_FILE    = Path("skipped_runs.jsonl")   # timed-out / skipped runs go here

_prov_lock  = threading.Lock()
_print_lock = threading.Lock()
_skip_lock  = threading.Lock()

# Cache of per-model OpenAI clients, built once per model (uses its own key)
_clients: dict[str, OpenAI] = {}
_clients_lock = threading.Lock()


# ── Utilities ──────────────────────────────────────────────────────────────────

def slugify(s: str) -> str:
    # Normalise BOTH separators consistently. Previously "." -> "-" while version
    # numbers already using "-" stayed as-is, which produced duplicate folders like
    # llama-3-1 vs llama-3_1. We now collapse "/" -> "__" and any "." to "-", and
    # additionally normalise stray "_" inside the model part to "-" so a model can
    # never map to two different folder names.
    if "/" in s:
        vendor, model = s.split("/", 1)
        model = model.replace(".", "-").replace("_", "-")
        return f"{vendor}__{model}"
    return s.replace(".", "-").replace("_", "-")


def extract_code(text: str) -> str:
    m = re.search(r"```python\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).rstrip()
    return re.sub(r"```\w*\n?", "", text).strip()


def tprint(*args, **kwargs):
    with _print_lock:
        print(*args, **kwargs)


def get_client(model_id: str) -> OpenAI:
    """Return (and cache) a client using this model's dedicated API key."""
    with _clients_lock:
        if model_id not in _clients:
            api_key = MODEL_CONFIGS[model_id]["api_key"]
            _clients[model_id] = OpenAI(api_key=api_key, base_url=NVIDIA_BASE_URL)
        return _clients[model_id]


def load_provenance(path: Path) -> tuple[set[tuple], set[tuple]]:
    success, all_recorded = set(), set()
    if not path.exists():
        return success, all_recorded
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                k = (r["task"], r["model"], r["run"])
                all_recorded.add(k)
                if "error" not in r:
                    success.add(k)
            except json.JSONDecodeError:
                pass
    return success, all_recorded


def append_provenance(record: dict) -> None:
    with _prov_lock:
        with open(PROVENANCE_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")


def load_truncated(path: Path) -> set[tuple]:
    """Return (task, model, run) keys for successful-but-truncated generations,
    keeping only the MOST RECENT record per key (so a later clean regeneration
    correctly clears an earlier truncated flag)."""
    latest: dict[tuple, dict] = {}
    if not path.exists():
        return set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                if "error" in r:
                    continue  # not a successful run, irrelevant here
                k = (r["task"], r["model"], r["run"])
                latest[k] = r  # later lines overwrite earlier ones -> most recent wins
            except json.JSONDecodeError:
                pass
    return {k for k, r in latest.items() if r.get("truncated") is True}


def append_skipped(record: dict) -> None:
    """Record a timed-out / skipped run in a SEPARATE file so it can be retried
    independently of other failures (via --retry-skipped)."""
    with _skip_lock:
        with open(SKIPPED_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")


def save_code(task_id: str, model_id: str, run: int, code: str,
              meta: dict | None = None) -> Path:
    # MODEL-FIRST layout (per requirement): each model gets its own top-level
    # folder, containing one sub-folder per task, containing the runs. This makes
    # it trivial to look at everything a single model produced.
    #   dataset_outputs/<model>/<task>/run<K>.py
    folder = OUTPUT_ROOT / slugify(model_id) / task_id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"run{run}.py"
    path.write_text(code, encoding="utf-8")
    # Write a per-run metadata sidecar so provenance travels WITH each file,
    # not only in the central JSONL. This makes the dataset self-describing and
    # citable at the file level.
    if meta is not None:
        (folder / f"run{run}.meta.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8")
    # Flag likely truncation so quality problems are visible at collection time.
    if _looks_truncated(code):
        (folder / f"run{run}.TRUNCATED").write_text(
            "This run may be truncated (hit max_tokens). Consider regenerating "
            "with a higher --max_tokens.", encoding="utf-8")
    return path


def _looks_truncated(code: str) -> bool:
    """Heuristic: a generation that stops mid-construct likely hit max_tokens."""
    s = code.rstrip()
    if not s:
        return True
    last = s.splitlines()[-1].rstrip() if s.splitlines() else ""
    # ends on an opening/continuation token, or with an unclosed triple quote
    if last.endswith(("(", "[", "{", ",", "=", "+", ":", "\\")):
        return True
    if s.count('"""') % 2 == 1 or s.count("'''") % 2 == 1:
        return True
    return False


# ── Probe ──────────────────────────────────────────────────────────────────────

def probe(model_id: str) -> tuple[bool, str]:
    try:
        client = get_client(model_id)
        client.chat.completions.create(
            model=model_id, max_tokens=5, temperature=0, timeout=15,
            messages=[{"role": "user", "content": "Say: ready"}],
        )
        return True, "ok"
    except APIStatusError as e:
        return False, f"HTTP {e.status_code}"
    except Exception as e:
        return False, str(e)[:60]


def probe_all(models: list[str]) -> list[str]:
    print("\nProbing models (each with its own API key) …\n")
    working = []
    for model in models:
        print(f"  · {model:<40}", end=" ", flush=True)
        ok, reason = probe(model)
        print("✓" if ok else f"✗  {reason}")
        if ok:
            working.append(model)
        time.sleep(0.3)
    print()
    return working


# ── Single API call ─────────────────────────────────────────────────────────────

def run_one(
    task_id: str,
    task_prompt: str,
    model_id: str,
    run: int,
    max_tokens: int,
    timeout: float,
    retries: int,
    label: str,
    temperature: float = 0.7,
) -> dict:
    client = get_client(model_id)
    extra_body = MODEL_CONFIGS[model_id].get("extra_body")

    last_err = ""
    for attempt in range(1, retries + 1):
        try:
            kwargs = dict(
                model=model_id,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=timeout,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": task_prompt},
                ],
            )
            if extra_body:
                kwargs["extra_body"] = extra_body

            resp = client.chat.completions.create(**kwargs)
            code = extract_code(resp.choices[0].message.content or "")
            meta = {
                "model":         model_id,
                "task":          task_id,
                "run":           run,
                "collected_at":  datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "model_version": resp.model,
                "temperature":   temperature,
                "max_tokens":    max_tokens,
                "truncated":     _looks_truncated(code),
                "n_lines":       len(code.splitlines()),
            }
            out_path = save_code(task_id, model_id, run, code, meta)
            append_provenance(meta)
            tprint(f"  ✓  {label}  → {out_path}")
            return {"success": True, "out_path": str(out_path), "model_version": resp.model}

        except APIStatusError as e:
            if e.status_code in (404, 410):
                last_err = f"HTTP {e.status_code} (permanent)"
                break
            last_err = f"HTTP {e.status_code}"
            if attempt < retries:
                time.sleep(5 * attempt)

        except Exception as e:
            last_err = str(e)[:80]
            # Timeouts are the "taking too long" case you want skipped and logged
            # separately. Detect them and stop retrying so we move on quickly.
            is_timeout = ("timeout" in last_err.lower() or "timed out" in last_err.lower()
                          or type(e).__name__.lower().startswith("timeout"))
            if is_timeout:
                tprint(f"  ⏭  SKIP (timeout) {label}  [{last_err}]")
                skip_rec = {
                    "model": model_id, "task": task_id, "run": run,
                    "collected_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "reason": "timeout", "detail": last_err,
                }
                append_skipped(skip_rec)
                append_provenance({**skip_rec, "model_version": "unknown",
                                   "error": "timeout (skipped)"})
                return {"success": False, "error": "timeout (skipped)", "skipped": True}
            if attempt < retries:
                time.sleep(5 * attempt)

    tprint(f"  ✗  {label}  [{last_err}]")
    append_provenance({
        "model":         model_id,
        "task":          task_id,
        "run":           run,
        "collected_at":  datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "model_version": "unknown",
        "error":         last_err,
    })
    return {"success": False, "error": last_err}


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="NVIDIA NIM Per-Key Dataset Generator")
    parser.add_argument("--tasks",        default="tasks.json")
    parser.add_argument("--k",            type=int,   default=3)
    parser.add_argument("--models",       default="",
                        help="Comma-separated subset of models from api_config.py (default: all)")
    parser.add_argument("--workers",      type=int,   default=5,
                        help="Parallel threads (default: 5; each model has its own key so this is safe)")
    parser.add_argument("--timeout",      type=float, default=120)
    parser.add_argument("--retries",      type=int,   default=2)
    parser.add_argument("--max_tokens",   type=int,   default=4096,
                        help="Raised from 2048 to reduce truncation on longer tasks")
    parser.add_argument("--temperature",  type=float, default=0.7,
                        help="Sampling temperature (0.7 is standard for capability "
                             "measurement; lower = more deterministic)")
    parser.add_argument("--resume",       action="store_true")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--retry-skipped", action="store_true",
                        help="Re-run only the runs that timed out (from skipped_runs.jsonl)")
    parser.add_argument("--retry-truncated", action="store_true",
                        help="Re-run only successful runs flagged truncated=true in provenance.jsonl")
    parser.add_argument("--no-probe",     action="store_true",
                        help="Skip the probe step and go straight to generation")
    args = parser.parse_args()

    # ── Resolve models ────────────────────────────────────────────────────────
    if args.models.strip():
        models = [m.strip() for m in args.models.split(",") if m.strip()]
        unknown = [m for m in models if m not in MODEL_CONFIGS]
        if unknown:
            print(f"ERROR: these models aren't in api_config.py: {unknown}")
            sys.exit(1)
    else:
        models = list(MODEL_CONFIGS.keys())

    if not args.no_probe:
        models = probe_all(models)

    if not models:
        print("ERROR: No working models.")
        sys.exit(1)

    # ── Tasks ─────────────────────────────────────────────────────────────────
    tasks_path = Path(args.tasks)
    if not tasks_path.exists():
        print(f"ERROR: {tasks_path} not found.")
        sys.exit(1)
    with open(tasks_path, encoding="utf-8") as f:
        tasks: dict[str, str] = json.load(f)

    OUTPUT_ROOT.mkdir(exist_ok=True)

    # ── Build work queue ──────────────────────────────────────────────────────
    success_set, all_recorded = load_provenance(PROVENANCE_FILE)

    all_jobs = [
        (task_id, model_id, run)
        for task_id in tasks
        for model_id in models
        for run in range(1, args.k + 1)
    ]

    if args.retry_truncated:
        truncated = load_truncated(PROVENANCE_FILE)
        jobs = [(t, m, r) for t, m, r in all_jobs if (t, m, r) in truncated]
        print(f"Retry-truncated mode: {len(jobs)} previously truncated runs to retry.")
        if args.max_tokens <= 4096:
            print(f"  ⚠  Tip: pass a higher --max_tokens (e.g. 8192) or these will "
                  f"likely truncate again at the same limit.")
    elif args.retry_skipped:
        # Load the skipped (timed-out) runs and retry only those.
        skipped = set()
        if SKIPPED_FILE.exists():
            for line in SKIPPED_FILE.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    try:
                        r = json.loads(line)
                        skipped.add((r["task"], r["model"], r["run"]))
                    except json.JSONDecodeError:
                        pass
        jobs = [(t, m, r) for t, m, r in all_jobs if (t, m, r) in skipped]
        # clear the skipped file so this run re-populates it with any that time out again
        if SKIPPED_FILE.exists():
            SKIPPED_FILE.rename(SKIPPED_FILE.with_suffix(".jsonl.prev"))
        print(f"Retry-skipped mode: {len(jobs)} previously timed-out runs to retry.")
    elif args.retry_failed:
        failed_only = all_recorded - success_set
        jobs = [(t, m, r) for t, m, r in all_jobs if (t, m, r) in failed_only]
        print(f"Retry-failed mode: {len(jobs)} previously failed runs to retry.")
    elif args.resume:
        jobs = [(t, m, r) for t, m, r in all_jobs if (t, m, r) not in all_recorded]
        print(f"Resume mode: skipping {len(all_recorded)} recorded, {len(jobs)} remaining.")
    else:
        jobs = all_jobs

    total = len(jobs)

    # ── Banner ────────────────────────────────────────────────────────────────
    print("=" * 70)
    print("  NVIDIA NIM Per-Key Dataset Generator")
    print("=" * 70)
    print(f"  Tasks          : {len(tasks)}")
    print(f"  Models (keys)  : {len(models)}")
    for m in models:
        print(f"                   • {m}")
    print(f"  k (runs/pair)  : {args.k}")
    print(f"  Jobs to run    : {total}")
    print(f"  Workers        : {args.workers}")
    print(f"  Timeout/call   : {args.timeout}s")
    print(f"  Retries/call   : {args.retries}")
    print(f"  Max tokens     : {args.max_tokens}")
    print(f"  Temperature    : {args.temperature}")
    print(f"  Output         : {OUTPUT_ROOT}/")
    print(f"  Provenance     : {PROVENANCE_FILE}")
    print("=" * 70 + "\n")

    if total == 0:
        print("Nothing to do — all runs already recorded.")
        sys.exit(0)

    # ── Parallel execution ────────────────────────────────────────────────────
    success_count = 0
    failures: list[dict] = []
    counter_lock = threading.Lock()

    def submit(job):
        task_id, model_id, run = job
        nonlocal success_count
        label = f"{task_id} | {model_id} | run={run}"
        result = run_one(
            task_id, tasks[task_id], model_id, run,
            args.max_tokens, args.timeout, args.retries, label,
            temperature=args.temperature,
        )
        with counter_lock:
            if result["success"]:
                success_count += 1
            else:
                failures.append({"task": task_id, "model": model_id,
                                 "run": run, "error": result.get("error", "")})
        return result

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(submit, job): job for job in jobs}
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                tprint(f"  !! Unexpected thread error: {e}")

    # ── Summary ───────────────────────────────────────────────────────────────
    SUMMARY_FILE.write_text(json.dumps({
        "total_jobs":   total,
        "success":      success_count,
        "failures":     len(failures),
        "failure_list": failures,
        "models":       models,
        "tasks":        list(tasks.keys()),
        "k":            args.k,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2), encoding="utf-8")

    # count truncation flags dropped during this run
    trunc = list(OUTPUT_ROOT.rglob("*.TRUNCATED"))

    print("\n" + "=" * 70)
    print(f"  Done.  ✓ {success_count} succeeded   ✗ {len(failures)} failed")
    if trunc:
        print(f"  ⚠  {len(trunc)} run(s) flagged as possibly TRUNCATED — consider")
        print(f"     regenerating those with a higher --max_tokens. See *.TRUNCATED files.")
    print(f"  Code      : {OUTPUT_ROOT}/")
    print(f"  Provenance: {PROVENANCE_FILE}")
    print(f"  Summary   : {SUMMARY_FILE}")
    print("=" * 70)

    if failures:
        print(f"\n{len(failures)} failed runs (run with --retry-failed to retry):")
        for f in failures[:20]:
            print(f"  • {f['task']} | {f['model']} | run={f['run']}  →  {f['error']}")
        if len(failures) > 20:
            print(f"  ... and {len(failures)-20} more (see summary.json)")


if __name__ == "__main__":
    main()
