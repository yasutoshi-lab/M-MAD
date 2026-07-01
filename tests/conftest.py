"""pytest 共通設定・フィクスチャ。

`code/` を sys.path に追加し、`import stage1 / stage2_3 / utils.*` を可能にする。
LLM API・.env・ネットワークに依存しない決定的なテストのためのフィクスチャも提供する。
"""

import os
import sys
import types

import pytest

CODE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "code")
if CODE_DIR not in sys.path:
    sys.path.insert(0, CODE_DIR)


@pytest.fixture
def clean_env(monkeypatch):
    """config を .env・環境変数に依存させず決定的にするフィクスチャ。

    `_load_dotenv` を no-op 化し、LLM 関連の環境変数を削除したうえで config モジュールを返す。

    Returns:
        module: utils.config モジュール。
    """
    import utils.config as config

    monkeypatch.setattr(config, "_load_dotenv", lambda: None)
    for var in [
        "LLM_PROVIDER", "LLM_MODEL", "LLM_BASE_URL", "LLM_API_KEY",
        "OPENAI_API_KEY", "OPENAI_BASE_URL", "GEMINI_API_KEY", "GCP_PROJECT",
        "GOOGLE_CLOUD_PROJECT", "LLM_LOCATION",
    ]:
        monkeypatch.delenv(var, raising=False)
    return config


def make_completion(content):
    """openai 1.x 互換の最小 ChatCompletion ダミーを生成する。

    `completion.choices[0].message.content` でアクセスできる構造を返す。

    Args:
        content (str): message.content に設定する文字列。

    Returns:
        types.SimpleNamespace: ダミー completion。
    """
    message = types.SimpleNamespace(content=content)
    choice = types.SimpleNamespace(message=message)
    return types.SimpleNamespace(choices=[choice])
