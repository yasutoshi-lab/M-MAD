import os


def _load_dotenv(path: str = None):
    """リポジトリルートの .env を読み、未設定の環境変数のみ補完する。

    python-dotenv 等の依存を増やさない簡易実装。既に os.environ に存在するキーは上書きしない
    （明示的な環境変数 / CLI での指定を優先する）。値が空の行（`KEY=`）は「未設定」とみなし
    環境変数に設定しない（Issue #47）。

    Args:
        path (str, optional): 読み込む .env のパス。省略時はリポジトリルートの .env。
    """
    if path is None:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        path = os.path.join(root, ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            value = value.strip().strip('"').strip("'")
            if not value:
                continue
            os.environ.setdefault(key.strip(), value)


def _vertex_base_url(project: str, location: str) -> str:
    """Vertex(Agent Platform) の OpenAI 互換エンドポイント URL を組み立てる。

    global は region プレフィックス無しのホストを使う。
    """
    if location == "global":
        host = "aiplatform.googleapis.com"
    else:
        host = f"{location}-aiplatform.googleapis.com"
    return f"https://{host}/v1/projects/{project}/locations/{location}/endpoints/openapi"


def get_llm_config():
    """LLM プロバイダ設定を環境変数（および .env）から解決して返す。

    環境変数:
        LLM_PROVIDER : "openai"（既定） | "gemini" | "vertex" | "anthropic" | "vllm"
        LLM_MODEL    : モデル名（省略時はプロバイダ既定。vertex は google/ プレフィックスを自動付与）
        LLM_BASE_URL : OpenAI 互換エンドポイント（省略時はプロバイダ既定）
        LLM_API_KEY  : API キー（省略時は OPENAI_API_KEY / GEMINI_API_KEY を参照）
        GCP_PROJECT / LLM_LOCATION : vertex 利用時のプロジェクトとリージョン（既定 location=global）
        VLLM_MODEL / VLLM_BASE_URL / VLLM_API_KEY : vllm 利用時のプロバイダ固有設定（Issue #67）

    Returns:
        dict: provider / model / base_url / api_key（vertex は None、トークンは
              build_openai_client() が ADC から解決）を持つ設定辞書。

    Raises:
        ValueError: provider が vllm でモデル名が未設定の場合。
    """
    _load_dotenv()
    # 空文字の環境変数は「未設定」とみなし既定値へフォールバックする（Issue #47）。
    provider = (os.environ.get("LLM_PROVIDER") or "openai").lower()

    if provider == "vertex":
        project = os.environ.get("GCP_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")
        location = os.environ.get("LLM_LOCATION") or "global"
        model = os.environ.get("LLM_MODEL") or "gemini-3.5-flash"
        if not model.startswith("google/"):
            model = "google/" + model
        return {
            "provider": "vertex",
            "model": model,
            "base_url": os.environ.get("LLM_BASE_URL") or _vertex_base_url(project, location),
            "api_key": None,  # ADC の OAuth トークンを build_openai_client() で解決
            "project": project,
            "location": location,
        }

    if provider == "gemini":
        return {
            "provider": "gemini",
            "model": os.environ.get("LLM_MODEL") or "gemini-3.5-flash",
            "base_url": os.environ.get("LLM_BASE_URL")
            or "https://generativelanguage.googleapis.com/v1beta/openai/",
            "api_key": os.environ.get("LLM_API_KEY") or os.environ.get("GEMINI_API_KEY"),
        }

    if provider == "anthropic":
        return {
            "provider": "anthropic",
            "model": os.environ.get("LLM_MODEL") or "claude-haiku-4-5",
            "base_url": os.environ.get("LLM_BASE_URL") or "https://api.anthropic.com/v1/",
            "api_key": os.environ.get("LLM_API_KEY") or os.environ.get("ANTHROPIC_API_KEY"),
        }

    if provider == "vllm":
        # ローカル/LAN 内の vLLM（OpenAI 互換サーバ）。サーバ本体は別リポジトリで運用し、
        # ここでは API 操作のみを行う（Issue #67）。
        # プロバイダ固有変数（VLLM_*）を用意するのは、run_jury.build_provider_env() が
        # 汎用の LLM_MODEL / LLM_BASE_URL / LLM_API_KEY を空値で上書きするため
        # （#47 の空値フォールバック利用）。jury 実行時は固有変数側で接続情報を保持する。
        model = os.environ.get("LLM_MODEL") or os.environ.get("VLLM_MODEL")
        if not model:
            # 配信モデル名はサーバ側で決まる任意の文字列（HF リポ名等）で既定を置けないため、
            # 空モデル名でリクエストを投げる前に fail-fast させる。
            raise ValueError(
                "LLM_PROVIDER=vllm ではモデル名が必須。VLLM_MODEL（または LLM_MODEL）に "
                "vLLM サーバが配信するモデル名を設定する（例: /v1/models の id）"
            )
        return {
            "provider": "vllm",
            "model": model,
            "base_url": os.environ.get("LLM_BASE_URL")
            or os.environ.get("VLLM_BASE_URL")
            or "http://localhost:8000/v1",
            # vLLM は既定でキー不要だが、OpenAI クライアントは非空キーを要求するためダミーを渡す。
            # 認証付きで起動している場合は VLLM_API_KEY / LLM_API_KEY で上書きできる。
            "api_key": os.environ.get("LLM_API_KEY") or os.environ.get("VLLM_API_KEY") or "EMPTY",
        }

    return {
        "provider": "openai",
        "model": os.environ.get("LLM_MODEL") or "gpt-4.1-mini",
        "base_url": os.environ.get("LLM_BASE_URL") or None,  # None → OpenAI 既定エンドポイント
        "api_key": os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY"),
    }


def _vertex_access_token() -> str:
    """ADC（Application Default Credentials）から OAuth アクセストークンを取得する。

    呼び出しごとにリフレッシュするため、長時間実行でもトークン失効に耐える。
    """
    import google.auth
    import google.auth.transport.requests

    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    credentials.refresh(google.auth.transport.requests.Request())
    return credentials.token


def build_openai_client(fallback_api_key: str = None):
    """設定に基づき openai.OpenAI クライアントを構築する。

    Args:
        fallback_api_key (str): 設定に API キーが無い場合に使うキー（stage1 の -k 引数など）。

    Returns:
        (client, model): 構築した OpenAI クライアントと使用モデル名。
    """
    from openai import OpenAI

    cfg = get_llm_config()
    kwargs = {}
    if cfg["provider"] == "vertex":
        # ADC の OAuth トークンを都度取得（api_key として渡す）
        api_key = _vertex_access_token()
    else:
        api_key = cfg["api_key"] or fallback_api_key
    if api_key:
        kwargs["api_key"] = api_key
    if cfg["base_url"]:
        kwargs["base_url"] = cfg["base_url"]
    return OpenAI(**kwargs), cfg["model"]
