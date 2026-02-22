import json
import logging
import os
import time
from typing import Any, TypeVar

import httpx
from dotenv import load_dotenv
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel, ValidationError
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from backend.evaluation.cost_tracker import record_llm_usage

load_dotenv()

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_client: AsyncOpenAI | None = None

# LLM request timeout: 60s for connection, 120s total (allows for slow responses)
LLM_TIMEOUT = httpx.Timeout(connect=60.0, read=120.0, write=60.0, pool=60.0)


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        api_key = os.environ.get("LLM_API_KEY")
        if not api_key:
            raise RuntimeError("LLM_API_KEY environment variable is required")
        _client = AsyncOpenAI(
            api_key=api_key,
            base_url=os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1"),
            timeout=LLM_TIMEOUT,
        )
    return _client


def get_model() -> str:
    return os.environ.get("LLM_MODEL", "gpt-4o")


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
    wait=wait_exponential(multiplier=1, min=2, max=15),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
async def _call_llm(
    client: AsyncOpenAI,
    augmented_messages: list[dict[str, Any]],
    temperature: float,
    max_tokens: int | None,
) -> str:
    model = get_model()
    logger.info("LLM request starting (model=%s, max_tokens=%s)", model, max_tokens)
    start_time = time.perf_counter()
    try:
        completion = await client.chat.completions.create(  # type: ignore[call-overload]
            model=model,
            messages=augmented_messages,
            response_format={"type": "json_object"},
            temperature=temperature,
            max_tokens=max_tokens,
        )
        elapsed = time.perf_counter() - start_time
        logger.info("LLM request completed in %.2fs", elapsed)

        if completion.usage:
            record_llm_usage(
                prompt_tokens=completion.usage.prompt_tokens,
                completion_tokens=completion.usage.completion_tokens,
                model=model,
            )

        raw_content = completion.choices[0].message.content
        if not raw_content:
            raise ValueError("LLM returned empty response")
        return raw_content
    except Exception as e:
        elapsed = time.perf_counter() - start_time
        logger.error("LLM request failed after %.2fs: %s: %s", elapsed, type(e).__name__, e)
        raise


async def structured_completion(
    messages: list[ChatCompletionMessageParam],
    response_model: type[T],
    temperature: float = 0.3,
    max_tokens: int | None = None,
) -> T:
    client = get_client()
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

    raw_content = await _call_llm(client, augmented_messages, temperature, max_tokens)

    try:
        parsed_json = json.loads(raw_content)
    except json.JSONDecodeError as e:
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
