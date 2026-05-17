"""
クラウドワークス取得モジュール (Playwright版)。
SPA(Vue.js)なので requests では取れない → ヘッドレスChromiumを使う。
"""
from __future__ import annotations
import os
import re
import time
import asyncio
import logging
from dataclasses import dataclass, asdict
from playwright.async_api import async_playwright

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 "
    "KoretaScraper/1.0 (contact: koretada.i@gmail.com)"
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


# クラウドワークスの全カテゴリ新着(2026年現在カテゴリ別URLが不安定なため
# 全カテゴリ新着順 + ページ数で量を稼ぐ方針)
CATEGORIES = {
    "all": ("https://crowdworks.jp/public/jobs?order=new", "その他"),
}


async def _scrape_page(browser, url: str, category_name: str) -> list[JobItem]:
    context = await browser.new_context(
        user_agent=USER_AGENT,
        locale="ja-JP",
        viewport={"width": 1280, "height": 800},
    )
    page = await context.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        try:
            await page.wait_for_selector('a[href^="/public/jobs/"]', timeout=15000)
        except Exception:
            log.warning("No job links rendered for %s", url)
        await page.wait_for_timeout(2500)

        raw_jobs = await page.evaluate(
            """() => {
                const out = [];
                const seen = new Set();
                document.querySelectorAll('a[href*="/public/jobs/"]').forEach(a => {
                    const href = a.getAttribute('href') || '';
                    const m = href.match(/^\\/public\\/jobs\\/(\\d+)$/);
                    if (!m) return;
                    const id = m[1];
                    if (seen.has(id)) return;
                    const title = (a.textContent || '').trim();
                    if (title.length < 5) return;
                    seen.add(id);
                    // 親要素から報酬テキストを取得
                    let p = a;
                    for (let i = 0; i < 8 && p; i++) {
                        p = p.parentElement;
                        if (!p) break;
                        const t = (p.textContent || '').trim();
                        if (/円/.test(t) && t.length > 30) break;
                    }
                    const parentText = p ? (p.textContent || '').trim().slice(0, 600) : '';
                    out.push({ id, href, title, parentText });
                });
                return out;
            }"""
        )
    finally:
        await context.close()

    items: list[JobItem] = []
    for r in raw_jobs:
        bm = re.search(r"((?:時給)?[\d,]+\s*円(?:[〜~][\d,]+\s*円)?)", r["parentText"])
        raw_budget = bm.group(1) if bm else ""
        nums = [int(n.replace(",", "")) for n in re.findall(r"([0-9,]+)\s*円", raw_budget)]
        if not nums:
            bmin, bmax = None, None
        elif len(nums) == 1:
            bmin = bmax = nums[0]
        else:
            bmin, bmax = min(nums), max(nums)
        btype = "時給" if "時給" in raw_budget else "固定"
        items.append(
            JobItem(
                source="クラウドワークス",
                source_job_id=r["id"],
                title=r["title"][:200],
                url=f"https://crowdworks.jp{r['href']}",
                budget_min=bmin,
                budget_max=bmax,
                budget_type=btype,
                category=category_name,
                description=r["parentText"],
                raw_budget_text=raw_budget,
            )
        )
    return items


async def _fetch_async(pages: int, delay: float) -> list[dict]:
    out: dict[str, dict] = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        first = True
        for key, (base_url, cat_name) in CATEGORIES.items():
            for page_num in range(1, pages + 1):
                if not first:
                    await asyncio.sleep(delay)
                first = False
                if page_num == 1:
                    url = base_url
                else:
                    sep = "&" if "?" in base_url else "?"
                    url = f"{base_url}{sep}page={page_num}"
                try:
                    items = await _scrape_page(browser, url, cat_name)
                    log.info("  CrowdWorks %s p%d: %d jobs", key, page_num, len(items))
                    for it in items:
                        out[it.source_job_id] = asdict(it)
                except Exception as exc:
                    log.exception("CrowdWorks fetch error %s p%d: %s", key, page_num, exc)
                    continue
        await browser.close()
    return list(out.values())


def fetch_crowdworks(pages: int = 2, delay: float | None = None) -> list[dict]:
    delay = DELAY if delay is None else delay
    return asyncio.run(_fetch_async(pages, delay))
