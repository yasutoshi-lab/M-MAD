# M-MAD テスト設計書

Issue #13 の一環として、M-MAD のテスト方針とテストケースを定義する。本書は**設計のみ**で、
実装（pytest コード）や CI 導入は含まない（別途判断）。

リファクタリング（PR #29/#30）により `stage2_3.py` が import 可能になり、両ステージが関数単位で
テスト可能になった。LLM 呼び出しは `code/utils/config.py:build_openai_client()`（および
`Agent.query`）に集約されており、**モック注入点が 1 箇所**で済むのが本設計の前提。

## 1. 方針

- **フレームワーク**: `pytest`（将来 `[dependency-groups] dev = ["pytest"]` に追加、`uv run pytest`）。
- **配置**: リポジトリルート `tests/`。`tests/conftest.py` で `code/` を `sys.path` に追加し、
  `import stage1 / stage2_3 / utils.*` を可能にする。
- **決定性**: 外部 I/O（LLM API・`.env`・ネットワーク）に依存しないことを最優先。
  - LLM: `build_openai_client` / `generate_answer` / `Agent.query` を `monkeypatch` で差し替え。
  - `.env`: `config._load_dotenv` を no-op 化し、`monkeypatch.setenv/delenv` で環境変数を制御。
- **層分け**:
  - **L1 純粋関数**（API 不要）… 最優先。回帰検知の土台。
  - **L2 モック使用ロジック**（討論・判定の分岐）… LLM をスタブ化して検証。
  - **L3 実 API E2E**（Stage1→Stage2&3）… 手動のみ。CI 非対象（コスト・認証のため）。
- **論文整合性**: 期待値は論文の手法（4 次元 / severity minor·major / non-translation /
  Judge 統合）に一致させる。挙動を変えるテストは書かない。

## 2. 共通フィクスチャ（設計）

- `add_code_to_path`（conftest, autouse): `code/` を `sys.path` に挿入。
- `fake_llm`（monkeypatch): 指定した応答テキスト列を順に返す `FakeCompletion` を生成し、
  `stage2_3.generate_answer` / `utils.config.build_openai_client` を差し替えるヘルパ。
  - 応答は `obj.choices[0].message.content` でアクセスできる形にする（openai 1.x 互換）。
- `clean_env`（monkeypatch): `config._load_dotenv` を no-op にし、`LLM_*`/`*_API_KEY` を削除。
- `stage1_output_factory`: `players`（4 次元 + Judge）・`source_segment`・`target_segment` を持つ
  Stage1 出力 dict を生成するヘルパ（L2 の `process_sample` テスト用）。

---

## 3. L1: 純粋関数テストケース

### 3.1 `code/stage1.py`

| ID | 対象 | 入力 | 期待 |
|---|---|---|---|
| S1-EJ-1 | `extract_json` | `'{"a":1}'` | `'{"a":1}'` |
| S1-EJ-2 | `extract_json` | `'pre {"a":1} post'` | `'{"a":1}'` |
| S1-EJ-3 | `extract_json` | ` ```json\n{"a":1}\n``` ` | `'{"a":1}'`（フェンス外側を除去） |
| S1-EJ-4 | `extract_json` | `'no braces'` | 空文字列（`find`=-1, `rfind`=-1 の現挙動を明記） |
| S1-PJ-1 | `parse_json_obj` | `'{"annotations": []}'` | `{"annotations": []}`（json.loads 経路） |
| S1-PJ-2 | `parse_json_obj` | `"{'annotations': [{'severity':'major'}]}"` | dict（literal_eval フォールバック） |
| S1-PJ-3 | `parse_json_obj` | `'not json'` | `ValueError`/`SyntaxError` を送出 |
| S1-LF-1 | `load_few_shots` | `'zh-en'` | module 名 `few_shot_demos`、warning 無し |
| S1-LF-2 | `load_few_shots` | `'en-de'` | `few_shot_demos_de` |
| S1-LF-3 | `load_few_shots` | `'he-en'` | `few_shot_demos_he` |
| S1-LF-4 | `load_few_shots` | `'fr-en'` | `few_shot_demos`（target en フォールバック）＋ warning 出力 |
| S1-LF-5 | `load_few_shots` | `'ja-de'` | `few_shot_demos_de`（target de フォールバック）＋ warning |
| S1-LF-6 | `load_few_shots` | `'xx-yy'` | `few_shot_demos`（既定）＋ warning |
| S1-LF-7 | `load_few_shots` | 返り値モジュール | `accuracy_user_shot` 等の必須変数が存在（len 3）、`nontran_user_shot` len ≥ 4 |

### 3.2 `code/stage2_3.py`

