"""
Notion データベースへの案件INSERT/重複チェック。
Notion API 2025-09 以降の data_sources エンドポイント対応版。
"""
from __future__ import annotations
import os
import logging
from notion_client import Client
from notion_client.errors import APIResponseError

log = logging.getLogger(__name__)

TOKEN = os.environ.get("NOTION_TOKEN", "")
DATABASE_ID = os.environ.get("NOTION_DATABASE_ID", "")
DATA_SOURCE_ID = os.environ.get("NOTION_DATA_SOURCE_ID", "")


def get_client() -> Client:
    if not TOKEN:
        raise RuntimeError("NOTION_TOKEN not set in env")
    return Client(auth=TOKEN)


def _resolve_data_source_id(client: Client) -> str:
    if DATA_SOURCE_ID:
        return DATA_SOURCE_ID
    if not DATABASE_ID:
        raise RuntimeError("NOTION_DATABASE_ID not set")
    db = client.databases.retrieve(database_id=DATABASE_ID)
    ds_list = db.get("data_sources", [])
    if not ds_list:
        raise RuntimeError("No data sources in database")
    return ds_list[0]["id"]


def fetch_existing_job_ids(client: Client, data_source_id: str | None = None) -> set[str]:
    ds_id = data_source_id or _resolve_data_source_id(client)
    existing: set[str] = set()
    cursor = None
    while True:
        kwargs = {"data_source_id": ds_id, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        try:
            resp = client.data_sources.query(**kwargs)
        except APIResponseError as exc:
            log.error("Notion query error: %s", exc)
            break
        for row in resp.get("results", []):
            props = row.get("properties", {})
            jid_prop = props.get("案件ID", {})
            for chunk in jid_prop.get("rich_text", []):
                txt = chunk.get("plain_text", "")
                if txt:
                    existing.add(txt)
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return existing


def _to_rich_text_chunks(text: str, chunk_size: int = 1900) -> list:
    """Notion rich_text は 1要素あたり 2000文字制限。
    長文を複数チャンクに分割して全文保存できるようにする。"""
    if not text:
        return [{"text": {"content": ""}}]
    chunks = []
    for i in range(0, len(text), chunk_size):
        c = text[i : i + chunk_size]
        if c:
            chunks.append({"text": {"content": c}})
    # Notion API は properties.rich_text の上限が大きめだが安全のため 100チャンクまで
    return chunks[:100]


def _build_properties(job: dict, scoring: dict, prompts: dict | None = None, batch_label: str = "朝便") -> dict:
    title = job.get("title", "")[:200] or "(無題)"
    props: dict = {
        "案件名": {"title": [{"text": {"content": title}}]},
        "スコア": {"number": scoring["score"]},
        "判定": {"select": {"name": scoring["rank"]}},
        "Claude完結度": {"select": {"name": scoring["claude_completable"]}},
        "完結理由": {
            "rich_text": [{"text": {"content": scoring["completion_reason"][:1900]}}]
        },
        "取得元": {"select": {"name": job.get("source", "クラウドワークス")}},
        "案件ID": {
            "rich_text": [{"text": {"content": job.get("source_job_id", "")[:100]}}]
        },
        "ステータス": {"select": {"name": "未確認"}},
        "地雷タグ": {
            "multi_select": [
                {"name": tag[:100]} for tag in scoring.get("landmine_tags", [])
            ]
        },
        "説明": {
            "rich_text": _to_rich_text_chunks(job.get("description") or "")
        },
        "取込便": {"select": {"name": batch_label}},
    }
    if job.get("budget_max"):
        props["報酬"] = {"number": job["budget_max"]}
    if job.get("budget_type"):
        props["報酬タイプ"] = {"select": {"name": job["budget_type"]}}
    if job.get("url"):
        props["URL"] = {"url": job["url"]}
    if job.get("category"):
        props["カテゴリ"] = {"select": {"name": job["category"]}}

    # プロンプト列
    if prompts:
        if prompts.get("application_draft"):
            props["応募テンプレ"] = {
                "rich_text": _to_rich_text_chunks(prompts["application_draft"])
            }
        if prompts.get("application_prompt"):
            props["応募プロンプト"] = {
                "rich_text": _to_rich_text_chunks(prompts["application_prompt"])
            }
        if prompts.get("claude_code_prompt"):
            props["Claude Codeプロンプト"] = {
                "rich_text": _to_rich_text_chunks(prompts["claude_code_prompt"])
            }
    return props


def insert_job(
    client: Client,
    job: dict,
    scoring: dict,
    batch_label: str = "朝便",
    prompts: dict | None = None,
    data_source_id: str | None = None,
) -> bool:
    ds_id = data_source_id or _resolve_data_source_id(client)
    props = _build_properties(job, scoring, prompts=prompts, batch_label=batch_label)
    try:
        client.pages.create(
            parent={"data_source_id": ds_id},
            properties=props,
        )
        return True
    except APIResponseError as exc:
        log.error("Notion insert error for %s: %s", job.get("source_job_id"), exc)
        return False
