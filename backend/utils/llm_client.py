import json
import logging
import os
import time
from collections.abc import Callable, Coroutine
from contextvars import ContextVar
from typing import Any, TypeVar

import httpx
import json_repair
from dotenv import load_dotenv
from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    InternalServerError,
    RateLimitError,
)
from openai.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel, ValidationError
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from backend.constants import LLM_DEFAULT_MAX_TOKENS, OLLAMA_BASE_URL
from backend.evaluation.cost_tracker import record_llm_usage
from backend.schemas import CostTier, ModelConfig, ModelProvider

load_dotenv()

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

TokenCallback = Callable[[str], Coroutine[Any, Any, None]]
token_callback_var: ContextVar[TokenCallback | None] = ContextVar(
    "token_callback_var", default=None
)

LLM_TIMEOUT = httpx.Timeout(connect=60.0, read=120.0, write=60.0, pool=60.0)

_client_cache: dict[tuple[str, str], AsyncOpenAI] = {}


def _get_or_create_client(api_key: str, base_url: str) -> AsyncOpenAI:
    cache_key = (base_url, api_key)
    if cache_key not in _client_cache:
        _client_cache[cache_key] = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=LLM_TIMEOUT,
        )
    return _client_cache[cache_key]


def get_client() -> AsyncOpenAI:
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        raise RuntimeError("LLM_API_KEY environment variable is required")
    base_url = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
    return _get_or_create_client(api_key, base_url)


def get_model() -> str:
    return os.environ.get("LLM_MODEL", "gpt-4o")


def _detect_provider_from_url(base_url: str) -> ModelProvider:
    url_lower = base_url.lower()
    if "openai.com" in url_lower:
        return ModelProvider.OPENAI
    if "deepseek.com" in url_lower:
        return ModelProvider.DEEPSEEK
    if "localhost" in url_lower or "127.0.0.1" in url_lower or "11434" in url_lower:
        return ModelProvider.OLLAMA
    return ModelProvider.CUSTOM


def _infer_capabilities(provider: ModelProvider, model_name: str) -> dict[str, Any]:
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


def _build_default_registry() -> dict[str, ModelConfig]:
    registry: dict[str, ModelConfig] = {}

    api_key = os.environ.get("LLM_API_KEY", "")
    base_url = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
    model_name = os.environ.get("LLM_MODEL", "gpt-4o")

    if api_key:
        provider = _detect_provider_from_url(base_url)
        model_id = f"{provider.value}:{model_name}"
        is_local = provider == ModelProvider.OLLAMA
        supports_json = provider != ModelProvider.OLLAMA
        caps = _infer_capabilities(provider, model_name)
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
            ds_caps = _infer_capabilities(ModelProvider.DEEPSEEK, ds_model)
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
        for m in ollama_models_str.split(","):
            m = m.strip()
            if not m:
                continue
            oid = f"ollama:{m}"
            ollama_caps = _infer_capabilities(ModelProvider.OLLAMA, m)
            registry[oid] = ModelConfig(
                id=oid,
                provider=ModelProvider.OLLAMA,
                model_name=m,
                display_name=f"{m} (Ollama, local)",
                api_base=OLLAMA_BASE_URL,
                api_key_env="",
                supports_json_mode=False,
                supports_structured_output=False,
                max_output_tokens=4096,
                is_local=True,
                **ollama_caps,
            )

    return registry


_model_registry: dict[str, ModelConfig] | None = None


def get_model_registry() -> dict[str, ModelConfig]:
    global _model_registry
    if _model_registry is None:
        from backend.config.loader import load_model_config

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
            except (json.JSONDecodeError, ValidationError) as e:
                logger.warning("MODEL_REGISTRY env var invalid (%s), using auto-detected", e)
                _model_registry = _build_default_registry()
        else:
            _model_registry = _build_default_registry()
    return _model_registry


def list_models() -> list[ModelConfig]:
    return [m for m in get_model_registry().values() if m.enabled]


def resolve_model(model_id: str | None = None) -> tuple[AsyncOpenAI, str, bool]:
    registry = get_model_registry()

    if model_id and model_id in registry:
        cfg = registry[model_id]
        api_key = os.environ.get(cfg.api_key_env, "") if cfg.api_key_env else "ollama"
        if not api_key and cfg.provider != ModelProvider.OLLAMA:
            logger.warning(
                "No API key for model %s (env: %s), falling back to default",
                model_id,
                cfg.api_key_env,
            )
        else:
            client = _get_or_create_client(api_key or "ollama", cfg.api_base)
            return client, cfg.model_name, cfg.supports_json_mode

    return get_client(), get_model(), True


