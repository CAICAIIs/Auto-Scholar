import json
import logging
import os
import time
from collections.abc import Callable, Coroutine
from contextvars import ContextVar
from typing import Any, TypeVar

import httpx
from dotenv import load_dotenv
from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    InternalServerError,
    RateLimitError,
)
from openai.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from backend.llm.execution import (
    build_execution_plan,
    execute_structured,
    mark_invocation_failure,
    mark_invocation_success,
)
from backend.llm.registry import (
    build_default_registry,
    detect_provider_from_url,
    infer_model_capabilities,
    list_models as list_registered_models,
    reset_model_registry,
)
from backend.llm.runtime import build_runtime_selection, resolve_model_config
from backend.llm.providers import resolve_api_key
from backend.constants import LLM_DEFAULT_MAX_TOKENS
from backend.evaluation.cost_tracker import record_llm_usage
from backend.schemas import ModelConfig, ModelProvider

_ = load_dotenv()

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

TokenCallback = Callable[[str], Coroutine[Any, Any, None]]
token_callback_var: ContextVar[TokenCallback | None] = ContextVar(
    "token_callback_var", default=None
)

LLM_TIMEOUT = httpx.Timeout(connect=60.0, read=120.0, write=60.0, pool=60.0)

_client_cache: dict[tuple[str, str], AsyncOpenAI] = {}


async def cleanup_llm_clients() -> None:
    if not _client_cache:
        return

    for cache_key, client in list(_client_cache.items()):
        try:
            await client.close()
            logger.info("Closed LLM client cache entry for base_url=%s", cache_key[0])
        except Exception as e:
            logger.warning("Failed to close LLM client cache entry %s: %s", cache_key[0], e)

    _client_cache.clear()
    logger.info("Cleared LLM client cache")


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
    return detect_provider_from_url(base_url)


def _infer_capabilities(provider: ModelProvider, model_name: str) -> dict[str, Any]:
    return infer_model_capabilities(provider, model_name)


def _build_default_registry() -> dict[str, ModelConfig]:
    return build_default_registry()


_model_registry: dict[str, ModelConfig] | None = None


def get_model_registry() -> dict[str, ModelConfig]:
    global _model_registry
    if _model_registry is None:
        reset_model_registry()
        from backend.llm.registry import get_model_registry as load_runtime_registry

        _model_registry = load_runtime_registry()
    return _model_registry


def list_models() -> list[ModelConfig]:
    return list_registered_models()


def resolve_model(model_id: str | None = None) -> tuple[AsyncOpenAI, str, bool]:
    registry = get_model_registry()
    cfg = resolve_model_config(model_registry=registry, model_id=model_id)
    if cfg is not None:
        api_key = resolve_api_key(cfg)
        client = _get_or_create_client(api_key, cfg.api_base)
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
    registry = get_model_registry()
    runtime_selection = build_runtime_selection(
        model_registry=registry,
        requested_model_id=model_id,
        task_type_value=task_type,
    )
    execution_plan = build_execution_plan(
        runtime_selection=runtime_selection,
        temperature=temperature,
        max_tokens=max_tokens,
        task_type=task_type,
    )

    return await execute_structured(
        execution_plan=execution_plan,
        response_model=response_model,
        messages=messages,
        schema_instruction=_build_schema_prompt(response_model),
        token_callback=token_callback_var.get(None),
        resolve_model=resolve_model,
        call_llm=_call_llm,
        call_llm_streaming=_call_llm_streaming,
        logger=logger,
    )
