from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, TypeVar

import json_repair
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel, ValidationError

from backend.llm.health import record_model_failure, record_model_success
from backend.llm.runtime import RuntimeSelection

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class ExecutionPlan:
    runtime_selection: RuntimeSelection
    resolution_order: list[str | None]
    temperature: float
    max_tokens: int | None
    task_type: str | None
    policy: "ExecutionPolicy"


@dataclass(frozen=True)
class ResolvedInvocation:
    client: AsyncOpenAI
    model_name: str
    supports_json_mode: bool
    candidate_model_id: str | None


class ExecutionPolicy(StrEnum):
    ALLOW_FALLBACK = "allow_fallback"
    SINGLE_MODEL_ONLY = "single_model_only"


TASK_EXECUTION_POLICY: dict[str, ExecutionPolicy] = {
    "planning": ExecutionPolicy.ALLOW_FALLBACK,
    "extraction": ExecutionPolicy.ALLOW_FALLBACK,
    "writing": ExecutionPolicy.ALLOW_FALLBACK,
    "qa": ExecutionPolicy.ALLOW_FALLBACK,
    "reflection": ExecutionPolicy.ALLOW_FALLBACK,
}


@dataclass(frozen=True)
class RuntimeTelemetryEvent:
    task_type: str | None
    requested_model_id: str | None
    selected_model_id: str | None
    candidate_model_id: str | None
    attempt_number: int
    fallback_chain: list[str]
    success: bool
    latency_ms: float
    error_type: str | None = None


def build_execution_plan(
    *,
    runtime_selection: RuntimeSelection,
    temperature: float,
    max_tokens: int | None,
    task_type: str | None,
) -> ExecutionPlan:
    raw_resolution_order = runtime_selection.fallback_chain or [runtime_selection.selected_model_id]
    resolution_order: list[str | None] = (
        list(raw_resolution_order) if raw_resolution_order else [None]
    )

    return ExecutionPlan(
        runtime_selection=runtime_selection,
        resolution_order=resolution_order,
        temperature=temperature,
        max_tokens=max_tokens,
        task_type=task_type,
        policy=TASK_EXECUTION_POLICY.get(task_type or "", ExecutionPolicy.ALLOW_FALLBACK),
    )


def can_retry_with_fallback(plan: ExecutionPlan) -> bool:
    return plan.policy == ExecutionPolicy.ALLOW_FALLBACK and len(plan.resolution_order) > 1


def mark_invocation_success(candidate_model_id: str | None) -> None:
    if candidate_model_id is not None:
        record_model_success(candidate_model_id)


def mark_invocation_failure(candidate_model_id: str | None) -> None:
    if candidate_model_id is not None:
        record_model_failure(candidate_model_id)


def create_runtime_telemetry_event(
    *,
    plan: ExecutionPlan,
    candidate_model_id: str | None,
    attempt_number: int,
    success: bool,
    latency_ms: float,
    error_type: str | None = None,
) -> RuntimeTelemetryEvent:
    return RuntimeTelemetryEvent(
        task_type=plan.task_type,
        requested_model_id=plan.runtime_selection.requested_model_id,
        selected_model_id=plan.runtime_selection.selected_model_id,
        candidate_model_id=candidate_model_id,
        attempt_number=attempt_number,
        fallback_chain=plan.runtime_selection.fallback_chain,
        success=success,
        latency_ms=latency_ms,
        error_type=error_type,
    )


async def execute_structured(
    *,
    execution_plan: ExecutionPlan,
    response_model: type[T],
    messages: list[ChatCompletionMessageParam],
    schema_instruction: str,
    token_callback: Any,
    resolve_model: Any,
    call_llm: Any,
    call_llm_streaming: Any,
    logger: logging.Logger,
) -> T:
    augmented_messages: list[dict[str, Any]] = []
    for msg in messages:
        message = dict(msg) if isinstance(msg, dict) else {"role": "user", "content": str(msg)}
        if message.get("role") == "system":
            message["content"] = f"{message['content']}\n\n{schema_instruction}"
        augmented_messages.append(message)

    if not any(message.get("role") == "system" for message in augmented_messages):
        augmented_messages.insert(0, {"role": "system", "content": schema_instruction})

    last_error: Exception | None = None
    raw_content = ""

    for attempt_number, candidate_model_id in enumerate(execution_plan.resolution_order, 1):
        client, model_name, supports_json_mode = resolve_model(candidate_model_id)
        started_at = time.perf_counter()
        try:
            if token_callback is not None:
                raw_content = await call_llm_streaming(
                    client,
                    augmented_messages,
                    execution_plan.temperature,
                    execution_plan.max_tokens,
                    on_token=token_callback,
                    model_name=model_name,
                    use_json_mode=supports_json_mode,
                    task_type=execution_plan.task_type or "",
                )
            else:
                raw_content = await call_llm(
                    client,
                    augmented_messages,
                    execution_plan.temperature,
                    execution_plan.max_tokens,
                    model_name=model_name,
                    use_json_mode=supports_json_mode,
                    task_type=execution_plan.task_type or "",
                )
            mark_invocation_success(candidate_model_id)
            logger.info(
                "Runtime invocation success",
                extra={
                    "extra_data": create_runtime_telemetry_event(
                        plan=execution_plan,
                        candidate_model_id=candidate_model_id,
                        attempt_number=attempt_number,
                        success=True,
                        latency_ms=(time.perf_counter() - started_at) * 1000,
                    ).__dict__
                },
            )
            break
        except Exception as exc:
            mark_invocation_failure(candidate_model_id)
            last_error = exc
            logger.warning(
                "Runtime invocation failed",
                extra={
                    "extra_data": create_runtime_telemetry_event(
                        plan=execution_plan,
                        candidate_model_id=candidate_model_id,
                        attempt_number=attempt_number,
                        success=False,
                        latency_ms=(time.perf_counter() - started_at) * 1000,
                        error_type=type(exc).__name__,
                    ).__dict__
                },
            )
            if candidate_model_id == execution_plan.resolution_order[
                -1
            ] or not can_retry_with_fallback(execution_plan):
                raise

    if not raw_content and last_error is not None:
        raise last_error

    return parse_structured_response(raw_content, response_model)


def parse_structured_response(raw_content: str, response_model: type[T]) -> T:
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
            if raw_content and ("Unterminated" in str(e) or raw_content.rstrip()[-1] not in "]}"):
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

    if not isinstance(parsed_json, dict):
        raise ValueError(
            f"LLM returned {type(parsed_json).__name__} instead of object for {response_model.__name__}"
        )

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
