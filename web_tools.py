# web_tools.pyウェブスクレイピングツール
"""
Web access tools (very simple version).

- fetch_url_and_summarize(url): Get HTML and return rough text summary.
- search_and_collect(keywords): Dummy search function (you can replace with real API).
"""

from typing import List, Dict
import requests
from bs4 import BeautifulSoup


def fetch_url_and_summarize(url: str, max_chars: int = 1000) -> str:
    """
    Fetch (取得する) the HTML of the URL and return a rough summary (ざっくり要約).

    NOTE:
        - This is a very simple heuristic.
        - For real use, you may want:
            - readability(可読性) ライブラリ
            - JavaScript 実行付きブラウザ (Playwright, Browser Use, etc.)
    """
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    texts = [p.get_text(strip=True) for p in soup.find_all("p")]
    full_text = "\n".join(texts)

    summary = full_text[:max_chars]
    return summary or "No content found."


def search_and_collect(keywords: str) -> List[Dict[str, str]]:
    """
    Dummy search (ダミー検索).

    REAL WORLD:
        - Google Custom Search API
        - Serper, Tavily
        - or scraping HTML search result page
    """
    # 擬似的なモック結果 (mock result)
    return [
        {
            "title": f"Security best practices for {keywords}",
            "url": "https://cheatsheetseries.owasp.org/",
            "snippet": "OWASP Cheat Sheet Series is a compilation of best practices..."
        }
    ]
