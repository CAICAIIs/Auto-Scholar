import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from backend.schemas import ModelConfig

logger = logging.getLogger(__name__)

_ENV_VAR_PATTERN = re.compile(r"\$\{([^}:]+)(?::-(.*?))?\}")


def _substitute_env_vars(value: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        var_name = match.group(1)
        default = match.group(2)
        env_val = os.environ.get(var_name)
        if env_val is not None:
            return env_val
        return default if default is not None else ""

    return _ENV_VAR_PATTERN.sub(_replace, value)


def _substitute_recursive(obj: Any) -> Any:
    if isinstance(obj, str):
        return _substitute_env_vars(obj)
    if isinstance(obj, dict):
        return {k: _substitute_recursive(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_substitute_recursive(item) for item in obj]
    return obj


def load_model_config(config_path: str | None = None) -> dict[str, ModelConfig] | None:
    if not config_path:
        return None

    path = Path(config_path)
    if not path.is_file():
        logger.warning("Model config file not found: %s", config_path)
        return None

    try:
        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
    except (OSError, yaml.YAMLError) as e:
        logger.warning("Failed to load model config from %s: %s", config_path, e)
        return None

    if not isinstance(data, dict) or "models" not in data:
        logger.warning("Model config missing 'models' key: %s", config_path)
        return None

    raw_models = data["models"]
    if not isinstance(raw_models, list) or not raw_models:
        logger.warning("Model config 'models' is empty or not a list: %s", config_path)
        return None

    registry: dict[str, ModelConfig] = {}
    for i, entry in enumerate(raw_models):
        entry = _substitute_recursive(entry)
        try:
            cfg = ModelConfig.model_validate(entry)
            registry[cfg.id] = cfg
        except ValidationError as e:
            logger.warning("Skipping invalid model entry %d in %s: %s", i, config_path, e)
            continue

    if not registry:
        logger.warning("No valid models loaded from %s", config_path)
        return None

    logger.info("Loaded %d model(s) from YAML config: %s", len(registry), config_path)
    return registry
