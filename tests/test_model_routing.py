import os
from unittest.mock import patch

from backend.schemas import ModelConfig, ModelProvider
from backend.utils.llm_client import (
    _build_default_registry,
    _detect_provider_from_url,
    _get_or_create_client,
    get_model_registry,
    list_models,
    resolve_model,
)


class TestDetectProvider:
    def test_openai_url(self):
        assert _detect_provider_from_url("https://api.openai.com/v1") == ModelProvider.OPENAI

    def test_deepseek_url(self):
        assert _detect_provider_from_url("https://api.deepseek.com/v1") == ModelProvider.DEEPSEEK

    def test_ollama_localhost(self):
        assert _detect_provider_from_url("http://localhost:11434/v1") == ModelProvider.OLLAMA

    def test_ollama_127(self):
        assert _detect_provider_from_url("http://127.0.0.1:11434/v1") == ModelProvider.OLLAMA

    def test_custom_url(self):
        assert _detect_provider_from_url("https://my-proxy.example.com/v1") == ModelProvider.CUSTOM


class TestBuildDefaultRegistry:
    @patch.dict(
        os.environ,
        {
            "LLM_API_KEY": "test-key",
            "LLM_BASE_URL": "https://api.openai.com/v1",
            "LLM_MODEL": "gpt-4o",
        },
        clear=False,
    )
    def test_default_openai_entry(self):
        registry = _build_default_registry()
        assert "openai:gpt-4o" in registry
        cfg = registry["openai:gpt-4o"]
        assert cfg.provider == ModelProvider.OPENAI
        assert cfg.model_name == "gpt-4o"
        assert cfg.supports_json_mode is True
        assert cfg.is_local is False

    @patch.dict(
        os.environ,
        {
            "LLM_API_KEY": "test-key",
            "LLM_BASE_URL": "http://localhost:11434/v1",
            "LLM_MODEL": "llama3.1:8b",
        },
        clear=False,
    )
    def test_ollama_detected_from_base_url(self):
        registry = _build_default_registry()
        assert "ollama:llama3.1:8b" in registry
        cfg = registry["ollama:llama3.1:8b"]
        assert cfg.provider == ModelProvider.OLLAMA
        assert cfg.supports_json_mode is False
        assert cfg.is_local is True

    @patch.dict(
        os.environ,
        {
            "LLM_API_KEY": "test-key",
            "LLM_BASE_URL": "https://api.openai.com/v1",
            "LLM_MODEL": "gpt-4o",
            "DEEPSEEK_API_KEY": "ds-key",
            "DEEPSEEK_MODEL": "deepseek-chat",
        },
        clear=False,
    )
    def test_deepseek_added_when_key_present(self):
        registry = _build_default_registry()
        assert "openai:gpt-4o" in registry
        assert "deepseek:deepseek-chat" in registry
        ds = registry["deepseek:deepseek-chat"]
        assert ds.provider == ModelProvider.DEEPSEEK
        assert ds.api_key_env == "DEEPSEEK_API_KEY"

    @patch.dict(
        os.environ,
        {
            "LLM_API_KEY": "test-key",
            "LLM_BASE_URL": "https://api.openai.com/v1",
            "LLM_MODEL": "gpt-4o",
            "OLLAMA_MODELS": "llama3.1:8b,mistral:7b",
        },
        clear=False,
    )
    def test_ollama_models_from_env(self):
        registry = _build_default_registry()
        assert "ollama:llama3.1:8b" in registry
        assert "ollama:mistral:7b" in registry
        for oid in ("ollama:llama3.1:8b", "ollama:mistral:7b"):
            cfg = registry[oid]
            assert cfg.is_local is True
            assert cfg.supports_json_mode is False

    @patch.dict(
        os.environ,
        {"LLM_API_KEY": "", "LLM_BASE_URL": "https://api.openai.com/v1", "LLM_MODEL": "gpt-4o"},
        clear=False,
    )
    def test_no_api_key_empty_registry(self):
        registry = _build_default_registry()
        assert len(registry) == 0


class TestResolveModel:
    @patch.dict(
        os.environ,
        {
            "LLM_API_KEY": "test-key",
            "LLM_BASE_URL": "https://api.openai.com/v1",
            "LLM_MODEL": "gpt-4o",
        },
        clear=False,
    )
    def test_none_model_id_returns_default(self):
        import backend.utils.llm_client as mod

        mod._model_registry = None
        mod._client_cache.clear()
        client, model_name, supports_json = resolve_model(None)
        assert model_name == "gpt-4o"
        assert supports_json is True

    @patch.dict(
        os.environ,
        {
            "LLM_API_KEY": "test-key",
            "LLM_BASE_URL": "https://api.openai.com/v1",
            "LLM_MODEL": "gpt-4o",
        },
        clear=False,
    )
    def test_unknown_model_id_falls_back(self):
        import backend.utils.llm_client as mod

        mod._model_registry = None
        mod._client_cache.clear()
        client, model_name, supports_json = resolve_model("nonexistent:model")
        assert model_name == "gpt-4o"

    @patch.dict(
        os.environ,
        {
            "LLM_API_KEY": "test-key",
            "LLM_BASE_URL": "https://api.openai.com/v1",
            "LLM_MODEL": "gpt-4o",
            "OLLAMA_MODELS": "llama3.1:8b",
        },
        clear=False,
    )
    def test_resolve_ollama_model(self):
        import backend.utils.llm_client as mod

        mod._model_registry = None
        mod._client_cache.clear()
        client, model_name, supports_json = resolve_model("ollama:llama3.1:8b")
        assert model_name == "llama3.1:8b"
        assert supports_json is False


class TestListModels:
    @patch.dict(
        os.environ,
        {
            "LLM_API_KEY": "test-key",
            "LLM_BASE_URL": "https://api.openai.com/v1",
            "LLM_MODEL": "gpt-4o",
        },
        clear=False,
    )
    def test_list_returns_enabled_models(self):
        import backend.utils.llm_client as mod

        mod._model_registry = None
        models = list_models()
        assert len(models) >= 1
        assert all(isinstance(m, ModelConfig) for m in models)
        assert all(m.enabled for m in models)


class TestClientCache:
    def test_same_params_return_same_client(self):
        import backend.utils.llm_client as mod

        mod._client_cache.clear()
        c1 = _get_or_create_client("key1", "https://api.openai.com/v1")
        c2 = _get_or_create_client("key1", "https://api.openai.com/v1")
        assert c1 is c2

    def test_different_params_return_different_clients(self):
        import backend.utils.llm_client as mod

        mod._client_cache.clear()
        c1 = _get_or_create_client("key1", "https://api.openai.com/v1")
        c2 = _get_or_create_client("key2", "http://localhost:11434/v1")
        assert c1 is not c2


class TestGetModelRegistry:
    @patch.dict(
        os.environ,
        {
            "LLM_API_KEY": "test-key",
            "LLM_BASE_URL": "https://api.openai.com/v1",
            "LLM_MODEL": "gpt-4o",
            "MODEL_REGISTRY": "",
        },
        clear=False,
    )
    def test_empty_registry_env_uses_auto_detect(self):
        import backend.utils.llm_client as mod

        mod._model_registry = None
        registry = get_model_registry()
        assert "openai:gpt-4o" in registry

    @patch.dict(
        os.environ,
        {
            "LLM_API_KEY": "test-key",
            "MODEL_REGISTRY": "not valid json",
        },
        clear=False,
    )
    def test_invalid_registry_json_falls_back(self):
        import backend.utils.llm_client as mod

        mod._model_registry = None
        registry = get_model_registry()
        assert isinstance(registry, dict)
