# セットアップ: vLLM（ローカル/LAN 内の OpenAI 互換サーバ）

[vLLM](https://github.com/vllm-project/vllm) が公開する **OpenAI 互換 Chat Completions API** 経由で、
手元 GPU（または LAN 内のホスト）のモデルを M-MAD のバックエンドとして使う手順（Issue #67）。

クラウド API のコスト・レート制限・データ持ち出しを避けたい場合に選ぶ。

- エンドポイント: `http://localhost:8000/v1`（既定。`VLLM_BASE_URL` で上書き）
- モデル: **サーバが配信するモデル名をそのまま指定**（`/v1/models` の `id`）
- 認証: 既定は不要（ダミーキー `EMPTY` を送る）。認証付き起動時は `VLLM_API_KEY`

---

## 0. スコープ（重要）

**本リポジトリに含めるのは API 操作のみ**で、vLLM サーバ本体（`vllm` パッケージ・CUDA・
モデル重み等のローカル推論依存）は**別リポジトリで運用する**。`pyproject.toml` に推論系の
依存は追加せず、既存の `openai` 1.x クライアントだけで完結させる。

したがって本ドキュメントは「**サーバが既に起動している前提**での接続手順」を扱う。
サーバの構築・起動・モデルのロードはサーバ側リポジトリの手順に従うこと。

## 1. 前提条件

- vLLM サーバが起動し、目的のモデルがロード済みであること
- そのポートに本ホストから到達できること（別ホストの場合は SSH ポートフォワード等）

```bash
# 例: 別ホストの vLLM を SSH ポートフォワードで localhost:8000 に見せる
ssh -N -L 8000:localhost:8000 <remote-host>
```

## 2. 疎通確認（`.env` を触る前に）

```bash
# 配信中のモデル一覧（ここに出る id をそのまま VLLM_MODEL に設定する）
curl -s http://localhost:8000/v1/models | jq -r '.data[].id'

# 1 リクエスト叩いてみる
curl -s http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"<model-id>","messages":[{"role":"user","content":"ping"}],"max_tokens":16}' \
  | jq -r '.choices[0].message.content'
```

到達できない場合はサーバ側の起動状態と、ポートフォワードのセッションが生きているかを確認する
（フォワードは切断されやすい。`ss -ltn | grep 8000` に listener が出るかで判別できる）。

## 3. `.env` の設定

リポジトリルートの `.env`（`.env.example` をコピー）に以下を設定する。

```env
LLM_PROVIDER=vllm
VLLM_MODEL=nvidia/Gemma-4-26B-A4B-NVFP4
VLLM_BASE_URL=http://localhost:8000/v1
# 認証付きで起動している場合のみ
# VLLM_API_KEY=your-key
```

- **`VLLM_MODEL` は必須**。ローカルは任意モデル名になるため既定値を置かず、未設定なら
  `ValueError` で fail-fast する（空モデル名でサーバを叩かないため）。
- **プロバイダ固有変数（`VLLM_*`）で設定すること**。`run_jury.py`（複数プロバイダ実行・#55）は
  汎用の `LLM_MODEL` / `LLM_BASE_URL` / `LLM_API_KEY` を空値で上書きするため、汎用変数だけに
  書いていると jury 実行時に接続情報が消える。
- 単発実行では汎用の `LLM_MODEL` / `LLM_BASE_URL` でも動く（汎用側が優先される）。

## 4. クライアント経由のスモークテスト

```bash
uv sync

uv run python -c "
import sys; sys.path.insert(0,'code')
from utils.config import build_openai_client
c, m = build_openai_client()
r = c.chat.completions.create(model=m, messages=[{'role':'user','content':'Reply with exactly: OK'}], max_tokens=10, temperature=0)
print(m, '->', r.choices[0].message.content)
"
```

## 5. パイプライン実行

```bash
# Stage 1（次元分解・アノテーション）
uv run python code/stage1.py -i data/input.<lp>.<system>_v2.txt -o data/output_<lp>_<system>_v1 -lp <lp>

# Stage 2 & 3（討論 + 最終判定）
uv run python code/stage2_3.py <system> <lp> 0 2000

# run-level jury（プロバイダ別に独立実行して出力を分離・#55）
uv run python code/run_jury.py -s <system> -lp <lp> -p openai vertex vllm

# プロバイダ間一致率レポート（#56）
uv run python code/jury_report.py -s <system> -lp <lp> -p openai vertex vllm
```

`run_jury.py` は vllm 実行前に `/v1/models` への到達性を 1 度だけ確認し、未到達なら
Stage1 を起動せずスキップする（サーバ停止・フォワード断のまま全セグメント分の失敗リトライを
空回りさせないため）。

## 6. 実行結果の来歴

Stage1 の出力 JSON には実際に使ったモデル・プロバイダが記録される（Issue #60）。

```json
{ "provider": "vllm", "model_name": "nvidia/Gemma-4-26B-A4B-NVFP4", "success": true }
```

## 7. トラブルシューティング

| 症状 | 原因 | 対処 |
|---|---|---|
| `ValueError: LLM_PROVIDER=vllm ではモデル名が必須` | `VLLM_MODEL` / `LLM_MODEL` が未設定 | `/v1/models` の `id` を `VLLM_MODEL` に設定 |
| `run_jury.py` が `エンドポイント未到達のためスキップ` | サーバ停止・ポートフォワード断 | 手順 2 の疎通確認をやり直す |
| `run_jury.py` が `VLLM_MODEL が未設定のためスキップ` | jury 実行時に固有変数が無い | 汎用 `LLM_MODEL` ではなく `VLLM_MODEL` に設定する（手順 3 の注記） |
| `success: false` + `api_failures` が出る | 応答が得られなかった（コンテキスト超過・サーバ側 OOM 等） | サーバのログと `max_model_len` を確認。集計時は `success:false` を除外・再実行する（#52） |
| `Connection error` が繰り返される | ベース URL の誤り（`/v1` の付け忘れ等） | `VLLM_BASE_URL` を `http://host:port/v1` 形式にする |

## 補足: 仕組み

- `code/utils/config.py` の `get_llm_config()` が `LLM_PROVIDER=vllm` を検出し、
  base_url / model / api_key を解決して `build_openai_client()` がクライアントを構築する。
- `code/utils/agent.py` の `support_models` allowlist は、self-hosted では配信モデル名を
  リポジトリ側で列挙できないため **`vllm` のとき検証をスキップ**する
  （`ALLOWLIST_EXEMPT_PROVIDERS`）。ホスト型プロバイダではモデル名タイポ検出のガードを維持する。
- 論文（arXiv:2412.20127）の 3 ステージ構成・MQM 4 次元・討論プロトコルには影響しない。
  **バックエンドの差し替えのみ**である。
