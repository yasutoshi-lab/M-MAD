# M-MAD ドキュメント

M-MAD の LLM バックエンド（プロバイダ）別セットアップ手順をまとめる。

M-MAD は OpenAI 互換の Chat Completions API を通じて LLM を呼び出す。プロバイダは
リポジトリルートの `.env`（または環境変数）の `LLM_PROVIDER` で切り替える。

| プロバイダ | `LLM_PROVIDER` | 認証 | ドキュメント |
|---|---|---|---|
| Google Agent Platform（旧 Vertex AI） | `vertex` | ADC（OAuth トークン） | [setup-vertex-adc.md](setup-vertex-adc.md) |
| Google AI Studio（Gemini API） | `gemini` | 静的 API キー | [setup-ai-studio.md](setup-ai-studio.md) |
| OpenAI | `openai`（既定） | `OPENAI_API_KEY` | （本 README 下部の補足を参照） |

いずれの方式でも、実行は uv を用いる（[../README.md](../README.md) の Environment Setup を参照）:

```bash
uv sync                 # ランタイム依存を導入
uv run python code/stage1.py --help
```

## どちらの Google 方式を選ぶか

- **`vertex`（推奨・Google Cloud 前提）**: GCP プロジェクト配下で Vertex AI を使う。
  認証は ADC（`gcloud auth application-default login`）で、API キーは不要。組織の GCP
  権限・課金・データ処理契約（DPA）の枠内で運用できる。エンドポイントは
  `aiplatform.googleapis.com`、モデルは `google/gemini-3.5-flash`。
- **`gemini`（AI Studio）**: 個人/簡易利用向け。AI Studio で発行した**静的 API キー**を使う。
  トークンのリフレッシュが不要で最も手軽。エンドポイントは
  `generativelanguage.googleapis.com`、モデルは `gemini-3.5-flash`。

> **注意**: 2 つは**別のエンドポイント・別の認証**であり、キーも互換ではない。AI Studio の
> キーで Vertex エンドポイントは叩けず、その逆も不可。Vertex 用に発行したキーで AI Studio
> エンドポイントへ投げると `403 API_KEY_SERVICE_BLOCKED` になる。

## 共通の設定変数

`.env`（リポジトリルート。`.gitignore` 済み）または環境変数で設定する。雛形は
[../.env.example](../.env.example)。

| 変数 | 用途 | 既定 |
|---|---|---|
| `LLM_PROVIDER` | `openai` / `gemini` / `vertex` | `openai` |
| `LLM_MODEL` | モデル名（vertex は `google/` を自動付与） | provider 依存 |
| `LLM_BASE_URL` | エンドポイント上書き（通常は不要） | provider 依存 |
| `LLM_API_KEY` | プロバイダ非依存の API キー上書き | なし |

設定の解決ロジックは `code/utils/config.py` の `get_llm_config()` / `build_openai_client()` を参照。

## OpenAI を使う場合（補足）

```env
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...
```

`LLM_BASE_URL` 未設定時は OpenAI の既定エンドポイントを使う。
