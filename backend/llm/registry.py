from __future__ import annotations

import json
import logging
import os
from typing import Any

from backend.config.loader import load_model_config
from backend.constants import LLM_DEFAULT_MAX_TOKENS, OLLAMA_BASE_URL
from backend.llm.health import get_model_health
from backend.schemas import CostTier, ModelConfig, ModelProvider

logger = logging.getLogger(__name__)

_model_registry: dict[str, ModelConfig] | None = None


def detect_provider_from_url(base_url: str) -> ModelProvider:
    url_lower = base_url.lower()
    if "openai.com" in url_lower:
        return ModelProvider.OPENAI
    if "deepseek.com" in url_lower:
        return ModelProvider.DEEPSEEK
    if "localhost" in url_lower or "127.0.0.1" in url_lower or "11434" in url_lower:
        return ModelProvider.OLLAMA
    return ModelProvider.CUSTOM


def infer_model_capabilities(provider: ModelProvider, model_name: str) -> dict[str, Any]:
    name_lower = model_name.lower()

    if provider == ModelProvider.OLLAMA:
        return {
            "max_context_tokens": 8_000,
            "supports_long_context": False,
            "cost_tier": CostTier.LOW,
            "reasoning_score": 4,
            "creativity_score": 4,
            "latency_score": 8,
        }

    if provider == ModelProvider.DEEPSEEK:
        is_reasoner = "reasoner" in name_lower or "r1" in name_lower
        return {
            "max_context_tokens": 64_000,
            "supports_long_context": True,
            "cost_tier": CostTier.LOW,
            "reasoning_score": 9 if is_reasoner else 7,
            "creativity_score": 6,
            "latency_score": 7,
        }

    is_mini = "mini" in name_lower
    is_o_series = name_lower.startswith("o1") or name_lower.startswith("o3")
    return {
        "max_context_tokens": 128_000,
        "supports_long_context": True,
        "cost_tier": CostTier.LOW if is_mini else CostTier.HIGH,
        "reasoning_score": 9 if is_o_series else (6 if is_mini else 8),
        "creativity_score": 5 if is_mini else 8,
        "latency_score": 9 if is_mini else 6,
    }


def build_default_registry() -> dict[str, ModelConfig]:
    registry: dict[str, ModelConfig] = {}

    api_key = os.environ.get("LLM_API_KEY", "")
    base_url = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
    model_name = os.environ.get("LLM_MODEL", "gpt-4o")

    if api_key:
        provider = detect_provider_from_url(base_url)
        model_id = f"{provider.value}:{model_name}"
        is_local = provider == ModelProvider.OLLAMA
        supports_json = provider != ModelProvider.OLLAMA
        caps = infer_model_capabilities(provider, model_name)
        registry[model_id] = ModelConfig(
            id=model_id,
            provider=provider,
            model_name=model_name,
            display_name=f"{model_name} ({provider.value})",
            api_base=base_url,
            api_key_env="LLM_API_KEY",
            supports_json_mode=supports_json,
            supports_structured_output=supports_json,
            max_output_tokens=LLM_DEFAULT_MAX_TOKENS,
            is_local=is_local,
            **caps,
        )

    deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if deepseek_key:
        ds_base = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        ds_model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
        ds_id = f"deepseek:{ds_model}"
        if ds_id not in registry:
            ds_caps = infer_model_capabilities(ModelProvider.DEEPSEEK, ds_model)
            registry[ds_id] = ModelConfig(
                id=ds_id,
                provider=ModelProvider.DEEPSEEK,
                model_name=ds_model,
                display_name=f"{ds_model} (DeepSeek)",
                api_base=ds_base,
                api_key_env="DEEPSEEK_API_KEY",
                supports_json_mode=True,
                supports_structured_output=True,
                max_output_tokens=LLM_DEFAULT_MAX_TOKENS,
                is_local=False,
                **ds_caps,
            )

    ollama_models_str = os.environ.get("OLLAMA_MODELS", "")
    if ollama_models_str:
        for model_name_entry in ollama_models_str.split(","):
            model_name_entry = model_name_entry.strip()
            if not model_name_entry:
                continue
            model_id = f"ollama:{model_name_entry}"
            ollama_caps = infer_model_capabilities(ModelProvider.OLLAMA, model_name_entry)
            registry[model_id] = ModelConfig(
                id=model_id,
                provider=ModelProvider.OLLAMA,
                model_name=model_name_entry,
                display_name=f"{model_name_entry} (Ollama, local)",
                api_base=OLLAMA_BASE_URL,
                api_key_env="",
                supports_json_mode=False,
                supports_structured_output=False,
                max_output_tokens=4096,
                is_local=True,
                **ollama_caps,
            )

    return registry


def get_model_registry() -> dict[str, ModelConfig]:
    global _model_registry
    if _model_registry is None:
        config_path = os.environ.get("MODEL_CONFIG_PATH", "")
        if config_path:
            yaml_registry = load_model_config(config_path)
            if yaml_registry:
                _model_registry = yaml_registry
                return _model_registry

        custom_json = os.environ.get("MODEL_REGISTRY", "")
        if custom_json.strip():
            try:
                raw_list = json.loads(custom_json)
                _model_registry = {}
                for item in raw_list:
                    cfg = ModelConfig.model_validate(item)
                    _model_registry[cfg.id] = cfg
            except Exception as e:
                logger.warning("MODEL_REGISTRY env var invalid (%s), using auto-detected", e)
                _model_registry = build_default_registry()
        else:
            _model_registry = build_default_registry()
    return _model_registry


def list_models() -> list[ModelConfig]:
    return [model for model in get_model_registry().values() if model.enabled]


def list_models_with_health() -> list[tuple[ModelConfig, object]]:
    return [(model, get_model_health(model)) for model in list_models()]


def reset_model_registry() -> None:
    global _model_registry
    _model_registry = None
