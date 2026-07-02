# MQM 用語リファレンス

M-MAD が出力するアノテーション（`category` / `severity` 等）の各用語が **何を表し、パイプラインの
どこで何に使われ、結果から何が読み取れるか** をまとめる。用語の定義はプロンプト実体
（`code/utils/stage1.json`）と論文（arXiv:2412.20127）、および MQM 標準（Freitag et al. 2021 /
WMT MQM ガイドライン）に基づく。

## MQM とは

**MQM（Multidimensional Quality Metrics）** は翻訳品質を「エラーの列挙」で表現する人手評価
フレームワーク。翻訳全体に 1 つの点数を付けるのではなく、**訳文中の問題箇所（error span）ごとに
「どの種類のエラーか（category）」と「どれほど深刻か（severity）」を記録**する。WMT Metrics Shared
Task の人手評価（ゴールドデータ）もこの方式であり、M-MAD は LLM でこの MQM アノテーションを
再現・自動化するフレームワークである。

## アノテーション 1 件の構造

Stage1 / Stage2&3 の出力に含まれる `annotations` 配列の 1 要素（[data-format.md](data-format.md)）:

```json
{
  "error_span": "in the disco",
  "category": "accuracy/mistranslation",
  "severity": "major",
  "is_source_error": "no"
}
```

| フィールド | 意味 | 読み方 |
|---|---|---|
| `error_span` | エラーに該当する**訳文中のテキスト範囲**。omission / source error の場合は原文側のスパンになりうる。non-translation の場合は `"all"`（segment 全体） | 「訳文のどこが悪いか」。修正箇所の特定に使う |
| `category` | エラー種別。`{次元}/{サブカテゴリ}` 形式（例 `accuracy/mistranslation`）または特別カテゴリ `non-translation` | 「どういう種類の問題か」。次元名から担当エージェント（検出観点）も分かる |
| `severity` | 重大度。`major` または `minor` の 2 値 | 「どれほど深刻か」。スコア化の重みが変わる（後述） |
| `is_source_error` | エラーの原因が**原文側**にあるか（`yes` / `no`）。原文自体の誤字・文法崩れ等に起因する場合 `yes` | `yes` なら MT システム（翻訳）の責任ではなく、入力品質の問題として切り分けられる |

## 4 つの評価次元（dimension）とサブカテゴリ

M-MAD は MQM のエラー類型を **4 次元**に分解し、次元ごとに専門エージェントを立てる
（Stage1 の Dimension Partition）。各次元が受け持つサブカテゴリはプロンプト
（`stage1.json` の `accuracy_agent` 等）で明示されている。

### Accuracy（正確性）— 「原文の意味が正しく伝わっているか」

原文と訳文の**意味の対応**に関するエラー。翻訳品質の根幹であり、Judge の重複解決でも最優先される。

| サブカテゴリ | 定義 | 例 |
|---|---|---|
| `accuracy/addition` | 原文に存在しない情報が訳文に**追加**されている | 原文にない「必ず」「すべての」等の語が訳文に出現する |
| `accuracy/omission` | 原文にある内容が訳文から**欠落**している | 原文の条件節「〜の場合は」が訳文で丸ごと抜けている |
| `accuracy/mistranslation` | 訳文が原文の意味を**正しく表していない**（誤訳） | 「右クリック」が "left click" と訳される |
| `accuracy/untranslated` | 原文のテキストが**翻訳されずに残っている** | 日本語原文の一部が英訳文中に日本語のまま残る |

### Fluency（流暢性）— 「訳文が言語としてまともか」

原文と比べなくても分かる、**訳文単体の言語的な問題**。

| サブカテゴリ | 定義 | 例 |
|---|---|---|
| `fluency/punctuation` | 句読点・記号がロケールやスタイルとして不適切 | 英文でピリオド抜け、全角記号の混入 |
| `fluency/spelling` | 綴り・大文字小文字の誤り | "recieve"（正: receive）、文頭が小文字 |
| `fluency/grammar` | 文法上の問題（正書法以外） | 主語と動詞の数の不一致、時制の誤り |
| `fluency/register` | 文法的レジスタ（丁寧さの水準）の誤り | フォーマルな文書で不適切にくだけた代名詞（独語 du 等）を使用 |
| `fluency/inconsistency` | 訳文内部の不整合（用語以外） | 同一 segment 内で表記スタイルが揺れる |
| `fluency/character encoding` | 文字化け（エンコーディング起因） | `ã‚µ` のような化けた文字列 |

### Terminology（用語）— 「専門用語・定訳が正しく一貫して使われているか」

| サブカテゴリ | 定義 | 例 |
|---|---|---|
| `terminology/inappropriate for context` | 用語が非標準、または文脈に合わない | UI 用語「保存」を "keep" と訳す（定訳は "save"） |
| `terminology/inconsistent use` | 同じ用語の訳が**一貫していない** | 同一文書内で「手順書」が "manual" と "procedure" に揺れる |

### Style（文体）— 「不自然・ぎこちなくないか」

| サブカテゴリ | 定義 | 例 |
|---|---|---|
| `style/awkward` | 文法的には正しいが文体的にぎこちない・不自然 | 直訳調で読みにくい言い回し |

