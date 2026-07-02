# データ形式リファレンス

各ステージの入出力ファイル形式を定義する。再現・デバッグ時の参照用。

## 入力: `data/input.{lp}.{system}_v2.txt`

タブ区切り・1 行 1 セグメント。

```
<source segment>\t<target segment>\t<annotated>
```

| 列 | 内容 |
|---|---|
| source segment | 原文（`lp` のソース言語） |
| target segment | 訳文（`lp` のターゲット言語） |
| annotated | `yes` / `no`。`no` はアノテーションをスキップし、Stage1 出力に `"None"` を書く |

- `lp`: `zh-en` / `en-de` / `he-en`、および `ja-{lang}`（`ja-zh-Hans` 等の複合ロケール可）
- `system`: MT システム名（例 `ANVITA`, `GPT4-5shot`, `refA`, `synthetic_ref`。ja 診断ではマニュアル ID）

### 手順書 JSON から生成する場合（`code/prepare_input.py`・Issue #50）

- 評価対象セグメント: 手順書 `title` / `mainSteps[i].title` / `mainSteps[i].detailedSteps[j].description` / 同 `.notes`（空はスキップ）
- **description 等の改行は単一スペースへ正規化して 1 セグメント**として扱う（ja と対象言語で
  行数が異なるとアラインメントが壊れるため分割しない。論文の segment 定義も複数文を許容）
- ja と対象言語は**構造パスで対応付け**。片側欠落は warning を出してスキップ
- 付随して `data/input.ja-{lang}.{manual_id}_v2.map.tsv` を生成:

```
line_no <TAB> path <TAB> kind
0       title                                    title
1       mainSteps[0].title                       title
2       mainSteps[0].detailedSteps[0].description description
```

`line_no`（0 始まり）は Stage1 出力 `{id}_v1.json` の id と一致し、メタ評価でのセグメント追跡に使う。

## Stage1 出力: `data/output_{lp}_{system}_{version}/{id}_v1.json`

- ファイル名の `{id}` は入力行インデックス（0 始まり）。
- `annotated == "no"` のサンプルは、中身が文字列 `"None"` の JSON（`"None"`）になる。
- 通常サンプルは `Debate.save_file` を整形した dict。主なキー:

| キー | 内容 |
|---|---|
| `start_time` / `end_time` | 実行時刻 |
| `model_name` / `temperature` | モデル・温度 |
| `num_players` | プレイヤー数（4 次元 + Judge = 5） |
| `success` | 正常完了フラグ |
| `src_lng` / `tgt_lng` | 言語表示名（例 `Chinese` / `English`） |
| `source_segment` / `target_segment` | 原文・訳文 |
| `accuracy_annotations` … `style_annotations` | プロンプトテンプレート由来のフィールド（`stage1.json` のキー） |
| `analysis` | Judge の分析文（`judge_ans` から統合） |
| `annotations` | **最終 MQM アノテーション配列**（Judge 統合結果） |
| `players` | 各プレイヤー名 → チャット履歴（`memory_lst`）の辞書 |

`annotations`（および Stage2&3 の出力）の 1 要素:

```json
{
  "error_span": "<訳文中のスパン。non-translation の場合は 'all'>",
  "category": "<{category}/{subcategory} または non-translation>",
  "severity": "<minor | major>",
  "is_source_error": "<yes | no>"
}
```

> 各次元エージェントの実アノテーションは `players["Accuracy Agent"][-1]["content"]` 等（履歴の末尾）に
> 入る。Stage2&3 はここを入力に取る。

## Stage2&3 出力: `data/stage2_3_{lp}_{system}/{i}_v1.json`

`response_dict` を書き出した dict。

| キー | 内容 |
|---|---|
| `source` / `target` | 原文・訳文 |
| `Accuracy` / `Fluency` / `Terminology` / `Style` | 各次元の討論後アノテーション（`{"annotations":[...]}`） |
| `judge` | 統合 Judge による最終アノテーション（`{"annotations":[...]}`） |

- 既に非空の出力があるサンプルはスキップ（再開可能）。
- 入力サンプルが `"None"` の場合は空ファイルを残す。

## メタ評価スコア: `metrics_scores/{metric}_{lp}.{seg,sys}.score`

タブ区切り。`{metric}` は `M-MAD` / `GEMBA-DA` / `GEMBA-MQM` / `EAPrompt` 等、`{lp}` は言語ペア。

- `.seg.score`（セグメントレベル）: `<system>\t<score>` を全セグメント分（1 行 1 セグメント）。
  ```
  ANVITA	-17
  ANVITA	-15
  ```
- `.sys.score`（システムレベル）: `<system>\t<score>` を 1 システム 1 行。
  ```
  ANVITA	-6484.5
  GPT4-5shot	-1602.6
  ```

スコアは MQM ペナルティに基づく負値（major/minor の重み付き和）。算出は
[meta-evaluation.md](meta-evaluation.md) を参照。
