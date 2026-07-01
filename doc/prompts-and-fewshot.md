# プロンプトと few-shot

プロンプトの所在・置換の仕組みと、few-shot デモ（4-shot）の構造・言語ペア追加手順をまとめる。

## プロンプトの所在

| 用途 | 場所 |
|---|---|
| Stage1 の全プロンプト | `code/utils/stage1.json`（テンプレート。`##placeholder##` を置換して使用） |
| Stage2&3 のプロンプト | `code/stage2_3.py` にモジュール定数として直書き（`system_prompts` / `user_prompt` / `judge_prompt` / `judge_system_prompt` / `judge_agent`） |

### `stage1.json` のキー
`base_system_prompt` / `accuracy_agent` / `fluency_agent` / `term_agent` / `style_agent` /
`judge_system_prompt` / `judge_agent`、および置換対象フィールド
（`source_segment` / `target_segment` / `src_lng` / `tgt_lng` / `*_annotations`）。

### プレースホルダ置換
`Debate.init_prompt()`（`code/stage1.py`）が各エージェントプロンプト内の
`##src_lng##` / `##tgt_lng##` / `##source_segment##` / `##target_segment##` を実値へ置換する。
Judge には 4 次元のアノテーション（`##accuracy_annotations##` 等）も差し込む。

## few-shot（4-shot demonstration strategy）

論文の Stage1 は **4-shot**（各次元 3 例 + non-translation 1 例）を採用する。実装では言語ペア別に
モジュールを分けている。

| モジュール | 対象言語ペア | ソース→ターゲット |
|---|---|---|
| `code/few_shot_demos.py` | `zh-en` | Chinese → English |
| `code/few_shot_demos_de.py` | `en-de` | English → German |
| `code/few_shot_demos_he.py` | `he-en` | Hebrew → English |

各モジュールが export する変数（同一インターフェース）:
`accuracy_user_shot` / `accuracy_mem_shot`、`fluency_*`、`term_*`、`style_*`（各 3 例）、
`nontran_user_shot` / `nontran_mem_shot`（non-translation 例）。`*_user_shot` は user 発話、
`*_mem_shot` は対応する期待アノテーション（assistant）。

### 選択ロジック（`stage1.py:load_few_shots`）
言語ペアから使用モジュールを解決する。解決順:
1. **完全一致ペア**（`DEMO_MODULE_BY_PAIR`）: `zh-en`→`few_shot_demos`、`en-de`→`few_shot_demos_de`、
   `he-en`→`few_shot_demos_he`
2. **ターゲット言語デフォルト**（`DEMO_MODULE_BY_TARGET`）: target `en`→`few_shot_demos`、`de`→`few_shot_demos_de`
3. **English 系デフォルト**（`DEFAULT_DEMO_MODULE` = `few_shot_demos`）

2/3 に落ちた場合（専用デモ無し）は warning を出す。フォールバックはソース言語が一致しないため、
論文が意図する「同一言語ペアの 4-shot」とは非整合になる点に注意。

## 言語ペアを追加する手順

新しい言語ペア（例 `de-en`）に**論文整合**の few-shot を用意する場合:

1. `code/few_shot_demos_<name>.py` を新規作成し、既存モジュールと**同じ変数名**で 4-shot を定義する
   （WMT MQM 由来の例が望ましい。`user_template` に `src_lng` / `tgt_lng` を指定）。
2. `code/stage1.py` の `DEMO_MODULE_BY_PAIR`（必要なら `DEMO_MODULE_BY_TARGET`）にマッピングを追加。
3. Stage2&3 は `code/stage2_3.py` の `system_prompts` を使う。言語名は `get_language_names(lp)` が
   `langcodes` で導出するため、対応言語なら追加不要。
4. `tests/test_stage1.py::TestLoadFewShots` にケースを追加し、フォールバック warning が出ないことを確認。

> 21 言語規模での few-shot データ整備は Issue #18 で追跡している。フォールバックのままでも
> クラッシュはしないが、論文整合性の観点では各ペア専用の 4-shot 用意が望ましい。

関連: [architecture.md](architecture.md)（Stage1 の位置づけ）、[data-format.md](data-format.md)
（アノテーションの JSON 形）。
