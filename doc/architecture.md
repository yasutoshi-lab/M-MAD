# アーキテクチャ

M-MAD は LLM を審査員（LLM-as-a-judge）として用いる機械翻訳（MT）品質評価フレームワーク。
MQM（Multidimensional Quality Metrics）アノテーションガイドラインを評価次元に分解し、次元ごとに
複数エージェントが討論（debate）することで、翻訳文のエラースパン・カテゴリ・重大度（severity）を
細粒度で検出・評価する。

- 論文: *Multidimensional Multi-Agent Debate for Advanced Machine Translation Evaluation*（arXiv:2412.20127）
- 評価対象: WMT-23 Metrics Shared Task（`zh-en` / `en-de` / `he-en`）
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

## エージェント抽象（`code/utils/agent.py`）
`Agent` は `memory_lst`（system / user / assistant のチャット履歴）を保持し、
`set_meta_prompt` / `add_event` / `add_memory` で構築、`ask()`→`query()` が LLM を呼ぶ。
`backoff` で RateLimit/APIError 等を指数バックオフ・最大 20 回リトライ。LLM 接続先は
`utils/config.py:build_openai_client()` が環境変数から解決する（OpenAI / Gemini / Vertex）。

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
| `code/stage2_3.py` | Stage 2 & 3（討論・最終判定。関数分割済み） |
| `code/few_shot_demos.py` / `_de.py` / `_he.py` | 言語ペア別 few-shot 例 |
| `code/utils/agent.py` | `Agent` 基底クラス（履歴管理・LLM 呼び出し・backoff） |
| `code/utils/config.py` | プロバイダ設定解決（`get_llm_config` / `build_openai_client`） |
| `code/utils/openai_utils.py` | トークン計算・モデル別最大コンテキスト・例外 |
| `code/utils/stage1.json` | Stage1 の全プロンプトテンプレート |
| `data/` | 入力データと Stage 出力 JSON |
| `metrics_scores/` | メタ評価結果 |
| `tests/` | ユニットテスト（pytest） |
