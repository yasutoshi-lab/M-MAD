# メタ評価ガイド

Stage2&3 で得た MQM アノテーションを WMT-23 の人手評価と突き合わせ、メトリクスの
**seg（セグメント）/ sys（システム）レベル相関**を算出する手順。

## 依存の導入

メタ評価専用の依存は optional な `eval` グループに分離されている（通常の Stage1/2&3 には不要）。

```bash
uv sync --group eval
# 導入されるもの: numpy, mt-metrics-eval（git+https://github.com/google-research/mt-metrics-eval）
```

- `mt-metrics-eval` は PyPI に無く git から取得するため、初回はネットワークが必要。
- CI（GitHub Actions）では `eval` グループを導入しない（重い git 依存を避けるため）。

## 実行

`wmt23_metrics.ipynb` を実行する（Jupyter / VS Code / `uv run jupyter` 等）。ノートブックは
`google-research/mt-metrics-eval` の評価ツールで WMT-23 の 3 言語ペア（`zh-en` / `en-de` / `he-en`）を
評価する。

大まかな流れ:
1. `mt_metrics_eval` の `EvalSet` を各言語ペアで読み込む。
2. `metrics_scores/{metric}_{lp}.{seg,sys}.score` を新規メトリクスとして取り込む
   （`EvalSet.AddMetricsFromDir()` 等）。
3. seg / sys レベルの相関を算出し、他メトリクス（GEMBA-DA / GEMBA-MQM / EAPrompt）と比較する。

> ノートブック内にはローカルパス（`os.chdir(...)`）が残っている場合がある。実行環境に合わせて
> リポジトリルートへ調整すること。

## スコアファイルの用意

Stage2&3 の出力（`data/stage2_3_{lp}_{system}/`）から、MQM ペナルティを集計して
`metrics_scores/M-MAD_{lp}.{seg,sys}.score` を生成する。形式は [data-format.md](data-format.md) を参照。

- seg: `<system>\t<score>`（1 行 1 セグメント）
- sys: `<system>\t<score>`（1 システム 1 行）
- スコアは major/minor の重み付き和に基づく負のペナルティ。

## スコアファイルの読み方（何が分かるか）

スコアは MQM ペナルティの合計で、**0 が最良（エラーなし）、負に大きいほど低品質**。
1 セグメントの重みは minor=-1 / major=-5 / non-translation=-25
（Freitag et al. 2021 / WMT 標準。用語の定義は [mqm-glossary.md](mqm-glossary.md)）。

### `.seg.score`（セグメントレベル）

1 行 = 1 セグメントのペナルティ。行番号は入力ファイルの行順（ja 診断ではさらに
`*.map.tsv` の `line_no` で手順書の構造パスに引き当てられる）。ここから分かること:

- **どの文が悪いか**: スコアが負に大きい行が要修正セグメント。`-25` は non-translation
  （訳が崩壊 or Judge パース失敗）なので最優先で人手確認する。
- **品質の分布**: 「平均は良いが -10 以下が数件ある」のか「全体に -1〜-3 が薄く広がる」のかで
  対処が変わる（前者は個別修正、後者は全体的な訳調・用語の見直し）。
- **具体的なエラー内容**: スコアは件数×重みの集約値なので、「なぜこの点数か」は同じ id の
  `data/stage2_3_{lp}_{system}/{i}_v1.json` の `annotations`（error_span / category / severity）
  まで戻って確認する。

### `.sys.score`（システムレベル）

1 行 = 1 システム（MT システム / マニュアル）の合計ペナルティ。**同一入力セット内での
順位比較**に使う（例: `ANVITA -6484.5` より `GPT4-5shot -1602.6` のほうが高品質）。

- 合計値はセグメント数に比例して大きくなるため、**セグメント数が異なる入力間で絶対値を
  比較しない**こと。規模が違う場合はセグメント平均に直して比べる。
- 数値そのものに絶対的な合否基準はない。「同条件で訳したシステム間の相対比較」と
  「同一システムの経時比較（改善したか）」が主用途。

### 相関（メタ評価の本体）が示すもの

`wmt23_metrics.ipynb` が算出する相関は、**M-MAD のスコアが WMT-23 の人手 MQM 評価と
どれだけ整合するか**＝「LLM 審査員としての信頼度」を測るもので、翻訳の品質そのものではない。

- **sys レベル相関**: システムの優劣順位を人手評価と同じ向きに付けられるか（ranking の妥当性）。
- **seg レベル相関**: 文単位の良し悪しまで人手と一致するか（より難しい。細粒度診断に使えるかの目安）。
- 相関が高いほど、そのメトリクス（M-MAD 設定・モデル）の自動評価を人手評価の代理として
  信頼できる。GEMBA-DA / GEMBA-MQM / EAPrompt との比較は「同じ LLM 系メトリクスの中での
  相対的な位置」を示す。

## プロバイダ間一致率レポート（run-level jury・Issue #56）

run-level jury（#55）で生成したプロバイダ別出力を突合し、**並記スコアと一致率等の記述統計**を
出力する読み取り専用の分析（本ノートブックと同格の後処理層）。**統合スコアは算出しない**
（論文準拠のレベル 1 運用。結論の統合・解釈は Curator が行う）。

```bash
uv run python code/jury_report.py -s <system> -lp <lp> -p openai anthropic vertex
# → data/jury_report.{lp}.{system}.md / .csv（gitignore 済み）
```

- セグメントスコアの重み: minor=-1 / major=-5 / non-translation=-25（Freitag et al. 2021 / WMT 標準）
- Stage1 が `success:false`（API 全滅・#52）のセグメントと judge がパース不能なセグメントは
  除外として明示（除外数はサマリ表に出る）
- 出力: プロバイダ別サマリ（平均スコア・severity 分布）/ ペア間統計（Spearman ρ・
  エラー有無一致率・Cohen's κ）/ 不一致セグメント列挙（人手確認の優先対象）
- **読み方**: 一致率が高い言語は診断結果が頑健。低い言語は「訳が悪い」のではなく
  「judge がその言語で信頼できない」可能性を示す（judge 依存のシグナル）

## 参考

- mt-metrics-eval: https://github.com/google-research/mt-metrics-eval
- WMT-23 Metrics Shared Task: https://wmt-metrics-task.github.io/
