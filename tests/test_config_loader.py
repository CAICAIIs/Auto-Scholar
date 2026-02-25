import os
from pathlib import Path

import pytest

import backend.utils.llm_client as llm_client_module
from backend.config.loader import _substitute_env_vars, load_model_config
from backend.schemas import CostTier, ModelProvider


class TestSubstituteEnvVars:
    def test_basic(self, monkeypatch):
        monkeypatch.setenv("HOME", "/users/test")
        assert _substitute_env_vars("${HOME}") == "/users/test"

    def test_with_default(self):
        result = _substitute_env_vars("${NONEXISTENT_VAR_12345:-fallback}")
        assert result == "fallback"

    def test_missing_no_default(self):
        key = "TOTALLY_MISSING_VAR_99999"
        assert os.environ.get(key) is None
        assert _substitute_env_vars(f"${{{key}}}") == ""

    def test_no_substitution(self):
        assert _substitute_env_vars("plain string") == "plain string"

    def test_multiple_vars(self, monkeypatch):
        monkeypatch.setenv("A_VAR", "hello")
        monkeypatch.setenv("B_VAR", "world")
        assert _substitute_env_vars("${A_VAR} ${B_VAR}") == "hello world"

    def test_env_var_overrides_default(self, monkeypatch):
        monkeypatch.setenv("MY_VAR", "real")
        assert _substitute_env_vars("${MY_VAR:-default}") == "real"

    def test_embedded_in_url(self, monkeypatch):
        monkeypatch.setenv("API_HOST", "api.example.com")
        result = _substitute_env_vars("https://${API_HOST}/v1")
        assert result == "https://api.example.com/v1"


VALID_YAML = """\
models:
  - id: "test:model-a"
    provider: "openai"
    model_name: "model-a"
    display_name: "Model A"
    api_base: "https://api.openai.com/v1"
    api_key_env: "LLM_API_KEY"
    supports_json_mode: true
    supports_structured_output: true
    max_output_tokens: 8192
    is_local: false
    max_context_tokens: 128000
    supports_long_context: true
    cost_tier: 3
    reasoning_score: 8
    creativity_score: 8
    latency_score: 6
"""


class TestLoadModelConfig:
    def test_load_valid_yaml(self, tmp_path):
        cfg_file = tmp_path / "models.yaml"
        cfg_file.write_text(VALID_YAML)
        result = load_model_config(str(cfg_file))
        assert result is not None
        assert "test:model-a" in result
        cfg = result["test:model-a"]
        assert cfg.provider == ModelProvider.OPENAI
        assert cfg.model_name == "model-a"
        assert cfg.cost_tier == CostTier.HIGH

    def test_env_substitution(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TEST_BASE_URL", "https://custom.api.com/v1")
        yaml_content = """\
models:
  - id: "test:sub"
    provider: "custom"
    model_name: "sub-model"
    display_name: "Sub Model"
    api_base: "${TEST_BASE_URL}"
    api_key_env: "LLM_API_KEY"
    cost_tier: 1
    reasoning_score: 5
    creativity_score: 5
    latency_score: 5
"""
        cfg_file = tmp_path / "models.yaml"
        cfg_file.write_text(yaml_content)
        result = load_model_config(str(cfg_file))
        assert result is not None
        assert result["test:sub"].api_base == "https://custom.api.com/v1"

    def test_missing_file(self):
        result = load_model_config("/nonexistent/path/models.yaml")
        assert result is None

    def test_none_path(self):
        result = load_model_config(None)
        assert result is None

    def test_empty_path(self):
        result = load_model_config("")
        assert result is None

    def test_invalid_yaml(self, tmp_path):
        cfg_file = tmp_path / "bad.yaml"
        cfg_file.write_text("{{{{not yaml at all::::")
        result = load_model_config(str(cfg_file))
        assert result is None

    def test_missing_models_key(self, tmp_path):
        cfg_file = tmp_path / "no_models.yaml"
        cfg_file.write_text("something_else:\n  - foo: bar\n")
        result = load_model_config(str(cfg_file))
        assert result is None

    def test_empty_models_list(self, tmp_path):
        cfg_file = tmp_path / "empty.yaml"
        cfg_file.write_text("models: []\n")
        result = load_model_config(str(cfg_file))
        assert result is None

    def test_invalid_entry_skipped(self, tmp_path):
        yaml_content = """\
models:
  - id: "test:valid"
    provider: "openai"
    model_name: "valid-model"
    display_name: "Valid"
    api_base: "https://api.openai.com/v1"
    cost_tier: 3
    reasoning_score: 8
    creativity_score: 8
    latency_score: 6
  - id: "test:bad"
    provider: "not_a_real_provider"
    model_name: "bad"
    reasoning_score: 999
"""
        cfg_file = tmp_path / "mixed.yaml"
        cfg_file.write_text(yaml_content)
        result = load_model_config(str(cfg_file))
        assert result is not None
        assert "test:valid" in result
        assert "test:bad" not in result

    def test_all_entries_invalid(self, tmp_path):
        yaml_content = """\
models:
  - id: "bad1"
    provider: "fake_provider"
    reasoning_score: 999
  - id: "bad2"
    provider: "another_fake"
    reasoning_score: -5
"""
        cfg_file = tmp_path / "all_bad.yaml"
        cfg_file.write_text(yaml_content)
        result = load_model_config(str(cfg_file))
        assert result is None


class TestRegistryYamlPriority:
    def setup_method(self):
        llm_client_module._model_registry = None

    def teardown_method(self):
        llm_client_module._model_registry = None

    def test_yaml_takes_priority(self, tmp_path, monkeypatch):
        cfg_file = tmp_path / "models.yaml"
        cfg_file.write_text(VALID_YAML)
        monkeypatch.setenv("MODEL_CONFIG_PATH", str(cfg_file))
        monkeypatch.setenv("LLM_API_KEY", "test-key")

        registry = llm_client_module.get_model_registry()
        assert "test:model-a" in registry

    def test_fallback_when_no_yaml(self, monkeypatch):
        monkeypatch.setenv("MODEL_CONFIG_PATH", "")
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
        monkeypatch.setenv("LLM_MODEL", "gpt-4o")

        registry = llm_client_module.get_model_registry()
        assert "test:model-a" not in registry
        assert len(registry) >= 1
