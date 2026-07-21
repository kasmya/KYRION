# How to Run the Dataset Generator — Complete Instructions

This answers every question you asked, in order.

---

## SETUP (one time)

1. Put these three files in the same folder:
   - `nvidia_dataset_generator_v3.py` (the generator)
   - `api_config.py` (your keys — copy from `api_config_TEMPLATE.py` and fill in)
   - `tasks_enhanced.json` (or your existing `tasks.json`)

2. Install the one dependency:
   ```bash
   pip install openai
   ```

3. Fill in `api_config.py`. Copy the template:
   ```bash
   cp api_config_TEMPLATE.py api_config.py
   ```
   Then edit `api_config.py` and replace each `nvapi-REPLACE_ME` with your real key,
   OR set environment variables (safer):
   ```bash
   export NVIDIA_KEY_GPTOSS=nvapi-xxxxx
   export NVIDIA_KEY_DEEPSEEK=nvapi-yyyyy
   # ... etc
   ```

---

## Q: Does it call all models at once, or do I run each task separately?

**One command runs EVERYTHING automatically.** You do NOT run tasks separately.
When you run it, it loops over every (model x task x run) combination by itself:

```bash
python nvidia_dataset_generator_v3.py --tasks tasks_enhanced.json
```

With 5 models, 20 tasks, k=3 runs, that's 5 x 20 x 3 = 300 generations, all handled
in one run. It uses parallel workers (default 5) so multiple calls happen at once,
but each model uses its OWN API key so quotas stay isolated.

If you ever want just ONE model:
```bash
python nvidia_dataset_generator_v3.py --tasks tasks_enhanced.json --models "openai/gpt-oss-120b"
```

---

## Q: Skip responses taking too long + log them separately for later

**Done — this is built in.** If a call times out, the generator:
1. Skips it immediately (stops retrying, moves on).
2. Logs it to a SEPARATE file: `skipped_runs.jsonl` (distinct from other failures).
3. Prints `⏭ SKIP (timeout)` so you see it live.

Control how long "too long" is with `--timeout` (seconds, default 120):
```bash
python nvidia_dataset_generator_v3.py --tasks tasks_enhanced.json --timeout 60
```
That skips anything taking over 60 seconds.

**Later, re-run ONLY the skipped ones:**
```bash
python nvidia_dataset_generator_v3.py --tasks tasks_enhanced.json --retry-skipped
```
This reads `skipped_runs.jsonl` and retries just those runs (e.g. at off-peak hours
when the API is faster). Anything that times out again is re-logged for another pass.

---

## Q: Are the API keys actually being used?

**Yes — verified.** The flow is:
- `api_config.py` holds `MODEL_CONFIGS[model]["api_key"]`.
- `get_client(model)` reads that key and creates a dedicated OpenAI client:
  `OpenAI(api_key=api_key, base_url=NVIDIA_BASE_URL)`.
- Every generation for that model uses that client, hence that key.

Each model has its own key, so if one key hits a rate limit the others keep working.
At startup, the `--probe` step tests each key with a tiny call and prints ✓ or ✗ per
model, so you'll SEE immediately if a key is wrong before generation starts.

---

## Q: Neat output format for the paper + testing

Each generation produces two files side by side:
- `run<K>.py` — the generated code
- `run<K>.meta.json` — provenance: model version, timestamp, temperature,
  max_tokens, line count, truncation flag

Plus three top-level logs:
- `provenance.jsonl` — every run (success and failure), one line each
- `skipped_runs.jsonl` — only the timed-out runs (for --retry-skipped)
- `summary.json` — final counts, failure list, truncation count

This is clean, self-describing, and directly usable by your auditor pipeline and
for the paper's reproducibility appendix.

---

## Q: Folder structure — model-wise

**Done — now MODEL-FIRST, exactly as you asked:**
```
dataset_outputs/
  openai__gpt-oss-120b/
    task01/
      run1.py
      run1.meta.json
      run2.py
      ...
    task02/
      ...
  deepseek-ai__deepseek-v4-flash/
    task01/
      ...
```
Every model gets its own top-level folder; inside it, one sub-folder per task, each
containing that model's runs for that task. Easy to see everything one model produced.

---

## THE COMMANDS YOU'LL ACTUALLY USE

```bash
# 1. Full run (everything, automatically)
python nvidia_dataset_generator_v3.py --tasks tasks_enhanced.json

# 2. If interrupted, resume where it stopped (skips already-done runs)
python nvidia_dataset_generator_v3.py --tasks tasks_enhanced.json --resume

# 3. Retry runs that timed out (from skipped_runs.jsonl)
python nvidia_dataset_generator_v3.py --tasks tasks_enhanced.json --retry-skipped

# 4. Retry any other failures (non-timeout errors)
python nvidia_dataset_generator_v3.py --tasks tasks_enhanced.json --retry-failed

# Useful options:
#   --timeout 60        skip anything over 60s
#   --max_tokens 4096   (default; raise if long tasks truncate)
#   --temperature 0.7   (default)
#   --workers 5         parallel calls
#   --k 3               runs per (model,task)
#   --models "a,b"      only specific models
```

## Typical workflow
1. Run the full command (#1). Let it finish.
2. Check the summary: it prints succeeded / failed / skipped / truncated counts.
3. Run `--retry-skipped` (#3) at a quieter time to fill timeout gaps.
4. Run `--retry-failed` (#4) for any remaining non-timeout failures.
5. When coverage is complete, import into the auditor with `step1_import_dataset.py`.

## Reminder: keep your keys safe
Add `api_config.py` to `.gitignore` so you never commit your keys:
```bash
echo "api_config.py" >> .gitignore
```
