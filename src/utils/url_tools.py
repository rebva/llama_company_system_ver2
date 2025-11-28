"""
URL 抽出ユーティリティ。
- 最初の URL を取り出し、残りのテキストを返す。
"""
import string
from typing import Tuple, Optional

# URL に使えそうな ASCII 文字だけを許可
ASCII_URL_CHARS = set(
    string.ascii_letters
    + string.digits
    + "-._~:/?#[]@!$&'()*+,;=%"
)


def extract_url_and_rest(message: str) -> Tuple[Optional[str], str]:
    """
    メッセージから最初の URL と、それ以外のテキストを分離する。
    - "http"/"https" を起点に ASCII_URL_CHARS だけを伸ばす
    - それ以外の文字（スペース/日本語など）が来たら URL 終了
    """
    start = message.find("http")
    if start == -1:
        return None, message

    url_chars = []
    for ch in message[start:]:
        if ch in ASCII_URL_CHARS:
            url_chars.append(ch)
        else:
            break

    if not url_chars:
        return None, message

    url = "".join(url_chars)
    rest = message[start + len(url_chars):].strip()
    return url, rest