def _build_schema_prompt(response_model: type[BaseModel]) -> str:
    schema = response_model.model_json_schema()
    defs = schema.pop("$defs", {})
    for key in ("title", "description", "$schema"):
        schema.pop(key, None)
    for prop in schema.get("properties", {}).values():
        prop.pop("title", None)
        prop.pop("description", None)

    required_fields = schema.get("required", [])
    properties = schema.get("properties", {})

    def _resolve_type(prop_schema: dict[str, Any]) -> str:
        if "$ref" in prop_schema:
            ref_name = prop_schema["$ref"].split("/")[-1]
            ref_def = defs.get(ref_name, {})
            ref_props = ref_def.get("properties", {})
            ref_required = ref_def.get("required", [])
            if ref_props:
                inner_fields = [f'"{k}"' for k in ref_required]
                return f"object with fields: {', '.join(inner_fields)}"
            return ref_name
        if prop_schema.get("type") == "array":
            items = prop_schema.get("items", {})
            item_type = _resolve_type(items)
            return f"array of {item_type}"
        return prop_schema.get("type", "unknown")

    field_descriptions: list[str] = []
    for field_name in required_fields:
        prop_schema = properties.get(field_name, {})
        field_type = _resolve_type(prop_schema)
        field_descriptions.append(f'  "{field_name}": <{field_type}>')

    example_structure = "{\n" + ",\n".join(field_descriptions) + "\n}"

    nested_hints: list[str] = []
    for def_name, def_schema in defs.items():
        def_required = def_schema.get("required", [])
        if def_required:
            nested_hints.append(f"{def_name}: use fields {def_required}")

    nested_info = ""
    if nested_hints:
        nested_info = f"\nNested object fields: {'; '.join(nested_hints)}"

    return (
        f"RESPONSE FORMAT: Return a JSON object with YOUR ACTUAL CONTENT.\n"
        f"Required fields: {required_fields}\n"
        f"Structure:\n{example_structure}{nested_info}\n"
        f"IMPORTANT: Fill in actual values, NOT the schema definition."
    )