> 実際の出力ではモデルにより表記が揺れることがある（例 `accuracy/omission` と
> `Omission translation`）。集計スクリプトはサブカテゴリ名でなく `severity` と
> `non-translation` の有無でスコア化するため（後述）、表記揺れはスコアに影響しない。

## severity（重大度）

各エラーに付与する 2 値の深刻度。定義は `base_system_prompt`（全次元エージェント共通）による。

| 値 | 定義（プロンプト原文の要約） | 直感的な目安 |
|---|---|---|
| `major` | **意味の重大な変化**により読者を混乱・誤解させうるエラー、または目立つ重要箇所に現れるエラー | 「この訳を信じて作業すると間違える」レベル |
| `minor` | 意味の損失はなく読者を誤解させないが、**気づかれる**エラー。文体品質・流暢さ・明瞭さを下げ、魅力を損なう | 「読めば分かるが品質が低いと感じる」レベル |

補足ルール（`base_system_prompt` より）:

- エラーは**可能な限り細粒度**に付ける。1 文に誤訳が 2 語あれば mistranslation を 2 件記録する。
- ただし**同一スパンに複数エラーが重なる場合は、最も深刻な 1 件のみ**を記録する。

## non-translation（特別カテゴリ）

訳文が**文字化けや原文と無関係な内容で崩壊しており、個別エラーを列挙する意味がない**場合に付ける
特別カテゴリ。次のルールが課される:

- `error_span` は `"all"`（segment 全体）、**1 segment に最大 1 件**
- non-translation を選んだら**他のエラーは一切列挙しない**（他のすべてのアノテーションを置き換える）
- `category` はサブカテゴリを持たず、そのまま `non-translation`

また実装上は「**安全側のフォールバック**」としても使われる: Stage1 の Judge 出力が 10 回
リトライしても JSON としてパースできない場合、そのサンプルは non-translation 扱いになる
（論文設計。[architecture.md](architecture.md)）。つまり出力中の non-translation には
「本当に破綻した訳」と「Judge 出力のパース失敗」の 2 経路があり、後者は `api_failures` には
記録されない点に注意（API 全滅による `success: false` とは別事象・Issue #52）。

## 各ステージで用語がどう使われるか

| ステージ | 用語の使われ方 |
|---|---|
| **Stage 1**（次元分解） | 4 次元エージェントが担当サブカテゴリの範囲でエラーを検出し、`category` / `severity` / `error_span` / `is_source_error` を付与。Judge が 4 次元分を統合 |
| **Stage 2**（討論） | **severity と non-translation が「争点」になる**。反対意見エージェントは元アノテーションの `major` を `minor` に置換（または non-translation を否定）した主張を持たされ、その妥当性を最大 4 ラウンド討論する。つまり討論で検証されるのは主に「このエラーは本当に major か」「本当に non-translation か」という重大度判定（詳細は [architecture.md](architecture.md) の討論ラウンド節） |
| **Stage 3**（最終判定） | 統合 Judge が重複を解決する。ルール: 同一 `error_span` に複数エラーがある場合は**最も深刻な 1 件のみ**残し、severity が同じなら**類型の記載順（accuracy → fluency → terminology → style）で先のカテゴリ**を採用（`judge_system_prompt`） |
| **メタ評価 / レポート** | `severity` と non-translation を**ペナルティ重みに変換**してセグメントスコアを算出（下記） |

## スコアへの変換（何が分かるか）

集計時は 1 セグメントのアノテーションを重み付き和で**負のペナルティスコア**にする
（`code/jury_report.py` の `MQM_WEIGHTS`。Freitag et al. 2021 / WMT 標準に一致）:

| エラー | 重み |
|---|---|
| minor 1 件 | **-1** |
| major 1 件 | **-5** |
| non-translation | **-25**（severity によらず固定） |

```
例: major 2 件 + minor 3 件 → スコア = 2×(-5) + 3×(-1) = -13
    エラーなし             → スコア = 0（最良）
    non-translation        → スコア = -25（最悪級）
```

このスコアから読み取れること:

- **0 に近いほど高品質**。major は minor の 5 倍のペナルティなので、「minor が多い訳」より
  「major が 1 つある訳」のほうが深刻、という MQM の価値判断が数値に反映される。
- セグメントスコアを束ねると **seg レベル**（文単位の品質分布）、システム/文書ごとに合算すると
  **sys レベル**（MT システム間・マニュアル間の優劣比較）の評価になる
  （[meta-evaluation.md](meta-evaluation.md)）。
- スコアだけでなく `category` の分布を見ると**改善の方向**が分かる: accuracy 系が多ければ
  訳の意味自体が危うい（人手レビュー必須）、terminology 系が多ければ用語集の整備で改善しうる、
  fluency/style 系のみなら意味は通っている、という切り分けができる。
- `is_source_error: yes` が多い場合は、翻訳ではなく**原文（入力データ）側の品質問題**を疑う。

## 関連ドキュメント

- [architecture.md](architecture.md) — 3 ステージ構成と討論ラウンドの進行
- [data-format.md](data-format.md) — アノテーションを含む入出力 JSON の全体スキーマ
- [prompts-and-fewshot.md](prompts-and-fewshot.md) — 用語定義の実体であるプロンプトの所在
- [meta-evaluation.md](meta-evaluation.md) — スコア化と相関評価・プロバイダ間一致率
