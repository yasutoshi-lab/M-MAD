# M-MAD ドキュメント

M-MAD の設計・実行・設定・開発に関するドキュメント索引。プロジェクト概要は
リポジトリ直下の [../README.md](../README.md) を参照。

## ドキュメント一覧

| ドキュメント | 内容 |
|---|---|
| [architecture.md](architecture.md) | 設計。3 ステージ構成・エージェント・データフロー・**論文（arXiv:2412.20127）との対応** |
| [usage.md](usage.md) | 実行ガイド（入力準備 → Stage1 → Stage2&3 → メタ評価の end-to-end） |
| [data-format.md](data-format.md) | 入出力の形式（入力タブ区切り・Stage 出力 JSON スキーマ・score 形式） |
| [configuration.md](configuration.md) | 設定リファレンス（env・プロバイダ既定・対応モデル・最大コンテキスト） |
| [setup-vertex-adc.md](setup-vertex-adc.md) | Google Agent Platform（Vertex）+ ADC 方式のセットアップ |
| [setup-ai-studio.md](setup-ai-studio.md) | Google AI Studio（Gemini API）+ 静的キー方式のセットアップ |
| [meta-evaluation.md](meta-evaluation.md) | メタ評価（`wmt23_metrics.ipynb` / mt-metrics-eval / seg・sys 相関） |
| [prompts-and-fewshot.md](prompts-and-fewshot.md) | プロンプトの所在・置換、few-shot 構造、言語ペア追加手順 |
| [contributing.md](contributing.md) | 開発ガイド（テスト/lint/pre-commit・PR フロー・論文整合性ルール） |
| [test-design.md](test-design.md) | テスト設計書（方針・L1/L2 ケース一覧） |

## LLM プロバイダの選択

M-MAD は OpenAI 互換の Chat Completions API 経由で LLM を呼ぶ。プロバイダは `.env`（または環境変数）の
`LLM_PROVIDER` で切り替える。設定値の詳細は [configuration.md](configuration.md)。

| プロバイダ | `LLM_PROVIDER` | 認証 | セットアップ |
|---|---|---|---|
| Google Agent Platform（旧 Vertex AI） | `vertex` | ADC（OAuth トークン） | [setup-vertex-adc.md](setup-vertex-adc.md) |
| Google AI Studio（Gemini API） | `gemini` | 静的 API キー | [setup-ai-studio.md](setup-ai-studio.md) |
| OpenAI | `openai`（既定） | `OPENAI_API_KEY` | [configuration.md](configuration.md) |

### どちらの Google 方式を選ぶか
- **`vertex`（推奨・Google Cloud 前提）**: GCP プロジェクト配下で Vertex を使う。認証は ADC で API キー不要。
  エンドポイントは `aiplatform.googleapis.com`、モデルは `google/gemini-3.5-flash`。
- **`gemini`（AI Studio）**: 個人/簡易利用向け。AI Studio 発行の静的 API キーを使う。
  エンドポイントは `generativelanguage.googleapis.com`、モデルは `gemini-3.5-flash`。

> **注意**: 2 つは別エンドポイント・別認証でキーも互換でない。Vertex 用キーで AI Studio エンドポイントを
> 叩くと `403 API_KEY_SERVICE_BLOCKED` になる。

## クイックスタート

```bash
uv sync                 # ランタイム依存を導入（Python 3.10）
cp .env.example .env    # プロバイダを設定
uv run python code/stage1.py --help
```

実行の詳細は [usage.md](usage.md)、開発は [contributing.md](contributing.md) を参照。
