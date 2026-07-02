"""run-level jury: プロバイダ別に Stage1 → Stage2&3 を独立実行するランナー（Issue #55）。

同一入力に対し、指定した各プロバイダで評価パイプラインを丸ごと独立実行し、
プロバイダ名入りのディレクトリへ出力を分離する。**各 run の内部は単一プロバイダ**であり、
討論・Judge にプロバイダ混成は発生しない（論文準拠のレベル 1 運用）。結果の突合・
一致率レポートは後処理（Issue #56）が担う。

出力:
    data/output_{lp}_{system}_{provider}/      … Stage1 出力
    data/stage2_3_{lp}_{system}_{provider}/    … Stage2&3 出力

.env の前提（jury 実行時）:
    プロバイダ固有のキー変数（OPENAI_API_KEY / ANTHROPIC_API_KEY / GEMINI_API_KEY、
    vertex は GCP_PROJECT + ADC）を設定すること。汎用 LLM_MODEL / LLM_BASE_URL /
    LLM_API_KEY はサブプロセス起動時に空値で上書きされ、各プロバイダの既定へ解決される
    （Issue #47 の空値フォールバック仕様を利用）。

実行例:
    uv run python code/run_jury.py -s <manual_id> -lp ja-en
    uv run python code/run_jury.py -s <manual_id> -lp ja-vi -p openai vertex --ending 5
"""

import argparse
import glob
import json
import os
import subprocess
import sys

MAD_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# プロバイダごとの認証前提（いずれか 1 つが非空なら実行可能とみなす）
PROVIDER_AUTH_VARS = {
    "openai": ("OPENAI_API_KEY",),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "gemini": ("GEMINI_API_KEY",),
    "vertex": ("GCP_PROJECT", "GOOGLE_CLOUD_PROJECT"),
}


def jury_output_dirs(lang_pair, system, provider):
    """プロバイダ別の Stage1 / Stage2&3 出力ディレクトリを返す。

    Args:
        lang_pair (str): 言語ペア（例 ja-en）。
        system (str): MT システム名（ja 診断ではマニュアル ID）。
        provider (str): プロバイダ名（openai / anthropic / gemini / vertex）。

    Returns:
        tuple[str, str]: (Stage1 出力ディレクトリ, Stage2&3 出力ディレクトリ)。
    """
    stage1_dir = os.path.join(MAD_PATH, "data", f"output_{lang_pair}_{system}_{provider}")
    stage2_dir = os.path.join(MAD_PATH, "data", f"stage2_3_{lang_pair}_{system}_{provider}")
    return stage1_dir, stage2_dir


def build_provider_env(provider, base_env):
    """サブプロセス用の環境変数 dict を作る（base_env は変更しない）。

    LLM_PROVIDER を指定プロバイダに設定し、汎用の LLM_MODEL / LLM_BASE_URL / LLM_API_KEY を
    空値で上書きする。空値は「未設定」扱い（Issue #47）のため、各プロバイダの既定モデル・
    既定エンドポイント・プロバイダ固有キーに解決され、.env の汎用値が他プロバイダへ
    波及することを防ぐ。

    Args:
        provider (str): プロバイダ名。
        base_env (dict): ベースとなる環境変数（通常 os.environ）。

    Returns:
        dict: サブプロセスへ渡す環境変数。
    """
    env = dict(base_env)
    env["LLM_PROVIDER"] = provider
    env["LLM_MODEL"] = ""
    env["LLM_BASE_URL"] = ""
    env["LLM_API_KEY"] = ""
    return env


def preflight(provider, environ):
    """プロバイダの認証前提を事前確認する（fail-fast per provider）。

    Args:
        provider (str): プロバイダ名。
        environ (Mapping): 確認対象の環境変数（.env 読込済みを想定）。

    Returns:
        tuple[bool, str]: (実行可能か, メッセージ)。空値のキーは未設定として扱う。
    """
    auth_vars = PROVIDER_AUTH_VARS.get(provider)
    if auth_vars is None:
        return False, f"unknown provider '{provider}'（対応: {sorted(PROVIDER_AUTH_VARS)}）"
    if any(environ.get(v) for v in auth_vars):
        return True, "ok"
    return False, f"{provider}: {' / '.join(auth_vars)} が未設定のためスキップ"