| ID | 対象 | 入力 | 期待 |
|---|---|---|---|
| S2-NL-1 | `isnull` | `'{"annotations": []}'` | `True` |
| S2-NL-2 | `isnull` | `'{"annotations":[]}'` / 単一引用符 2 種 | すべて `True` |
| S2-NL-3 | `isnull` | `'{"annotations":[{"x":1}]}'` | `False` |
| S2-DQ-1 | `is_only_double_quotes` | `'"'` / `'“”'` | `True` |
| S2-DQ-2 | `is_only_double_quotes` | `'ab"'` | `False` |
| S2-DQ-3 | `is_only_double_quotes` | `''` | `True`（`all([])` の現挙動を明記） |
| S2-EA-1 | `extract_annotations` | `'{"annotations":[{"error_span":"x"}]}'` | `{"annotations":[{"error_span":"x"}]}` |
| S2-EA-2 | `extract_annotations` | 解析文＋単一 annotations ブロック（末尾に角括弧なし） | そのブロックを抽出 |
| S2-EA-2b | `extract_annotations` | annotations ブロックが複数 | `{"annotations":[]}`（貪欲正規表現で連結が壊れる現挙動） |
| S2-EA-3 | `extract_annotations` | annotations 内が不正 JSON | `{"annotations":[]}`（デコード失敗フォールバック） |
| S2-EA-4 | `extract_annotations` | `'annotations 無し'` | `None`（一致無し） |
| S2-GL-1 | `get_language_names` | `'zh-en'` | `('Chinese','English')` |
| S2-GL-2 | `get_language_names` | `'en-de'` | `('English','German')` |
| S2-GL-3 | `get_language_names` | `'he-en'` | `('Hebrew','English')` |
| S2-MSG-1 | `set_meta_prompt` | `'x'` | `{"role":"system","content":"x"}` |
| S2-MSG-2 | `add_event` | `'x'` | `{"role":"user","content":"x"}` |
| S2-MSG-3 | `ask_prompt` | `'x'` | `[{"role":"user","content":"x"}]` |
| S2-MSG-4 | `construct_assistant_message` | Fake completion(content='x') | `{"role":"assistant","content":"x"}` |
| S2-MSG-5 | `construct_message` | 相手 context 2 件, idx | role=user、相手回答の引用と再考指示・JSON 指定を含む |

### 3.3 `code/utils/config.py`（`clean_env` 使用）

| ID | 対象 | 入力（env） | 期待 |
|---|---|---|---|
| CF-1 | `get_llm_config` | 何も設定なし | provider=openai / model=gpt-4.1-mini / base_url=None / api_key=OPENAI_API_KEY 参照 |
| CF-2 | `get_llm_config` | `LLM_PROVIDER=gemini`,`GEMINI_API_KEY=k` | provider=gemini / model=gemini-3.5-flash / base_url=generativelanguage.../openai/ / api_key='k' |
| CF-3 | `get_llm_config` | `LLM_PROVIDER=vertex`,`GCP_PROJECT=p` | provider=vertex / model=`google/gemini-3.5-flash` / base_url に p と global / api_key=None / project=p |
| CF-4 | `get_llm_config` | `LLM_PROVIDER=vertex`,`LLM_MODEL=google/x` | model がそのまま（二重 `google/` 付与しない） |
| CF-5 | `get_llm_config` | `LLM_MODEL=foo`（openai） | model=foo で上書き |
| CF-6 | `_vertex_base_url` | `('p','global')` | `https://aiplatform.googleapis.com/v1/projects/p/locations/global/endpoints/openapi` |
| CF-7 | `_vertex_base_url` | `('p','us-central1')` | host が `us-central1-aiplatform.googleapis.com` |
| CF-8 | `build_openai_client` | provider=vertex（`_vertex_access_token` をモック） | client.base_url が aiplatform、model=`google/gemini-3.5-flash` |
| CF-9 | `build_openai_client` | provider=openai, fallback_api_key='k' | api_key='k' が使われ base_url 既定（None） |
| CF-10 | `get_llm_config` | `LLM_MODEL=''`（openai） | model=gpt-4.1-mini（空値は既定へフォールバック・Issue #47） |
| CF-11 | `get_llm_config` | `LLM_PROVIDER=''` | provider=openai |
| CF-12 | `get_llm_config` | `LLM_BASE_URL=''`（openai / gemini） | openai: base_url=None / gemini: 既定 URL |
| CF-13 | `get_llm_config` | `LLM_PROVIDER=vertex`,`GCP_PROJECT=p`,`LLM_LOCATION=''` | base_url に `locations/global` |
| CF-14 | `_load_dotenv` | tmp .env に `LLM_MODEL=`（空値行）と `KEY=bar` | 空値行は os.environ に設定されず、値あり行のみ setdefault |

### 3.4 `code/utils/openai_utils.py`

