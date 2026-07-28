"""run_jury.py の純粋関数（L1）ユニットテスト（Issue #55）。"""

import run_jury


class TestJuryOutputDirs:
    """jury_output_dirs のテスト（RJ-DIR）。"""

    def test_naming_convention(self):
        stage1_dir, stage2_dir = run_jury.jury_output_dirs("ja-en", "manualX", "openai")
        assert stage1_dir.endswith("data/output_ja-en_manualX_openai")
        assert stage2_dir.endswith("data/stage2_3_ja-en_manualX_openai")

    def test_providers_get_distinct_dirs(self):
        dirs = {run_jury.jury_output_dirs("ja-en", "m", p) for p in ("openai", "anthropic", "vertex")}
        assert len(dirs) == 3


class TestBuildProviderEnv:
    """build_provider_env のテスト（RJ-ENV）。"""

    def test_provider_set_and_generic_vars_blanked(self):
        base = {"PATH": "/bin", "LLM_MODEL": "gpt-4.1-mini", "LLM_API_KEY": "k", "LLM_BASE_URL": "u"}
        env = run_jury.build_provider_env("anthropic", base)
        assert env["LLM_PROVIDER"] == "anthropic"
        # 汎用変数は空値上書き（#47 の空値フォールバックでプロバイダ既定へ解決される）
        assert env["LLM_MODEL"] == ""
        assert env["LLM_BASE_URL"] == ""
        assert env["LLM_API_KEY"] == ""
        assert env["PATH"] == "/bin"

    def test_base_env_not_mutated(self):
        base = {"LLM_MODEL": "gpt-4.1-mini"}
        run_jury.build_provider_env("openai", base)
        assert base == {"LLM_MODEL": "gpt-4.1-mini"}


class TestPreflight:
    """preflight のテスト（RJ-PF）。"""

    def test_openai_requires_key(self):
        ok, msg = run_jury.preflight("openai", {})
        assert not ok
        assert "OPENAI_API_KEY" in msg
        assert run_jury.preflight("openai", {"OPENAI_API_KEY": "k"})[0]

    def test_anthropic_and_gemini(self):
        assert not run_jury.preflight("anthropic", {})[0]
        assert run_jury.preflight("anthropic", {"ANTHROPIC_API_KEY": "k"})[0]
        assert not run_jury.preflight("gemini", {})[0]
        assert run_jury.preflight("gemini", {"GEMINI_API_KEY": "k"})[0]

    def test_vertex_accepts_either_project_var(self):
        assert not run_jury.preflight("vertex", {})[0]
        assert run_jury.preflight("vertex", {"GCP_PROJECT": "p"})[0]
        assert run_jury.preflight("vertex", {"GOOGLE_CLOUD_PROJECT": "p"})[0]

    def test_empty_value_is_treated_as_unset(self):
        assert not run_jury.preflight("openai", {"OPENAI_API_KEY": ""})[0]

    def test_unknown_provider(self):
        ok, msg = run_jury.preflight("foo", {})
        assert not ok
        assert "foo" in msg

    def test_vllm_requires_model_name(self):
        # vllm はキー不要だが、配信モデル名に既定を置けないため VLLM_MODEL を必須とする（#67）。
        ok, msg = run_jury.preflight("vllm", {})
        assert not ok
        assert "VLLM_MODEL" in msg
        assert run_jury.preflight("vllm", {"VLLM_MODEL": "org/local-model"})[0]


class TestResolveBaseUrl:
    """resolve_base_url のテスト（RJ-URL・#67）。"""

    def test_non_vllm_provider_returns_none(self):
        assert run_jury.resolve_base_url("openai", {}) is None

    def test_default_endpoint(self):
        assert run_jury.resolve_base_url("vllm", {}) == "http://localhost:8000/v1"

    def test_provider_specific_var(self):
        env = {"VLLM_BASE_URL": "http://vllm-host:9000/v1"}
        assert run_jury.resolve_base_url("vllm", env) == "http://vllm-host:9000/v1"

    def test_blanked_generic_var_falls_back(self):
        # build_provider_env が LLM_BASE_URL を空値化した後でも固有変数で解決できる（#47 + #67）。
        env = run_jury.build_provider_env("vllm", {"VLLM_BASE_URL": "http://vllm-host:9000/v1"})
        assert run_jury.resolve_base_url("vllm", env) == "http://vllm-host:9000/v1"


class TestCheckEndpointReachable:
    """check_endpoint_reachable のテスト（RJ-PING・#67）。urlopen を差し替えネットワーク非依存にする。"""

    class _FakeResponse:
        def __init__(self, status):
            self.status = status

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def getcode(self):
            return self.status

    def test_reachable(self, monkeypatch):
        called = {}

        def fake_urlopen(url, timeout=None):
            called["url"] = url
            return self._FakeResponse(200)

        monkeypatch.setattr(run_jury.urllib.request, "urlopen", fake_urlopen)
        ok, msg = run_jury.check_endpoint_reachable("http://localhost:8000/v1")
        assert ok
        assert called["url"] == "http://localhost:8000/v1/models"
        assert "OK" in msg

    def test_trailing_slash_is_normalized(self, monkeypatch):
        called = {}

        def fake_urlopen(url, timeout=None):
            called["url"] = url
            return self._FakeResponse(200)

        monkeypatch.setattr(run_jury.urllib.request, "urlopen", fake_urlopen)
        run_jury.check_endpoint_reachable("http://localhost:8000/v1/")
        assert called["url"] == "http://localhost:8000/v1/models"

    def test_non_200_is_unreachable(self, monkeypatch):
        monkeypatch.setattr(run_jury.urllib.request, "urlopen",
                            lambda url, timeout=None: self._FakeResponse(503))
        ok, msg = run_jury.check_endpoint_reachable("http://localhost:8000/v1")
        assert not ok
        assert "503" in msg

    def test_connection_error_is_unreachable(self, monkeypatch):
        # ポート転送断（接続拒否）を模す。例外を伝播させず (False, message) を返す。
        def raise_urlerror(url, timeout=None):
            raise run_jury.urllib.error.URLError("Connection refused")

        monkeypatch.setattr(run_jury.urllib.request, "urlopen", raise_urlerror)
        ok, msg = run_jury.check_endpoint_reachable("http://localhost:8000/v1")
        assert not ok
        assert "到達できない" in msg


class TestCountStage1Results:
    """count_stage1_results のテスト（RJ-CNT）。"""

    def test_counts_success_and_failures(self, tmp_path):
        import json
        (tmp_path / "0_v1.json").write_text(json.dumps({"success": True}), encoding="utf-8")
        (tmp_path / "1_v1.json").write_text(json.dumps({"success": False, "api_failures": ["x"]}), encoding="utf-8")
        (tmp_path / "2_v1.json").write_text(json.dumps("None"), encoding="utf-8")  # annotated=no
        (tmp_path / "0-config_v1.json").write_text("{}", encoding="utf-8")  # config は数えない
        total, failed = run_jury.count_stage1_results(str(tmp_path))
        assert total == 2
        assert failed == 1
