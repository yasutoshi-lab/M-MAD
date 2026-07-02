"""プロバイダ間一致率レポート: 並記スコアと記述統計の集計（Issue #56）。

run-level jury（Issue #55）で生成したプロバイダ別の Stage2&3 出力を読み取り専用で突合し、
プロバイダ別スコアの並記表と一致率等の**記述統計**を Markdown / CSV で出力する。
**統合スコア（平均・多数決等の単一評価値）は算出しない**（論文準拠のレベル 1 運用。
3 つの独立した測定結果の「関係」を記述するのみで、結論の統合は Curator が行う）。

スコア重みは Freitag et al. 2021 (TACL) / WMT の MQM 標準:
    minor = -1 / major = -5 / non-translation = -25

入力（読み取りのみ）:
    data/stage2_3_{lp}_{system}_{provider}/{i}_v1.json   … 最終アノテーション（judge）
    data/output_{lp}_{system}_{provider}/{i}_v1.json     … Stage1 の success / api_failures（#52）
    data/input.{lp}.{system}_v2.map.tsv                  … （あれば）セグメント→構造パス対応

実行例:
    uv run python code/jury_report.py -s <manual_id> -lp ja-en -p openai anthropic vertex
"""

import argparse
import csv
import json
import os

MAD_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Freitag et al. 2021 / WMT 標準の MQM 重み
MQM_WEIGHTS = {"non-translation": -25, "major": -5, "minor": -1}

# 不一致セグメントとして列挙するスコア差の閾値（major 1 件ぶん）
DISAGREEMENT_SCORE_GAP = 5


def mqm_score(annotations):
    """アノテーション配列から MQM セグメントスコアを算出する。

    non-translation は severity によらず -25、それ以外は major=-5 / その他=-1。

    Args:
        annotations (list[dict]): 最終アノテーション配列。

    Returns:
        int: セグメントスコア（0 以下）。
    """
    score = 0
    for ann in annotations:
        if str(ann.get("category", "")).strip() == "non-translation":
            score += MQM_WEIGHTS["non-translation"]
        elif str(ann.get("severity", "")).strip().lower() == "major":
            score += MQM_WEIGHTS["major"]
        else:
            score += MQM_WEIGHTS["minor"]
    return score


def parse_final_annotations(judge_value):
    """Stage2&3 出力の judge フィールドから最終アノテーション配列を防御的に取り出す。

    Args:
        judge_value: dict（`annotations` キー）/ JSON 文字列 / その他。

    Returns:
        list | None: アノテーション配列。解釈できない場合は None。
    """
    if isinstance(judge_value, dict) and isinstance(judge_value.get("annotations"), list):
        return judge_value["annotations"]
    if isinstance(judge_value, str):
        try:
            parsed = json.loads(judge_value)
        except (json.JSONDecodeError, ValueError):
            return None
        if isinstance(parsed, dict) and isinstance(parsed.get("annotations"), list):
            return parsed["annotations"]
    return None


def severity_counts(annotations):
    """severity 別（minor / major / non-translation）の件数を数える。"""
    counts = {"minor": 0, "major": 0, "non-translation": 0}
    for ann in annotations:
        if str(ann.get("category", "")).strip() == "non-translation":
            counts["non-translation"] += 1
        elif str(ann.get("severity", "")).strip().lower() == "major":
            counts["major"] += 1
        else:
            counts["minor"] += 1
    return counts


def _ranks(values):
    """同順位を平均ランクで扱うランク列を返す。"""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg_rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    return ranks


def spearman(xs, ys):
    """Spearman 順位相関係数（同順位は平均ランク）。

    Returns:
        float | None: 相関係数。要素数 < 2 またはいずれかの分散が 0 なら None。
    """
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    rank_x, rank_y = _ranks(xs), _ranks(ys)
    mean_x = sum(rank_x) / len(rank_x)
    mean_y = sum(rank_y) / len(rank_y)
    cov = sum((a - mean_x) * (b - mean_y) for a, b in zip(rank_x, rank_y))
    var_x = sum((a - mean_x) ** 2 for a in rank_x)
    var_y = sum((b - mean_y) ** 2 for b in rank_y)
    if var_x == 0 or var_y == 0:
        return None
    return cov / (var_x * var_y) ** 0.5


def cohen_kappa(a, b):
    """二値判定列の Cohen's κ。

    Returns:
        float | None: κ。期待一致率が 1（両者とも定数）の退化ケースは None。
    """
    if len(a) != len(b) or not a:
        return None
    n = len(a)
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    pa = sum(a) / n
    pb = sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    if pe == 1:
        return None
    return (po - pe) / (1 - pe)


