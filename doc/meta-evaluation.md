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

## 参考

- mt-metrics-eval: https://github.com/google-research/mt-metrics-eval
- WMT-23 Metrics Shared Task: https://wmt-metrics-task.github.io/