| ID | 対象 | 入力 | 期待 |
|---|---|---|---|
| OU-1 | `num_tokens_from_string` | `('hello world','gpt-4o-mini')` | 正の int（tiktoken 既知モデル） |
| OU-2 | `num_tokens_from_string` | `('hello','gemini-3.5-flash')` | 正の int（cl100k_base フォールバックで例外無し） |
| OU-3 | `OutOfQuotaException('k')` | `str()` | `'No quota for key: k'` を含む |
| OU-4 | `AccessTerminatedException('k', cause='c')` | `str()` | `'Caused by c'` を含む |

---

## 4. L2: モック使用ロジック（設計）

`fake_llm` で LLM 応答を固定し、討論・判定の**分岐**を検証する。API は呼ばない。

### 4.1 `stage2_3.run_dimension_debate`

| ID | シナリオ | モック | 期待 |
|---|---|---|---|
| L2-DD-1 | annotation に "major" 無し・非翻訳でない → other==annotation | 応答不要 | 討論せず annotation をそのまま返す（API 未呼び出し） |
| L2-DD-2 | "major" あり → 討論。round1 の judge が "yes" | agent 応答＋judge="yes" | 早期 return（agent0 の抽出結果）、以降ラウンド未実行 |
| L2-DD-3 | 全ラウンド judge が "no" | judge="no" ×3 | ループ後の "no" 分岐で agent0 抽出結果を返す |
| L2-DD-4 | judge が "yes"/"no" いずれも含まない | judge="maybe" | `_NO_RESULT` を返す（元挙動：未設定） |
| L2-DD-5 | 元 annotation が non-translation | 応答不要 | other_annotation が否定文になり討論経路へ入る |

### 4.2 `stage2_3.run_final_judge`

| ID | シナリオ | モック | 期待 |
|---|---|---|---|
| L2-FJ-1 | 4 次元すべて空アノテーション | 応答不要 | `{"annotations":[]}`（API 未呼び出し） |
| L2-FJ-2 | source/target が引用符のみ | 応答不要 | `{"annotations":[]}`（API 未呼び出し） |
| L2-FJ-3 | 通常ケース | judge 応答固定 | `extract_annotations` で dict を返す |

### 4.3 `stage2_3.process_sample`

| ID | シナリオ | 期待 |
|---|---|---|
| L2-PS-1 | 全次元空の Stage1 出力（fixture） | response_dict に source/target/4 次元/judge キーが揃う。前サンプル値の混入が無い（#6） |
| L2-PS-2 | 2 サンプル連続処理 | 各 response_dict が独立（per-sample 初期化の確認） |

### 4.4 `stage1.Debate._eval_dimension` / `init_agents`

| ID | シナリオ | モック | 期待 |
|---|---|---|---|
| L2-ED-1 | `agent.ask` が正常応答 | Agent.ask をスタブ | few-shot（3+1）注入後に注釈を返し、add_memory される |
| L2-ED-2 | `agent.ask` が毎回例外 | ask が raise | `count<10` で終了し、フォールバック `{"annotations": []}` を返す（#5）＋`api_failures` に記録（#52） |
| L2-JG-1 | Judge が不正 JSON を返し続ける | ask が非 JSON | 10 回後に non-translation フォールバック（#5/#7）。**`api_failures` には記録しない**（応答ありのパース失敗・#52） |
| L2-JG-2 | Judge の ask が毎回例外（API 全滅） | ask が raise | non-translation フォールバック＋`api_failures` に記録（#52） |
| L2-RN-1 | `run()` | api_failures 空 / 1 件以上 | success=true / **success=false**＋api_failures を save_file に格納（#52） |

> L2-ED-1/2・L2-JG-1/2・L2-RN-1 は Issue #52 の対応で `tests/test_stage1_debate.py` に**実装済み**
> （`Debate.__new__` でフェイク agent を注入する方式）。

---

## 5. 対象外・留意

- **L3 実 API E2E** は Vertex/Gemini で手動確認済み。CI では回さない（コスト・ADC 認証のため）。
- `main()`（両ステージ）・ファイル I/O は L2 の `process_sample` 等で主要ロジックを担保し、
  I/O 自体は薄いため優先度低（必要なら `tmp_path` で最小確認）。
- `generate_answer` 内の二重 try（非リトライ）は **Issue #10** 管轄。テストは現挙動に合わせる。
- few-shot データ拡充は **Issue #18**。テストは現存 3 モジュール前提。

## 6. 実装時の進め方（参考・別途着手）

1. `pytest` を dev グループに追加、`tests/conftest.py`（sys.path・フィクスチャ）。
2. L1（3 章）を実装 → `uv run pytest` で緑を確認。
3. L2（4 章）を実装（`fake_llm` スタブ）。
4. （任意）最小 CI（`uv sync` + `uv run pytest`）の導入是非を判断。
