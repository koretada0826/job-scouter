"""
案件取得→スコアリング→Notion登録 を1便分まとめて実行する司令塔。

使い方:
    python scripts/batch_pickup.py             # 自動で時間帯判定
    python scripts/batch_pickup.py 朝便         # 明示指定
    python scripts/batch_pickup.py 朝便 --test  # 1サイト最小ページのテスト実行
"""
from __future__ import annotations
import os
import sys
import time
import logging
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from modules.fetchers import fetch_lancers, fetch_coconala, fetch_crowdworks
from modules.fetchers.detail_fetcher import fetch_detail
from modules.job_scorer import score_job, score_with_detail
from modules.notion_writer import get_client, fetch_existing_job_ids, insert_job
from modules.mail_sender import send_summary_email
from modules.auto_prompt_gen import generate_prompts

DETAIL_DELAY_SECONDS = int(os.environ.get("DETAIL_DELAY_SECONDS", "30"))

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("batch_pickup")


def _detect_batch_label() -> str:
    h = datetime.now().hour
    if 5 <= h < 11:
        return "朝便"
    if 11 <= h < 17:
        return "昼便"
    return "夜便"


def main() -> int:
    args = sys.argv[1:]
    test_mode = "--test" in args
    args = [a for a in args if a != "--test"]

    batch_label = args[0] if args else _detect_batch_label()
    log.info("=== Batch pickup start (label=%s, test=%s) ===", batch_label, test_mode)

    pages = 1 if test_mode else int(os.environ.get("FETCH_PAGES_PER_CATEGORY", "2"))

    all_jobs: list[dict] = []

    # ランサーズ
    log.info("--- Fetching Lancers ---")
    try:
        if test_mode:
            jobs = fetch_lancers(categories=["system"], pages=1, delay=2)
        else:
            jobs = fetch_lancers(pages=pages)
        log.info("Lancers: %d jobs", len(jobs))
        all_jobs.extend(jobs)
    except Exception as exc:
        log.exception("Lancers fetch failed: %s", exc)

    # ココナラ
    log.info("--- Fetching Coconala ---")
    try:
        if test_mode:
            jobs = fetch_coconala(pages=1, delay=2)
        else:
            jobs = fetch_coconala(pages=pages)
        log.info("Coconala: %d jobs", len(jobs))
        all_jobs.extend(jobs)
    except Exception as exc:
        log.exception("Coconala fetch failed: %s", exc)

    # クラウドワークス
    log.info("--- Fetching CrowdWorks ---")
    try:
        if test_mode:
            cw_pages = 1
            cw_delay = 2
        else:
            cw_pages = pages
            cw_delay = None
        jobs = fetch_crowdworks(pages=cw_pages, delay=cw_delay)
        log.info("CrowdWorks: %d jobs", len(jobs))
        all_jobs.extend(jobs)
    except Exception as exc:
        log.exception("CrowdWorks fetch failed: %s", exc)

    log.info("=== Total fetched: %d jobs ===", len(all_jobs))

    if not all_jobs:
        log.warning("No jobs fetched. Exit.")
        return 0

    # 一次スコアリング(一覧情報のみ)
    log.info("--- Primary scoring (list-only) ---")
    blocked_primary = 0
    primary_pass: list[tuple[dict, dict]] = []
    for job in all_jobs:
        result = score_job(job)
        if result["should_block"]:
            blocked_primary += 1
            continue
        primary_pass.append((job, dict(result)))
    log.info("Primary: pass=%d, blocked=%d", len(primary_pass), blocked_primary)

    # Notion重複除外(早い段階で行って詳細取得を減らす)
    log.info("--- Notion: fetching existing IDs ---")
    client = get_client()
    existing_ids = fetch_existing_job_ids(client)
    log.info("Existing in Notion: %d", len(existing_ids))

    primary_pass = [
        (j, s) for j, s in primary_pass if j["source_job_id"] not in existing_ids
    ]
    log.info("After dedup: %d", len(primary_pass))

    # 詳細ページ取得+再判定
    if test_mode:
        log.info("--- Skipping detail fetch (test mode) ---")
        final_jobs = primary_pass
        blocked_detail = 0
    else:
        log.info(
            "--- Detail fetch & re-score (%d candidates, delay=%ds) ---",
            len(primary_pass),
            DETAIL_DELAY_SECONDS,
        )
        final_jobs: list[tuple[dict, dict]] = []
        blocked_detail = 0
        for i, (job, primary_score) in enumerate(primary_pass):
            if i > 0:
                time.sleep(DETAIL_DELAY_SECONDS)
            log.info(
                "  [%d/%d] %s %s",
                i + 1,
                len(primary_pass),
                job["source"],
                job["title"][:50],
            )
            detail_text = fetch_detail(job["source"], job["url"])
            if not detail_text:
                # 詳細取得失敗 → 一次判定で通す
                final_jobs.append((job, primary_score))
                continue
            re_result = score_with_detail(job, detail_text)
            if re_result["should_block"]:
                blocked_detail += 1
                log.info(
                    "    → BLOCK by detail: %s", re_result["block_reason"]
                )
                continue
            final_jobs.append((job, dict(re_result)))
        log.info("Detail blocked: %d, Final pass: %d", blocked_detail, len(final_jobs))

    scored = final_jobs

    # プロンプト生成 + INSERT
    log.info("--- Generating prompts & inserting to Notion ---")
    inserted = 0
    skipped = 0
    failed = 0
    scored_with_prompts: list[tuple[dict, dict, dict]] = []
    for job, scoring in scored:
        if job["source_job_id"] in existing_ids:
            skipped += 1
            continue
        prompts = generate_prompts(job, scoring)
        ok = insert_job(client, job, scoring, batch_label=batch_label, prompts=prompts)
        if ok:
            inserted += 1
            scored_with_prompts.append((job, scoring, prompts))
            log.info(
                "  [%s] %s/%d %s",
                scoring["rank"],
                job["source"],
                scoring["score"],
                job["title"][:60],
            )
        else:
            failed += 1

    log.info(
        "=== DONE: inserted=%d skipped=%d failed=%d primary_blocked=%d detail_blocked=%d ===",
        inserted,
        skipped,
        failed,
        blocked_primary,
        blocked_detail,
    )

    # メール通知
    if inserted > 0:
        log.info("--- Sending email summary ---")
        ok = send_summary_email(scored_with_prompts, batch_label)
        log.info("Email send result: %s", "OK" if ok else "FAILED")
    else:
        log.info("No new jobs - email skipped")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
