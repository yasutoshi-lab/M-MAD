# アーキテクチャ

M-MAD は LLM を審査員（LLM-as-a-judge）として用いる機械翻訳（MT）品質評価フレームワーク。
MQM（Multidimensional Quality Metrics）アノテーションガイドラインを評価次元に分解し、次元ごとに
複数エージェントが討論（debate）することで、翻訳文のエラースパン・カテゴリ・重大度（severity）を
細粒度で検出・評価する。

- 論文: *Multidimensional Multi-Agent Debate for Advanced Machine Translation Evaluation*（arXiv:2412.20127）
- 評価対象: WMT-23 Metrics Shared Task（`zh-en` / `en-de` / `he-en`）
- fork 拡張: ja→多言語診断（`ja-{lang}`。手順書 JSON 前処理・ja 共有 few-shot・run-level jury。
  手法自体は論文のまま。後述の「run-level jury」節と [usage.md](usage.md) を参照）
- フレームワーク図: [`asset/framework.png`](../asset/framework.png)

## 3 ステージ

```
data/input.{lp}.{system}_v2.txt
   │
   ▼  Stage 1  (code/stage1.py)           Dimension Partition
   │     MQM を 4 次元へ分解し、次元ごとに独立アノテーション → Judge が統合
   ▼
data/output_{lp}_{system}_v1/{id}_v1.json
   │
   ▼  Stage 2 & 3  (code/stage2_3.py)     Multi-Agent Debate → Final Judgment
   │     各次元で 2 エージェントが討論し合意形成 → 統合 Judge が最終 MQM 出力
   ▼
data/stage2_3_{lp}_{system}/{i}_v1.json
   │
   ▼  Meta-evaluation  (wmt23_metrics.ipynb)
   │     mt-metrics-eval で seg / sys レベル相関を算出
   ▼
metrics_scores/{metric}_{lp}.{seg,sys}.score
```

### Stage 1 — Dimension Partition（`code/stage1.py`）
MQM を **4 次元**に分解し、各次元エージェント + Judge の計 5 エージェントで評価する。

| エージェント | 役割 | MQM サブカテゴリ例 |
|---|---|---|
| Accuracy Agent | 正確性エラー検出 | addition / mistranslation / omission / untranslated |
| Fluency Agent | 流暢性エラー検出 | grammar / punctuation / spelling / register 等 |
| Terminology Agent | 用語エラー検出 | inappropriate for context / inconsistent use |
| Style Agent | 文体エラー検出 | awkward |
| Judge | 4 次元の結果を統合し最終アノテーション（JSON）を生成 | — |

- 各次元エージェントには `base_system_prompt`、Judge には `judge_system_prompt` を設定。
- 言語ペア別 **4-shot**（3 例 + non-translation 1 例）を注入してから評価（[prompts-and-fewshot.md](prompts-and-fewshot.md)）。
- 重大な破綻（garbled / 無関係訳）には特別カテゴリ **non-translation**（segment 全体・1 件のみ）を割り当てる。
- Judge 出力は `extract_json()` → `parse_json_obj()`（`json.loads`→失敗時 `ast.literal_eval`）で安全にパース。
  最大 10 回リトライ、失敗時は non-translation にフォールバック。
- **可観測性**: LLM 応答を 1 度も得られなかったエージェント（API 全滅）があると、出力 JSON は
  `success: false`＋`api_failures`（記録配列）になる（#52）。パース失敗由来のフォールバック
  （論文設計の逃げ道）とは区別される。出力には実使用の `model_name` / `provider` も記録される（#60）。

実装の中心は `Debate` クラス（1 サンプル分の討論を統括）と `DebatePlayer`（`Agent` 派生）。

### Stage 2 & 3 — Multi-Agent Debate + Final Judgment（`code/stage2_3.py`）
1. Stage1 出力（各次元エージェントの最終アノテーション）を読み込む。
2. 各 MQM 次元で **2 エージェント**を用意し、片方に「反対意見」（`major`→`minor` 置換、
   non-translation 否定文）を持たせて **最大 4 ラウンド**討論（`run_dimension_debate`）。
3. 各ラウンド後、`judge_prompt` で 2 者のアノテーションが一貫（yes/no）かを判定。yes なら早期終了。
4. 4 次元の合意結果を統合 Judge（`run_final_judge`）に渡し、重複除去・重大度優先ルール適用のうえ
   最終 MQM アノテーションを JSON 出力。

