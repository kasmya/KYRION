"""
api_config.py — model -> API key configuration for the NVIDIA NIM generator.
============================================================================
Copy this file to `api_config.py` (same folder as the generator) and fill in
your real keys. NEVER commit api_config.py to git — add it to .gitignore.

Each model uses its OWN dedicated key, so per-model quota/rate limits are
isolated. If several models share one key, just repeat the same key value.
"""
import os

# NVIDIA NIM OpenAI-compatible endpoint
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

# One entry per model. The key can be a literal string, but reading from an
# environment variable is safer (shown for the first entry).
MODEL_CONFIGS = {
    "openai/gpt-oss-120b": {
        "api_key": os.environ.get("NVIDIA_KEY_GPTOSS", "nvapi-REPLACE_ME"),
        # optional per-model params passed to the API:
        # "extra_body": {"chat_template_kwargs": {"thinking": True}},
    },
    "nvidia/llama-3.3-nemotron-super-49b-v1": {
        "api_key": os.environ.get("NVIDIA_KEY_NEMOTRON", "nvapi-REPLACE_ME"),
    },
    "meta/llama-3.3-70b-instruct": {
        "api_key": os.environ.get("NVIDIA_KEY_LLAMA33", "nvapi-REPLACE_ME"),
    },
    "meta/llama-3.1-70b-instruct": {
        "api_key": os.environ.get("NVIDIA_KEY_LLAMA31", "nvapi-REPLACE_ME"),
    },
    "deepseek-ai/deepseek-v4-flash": {
        "api_key": os.environ.get("NVIDIA_KEY_DEEPSEEK", "nvapi-REPLACE_ME"),
    },
}
