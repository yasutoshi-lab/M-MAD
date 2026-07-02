"""手順書 JSON から Stage1 入力（タブ区切り）を生成する前処理（Issue #50）。

`.input/<manual_id>/{manual_id}-{lang}.json`（原文 `*-ja.json`＋翻訳）を読み、
ja と対象言語のセグメントを構造パスで対応付けて、Stage1 の入力形式
`source <TAB> target <TAB> annotated(yes/no)` を書き出す。

出力（既存パイプラインの命名規約 `data/input.{lp}.{system}_v2.txt` に適合。system = manual_id）:
    {out_dir}/input.ja-{lang}.{manual_id}_v2.txt      … `ja_text<TAB>x_text<TAB>yes`
    {out_dir}/input.ja-{lang}.{manual_id}_v2.map.tsv  … `line_no<TAB>path<TAB>kind`
                                                        （line_no は 0 始まり＝Stage1 出力 {id}_v1.json と一致）

評価対象セグメント: トップ `title` / `mainSteps[i].title` /
`mainSteps[i].detailedSteps[j].description` / 同 `.notes`。
description 等に含まれる改行は単一スペースへ正規化し 1 セグメントとして扱う
（ja と対象言語で行数が異なるとアラインメントが壊れるため分割しない）。

実行例:
    uv run python code/prepare_input.py                    # .input 配下の全マニュアル×全言語
    uv run python code/prepare_input.py -m <manual_id> -l en vi my
"""

import argparse
import json
import os


def flatten_text(text):
    """改行・タブ・連続空白を単一スペースへ正規化する。

    タブ区切り入力（1 行 1 セグメント）にセグメントを収めるための正規化。

    Args:
        text (str): 元テキスト。

    Returns:
        str: 正規化済みテキスト（空白のみなら空文字列）。
    """
    return " ".join(text.split())


def extract_segments(manual):
    """手順書 dict から評価対象セグメントを構造パス付きで抽出する。

    対象は `title` / `mainSteps[i].title` / `mainSteps[i].detailedSteps[j].description` /
    同 `.notes`。flatten 後に空になるテキストはスキップする。

    Args:
        manual (dict): 手順書 JSON（トップレベル dict）。

    Returns:
        list[tuple[str, str]]: (構造パス, 正規化済みテキスト) のリスト（文書順）。
    """
    segments = []

    def add(path, text):
        if text is None:
            return
        flat = flatten_text(str(text))
        if flat:
            segments.append((path, flat))

    add("title", manual.get("title"))
    for i, step in enumerate(manual.get("mainSteps") or []):
        add(f"mainSteps[{i}].title", step.get("title"))
        for j, detail in enumerate(step.get("detailedSteps") or []):
            add(f"mainSteps[{i}].detailedSteps[{j}].description", detail.get("description"))
            add(f"mainSteps[{i}].detailedSteps[{j}].notes", detail.get("notes"))
    return segments


def build_pairs(ja_manual, x_manual):
    """ja と対象言語の手順書を構造パスで対応付けてペアを作る。

    片側にしか存在しない（または片側が空の）パスはペアにせずスキップとして返す。

    Args:
        ja_manual (dict): 原文（ja）の手順書 JSON。
        x_manual (dict): 対象言語の手順書 JSON。

    Returns:
        tuple[list[tuple[str, str, str]], list[str]]:
            (path, ja_text, x_text) のリストと、スキップした path のリスト。
    """
    ja_segments = extract_segments(ja_manual)
    x_map = dict(extract_segments(x_manual))

    pairs = []
    skipped = []
    for path, ja_text in ja_segments:
        x_text = x_map.get(path)
        if x_text:
            pairs.append((path, ja_text, x_text))
        else:
            skipped.append(path)
    ja_paths = {path for path, _ in ja_segments}
    skipped.extend(path for path in x_map if path not in ja_paths)
    return pairs, skipped


