# run-level jury の長時間バッチ運用ノート

`run_jury.py`（#55）で **手順書 × 多言語 × 複数プロバイダ**の評価を回したときに得られた運用知見。
手法・コードの説明は [README.md](README.md) / [usage.md](usage.md) を参照。本ドキュメントは
「どう確認し、どう実行し、どう詰まったか」の作業記録である。

初出: 2026-07-09 の実行（2 手順書 × 21 言語 × openai/vertex の 2 プロバイダ ＝ 84 通り）。

> **表記について**: 本リポジトリは公開されているため、社内データである手順書は
> **A / B / C / D のラベル**で示す（実 ID は追跡対象外の `.input/` を参照）。ラベルは
> [#70](https://github.com/yasutoshi-lab/M-MAD/issues/70) と共通である。手順書の本文・
> 製品名・翻訳内容は本ドキュメントに記載しない。

## 1. 実行可否の確認手順

本番実行（実 API コストが発生するフルパイプライン）を始める前に、以下を確認する。

- **認証情報の有無**（値は見ない）: `grep -E "^(OPENAI_API_KEY|GCP_PROJECT|...)=" .env | sed -E 's/=(.+)/=<set>/'` のように
  値をマスクしてキーの存在だけ確認する
- **Vertex ADC の実可動確認**: `gcloud auth application-default print-access-token` が exit 0 で
  トークンらしき文字列を返すかで確認（トークン内容はログに残さない）
- **self-hosted（vllm）の疎通確認**: `curl -s <VLLM_BASE_URL>/models`。`run_jury.py` は vllm 実行前に
  同等の到達性チェックを行い、未到達なら Stage1 を起動せずスキップする（#67）
- **既存の同種実績の有無**: 同じ言語構成のレポート（`JURY_AGREEMENT_*.md`）が既にあれば、
  手法自体は実証済みと判断できる
- **実際に 1 回動かして確認**: 過去の出力（`data/output_ja-en_<手順書>_<provider>/0_v1.json` 等）の
  `"success": true` / `model_name` / `start_time` を見て、直近に本当に成功実行された形跡があるかを
  裏取りする（推測ではなく実データで確認）

結論だけ聞かれても「動くはず」ではなく、上記のような裏取りをしてから着手する。

## 2. 翻訳済み手順書（`.input/`）の確認

- 手順書は `.input/<manual_id>/<manual_id>-<lang>.json`（原文 `-ja.json` + 各言語）の構成
- `code/prepare_input.py` が `title` / `mainSteps[].title` / `detailedSteps[].description` / `.notes` を
  構造パスで対応付け、`data/input.ja-{lang}.{manual_id}_v2.txt`（タブ区切り）と
  `.map.tsv`（セグメント番号↔構造パス）を生成する
- 初出時は両手順書とも 21 言語分の入力が**既に生成済み**だったため `prepare_input.py` の再実行は不要だった。
  実行前に `ls data/input.ja-*.<manual_id>*` で存在確認するだけで済む
- セグメント数は `wc -l data/input.ja-en.<manual_id>_v2.txt` で確認する（手順書 C=18 / 手順書 D=22）
- **入力データ自体の不備に注意**: 未翻訳（訳文＝原文）・訳文重複による内容欠落があると、
  M-MAD は non-translation（-25）を割り当てるため、その言語の平均スコアが翻訳品質と無関係に沈む。
  検出の自動化は [#70](https://github.com/yasutoshi-lab/M-MAD/issues/70) で対応する

## 3. 並列実行の単位

- 「1 手順書 × 1 プロバイダ」を 1 ジョブとして並列化できる
- 出力先（`data/output_ja-{lang}_{manual}_{provider}/`, `data/stage2_3_ja-{lang}_{manual}_{provider}/`）が
  ジョブ間で重複しないため、**worktree 分離は不要**（ファイル競合が起きない設計なら並列化は素直に安全）
- ジョブに渡す指示は具体的にするほど自走する: 対象手順書・provider・言語コードのリスト・実行コマンド例
  （`uv run python code/run_jury.py -s <manual_id> -lp ja-<lang> -p <provider>`）・1 言語失敗しても止めずに
  次へ進める・完了後の報告フォーマット（言語別セグメント数 / `success:false` 件数 / 成功失敗一覧）

## 4. 長時間バッチは OS レベルでデタッチする

**現象**: エージェント機能のバックグラウンド実行は、ホストプロセスのライフサイクルに紐づく。
セッション/プロセスが再起動すると、その時点までの進捗はディスク上のファイルに残るが、
ジョブ自体は停止して再開されない。再開させても同じ理由で再度止まることがある。

**教訓**: 数分〜十数分で終わる作業には向くが、**数十分〜時間単位の長時間バッチには不向き**。

**対処（OS レベルのデタッチ実行）**:

```bash
setsid nohup <script> <args...> > <logfile> 2>&1 < /dev/null &
disown
```

- `setsid`: 新しいセッションでプロセスを起動し、親シェルのセッションから切り離す
- `nohup` + `< /dev/null`: 標準入出力を親から切り離し、SIGHUP を無視させる
- `disown`: シェルのジョブテーブルから外し、シェル終了時にプロセスへ影響が及ばないようにする
- 実行内容は事前にシェルスクリプト化（言語をループし `run_jury.py` を順に呼ぶ）し、ログをファイルへ
  リダイレクトする

これによりホスト側のプロセスが再起動しても OS プロセスは生き残り、最後まで完走できる。

**進捗確認の方法**:

```bash
ps -ef | grep "[r]un_combo.sh"                      # プロセスが生きているか
tail -n 6 <logfile>                                  # 直近の状況（ALL_DONE が出れば完了）
ls data/stage2_3_ja-<lang>_<manual>_<provider>/*_v1.json | wc -l   # 生成ファイル数で完了判定
```

## 5. 中断からの再開（部分完了状態の扱い）

- `stage1.py` は呼ばれるたびに**入力ファイルの全行を毎回処理する**（既存ファイルのスキップ・
  resume ロジックは無い）。「途中まで終わった言語」を再実行するとその言語の全セグメントが
  作り直される
- 一方 `stage2_3.py` は**既存の非空出力をスキップ**するため、再実行のコストは Stage1 側に偏る
- そのため中断復旧時は、**完了済み言語を再実行対象から外し、未完了・部分完了の言語だけを渡す**
- 完了判定は「`stage2_3_ja-{lang}_{manual}_{provider}/` 内の `_v1.json`（`-config` 除く）の件数が、
  その手順書のセグメント数と一致するか」で機械的に行える

## 6. 既知の失敗モードと回避策

### `stage2_3.py` の未捕捉例外（[#68](https://github.com/yasutoshi-lab/M-MAD/issues/68)）

- `run_final_judge()` 内の `generate_answer(...).choices[0].message.content` は、`generate_answer()` が
  `None` を返すケース（一時的な空応答等）を考慮しておらず、`AttributeError` でプロセス全体が異常終了する
- `stage1.py` はサンプル単位の `try/except` で継続する設計（#10）だが、`stage2_3.py` のメインループには
  同等の保護が無い
- **欠損セグメントの埋め方**（コード変更なしで復旧可能）: `starting`/`ending` は 0-indexed の
  `range(starting, ending)` なので、欠損した 1 セグメントだけを狙って再実行できる

  ```bash
  LLM_PROVIDER=<provider> LLM_MODEL= LLM_BASE_URL= LLM_API_KEY= \
    uv run python code/stage2_3.py <manual_id> ja-<lang> <欠損id> <欠損id+1> \
    -i data/output_ja-<lang>_<manual_id>_<provider> \
    -o data/stage2_3_ja-<lang>_<manual_id>_<provider>
  ```

  （`LLM_MODEL` 等を空値で上書きするのは `run_jury.py` の `build_provider_env()` と同じ流儀。
  `.env` の汎用値が他プロバイダへ波及するのを防ぐため・#47）

### API 全滅（`success:false`）

- Stage1 で 1 度も応答を得られなかったエージェントがあると `success: false` ＋ `api_failures` が
  記録される（#52）。集計時は該当サンプルを除外するか再実行する
- `run_jury.py` は Stage1 の全サンプルが `success:false` の場合、Stage2&3 をスキップして警告する

## 7. Git / Issue 運用

- Issue 作成は `gh issue create --repo yasutoshi-lab/M-MAD` を明示し、upstream に誤って作成しない
  （`git remote -v` で `origin` が自リポジトリであることを事前確認）
- Issue 表題は `【項目】主題-優先度` 形式
- **公開リポジトリであることを常に意識する**: Issue / PR / doc に手順書の本文・製品名・実 ID を
  記載しない。件数・言語コード・構造パス・セグメント番号までに留める
