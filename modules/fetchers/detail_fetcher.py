"""
案件詳細ページの取得モジュール(3サイト共通インターフェース)。

一覧情報だけで判定するのは精度が荒いため、
S/A候補に絞ったうえで詳細ページの本文を取得→再判定する。
"""
from __future__ import annotations
import os
import re
import time
import logging
import asyncio
from typing import Callable
import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

USER_AGENT = os.environ.get(
    "FETCH_USER_AGENT",
    "KoretaScraper/1.0 (contact: koretada.i@gmail.com)",
)
PW_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 "
    "KoretaScraper/1.0 (contact: koretada.i@gmail.com)"
)


def _fetch_with_requests(url: str) -> str:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "ja,en;q=0.9",
    }
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return r.text


def _extract_text(html: str, max_len: int = 4000) -> str:
    """HTMLから本文テキストを抽出(タグ除去・改行整理)。"""
    soup = BeautifulSoup(html, "html.parser")
    # script / style / nav / header / footer を消す
    for sel in ["script", "style", "nav", "header", "footer", "aside"]:
        for el in soup.select(sel):
            el.decompose()
    text = soup.get_text(" ", strip=True)
    # 余分な空白を整理
    text = re.sub(r"\s+", " ", text)
    return text[:max_len]


def fetch_lancers_detail(url: str) -> str:
    html = _fetch_with_requests(url)
    return _extract_text(html)


def fetch_coconala_detail(url: str) -> str:
    html = _fetch_with_requests(url)
    return _extract_text(html)


async def _fetch_cw_detail_async(url: str) -> str:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent=PW_USER_AGENT,
                locale="ja-JP",
            )
            page = await context.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2500)
                html = await page.content()
            finally:
                await context.close()
        finally:
            await browser.close()
    return _extract_text(html)


def fetch_crowdworks_detail(url: str) -> str:
    return asyncio.run(_fetch_cw_detail_async(url))


# 共通インターフェース: source 名 -> 詳細取得関数
DETAIL_FETCHERS: dict[str, Callable[[str], str]] = {
    "ランサーズ": fetch_lancers_detail,
    "ココナラ": fetch_coconala_detail,
    "クラウドワークス": fetch_crowdworks_detail,
}


def fetch_detail(source: str, url: str) -> str:
    """与えられた source 名と URL から本文テキストを取得。失敗時は空文字。"""
    fn = DETAIL_FETCHERS.get(source)
    if not fn:
        log.warning("Unknown source: %s", source)
        return ""
    try:
        return fn(url)
    except Exception as exc:
        log.error("Detail fetch failed: %s %s: %s", source, url, exc)
        return ""
