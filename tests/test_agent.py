"""utils/agent.py のリトライ分類テスト（LLM モック使用・Issue #58）。

恒久エラー（4xx）は backoff でリトライせず即時伝播し、一時的エラー（429/接続/5xx）のみ
リトライされることを、呼び出し回数カウンタ付きのフェイク client で検証する。
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


class TestQueryRetryClassification:
    """Agent.query のリトライ分類（#58）。"""

    def _patch_client(self, monkeypatch, fake):
        monkeypatch.setattr(agent_module, "build_openai_client",
                            lambda fallback_api_key=None: (fake, "gpt-4.1-mini"))

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
