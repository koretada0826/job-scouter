"""
ランサーズ取得モジュール。
SSRなので requests + BeautifulSoup でOK。
"""
from __future__ import annotations
import os
import re
import time
import logging
from dataclasses import dataclass, asdict
from typing import Iterable
import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

USER_AGENT = os.environ.get(
    "FETCH_USER_AGENT",
    "KoretaScraper/1.0 (contact: koretada.i@gmail.com)",
)
DELAY = float(os.environ.get("FETCH_DELAY_SECONDS", "60"))

# Lancers カテゴリパス → 表示名
CATEGORIES = {
    "system": "システム開発",
    "web": "Web開発",
    "writing": "ライティング",
    "task": "データ処理",
    "design": "デザイン",
}


@dataclass
class JobItem:
    source: str           # "ランサーズ"
    source_job_id: str
    title: str
    url: str
    budget_min: int | None
    budget_max: int | None
    budget_type: str | None  # "固定" / "時給" / "出来高" / None
    category: str
    description: str       # 一覧に出てる説明文
    raw_budget_text: str   # 元の報酬テキスト


def _parse_budget(text: str) -> tuple[int | None, int | None, str | None]:
    """報酬テキストから min/max/type を抽出。
    例: "5,000円〜10,000円" / "時給1,500円〜" / "予算非公開"
    """
    if not text:
        return None, None, None
    btype = None
    if "時給" in text:
        btype = "時給"
    elif "出来高" in text:
        btype = "出来高"
    else:
        btype = "固定"

    nums = [int(n.replace(",", "")) for n in re.findall(r"([0-9,]+)\s*円", text)]
    if not nums:
        return None, None, btype
    if len(nums) == 1:
        return nums[0], nums[0], btype
    return min(nums), max(nums), btype


def _fetch_listing_page(category: str, page: int) -> str:
    """指定カテゴリ・ページの HTML を取得。"""
    if page == 1:
        url = f"https://www.lancers.jp/work/search/{category}"
    else:
        url = f"https://www.lancers.jp/work/search/{category}?page={page}"
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "ja,en;q=0.9",
    }
    log.info("Fetching Lancers %s page=%d", category, page)
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return r.text


def _parse_listing(html: str, category_name: str) -> list[JobItem]:
    """一覧HTMLから案件カードを抽出。"""
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[JobItem] = []
    seen_ids: set[str] = set()

    # 案件カード: a[href*="/work/detail/{ID}"] が含まれる li
    for a in soup.select('a[href*="/work/detail/"]'):
        href = a.get("href", "")
        m = re.search(r"/work/detail/(\d+)", href)
        if not m:
            continue
        job_id = m.group(1)
        if job_id in seen_ids:
            continue
        seen_ids.add(job_id)

        title = a.get_text(strip=True)
        if not title or len(title) < 5:
            continue

        # 親要素から報酬テキスト等を探す(li/article 親)
        parent = a
        for _ in range(6):
            parent = parent.parent
            if parent is None:
                break
            txt = parent.get_text(" ", strip=True)
            if "円" in txt and len(txt) > 30:
                break

        parent_text = parent.get_text(" ", strip=True) if parent else ""
        # 報酬テキスト抽出(円が出てくる範囲)
        budget_match = re.search(r"((?:時給)?[\d,]+\s*円(?:〜[\d,]+\s*円)?)", parent_text)
        raw_budget = budget_match.group(1) if budget_match else ""
        budget_min, budget_max, budget_type = _parse_budget(raw_budget)

        # 説明文(タイトル以外の前置きテキストを取れる範囲で)
        description = parent_text[:600] if parent_text else ""

        absolute_url = (
            href if href.startswith("http") else f"https://www.lancers.jp{href}"
        )
        jobs.append(
            JobItem(
                source="ランサーズ",
                source_job_id=job_id,
                title=title[:200],
                url=absolute_url,
                budget_min=budget_min,
                budget_max=budget_max,
                budget_type=budget_type,
                category=category_name,
                description=description,
                raw_budget_text=raw_budget,
            )
        )
    return jobs


def fetch_lancers(
    categories: Iterable[str] | None = None,
    pages: int = 2,
    delay: float | None = None,
) -> list[dict]:
    """ランサーズの新着案件を取得。
    Returns: list of dict (JobItem.asdict)
    """
    if categories is None:
        categories = list(CATEGORIES.keys())
    delay = DELAY if delay is None else delay

    all_jobs: list[dict] = []
    first = True
    for cat_key in categories:
        cat_name = CATEGORIES.get(cat_key, cat_key)
        for page in range(1, pages + 1):
            if not first:
                time.sleep(delay)
            first = False
            try:
                html = _fetch_listing_page(cat_key, page)
                jobs = _parse_listing(html, cat_name)
                log.info("  Lancers %s p%d: %d jobs", cat_key, page, len(jobs))
                all_jobs.extend(asdict(j) for j in jobs)
            except Exception as exc:
                log.exception("Lancers fetch error: %s p%d: %s", cat_key, page, exc)
                continue

    # 重複除去 (source_job_id ベース)
    deduped: dict[str, dict] = {}
    for j in all_jobs:
        deduped[j["source_job_id"]] = j
    return list(deduped.values())
