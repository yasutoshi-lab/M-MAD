import tiktoken


model2max_context = {
    "gpt-4": 7900,
    "gpt-4-0314": 7900,
    "gpt-3.5-turbo-0301": 3900,
    "gpt-3.5-turbo": 3900,
    "text-davinci-003": 4096,
    "text-davinci-002": 4096,
    "gpt-4o-mini":16384,
    "qwen2.5-72b-instruct": 131072,
    "Llama-3.1-70B-Instruct": 131072,
    "gemini-3.5-flash": 1000000,
    "claude-haiku-4-5": 200000,
}

class OutOfQuotaException(Exception):
    """API キーがクォータ超過したときに送出される例外。

    Attributes:
        key (str): クォータ超過した API キー。
        cause: 元となった例外（任意）。
    """
    def __init__(self, key, cause=None):
        """クォータ超過メッセージを組み立てて例外を初期化する。

        Args:
            key (str): クォータ超過した API キー。
            cause (optional): 元となった例外。
        """
        super().__init__(f"No quota for key: {key}")
        self.key = key
        self.cause = cause

    def __str__(self):
        """例外の文字列表現を返す（cause があれば併記する）。

        Returns:
            str: エラーメッセージ。
        """
        if self.cause:
            return f"{super().__str__()}. Caused by {self.cause}"
        else:
            return super().__str__()

class AccessTerminatedException(Exception):
    """API キーが利用停止されたときに送出される例外。

    Attributes:
        key (str): 利用停止された API キー。
        cause: 元となった例外（任意）。
    """
    def __init__(self, key, cause=None):
        """利用停止メッセージを組み立てて例外を初期化する。

        Args:
            key (str): 利用停止された API キー。
            cause (optional): 元となった例外。
        """
        super().__init__(f"Access terminated key: {key}")
        self.key = key
        self.cause = cause

    def __str__(self):
        """例外の文字列表現を返す（cause があれば併記する）。

        Returns:
            str: エラーメッセージ。
        """
        if self.cause:
            return f"{super().__str__()}. Caused by {self.cause}"
        else:
            return super().__str__()

def num_tokens_from_string(string: str, model_name: str) -> int:
    """Returns the number of tokens in a text string.

    tiktoken が未対応のモデル（Gemini 等）では cl100k_base に近似フォールバックする。
    """
    try:
        encoding = tiktoken.encoding_for_model(model_name)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")
    num_tokens = len(encoding.encode(string))
    return num_tokens

