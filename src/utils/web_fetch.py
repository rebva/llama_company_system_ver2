"""
シンプルなスクレイピングヘルパー。
- URL を取得してテキスト要約を返す。
"""
import requests
from bs4 import BeautifulSoup

from src.config import DEFAULT_HEADERS


def fetch_url_and_summarize(url: str, max_chars: int = 1200) -> str:
    """
    ページを取得し、段落テキストをつなげて頭から指定文字数まで返す。
    """
    resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=10)
    resp.raise_for_status()

    # 推定エンコーディングを尊重して文字化けを防ぐ
    if resp.apparent_encoding:
        resp.encoding = resp.apparent_encoding

    soup = BeautifulSoup(resp.text, "html.parser")
    texts = [p.get_text(strip=True) for p in soup.find_all("p")]
    full_text = "\n".join(texts)

    summary = full_text[:max_chars]
    return summary or "No content found."
