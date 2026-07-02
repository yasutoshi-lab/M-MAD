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