def load_provider_results(lang_pair, system, provider, data_dir=None):
    """1 プロバイダぶんの結果を読み込み、セグメント ID → 結果 dict を返す。

    Stage1 の success:false（API 全滅・#52）と judge のパース不能は excluded に理由を入れ、
    統計から除外できるようにする。

    Args:
        lang_pair (str): 言語ペア。
        system (str): システム名。
        provider (str): プロバイダ名（ディレクトリサフィックス）。
        data_dir (str, optional): data ディレクトリ（省略時はリポジトリの data/）。

    Returns:
        dict[int, dict]: {id: {score, has_error, counts, excluded, source, target}}。
    """
    data_dir = data_dir or os.path.join(MAD_PATH, "data")
    stage2_dir = os.path.join(data_dir, f"stage2_3_{lang_pair}_{system}_{provider}")
    stage1_dir = os.path.join(data_dir, f"output_{lang_pair}_{system}_{provider}")

    results = {}
    if not os.path.isdir(stage2_dir):
        return results
    for name in sorted(os.listdir(stage2_dir)):
        stem = name.split("_v1.json")[0]
        if not (name.endswith("_v1.json") and stem.isdigit()):
            continue
        seg_id = int(stem)
        with open(os.path.join(stage2_dir, name), encoding="utf-8") as f:
            try:
                data = json.load(f)
            except (json.JSONDecodeError, ValueError):
                data = None

        excluded = None
        stage1_path = os.path.join(stage1_dir, name)
        if os.path.exists(stage1_path):
            with open(stage1_path, encoding="utf-8") as f:
                try:
                    stage1_data = json.load(f)
                except (json.JSONDecodeError, ValueError):
                    stage1_data = None
            if isinstance(stage1_data, dict) and not stage1_data.get("success", True):
                excluded = "stage1 success:false（API 全滅・#52）"

        annotations = parse_final_annotations(data.get("judge")) if isinstance(data, dict) else None
        if annotations is None and excluded is None:
            excluded = "judge のパース不能"

        results[seg_id] = {
            "score": mqm_score(annotations) if annotations is not None else None,
            "has_error": bool(annotations) if annotations is not None else None,
            "counts": severity_counts(annotations or []),
            "excluded": excluded,
            "source": (data or {}).get("source", "") if isinstance(data, dict) else "",
            "target": (data or {}).get("target", "") if isinstance(data, dict) else "",
        }
    return results


