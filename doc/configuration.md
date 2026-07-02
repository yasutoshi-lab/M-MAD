# 設定リファレンス

LLM プロバイダ・モデル・接続先の設定を横断的にまとめる。プロバイダ別の詳細手順は
[setup-vertex-adc.md](setup-vertex-adc.md) / [setup-ai-studio.md](setup-ai-studio.md)、選択指針は
[README.md](README.md) を参照。

設定は `code/utils/config.py`（`get_llm_config()` / `build_openai_client()`）が、環境変数および
リポジトリルートの `.env`（自動読込・`setdefault` なので明示指定が優先）から解決する。

## 環境変数

| 変数 | 用途 | 既定 |
|---|---|---|
| `LLM_PROVIDER` | `openai` / `gemini` / `vertex` / `anthropic` | `openai` |
| `LLM_MODEL` | モデル名（provider 既定を上書き。vertex は `google/` を自動付与） | provider 依存 |
| `LLM_BASE_URL` | OpenAI 互換エンドポイントの上書き（通常不要） | provider 依存 |
| `LLM_API_KEY` | プロバイダ非依存の API キー上書き | なし |
| `OPENAI_API_KEY` | OpenAI 利用時の API キー | なし |
| `GEMINI_API_KEY` | Gemini(AI Studio) 利用時の API キー | なし |
| `ANTHROPIC_API_KEY` | Anthropic 利用時の API キー | なし |
| `GCP_PROJECT` / `GOOGLE_CLOUD_PROJECT` | Vertex 利用時の GCP プロジェクト | なし |
| `LLM_LOCATION` | Vertex のリージョン（`global` など） | `global` |

## プロバイダ別の既定

| provider | model 既定 | base_url | 認証 |
|---|---|---|---|
| `openai` | `gpt-4.1-mini` | OpenAI 既定 | `OPENAI_API_KEY`（または `LLM_API_KEY`） |
| `gemini` | `gemini-3.5-flash` | `https://generativelanguage.googleapis.com/v1beta/openai/` | `GEMINI_API_KEY`（静的キー） |
| `vertex` | `google/gemini-3.5-flash` | `https://{location}-aiplatform.googleapis.com/v1/projects/{GCP_PROJECT}/locations/{location}/endpoints/openapi`（`global` は host が `aiplatform.googleapis.com`） | ADC の OAuth トークン（`gcloud auth application-default login`） |
| `anthropic` | `claude-haiku-4-5` | `https://api.anthropic.com/v1/`（OpenAI 互換エンドポイント） | `ANTHROPIC_API_KEY`（または `LLM_API_KEY`） |

## 対応モデルと最大コンテキスト

`code/utils/agent.py:support_models`:
`gpt-3.5-turbo` / `gpt-3.5-turbo-0301` / `gpt-4o-mini` / `gpt-4.1-mini` / `qwen2.5-72b-instruct` /
`Llama-3.1-70B-Instruct` / `gemini-3.5-flash` / `google/gemini-3.5-flash` / `claude-haiku-4-5`

`code/utils/openai_utils.py:model2max_context`（トークン計算のフォールバックあり。未知モデルは
`num_tokens_from_string` が `cl100k_base` に近似）:

| モデル | 最大コンテキスト |
|---|---|
| `gpt-4` / `gpt-4-0314` | 7900 |
| `gpt-3.5-turbo` / `-0301` | 3900 |
| `gpt-4o-mini` | 16384 |
| `gpt-4.1-mini` | 1047576 |
| `qwen2.5-72b-instruct` / `Llama-3.1-70B-Instruct` | 131072 |
| `gemini-3.5-flash` | 1000000 |
| `claude-haiku-4-5` | 200000 |

## 例（`.env`）

```env
# Vertex（推奨・Google Cloud）
LLM_PROVIDER=vertex
LLM_MODEL=gemini-3.5-flash
GCP_PROJECT=your-gcp-project-id
LLM_LOCATION=global

# Gemini（AI Studio・静的キー）
# LLM_PROVIDER=gemini
# GEMINI_API_KEY=your-gemini-api-key

# OpenAI
# LLM_PROVIDER=openai
# OPENAI_API_KEY=sk-...

# Anthropic（OpenAI 互換エンドポイント）
# LLM_PROVIDER=anthropic
# LLM_MODEL=claude-haiku-4-5
# ANTHROPIC_API_KEY=sk-ant-...
```

雛形は [`.env.example`](../.env.example)。`.env` は `.gitignore` 済みでコミットされない。
