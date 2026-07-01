import os


def _load_dotenv():
    """リポジトリルートの .env を読み、未設定の環境変数のみ補完する。

    python-dotenv 等の依存を増やさない簡易実装。既に os.environ に存在するキーは上書きしない
    （明示的な環境変数 / CLI での指定を優先する）。
    """
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
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


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
        LLM_PROVIDER : "openai"（既定） | "gemini" | "vertex"
        LLM_MODEL    : モデル名（省略時はプロバイダ既定。vertex は google/ プレフィックスを自動付与）
        LLM_BASE_URL : OpenAI 互換エンドポイント（省略時はプロバイダ既定）
        LLM_API_KEY  : API キー（省略時は OPENAI_API_KEY / GEMINI_API_KEY を参照）
        GCP_PROJECT / LLM_LOCATION : vertex 利用時のプロジェクトとリージョン（既定 location=global）

    Returns:
        dict: provider / model / base_url / api_key（vertex は None、トークンは
              build_openai_client() が ADC から解決）を持つ設定辞書。
    """
    _load_dotenv()
    provider = os.environ.get("LLM_PROVIDER", "openai").lower()

    if provider == "vertex":
        project = os.environ.get("GCP_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")
        location = os.environ.get("LLM_LOCATION", "global")
        model = os.environ.get("LLM_MODEL", "gemini-3.5-flash")
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
            "model": os.environ.get("LLM_MODEL", "gemini-3.5-flash"),
            "base_url": os.environ.get(
                "LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"
            ),
            "api_key": os.environ.get("LLM_API_KEY") or os.environ.get("GEMINI_API_KEY"),
        }

    return {
        "provider": "openai",
        "model": os.environ.get("LLM_MODEL", "gpt-4o-mini"),
        "base_url": os.environ.get("LLM_BASE_URL"),  # None → OpenAI 既定エンドポイント
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
