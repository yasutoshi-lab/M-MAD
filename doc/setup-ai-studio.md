# セットアップ: Google AI Studio（Gemini API）+ 静的 API キー方式

Google AI Studio が提供する **Gemini API の OpenAI 互換エンドポイント**を、
**静的 API キー**で利用する手順。トークンのリフレッシュが不要で最も手軽。

- エンドポイント: `https://generativelanguage.googleapis.com/v1beta/openai/`
- モデル: `gemini-3.5-flash`（`google/` プレフィックスは付けない）
- 認証: AI Studio で発行した API キー（`GEMINI_API_KEY`）

---

## 1. 前提条件

- Google アカウント
- [Google AI Studio](https://aistudio.google.com/apikey) で発行した **Gemini API キー**
- キーが紐づくプロジェクトで **Generative Language API（`generativelanguage.googleapis.com`）が有効**
  かつ、キーに**当該 API をブロックする API 制限がかかっていない**こと

> **重要**: このキーは AI Studio（Gemini API）専用。Vertex/Agent Platform とは別物で、
> Vertex エンドポイントには使えない。逆に Vertex 用に発行したキーを本エンドポイントへ使うと
> `403 API_KEY_SERVICE_BLOCKED` になる。Vertex を使う場合は
> [setup-vertex-adc.md](setup-vertex-adc.md) を参照。

## 2. API キーの取得

1. https://aistudio.google.com/apikey にアクセス。
2. 「Create API key」でキーを発行（既存 GCP プロジェクトに紐づけ可能）。
3. 発行されたキーを控える（**チャットや公開場所に貼らない**）。

## 3. `.env` の設定

リポジトリルートに `.env` を作成する（`.env.example` をコピー）。

```env
LLM_PROVIDER=gemini
LLM_MODEL=gemini-3.5-flash
GEMINI_API_KEY=your-gemini-api-key
```

- `.env` は `.gitignore` 済みでコミットされない。
- `LLM_BASE_URL` は通常不要（既定で `https://generativelanguage.googleapis.com/v1beta/openai/`）。

## 4. 依存インストールと疎通確認

```bash
uv sync

# 1 リクエストのスモークテスト
uv run python -c "
import sys; sys.path.insert(0,'code')
from utils.config import build_openai_client
c, m = build_openai_client()
r = c.chat.completions.create(model=m, messages=[{'role':'user','content':'Reply with exactly: OK'}], max_tokens=10, temperature=0)
print(m, '->', r.choices[0].message.content)
"
```

`gemini-3.5-flash -> OK` が返れば疎通成功。

## 5. パイプライン実行

```bash
# Stage 1（次元分解・アノテーション）
sh run_stage1.sh

# Stage 2 & 3（討論 + 最終判定）
sh run_stage2_3.sh
```

キー・モデル・プロバイダは `.env` から読み込まれる。

## 6. トラブルシューティング

| 症状 | 原因 | 対処 |
|---|---|---|
| `403 PERMISSION_DENIED` / `API_KEY_SERVICE_BLOCKED` | Generative Language API 未有効、またはキーの API 制限 | キーのプロジェクトで当該 API を有効化し、キー制限を見直す。または AI Studio で新規キーを発行 |
| `consumer: projects/NNN` が想定と違う | キーが別プロジェクトのもの | 意図したプロジェクトのキーを使う |
| `401 Unauthorized` | キーが無効/失効 | 新しいキーを発行して `.env` を更新 |
| `404` / モデル不明 | モデル名の誤り | `gemini-3.5-flash`（`google/` を付けない）を指定 |

## 補足: 仕組み

`code/utils/config.py` の `get_llm_config()` が `LLM_PROVIDER=gemini` を検出し、
base_url を `https://generativelanguage.googleapis.com/v1beta/openai/`、api_key を
`GEMINI_API_KEY`（または `LLM_API_KEY`）として `build_openai_client()` がクライアントを構築する。