def count_stage1_results(stage1_dir):
    """Stage1 出力の (対象サンプル数, success:false 件数) を数える（Issue #52 の検知）。

    `{id}-config_v1.json`（プロンプト設定）と `"None"`（annotated=no）は対象外。

    Args:
        stage1_dir (str): Stage1 出力ディレクトリ。

    Returns:
        tuple[int, int]: (サンプル数, success:false 件数)。
    """
    total = 0
    failed = 0
    for path in sorted(glob.glob(os.path.join(stage1_dir, "*_v1.json"))):
        if "-config" in os.path.basename(path):
            continue
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            continue
        total += 1
        if not data.get("success", True):
            failed += 1
    return total, failed


def run_provider(provider, system, lang_pair, input_file, starting, ending, base_env):
    """1 プロバイダぶんの Stage1 → Stage2&3 をサブプロセスで実行する。

    Stage1 の全サンプルが API 全滅（success:false）の場合は Stage2&3 をスキップする。

    Args:
        provider (str): プロバイダ名。
        system (str): MT システム名。
        lang_pair (str): 言語ペア。
        input_file (str): Stage1 入力ファイルのパス。
        starting (int): Stage2&3 の開始サンプル index。
        ending (int): Stage2&3 の終了サンプル index（2000 = 全件）。
        base_env (dict): ベース環境変数。

    Returns:
        bool: 正常に Stage2&3 まで完了したら True。
    """
    stage1_dir, stage2_dir = jury_output_dirs(lang_pair, system, provider)
    env = build_provider_env(provider, base_env)
    code_dir = os.path.join(MAD_PATH, "code")

    print(f"\n===== provider: {provider} =====")
    subprocess.run(
        [sys.executable, os.path.join(code_dir, "stage1.py"),
         "-i", input_file, "-o", stage1_dir, "-lp", lang_pair],
        check=True, env=env,
    )
    total, failed = count_stage1_results(stage1_dir)
    print(f"[{provider}] Stage1: {total} samples（success:false {failed} 件）→ {stage1_dir}")
    if total and failed == total:
        print(f"[warn] {provider}: 全サンプルが API 全滅。認証・設定を確認（Stage2&3 はスキップ）")
        return False

    subprocess.run(
        [sys.executable, os.path.join(code_dir, "stage2_3.py"),
         system, lang_pair, str(starting), str(ending),
         "-i", stage1_dir, "-o", stage2_dir],
        check=True, env=env,
    )
    n_out = len(glob.glob(os.path.join(stage2_dir, "*_v1.json")))
    print(f"[{provider}] Stage2&3: {n_out} files → {stage2_dir}")
    return True


def parse_args():
    """CLI 引数を解析して返す。"""
    parser = argparse.ArgumentParser(
        description="プロバイダ別に Stage1→Stage2&3 を独立実行する（run-level jury）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("-s", "--system", type=str, required=True, help="MT システム名（ja 診断ではマニュアル ID）")
    parser.add_argument("-lp", "--lang-pair", type=str, required=True, help="言語ペア（例 ja-en）")
    parser.add_argument("-p", "--providers", type=str, nargs="+",
                        default=["openai", "anthropic", "vertex"], help="実行するプロバイダ")
    parser.add_argument("--starting", type=int, default=0, help="Stage2&3 の開始サンプル index")
    parser.add_argument("--ending", type=int, default=2000, help="Stage2&3 の終了サンプル index（2000 = 全件）")
    return parser.parse_args()


def main():
    """全プロバイダぶんの評価を順に実行するエントリポイント。"""
    from utils.config import _load_dotenv
    _load_dotenv()  # preflight が .env のプロバイダ固有キーを参照できるようにする

    args = parse_args()
    input_file = os.path.join(MAD_PATH, "data", f"input.{args.lang_pair}.{args.system}_v2.txt")
    if not os.path.exists(input_file):
        raise SystemExit(f"[error] 入力ファイルが無い: {input_file}（prepare_input.py で生成する）")

    results = {}
    for provider in args.providers:
        ok, message = preflight(provider, os.environ)
        if not ok:
            print(f"[skip] {message}")
            results[provider] = "skipped"
            continue
        done = run_provider(provider, args.system, args.lang_pair,
                            input_file, args.starting, args.ending, os.environ)
        results[provider] = "done" if done else "failed"

    print("\n===== summary =====")
    for provider, status in results.items():
        print(f"{provider}: {status}")


if __name__ == "__main__":
    main()
