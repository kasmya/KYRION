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

_prov_lock  = threading.Lock()
_print_lock = threading.Lock()

# Cache of per-model OpenAI clients, built once per model (uses its own key)
_clients: dict[str, OpenAI] = {}
_clients_lock = threading.Lock()


# ── Utilities ──────────────────────────────────────────────────────────────────

def slugify(s: str) -> str:
    return s.replace("/", "__").replace(".", "-")


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


def save_code(task_id: str, model_id: str, run: int, code: str) -> Path:
    folder = OUTPUT_ROOT / task_id / slugify(model_id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"run{run}.py"
    path.write_text(code, encoding="utf-8")
    return path


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
) -> dict:
    client = get_client(model_id)
    extra_body = MODEL_CONFIGS[model_id].get("extra_body")

    last_err = ""
    for attempt in range(1, retries + 1):
        try:
            kwargs = dict(
                model=model_id,
                max_tokens=max_tokens,
                temperature=1.0,
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
            out_path = save_code(task_id, model_id, run, code)
            append_provenance({
                "model":         model_id,
                "task":          task_id,
                "run":           run,
                "collected_at":  datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "model_version": resp.model,
            })
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
    parser.add_argument("--timeout",      type=float, default=90)
    parser.add_argument("--retries",      type=int,   default=2)
    parser.add_argument("--max_tokens",   type=int,   default=2048)
    parser.add_argument("--resume",       action="store_true")
    parser.add_argument("--retry-failed", action="store_true")
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

    if args.retry_failed:
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
            args.max_tokens, args.timeout, args.retries, label
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

    print("\n" + "=" * 70)
    print(f"  Done.  ✓ {success_count} succeeded   ✗ {len(failures)} failed")
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
