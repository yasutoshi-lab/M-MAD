"""utils/config.py の純粋関数（L1）ユニットテスト。"""


class TestGetLlmConfig:
    """get_llm_config のテスト（CF-1..5）。clean_env で .env/環境変数から隔離する。"""

    def test_default_openai(self, clean_env):
        cfg = clean_env.get_llm_config()
        assert cfg["provider"] == "openai"
        assert cfg["model"] == "gpt-4o-mini"
        assert cfg["base_url"] is None

    def test_gemini(self, clean_env, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "gemini")
        monkeypatch.setenv("GEMINI_API_KEY", "k")
        cfg = clean_env.get_llm_config()
        assert cfg["provider"] == "gemini"
        assert cfg["model"] == "gemini-3.5-flash"
        assert "generativelanguage.googleapis.com" in cfg["base_url"]
        assert cfg["api_key"] == "k"

    def test_anthropic(self, clean_env, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "anthropic")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
        cfg = clean_env.get_llm_config()
        assert cfg["provider"] == "anthropic"
        assert cfg["model"] == "claude-haiku-4-5"
        assert cfg["base_url"] == "https://api.anthropic.com/v1/"
        assert cfg["api_key"] == "k"

    def test_anthropic_model_override(self, clean_env, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "anthropic")
        monkeypatch.setenv("LLM_MODEL", "claude-opus-4-8")
        assert clean_env.get_llm_config()["model"] == "claude-opus-4-8"

    def test_vertex(self, clean_env, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "vertex")
        monkeypatch.setenv("GCP_PROJECT", "p")
        cfg = clean_env.get_llm_config()
        assert cfg["provider"] == "vertex"
        assert cfg["model"] == "google/gemini-3.5-flash"
        assert "aiplatform.googleapis.com" in cfg["base_url"]
        assert "projects/p/locations/global" in cfg["base_url"]
        assert cfg["api_key"] is None

    def test_vertex_model_not_double_prefixed(self, clean_env, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "vertex")
        monkeypatch.setenv("GCP_PROJECT", "p")
        monkeypatch.setenv("LLM_MODEL", "google/x")
        assert clean_env.get_llm_config()["model"] == "google/x"

    def test_model_override_openai(self, clean_env, monkeypatch):
        monkeypatch.setenv("LLM_MODEL", "foo")
        assert clean_env.get_llm_config()["model"] == "foo"


class TestVertexBaseUrl:
    """_vertex_base_url のテスト（CF-6/7）。"""

    def test_global(self, clean_env):
        url = clean_env._vertex_base_url("p", "global")
        assert url == "https://aiplatform.googleapis.com/v1/projects/p/locations/global/endpoints/openapi"

    def test_regional_host(self, clean_env):
        url = clean_env._vertex_base_url("p", "us-central1")
        assert url.startswith("https://us-central1-aiplatform.googleapis.com/")


class TestBuildOpenaiClient:
    """build_openai_client のテスト（CF-8/9）。"""

    def test_vertex_uses_adc_token_and_endpoint(self, clean_env, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "vertex")
        monkeypatch.setenv("GCP_PROJECT", "p")
        monkeypatch.setattr(clean_env, "_vertex_access_token", lambda: "tok")
        client, model = clean_env.build_openai_client()
        assert model == "google/gemini-3.5-flash"
        assert "aiplatform.googleapis.com" in str(client.base_url)

    def test_openai_with_fallback_key(self, clean_env):
        client, model = clean_env.build_openai_client(fallback_api_key="k")
        assert model == "gpt-4o-mini"
        assert "api.openai.com" in str(client.base_url)