def load_segment_paths(lang_pair, system, data_dir=None):
    """map.tsv（prepare_input.py の出力）があれば line_no → 構造パスの dict を返す。"""
    data_dir = data_dir or os.path.join(MAD_PATH, "data")
    map_path = os.path.join(data_dir, f"input.{lang_pair}.{system}_v2.map.tsv")
    paths = {}
    if not os.path.exists(map_path):
        return paths
    with open(map_path, encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            try:
                paths[int(row["line_no"])] = row["path"]
            except (KeyError, ValueError):
                continue
    return paths


def build_report(lang_pair, system, providers, results_by_provider, segment_paths=None):
    """並記表・ペア間統計・不一致列挙を含む Markdown と CSV 行を組み立てる。

    Args:
        lang_pair (str): 言語ペア。
        system (str): システム名。
        providers (list[str]): プロバイダ名（表示順）。
        results_by_provider (dict[str, dict[int, dict]]): load_provider_results の結果。
        segment_paths (dict[int, str], optional): セグメント ID → 構造パス。

    Returns:
        tuple[str, list[list]]: (Markdown 文字列, CSV 行リスト（ヘッダ含む）)。
    """
    segment_paths = segment_paths or {}
    all_ids = sorted({i for r in results_by_provider.values() for i in r})
    # 全プロバイダで有効（存在し・除外されていない）な共通セグメント
    common_ids = [i for i in all_ids
                  if all(i in results_by_provider[p] and results_by_provider[p][i]["excluded"] is None
                         for p in providers)]

    lines = [
        f"# プロバイダ間一致率レポート: {lang_pair} / {system}",
        "",
        "> 本レポートは **記述統計** であり、統合スコア（平均・多数決等の単一評価値）は算出しない",
        "> （論文準拠のレベル 1 運用）。結論の統合・解釈は Curator が行う。",
        f"> MQM 重み: minor={MQM_WEIGHTS['minor']} / major={MQM_WEIGHTS['major']} / "
        f"non-translation={MQM_WEIGHTS['non-translation']}（Freitag et al. 2021 / WMT 標準）",
        "",
        f"- 全セグメント: {len(all_ids)} / 共通有効セグメント: {len(common_ids)}"
        "（除外＝Stage1 API 全滅 or judge パース不能）",
        "",
        "## プロバイダ別サマリ（共通有効セグメント上）",
        "",
        "| provider | 有効 | 除外 | 平均スコア | minor | major | non-translation | エラー有りセグメント |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for provider in providers:
        res = results_by_provider[provider]
        excluded_n = sum(1 for r in res.values() if r["excluded"] is not None)
        scores = [res[i]["score"] for i in common_ids]
        mean_score = sum(scores) / len(scores) if scores else 0.0
        counts = {"minor": 0, "major": 0, "non-translation": 0}
        for i in common_ids:
            for key in counts:
                counts[key] += res[i]["counts"][key]
        error_segments = sum(1 for i in common_ids if res[i]["has_error"])
        lines.append(
            f"| {provider} | {len(common_ids)} | {excluded_n} | {mean_score:.2f} "
            f"| {counts['minor']} | {counts['major']} | {counts['non-translation']} "
            f"| {error_segments} |")

    lines += ["", "## ペア間の一致統計（共通有効セグメント上）", "",
              "| ペア | Spearman ρ | エラー有無一致率 | Cohen's κ |", "|---|---|---|---|"]
    for idx, p1 in enumerate(providers):
        for p2 in providers[idx + 1:]:
            xs = [results_by_provider[p1][i]["score"] for i in common_ids]
            ys = [results_by_provider[p2][i]["score"] for i in common_ids]
            e1 = [results_by_provider[p1][i]["has_error"] for i in common_ids]
            e2 = [results_by_provider[p2][i]["has_error"] for i in common_ids]
            rho = spearman(xs, ys)
            agree = (sum(1 for a, b in zip(e1, e2) if a == b) / len(e1)) if e1 else None
            kappa = cohen_kappa(e1, e2)
            fmt = lambda v: "n/a" if v is None else f"{v:.3f}"  # noqa: E731
            lines.append(f"| {p1} vs {p2} | {fmt(rho)} | {fmt(agree)} | {fmt(kappa)} |")

    lines += ["", f"## 不一致セグメント（スコア差 ≥ {DISAGREEMENT_SCORE_GAP} または エラー有無不一致）", ""]
    disagreements = []
    for i in common_ids:
        scores = [results_by_provider[p][i]["score"] for p in providers]
        errors = [results_by_provider[p][i]["has_error"] for p in providers]
        if (max(scores) - min(scores) >= DISAGREEMENT_SCORE_GAP) or len(set(errors)) > 1:
            disagreements.append(i)
    if disagreements:
        for i in disagreements:
            any_provider = results_by_provider[providers[0]][i]
            path = segment_paths.get(i, "")
            score_view = " / ".join(f"{p}={results_by_provider[p][i]['score']}" for p in providers)
            lines.append(f"- seg {i}{f'（{path}）' if path else ''}: {score_view}")
            lines.append(f"  - src: {any_provider['source'][:80]}")
            lines.append(f"  - tgt: {any_provider['target'][:80]}")
    else:
        lines.append("（なし）")

    # CSV（全セグメント。除外理由も残す）
    header = ["segment_id", "path"]
    for provider in providers:
        header += [f"{provider}_score", f"{provider}_has_error", f"{provider}_excluded"]
    csv_rows = [header]
    for i in all_ids:
        row = [i, segment_paths.get(i, "")]
        for provider in providers:
            res = results_by_provider[provider].get(i)
            if res is None:
                row += ["", "", "missing"]
            else:
                row += [res["score"], res["has_error"], res["excluded"] or ""]
        csv_rows.append(row)

    return "\n".join(lines) + "\n", csv_rows


def parse_args():
    """CLI 引数を解析して返す。"""
    parser = argparse.ArgumentParser(
        description="プロバイダ別 M-MAD 出力の並記と一致率統計（読み取り専用・統合スコアなし）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("-s", "--system", type=str, required=True, help="MT システム名（ja 診断ではマニュアル ID）")
    parser.add_argument("-lp", "--lang-pair", type=str, required=True, help="言語ペア（例 ja-en）")
    parser.add_argument("-p", "--providers", type=str, nargs="+", required=True,
                        help="突合するプロバイダ名（2 つ以上を推奨）")
    parser.add_argument("-o", "--out-base", type=str, default=None,
                        help="出力パスの接頭辞（省略時 data/jury_report.{lp}.{system}）")
    return parser.parse_args()


def main():
    """レポートを生成し Markdown / CSV を書き出すエントリポイント。"""
    args = parse_args()
    results_by_provider = {}
    for provider in args.providers:
        results = load_provider_results(args.lang_pair, args.system, provider)
        if not results:
            raise SystemExit(
                f"[error] {provider} の出力が無い: "
                f"data/stage2_3_{args.lang_pair}_{args.system}_{provider}（run_jury.py で生成する）")
        results_by_provider[provider] = results

    segment_paths = load_segment_paths(args.lang_pair, args.system)
    markdown, csv_rows = build_report(
        args.lang_pair, args.system, args.providers, results_by_provider, segment_paths)

    out_base = args.out_base or os.path.join(
        MAD_PATH, "data", f"jury_report.{args.lang_pair}.{args.system}")
    with open(f"{out_base}.md", "w", encoding="utf-8") as f:
        f.write(markdown)
    with open(f"{out_base}.csv", "w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(csv_rows)
    print(f"[ok] report → {out_base}.md / {out_base}.csv")
    print(markdown)


if __name__ == "__main__":
    main()
