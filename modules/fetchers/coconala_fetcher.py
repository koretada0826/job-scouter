"""
ココナラ公開依頼 取得モジュール。Nuxt.js SSRなので requests でOK。
"""
from __future__ import annotations
import os
import re
import time
import logging
from dataclasses import dataclass, asdict
import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

USER_AGENT = os.environ.get(
    "FETCH_USER_AGENT",
    "KoretaScraper/1.0 (contact: koretada.i@gmail.com)",
)
DELAY = float(os.environ.get("FETCH_DELAY_SECONDS", "60"))


@dataclass
class JobItem:
    source: str
    source_job_id: str
    title: str
    url: str
    budget_min: int | None
    budget_max: int | None
    budget_type: str | None
    category: str
    description: str
    raw_budget_text: str


def _parse_budget(text: str) -> tuple[int | None, int | None, str | None]:
    if not text:
        return None, None, None
    nums = [int(n.replace(",", "")) for n in re.findall(r"([0-9,]+)\s*円", text)]
    btype = "固定"
    if not nums:
        return None, None, btype
    if len(nums) == 1:
        return nums[0], nums[0], btype
    return min(nums), max(nums), btype


def _fetch_listing_page(page: int) -> str:
    if page == 1:
        url = "https://coconala.com/requests"
    else:
        url = f"https://coconala.com/requests?page={page}"
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "ja,en;q=0.9",
    }
    log.info("Fetching Coconala /requests page=%d", page)
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return r.text


def _parse_listing(html: str) -> list[JobItem]:
    soup = BeautifulSoup(html, "html.parser")
    jobs_by_id: dict[str, dict] = {}

    # 案件詳細リンクは 相対 `/requests/数字` または絶対 `https://coconala.com/requests/数字`
    # ID をキーにして、テキストの長いものを優先で保持
    for a in soup.find_all("a", href=True):
        href = a["href"]
        m = re.search(r"/requests/(\d+)(?:[/?#]|$)", href)
        if not m:
            continue
        # カテゴリ系 (/requests/categories/...) は除外
        if "/categories/" in href or href.endswith("/recommend"):
            continue
        job_id = m.group(1)
        title = a.get_text(strip=True)

        # 既存より新しい(タイトル長い)方を優先
        existing = jobs_by_id.get(job_id)
        if existing and len(existing["title"]) >= len(title):
            continue

        jobs_by_id[job_id] = {"a": a, "title": title, "href": href}

    jobs: list[JobItem] = []
    for job_id, info in jobs_by_id.items():
        a = info["a"]
        title = info["title"]
        href = info["href"]
        if not title or len(title) < 5:
            # タイトル取れてない場合、親要素から検索
            p = a.parent
            for _ in range(5):
                if p is None:
                    break
                txt = p.get_text(" ", strip=True)
                if len(txt) > 10:
                    title = txt[:200]
                    break
                p = p.parent
        if not title or len(title) < 5:
            continue

        parent = a
        for _ in range(8):
            if parent is None:
                break
            parent = parent.parent
            if parent is None:
                break
            txt = parent.get_text(" ", strip=True)
            if "円" in txt and len(txt) > 30:
                break

        parent_text = parent.get_text(" ", strip=True) if parent else ""
        budget_match = re.search(r"((?:時給)?[\d,]+\s*円(?:[〜~][\d,]+\s*円)?)", parent_text)
        raw_budget = budget_match.group(1) if budget_match else ""
        budget_min, budget_max, budget_type = _parse_budget(raw_budget)

        absolute_url = (
            href if href.startswith("http") else f"https://coconala.com{href}"
        )
        jobs.append(
            JobItem(
                source="ココナラ",
                source_job_id=job_id,
                title=title[:200],
                url=absolute_url,
                budget_min=budget_min,
                budget_max=budget_max,
                budget_type=budget_type,
                category="その他",
                description=parent_text[:600],
                raw_budget_text=raw_budget,
            )
        )
    return jobs


def fetch_coconala(pages: int = 3, delay: float | None = None) -> list[dict]:
    delay = DELAY if delay is None else delay
    all_jobs: list[dict] = []
    for page in range(1, pages + 1):
        if page > 1:
            time.sleep(delay)
        try:
            html = _fetch_listing_page(page)
            jobs = _parse_listing(html)
            log.info("  Coconala p%d: %d jobs", page, len(jobs))
            all_jobs.extend(asdict(j) for j in jobs)
        except Exception as exc:
            log.exception("Coconala fetch error p%d: %s", page, exc)
            continue
    deduped: dict[str, dict] = {}
    for j in all_jobs:
        deduped[j["source_job_id"]] = j
    return list(deduped.values())
