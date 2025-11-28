"""
互換用モジュール。実装は src/utils/web_fetch.py に集約。
"""
from typing import List, Dict

from src.utils.web_fetch import fetch_url_and_summarize  # noqa: F401


def search_and_collect(keywords: str) -> List[Dict[str, str]]:
    """ダミー検索（従来通り）。"""
    return [
        {
            "title": f"Security best practices for {keywords}",
            "url": "https://cheatsheetseries.owasp.org/",
            "snippet": "OWASP Cheat Sheet Series is a compilation of best practices..."
        }
    ]
