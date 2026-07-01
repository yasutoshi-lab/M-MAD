# セットアップ: Google Agent Platform（旧 Vertex AI）+ ADC 方式

Google Cloud の Agent Platform（Vertex AI）の **OpenAI 互換エンドポイント**を、
**ADC（Application Default Credentials）の OAuth トークン**で利用する手順。API キーは不要。

- エンドポイント: `https://{location}-aiplatform.googleapis.com/v1/projects/{PROJECT}/locations/{location}/endpoints/openapi`
  （`location=global` の場合はホストが `aiplatform.googleapis.com`）
- モデル: `google/gemini-3.5-flash`（`LLM_MODEL` に `gemini-3.5-flash` を指定すれば `google/` は自動付与）
- 認証: ADC の OAuth アクセストークン（`code/utils/config.py` が呼び出しごとに取得・リフレッシュ）

---

## 1. 前提条件

- Google Cloud プロジェクト（例: `your-gcp-project-id`）
- [gcloud CLI](https://cloud.google.com/sdk/docs/install) がインストール済み
- 対象プロジェクトで **Vertex AI API（`aiplatform.googleapis.com`）が有効**
- 実行アカウントに **Vertex AI User（`roles/aiplatform.user`）** 相当の権限
- `gemini-3.5-flash` が利用するリージョン（本手順は `global`）で利用可能なこと

## 2. gcloud 認証（ADC）

アカウントログインとは別に、アプリケーション用の ADC を設定する。

```bash
# 1) アカウントにログイン（未ログインの場合）
gcloud auth login

# 2) 使用プロジェクトを設定
gcloud config set project your-gcp-project-id

# 3) ADC を設定（アプリからの認証に使う）
#    ヘッドレス環境ではブラウザ無しの device フローを使う
gcloud auth application-default login --no-launch-browser
#    → 表示 URL を手元ブラウザで開いて認可 → 検証コードを端末に貼り付け

# 4) ADC の quota project を設定
gcloud auth application-default set-quota-project your-gcp-project-id
```

ADC の資格情報は `~/.config/gcloud/application_default_credentials.json` に保存される
（リポジトリにはコミットされない）。

## 3. Vertex AI API の有効化（未有効の場合）

```bash
gcloud services enable aiplatform.googleapis.com --project your-gcp-project-id
```

## 4. `.env` の設定

リポジトリルートに `.env` を作成する（`.env.example` をコピー）。**API キーは不要**。

```env
LLM_PROVIDER=vertex
LLM_MODEL=gemini-3.5-flash
GCP_PROJECT=your-gcp-project-id
LLM_LOCATION=global
```

- `GCP_PROJECT` は `GOOGLE_CLOUD_PROJECT` でも可。
- `LLM_LOCATION` を `us-central1` 等に変えるとリージョナルエンドポイントになる。

## 5. 依存インストールと疎通確認

```bash
uv sync   # google-auth を含む依存を導入

# ADC トークンが取得できるか（値は表示されない）
uv run python -c "import sys; sys.path.insert(0,'code'); from utils.config import _vertex_access_token; print('token len', len(_vertex_access_token()))"

# 1 リクエストのスモークテスト
uv run python -c "
import sys; sys.path.insert(0,'code')
from utils.config import build_openai_client
c, m = build_openai_client()
r = c.chat.completions.create(model=m, messages=[{'role':'user','content':'Reply with exactly: OK'}], max_tokens=10, temperature=0)
print(m, '->', r.choices[0].message.content)
"
```

`google/gemini-3.5-flash -> OK` が返れば疎通成功。

## 6. パイプライン実行

```bash
# Stage 1（次元分解・アノテーション）
sh run_stage1.sh              # 例: sh stage1.sh <system> <lp> <start> <version>

# Stage 2 & 3（討論 + 最終判定）
sh run_stage2_3.sh            # 例: python code/stage2_3.py <system> <lp> <start> <end>
```

API キー・モデル・プロバイダは `.env` から読み込まれる（`stage1.sh` の `-k` は不要）。

## 7. トラブルシューティング

| 症状 | 原因 | 対処 |
|---|---|---|
| `DefaultCredentialsError: Your default credentials were not found` | ADC 未設定 | `gcloud auth application-default login` を実行 |
| `403 PERMISSION_DENIED` / `API_KEY_SERVICE_BLOCKED` | AI Studio エンドポイントに Vertex 用資格で接続、またはキー種別の不一致 | `LLM_PROVIDER=vertex` になっているか、`LLM_BASE_URL` を上書きしていないか確認 |
| `403` で `aiplatform...` が拒否 | Vertex AI API 未有効 / IAM 権限不足 | API 有効化、`roles/aiplatform.user` 付与 |
| `404` / モデル不明 | 指定リージョンで `gemini-3.5-flash` 未提供 | `LLM_LOCATION` を `global` や `us-central1` に変更 |
| トークン失効 | 長時間実行 | 本実装は呼び出しごとにトークンを再取得するため通常は問題にならない |

## 補足: 仕組み

`code/utils/config.py`:
- `get_llm_config()` が `LLM_PROVIDER=vertex` を検出し、`GCP_PROJECT` / `LLM_LOCATION` から
  base_url を組み立て、モデルに `google/` を付与する。
- `build_openai_client()` が ADC から OAuth トークンを取得し、`OpenAI(api_key=<token>, base_url=...)`
  を構築する。トークンは呼び出しごとにリフレッシュされる。