@retry(
    wait=wait_random_exponential(min=1, max=30),
    stop=stop_after_attempt(4),
    retry=retry_if_exception_type(
        (
            httpx.TimeoutException,
            httpx.ConnectError,
            RateLimitError,
            APIConnectionError,
            APITimeoutError,
            InternalServerError,
        )
    ),
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
async def _call_llm(
    client: AsyncOpenAI,
    augmented_messages: list[dict[str, Any]],
    temperature: float,
    max_tokens: int | None,
    model_name: str | None = None,
    use_json_mode: bool = True,
    task_type: str = "",
) -> str:
    effective_model = model_name or get_model()
    effective_max_tokens = max_tokens or LLM_DEFAULT_MAX_TOKENS
    logger.info(
        "LLM request starting (model=%s, max_tokens=%s)", effective_model, effective_max_tokens
    )
    start_time = time.perf_counter()
    try:
        kwargs: dict[str, Any] = {
            "model": effective_model,
            "messages": augmented_messages,
            "temperature": temperature,
            "max_tokens": effective_max_tokens,
        }
        if use_json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        completion = await client.chat.completions.create(**kwargs)  # type: ignore[call-overload]
        elapsed = time.perf_counter() - start_time
        logger.info("LLM request completed in %.2fs", elapsed)

        if completion.usage:
            record_llm_usage(
                prompt_tokens=completion.usage.prompt_tokens,
                completion_tokens=completion.usage.completion_tokens,
                model=effective_model,
                task_type=task_type,
            )

        raw_content = completion.choices[0].message.content
        if not raw_content:
            raise ValueError("LLM returned empty response")
        return raw_content
    except Exception as e:
        elapsed = time.perf_counter() - start_time
        logger.error("LLM request failed after %.2fs: %s: %s", elapsed, type(e).__name__, e)
        raise


async def _call_llm_streaming(
    client: AsyncOpenAI,
    augmented_messages: list[dict[str, Any]],
    temperature: float,
    max_tokens: int | None,
    on_token: TokenCallback,
    model_name: str | None = None,
    use_json_mode: bool = True,
    task_type: str = "",
) -> str:
    effective_model = model_name or get_model()
    effective_max_tokens = max_tokens or LLM_DEFAULT_MAX_TOKENS
    logger.info(
        "LLM streaming request starting (model=%s, max_tokens=%s)",
        effective_model,
        effective_max_tokens,
    )
    start_time = time.perf_counter()
    try:
        kwargs: dict[str, Any] = {
            "model": effective_model,
            "messages": augmented_messages,
            "temperature": temperature,
            "max_tokens": effective_max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if use_json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        chunks: list[str] = []
        prompt_tokens = 0
        completion_tokens = 0

        stream = await client.chat.completions.create(**kwargs)  # type: ignore[call-overload]
        async for chunk in stream:
            if chunk.usage:
                prompt_tokens = chunk.usage.prompt_tokens
                completion_tokens = chunk.usage.completion_tokens
            if chunk.choices and chunk.choices[0].delta.content:
                token = chunk.choices[0].delta.content
                chunks.append(token)
                await on_token(token)

        elapsed = time.perf_counter() - start_time
        logger.info("LLM streaming request completed in %.2fs", elapsed)

        if prompt_tokens or completion_tokens:
            record_llm_usage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                model=effective_model,
                task_type=task_type,
            )

        raw_content = "".join(chunks)
        if not raw_content:
            raise ValueError("LLM returned empty response")
        return raw_content
    except Exception as e:
        elapsed = time.perf_counter() - start_time
        logger.error(
            "LLM streaming request failed after %.2fs: %s: %s", elapsed, type(e).__name__, e
        )
        raise


async def structured_completion(
    messages: list[ChatCompletionMessageParam],
    response_model: type[T],
    temperature: float = 0.3,
    max_tokens: int | None = None,
    model_id: str | None = None,
    task_type: str | None = None,
) -> T:
    effective_model_id = model_id
    if not effective_model_id and task_type:
        from backend.llm.router import select_model
        from backend.llm.task_types import TaskType

        try:
            tt = TaskType(task_type)
            registry = get_model_registry()
            effective_model_id = select_model(tt, registry, override_model_id=model_id)
        except (ValueError, KeyError):
            logger.warning("Unknown task_type=%s, using default model", task_type)

    client, model_name, supports_json_mode = resolve_model(effective_model_id)
    schema_instruction = _build_schema_prompt(response_model)

    augmented_messages: list[dict[str, Any]] = []
    for msg in messages:
        m = dict(msg) if isinstance(msg, dict) else {"role": "user", "content": str(msg)}
        if m.get("role") == "system":
            m["content"] = f"{m['content']}\n\n{schema_instruction}"
            augmented_messages.append(m)
        else:
            augmented_messages.append(m)

    if not any(m.get("role") == "system" for m in augmented_messages):
        augmented_messages.insert(0, {"role": "system", "content": schema_instruction})

    on_token = token_callback_var.get(None)
    if on_token is not None:
        raw_content = await _call_llm_streaming(
            client,
            augmented_messages,
            temperature,
            max_tokens,
            on_token=on_token,
            model_name=model_name,
            use_json_mode=supports_json_mode,
            task_type=task_type or "",
        )
    else:
        raw_content = await _call_llm(
            client,
            augmented_messages,
            temperature,
            max_tokens,
            model_name=model_name,
            use_json_mode=supports_json_mode,
            task_type=task_type or "",
        )

    try:
        parsed_json = json.loads(raw_content)
    except json.JSONDecodeError as e:
        logger.warning("json.loads failed (%s), attempting json_repair...", e)
        try:
            parsed_json = json_repair.loads(raw_content)
            if not isinstance(parsed_json, dict):
                raise ValueError(
                    f"json_repair produced {type(parsed_json).__name__}, expected dict"
                )
            logger.info("json_repair succeeded, recovered valid JSON")
        except Exception:
            truncated_hint = ""
            if "Unterminated" in str(e) or raw_content.rstrip()[-1] not in "]}":
                truncated_hint = (
                    " (output likely truncated - try reducing paper count or increasing max_tokens)"
                )
            logger.error(
                "LLM returned invalid JSON: %s%s\nRaw (last 500 chars): ...%s",
                e,
                truncated_hint,
                raw_content[-500:],
            )
            raise ValueError(f"LLM 返回无效 JSON{truncated_hint}: {e}") from e

    schema_keys = {"properties", "type", "required", "$schema", "$defs"}
    actual_keys = set(parsed_json.keys()) - schema_keys

    if "properties" in parsed_json and not actual_keys:
        logger.error(
            "LLM returned schema definition instead of content. Raw: %s",
            raw_content[:500],
        )
        raise ValueError(
            "LLM returned the JSON schema instead of actual content. "
            "This is a model behavior issue - the prompt may need adjustment."
        )

    if "properties" in parsed_json and actual_keys:
        logger.warning(
            "LLM mixed schema with content. Extracting actual data from keys: %s",
            actual_keys,
        )
        parsed_json = {k: v for k, v in parsed_json.items() if k not in schema_keys}

    try:
        return response_model.model_validate(parsed_json)
    except ValidationError as e:
        logger.error("LLM output failed validation: %s\nRaw: %s", e, raw_content[:500])
        raise ValueError(f"LLM output does not match {response_model.__name__}: {e}") from e