### メタ評価（`wmt23_metrics.ipynb`）
`google-research/mt-metrics-eval` を用いて seg / sys レベル相関を算出する。詳細は
[meta-evaluation.md](meta-evaluation.md)。

### run-level jury（fork 拡張・`code/run_jury.py` / `code/jury_report.py`）
同一入力に対しパイプライン全体をプロバイダごとに独立実行し（**各 run 内は単一プロバイダ＝
論文準拠のまま**）、出力を `data/{output,stage2_3}_{lp}_{system}_{provider}` に分離する。
`jury_report.py` は完了済み出力を読み取り専用で突合し、プロバイダ別スコアの並記と一致率等の
**記述統計**（Spearman ρ / Cohen's κ / 不一致セグメント列挙）を出力する。統合スコアは作らない
（レベル 1 運用。討論内のプロバイダ混成は論文の future work であり未実装）。
詳細は [usage.md](usage.md) / [meta-evaluation.md](meta-evaluation.md)。

## エージェント抽象（`code/utils/agent.py`）
`Agent` は `memory_lst`（system / user / assistant のチャット履歴）を保持し、
`set_meta_prompt` / `add_event` / `add_memory` で構築、`ask()`→`query()` が LLM を呼ぶ。
`backoff` は**一時的エラーのみ**（RateLimit / 接続断 / タイムアウト / 5xx）を指数バックオフ・
最大 20 回リトライし、4xx の恒久エラー（BadRequest / 認証等）は即時伝播して #52 の
`success:false` 経路に落ちる（#58）。LLM 接続先は
`utils/config.py:build_openai_client()` が環境変数から解決する（OpenAI / Gemini / Vertex / Anthropic）。

## 論文との対応・整合性

| 論文の構成要素 | 実装 |
|---|---|
| 3 ステージ（Dimension Partition → Multi-Agent Debate → Final Judgment） | Stage1 / Stage2 / Stage3（stage1.py, stage2_3.py） |
| MQM 4 次元（Accuracy / Fluency / Terminology / Style） | `NAME_LIST` / `MQM_AGENTS` |
| 4-shot demonstration strategy（WMT-22 MQM 由来） | `few_shot_demos*.py`（3 例 + non-translation 1 例） |
| 討論ラウンド・合意判定 | Stage2 の最大 4 ラウンド + `judge_prompt`（yes/no） |
| severity（minor / major）・non-translation | 各プロンプト・Judge 統合ルール |

> **重要**: コード変更時は上記の設計意図（ステージ構成・4 次元・討論・severity・non-translation・
> Judge 統合）を変えないこと。乖離しうる場合は論文の該当箇所を根拠に確認する。詳細は
> [contributing.md](contributing.md)。

## ディレクトリ構成

| パス | 役割 |
|---|---|
| `code/stage1.py` | Stage 1（`Debate`/`DebatePlayer`、CLI エントリ） |
| `code/stage2_3.py` | Stage 2 & 3（討論・最終判定。関数分割済み。`-i`/`-o` で入出力上書き可） |
| `code/few_shot_demos.py` / `_de.py` / `_he.py` / `_ja.py` | 言語ペア別 few-shot 例（`_ja` は全 ja-* 共有） |
| `code/prepare_input.py` | 手順書 JSON → Stage1 入力の前処理（fork 拡張） |
| `code/run_jury.py` | run-level jury: プロバイダ別独立実行（fork 拡張） |
| `code/jury_report.py` | プロバイダ間一致率レポート（fork 拡張・読み取り専用） |
| `code/utils/agent.py` | `Agent` 基底クラス（履歴管理・LLM 呼び出し・backoff） |
| `code/utils/config.py` | プロバイダ設定解決（`get_llm_config` / `build_openai_client`） |
| `code/utils/openai_utils.py` | トークン計算・モデル別最大コンテキスト・例外 |
| `code/utils/stage1.json` | Stage1 の全プロンプトテンプレート |
| `data/` | 入力データと Stage 出力 JSON |
| `metrics_scores/` | メタ評価結果 |
| `tests/` | ユニットテスト（pytest。L1 純粋関数＋L2 LLM モック） |