def discover_manual_ids(input_dir):
    """input_dir 配下から `{manual_id}-ja.json` を持つマニュアル ID を列挙する。"""
    ids = []
    for name in sorted(os.listdir(input_dir)):
        subdir = os.path.join(input_dir, name)
        if os.path.isdir(subdir) and os.path.exists(os.path.join(subdir, f"{name}-ja.json")):
            ids.append(name)
    return ids


def discover_langs(input_dir, manual_id):
    """マニュアルディレクトリの `{manual_id}-{lang}.json` から対象言語（ja 以外）を列挙する。"""
    prefix = f"{manual_id}-"
    langs = []
    for name in sorted(os.listdir(os.path.join(input_dir, manual_id))):
        if name.startswith(prefix) and name.endswith(".json"):
            lang = name[len(prefix):-len(".json")]
            if lang != "ja":
                langs.append(lang)
    return langs


def process_manual(input_dir, manual_id, langs, out_dir):
    """1 マニュアルについて指定言語ぶんの Stage1 入力と map.tsv を書き出す。

    Args:
        input_dir (str): `.input` 相当のルートディレクトリ。
        manual_id (str): マニュアル ID（サブディレクトリ名）。
        langs (list[str]): 対象言語コード（ja 除く）。
        out_dir (str): 出力先ディレクトリ。

    Returns:
        None
    """
    subdir = os.path.join(input_dir, manual_id)
    with open(os.path.join(subdir, f"{manual_id}-ja.json"), encoding="utf-8") as f:
        ja_manual = json.load(f)

    for lang in langs:
        x_path = os.path.join(subdir, f"{manual_id}-{lang}.json")
        if not os.path.exists(x_path):
            print(f"[warn] {manual_id}: {lang} の JSON が無いためスキップ")
            continue
        with open(x_path, encoding="utf-8") as f:
            x_manual = json.load(f)

        pairs, skipped = build_pairs(ja_manual, x_manual)
        for path in skipped:
            print(f"[warn] {manual_id} ja-{lang}: 片側欠落のためスキップ: {path}")

        base = os.path.join(out_dir, f"input.ja-{lang}.{manual_id}_v2")
        with open(f"{base}.txt", "w", encoding="utf-8") as f:
            for _, ja_text, x_text in pairs:
                f.write(f"{ja_text}\t{x_text}\tyes\n")
        with open(f"{base}.map.tsv", "w", encoding="utf-8") as f:
            f.write("line_no\tpath\tkind\n")
            for line_no, (path, _, _) in enumerate(pairs):
                kind = path.rsplit(".", 1)[-1] if "." in path else path
                f.write(f"{line_no}\t{path}\t{kind}\n")
        print(f"[ok] {manual_id} ja-{lang}: {len(pairs)} segments"
              + (f"（{len(skipped)} skipped）" if skipped else ""))


def parse_args():
    """CLI 引数を解析して返す。"""
    parser = argparse.ArgumentParser(
        description="手順書 JSON から Stage1 入力（タブ区切り）を生成する",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("-i", "--input-dir", type=str, default=".input", help="手順書 JSON のルートディレクトリ")
    parser.add_argument("-m", "--manual-id", type=str, nargs="*", default=None,
                        help="対象マニュアル ID（省略時は input-dir 配下を自動検出）")
    parser.add_argument("-l", "--langs", type=str, nargs="*", default=None,
                        help="対象言語コード（省略時は JSON ファイル名から自動検出・ja 除く）")
    parser.add_argument("-o", "--out-dir", type=str, default="data", help="出力先ディレクトリ")
    return parser.parse_args()


def main():
    """全マニュアル×全言語の Stage1 入力を生成するエントリポイント。"""
    args = parse_args()
    manual_ids = args.manual_id or discover_manual_ids(args.input_dir)
    if not manual_ids:
        raise SystemExit(f"[error] {args.input_dir} に処理対象のマニュアルが見つからない")
    os.makedirs(args.out_dir, exist_ok=True)
    for manual_id in manual_ids:
        langs = args.langs or discover_langs(args.input_dir, manual_id)
        process_manual(args.input_dir, manual_id, langs, args.out_dir)


if __name__ == "__main__":
    main()
