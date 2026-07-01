"""utils/openai_utils.py の純粋関数（L1）ユニットテスト。"""

from utils.openai_utils import (
    num_tokens_from_string,
    OutOfQuotaException,
    AccessTerminatedException,
)


class TestNumTokensFromString:
    """num_tokens_from_string のテスト（OU-1/2）。"""

    def test_known_model(self):
        assert num_tokens_from_string("hello world", "gpt-4o-mini") > 0

    def test_unknown_model_falls_back(self):
        # tiktoken 未対応モデルでも cl100k_base フォールバックで例外なく数えられる。
        assert num_tokens_from_string("hello", "gemini-3.5-flash") > 0


class TestExceptions:
    """独自例外の文字列表現テスト（OU-3/4）。"""

    def test_out_of_quota_message(self):
        assert "No quota for key: k" in str(OutOfQuotaException("k"))

    def test_access_terminated_with_cause(self):
        assert "Caused by c" in str(AccessTerminatedException("k", cause="c"))
