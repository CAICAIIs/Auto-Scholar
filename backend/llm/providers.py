from __future__ import annotations

import logging
import os

from backend.schemas import ModelConfig, ModelProvider

logger = logging.getLogger(__name__)


def resolve_api_key(config: ModelConfig | None) -> str:
    if config is None:
        api_key = os.environ.get("LLM_API_KEY")
        if not api_key:
            raise RuntimeError("LLM_API_KEY environment variable is required")
        return api_key

    if config.provider == ModelProvider.OLLAMA:
        return "ollama"

    api_key = os.environ.get(config.api_key_env, "") if config.api_key_env else ""
    if api_key:
        return api_key

    logger.warning(
        "No API key for model %s (env: %s), falling back to default",
        config.id,
        config.api_key_env,
    )
    fallback_api_key = os.environ.get("LLM_API_KEY")
    if not fallback_api_key:
        raise RuntimeError("LLM_API_KEY environment variable is required")
    return fallback_api_key
