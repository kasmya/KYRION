"""
api_config.py — model -> API key configuration for the NVIDIA NIM generator.
============================================================================
Keys are read ONLY from environment variables — there is no literal fallback,
so this file is safe to commit. Each model uses its OWN dedicated key, so
per-model quota/rate limits are isolated from each other.

Set the env vars referenced below (e.g. in a local, gitignored .env file)
before running humaneval_completions.py or anything else that imports this
module.
"""
import os


def _required_key(env_var: str) -> str:
    value = os.environ.get(env_var)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable {env_var}. "
            "Set it to your NVIDIA NIM API key before running this script."
        )
    return value


# NVIDIA NIM OpenAI-compatible endpoint
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

MODEL_CONFIGS = {

    "deepseek-ai/deepseek-v4-pro": {
        "api_key": _required_key("NVIDIA_KEY_DEEPSEEK_PRO"),
        "extra_body": {"chat_template_kwargs": {"thinking": False}},
    },

    "qwen/qwen3.5-397b-a17b": {
        "api_key": _required_key("NVIDIA_KEY_QWEN35"),
    },

    "nvidia/nemotron-3-ultra-550b-a55b": {
        "api_key": _required_key("NVIDIA_KEY_NEMOTRON_ULTRA"),
        "extra_body": {
            "chat_template_kwargs": {"enable_thinking": True},
            "reasoning_budget": 16384,
        },
    },

    "openai/gpt-oss-120b": {
        "api_key": _required_key("NVIDIA_KEY_GPTOSS"),
    },

}
