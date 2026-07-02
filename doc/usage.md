# 実行ガイド（end-to-end）

入力準備 → Stage1 → Stage2&3 → メタ評価の一連の流れをまとめる。環境構築・プロバイダ設定は
[../README.md](../README.md) と [configuration.md](configuration.md) を参照。入出力の詳細な仕様は
[data-format.md](data-format.md)。

## 0. 前提

```bash
uv sync                 # ランタイム依存を導入（Python 3.10）
cp .env.example .env    # LLM プロバイダを設定（例: vertex / gemini / openai）
```

`uv run <cmd>` で仮想環境内のコマンドを実行する。スクリプトはリポジトリ内のどのディレクトリからでも
実行できる（パスはスクリプト位置基準で解決）。

## 1. 入力データ

`data/input.{lp}.{system}_v2.txt`（タブ区切り: `source <TAB> target <TAB> annotated(yes/no)`）。
`annotated == "no"` の行はアノテーションをスキップし `"None"` を書き出す。形式の詳細は
[data-format.md](data-format.md)。

- `lp`: 言語ペア（`zh-en` / `en-de` / `he-en`、および ja→多言語診断の `ja-{lang}`。`ja-zh-Hans` 等の複合ロケール可）
- `system`: MT システム名（例: `ANVITA`, `GPT4-5shot`, `refA`, `synthetic_ref` …。ja 診断ではマニュアル ID）

### 1b. 手順書 JSON からの入力生成（ja→多言語診断・Issue #50）

`.input/<manual_id>/{manual_id}-{lang}.json`（原文 `*-ja.json`＋翻訳）から Stage1 入力を生成する:

```bash
uv run python code/prepare_input.py                        # .input 配下の全マニュアル×全言語
uv run python code/prepare_input.py -m <manual_id> -l en vi my   # マニュアル・言語を指定
```

→ `data/input.ja-{lang}.{manual_id}_v2.txt`（本体）と `…_v2.map.tsv`（セグメント対応表）を生成。
生成物は `.gitignore` 済み（元データ同様コミットしない）。詳細は [data-format.md](data-format.md)。

## 2. Stage 1（Dimension Partition）

```bash
sh run_stage1.sh
```

`run_stage1.sh` は `stage1.sh <system> <lp> <start> <version>` を呼ぶ。直接指定する場合:

```bash
sh stage1.sh ANVITA "zh-en" 0 v1
# 直接 Python: uv run python code/stage1.py -i <input.txt> -o <out_dir> -lp <lp> [-s <start>] [-m <model>]
```

| 引数 | 意味 |
|---|---|
| `<system>` | MT システム名 |
| `<lp>` | 言語ペア |
| `<start>` | 入力ファイルの開始行 |
| `<version>` | 出力ディレクトリのサフィックス（例 `v1`） |

- 出力: `data/output_{lp}_{system}_{version}/{id}_v1.json`（4 次元 + Judge の結果と全履歴）。
- API キー・モデル・プロバイダは `.env` から読み込まれる（`-k` は任意）。

## 3. Stage 2 & 3（Multi-Agent Debate + Final Judgment）

```bash
sh run_stage2_3.sh
# 直接: uv run python code/stage2_3.py <system> <lp> <starting> <ending>
#   例: uv run python code/stage2_3.py synthetic_ref "zh-en" 0 1000
#   ending=2000 を渡すと入力全件を対象にする
```

- 入力: `data/output_{lp}_{system}_v1/`（Stage1 出力）。
- 出力: `data/stage2_3_{lp}_{system}/{i}_v1.json`（討論後の最終アノテーション）。
- 既に非空の出力があるサンプルはスキップ（再開可能）。

## 4. メタ評価

`wmt23_metrics.ipynb` を実行して seg / sys レベル相関を算出する。詳細と依存導入は
[meta-evaluation.md](meta-evaluation.md)。

```bash
uv sync --group eval    # numpy / mt-metrics-eval を追加導入（手順4のみで必要）
```

## つまずきやすい点

- **プロバイダ未設定**: `.env` が無い / キー不正だと LLM 呼び出しで失敗する（[configuration.md](configuration.md)）。
- **失敗サンプルの欠落**: 例外は握りつぶさずログ出力される。件数が合わない場合はログの `[error]`/`[warn]` を確認。
- **出力先**: 生成物はすべて `data/` 配下（`data/output_*` / `data/stage2_3_*`）。`.gitignore` 済み。
