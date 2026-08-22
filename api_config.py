"""
api_config.py — model -> API key configuration for the NVIDIA NIM generator.
============================================================================
NEVER commit this file to git — add `api_config.py` to .gitignore.

Each model uses its OWN dedicated key, so per-model quota/rate limits are
isolated from each other. Keys can be overridden via environment variable
(recommended) or fall back to the literal string below.
"""
import os

# NVIDIA NIM OpenAI-compatible endpoint
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

MODEL_CONFIGS = {

    "deepseek-ai/deepseek-v4-pro": {
        "api_key": os.environ.get(
            "NVIDIA_KEY_DEEPSEEK_PRO",
            "REDACTED_NVIDIA_KEY",
        ),
        "extra_body": {"chat_template_kwargs": {"thinking": False}},
    },

    "qwen/qwen3.5-397b-a17b": {
        "api_key": os.environ.get(
            "NVIDIA_KEY_QWEN35",
            "REDACTED_NVIDIA_KEY",
        ),
    },

    

    "nvidia/nemotron-3-ultra-550b-a55b": {
        "api_key": os.environ.get(
            "NVIDIA_KEY_NEMOTRON_ULTRA",
            "REDACTED_NVIDIA_KEY",
        ),
        "extra_body": {
            "chat_template_kwargs": {"enable_thinking": True},
            "reasoning_budget": 16384,
        },
    },

    "openai/gpt-oss-120b": {
        "api_key": os.environ.get(
            "NVIDIA_KEY_GPTOSS",
            "REDACTED_NVIDIA_KEY",
        ),
    },

}
