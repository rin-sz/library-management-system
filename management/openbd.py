from datetime import datetime

import requests

OPENBD_API_URL = "https://api.openbd.jp/v1/get"


class OpenBDError(Exception):
    """openBD APIとの通信に関するエラー"""

    pass


def _parse_pubdate(pubdate: str | None) -> str | None:
    """openBDのpubdate(不定形式)をISO 8601形式に正規化する。"""
    if not pubdate:
        return None
    pubdate = pubdate.strip()
    for fmt in ("%Y%m%d", "%Y-%m", "%Y%m", "%Y"):
        try:
            return datetime.strptime(pubdate, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def get_book_by_isbn(isbn: str) -> dict | None:
    """ISBNを指定してopenBDから書誌情報を取得する。該当なしならNone。"""
    try:
        response = requests.get(
            OPENBD_API_URL,
            params={"isbn": isbn},
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        raise OpenBDError(f"openBDへの接続に失敗しました: {e}") from e

    if not data or data[0] is None:
        return None

    summary = data[0].get("summary")
    if not summary:
        return None

    return {
        "isbn": summary.get("isbn"),
        "title": summary.get("title"),
        "author": summary.get("author"),
        "publisher": summary.get("publisher"),
        "published_date": _parse_pubdate(summary.get("pubdate")),
        "thumbnail_url": summary.get("cover"),
    }
