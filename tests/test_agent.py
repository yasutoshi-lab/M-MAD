"""utils/agent.py のリトライ分類・モデル allowlist テスト（LLM モック使用・Issue #58/#67）。

恒久エラー（4xx）は backoff でリトライせず即時伝播し、一時的エラー（429/接続/5xx）のみ
リトライされることを、呼び出し回数カウンタ付きのフェイク client で検証する。
併せて、self-hosted（vllm）では support_models の allowlist が免除されることを検証する。
"""

from types import SimpleNamespace

import httpx
import pytest
from openai import BadRequestError, RateLimitError

from conftest import make_completion
from utils import agent as agent_module
from utils.agent import Agent
from utils.openai_utils import OutOfQuotaException


def _http_response(status_code):
    request = httpx.Request("POST", "https://api.test/v1/chat/completions")
    return httpx.Response(status_code, request=request)


def make_bad_request_error():
    return BadRequestError("invalid request", response=_http_response(400), body=None)


def make_rate_limit_error(message="rate limited"):
    return RateLimitError(message, response=_http_response(429), body=None)


class FakeClient:
    """先頭から errors を順に送出し、尽きたら正常応答を返すフェイク client。"""

    def __init__(self, errors):
        self.calls = 0
        self._errors = list(errors)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **_kwargs):
        self.calls += 1
        if self._errors:
            raise self._errors.pop(0)
        return make_completion("ok")


def make_agent():
    agent = Agent(model_name="gpt-4.1-mini", name="tester", temperature=0)
    agent.openai_api_key = None
    return agent


def patch_backend(monkeypatch, fake, model="gpt-4.1-mini", provider="openai"):
    """client / モデル / provider の解決をフェイクへ差し替える（.env・ネットワーク非依存）。"""
    monkeypatch.setattr(agent_module, "build_openai_client",
                        lambda fallback_api_key=None: (fake, model))
    monkeypatch.setattr(agent_module, "get_llm_config", lambda: {"provider": provider})


class TestQueryRetryClassification:
    """Agent.query のリトライ分類（#58）。"""

    def _patch_client(self, monkeypatch, fake):
        patch_backend(monkeypatch, fake)

    def test_permanent_error_fails_fast(self, monkeypatch):
        # 400 BadRequest（恒久エラー）はリトライせず 1 回で即時伝播する。
        fake = FakeClient([make_bad_request_error()] * 5)
        self._patch_client(monkeypatch, fake)
        with pytest.raises(BadRequestError):
            make_agent().ask()
        assert fake.calls == 1

    def test_transient_error_is_retried(self, monkeypatch):
        # 429（一時的エラー）はリトライされ、2 回目の正常応答を返す。
        fake = FakeClient([make_rate_limit_error()])
        self._patch_client(monkeypatch, fake)
        assert make_agent().ask() == "ok"
        assert fake.calls == 2

    def test_quota_exceeded_converts_immediately(self, monkeypatch):
        # クォータ超過文言つき 429 は OutOfQuotaException へ即時変換（従来挙動の固定）。
        fake = FakeClient([make_rate_limit_error(
            "You exceeded your current quota, please check your plan and billing details")])
        self._patch_client(monkeypatch, fake)
        with pytest.raises(OutOfQuotaException):
            make_agent().ask()
        assert fake.calls == 1


class TestModelAllowlist:
    """support_models allowlist の適用範囲（#67）。"""

    def test_vllm_allows_unlisted_model(self, monkeypatch):
        # self-hosted は任意のモデル名（HF リポ名等）を配信するため allowlist を免除する。
        fake = FakeClient([])
        patch_backend(monkeypatch, fake, model="nvidia/Gemma-4-26B-A4B-NVFP4", provider="vllm")
        assert make_agent().ask() == "ok"
        assert fake.calls == 1

    def test_hosted_provider_still_rejects_unlisted_model(self, monkeypatch):
        # ホスト型ではモデル名タイポ検出のガード（#12）を維持し、API を叩かずに落とす。
        fake = FakeClient([])
        patch_backend(monkeypatch, fake, model="gpt-4.1-mini-typo", provider="openai")
        with pytest.raises(AssertionError):
            make_agent().ask()
        assert fake.calls == 0

    def test_hosted_provider_accepts_listed_model(self, monkeypatch):
        fake = FakeClient([])
        patch_backend(monkeypatch, fake, model="claude-haiku-4-5", provider="anthropic")
        assert make_agent().ask() == "ok"
