# -*- coding: utf-8 -*-
"""SQLite データベース操作

このファイルは「案件データをディスクに保存・取り出しする係」です。
初回起動時にDBとテーブルを自動生成し、必要なら簡易マイグレーションも行います。
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

from .constants import DEFAULT_SETTINGS
from .models import Job
from .utils import now_str


DB_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DB_DIR / "database.sqlite"


# jobsテーブルに必要なカラム定義(マイグレーション用)
JOB_COLUMNS: dict[str, str] = {
    "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
    "platform": "TEXT",
    "title": "TEXT",
    "url": "TEXT",
    "description": "TEXT",
    "budget": "TEXT",
    "category": "TEXT",
    "deadline": "TEXT",
    "client_memo": "TEXT",
    "memo": "TEXT",
    "status": "TEXT",
    "score_total": "INTEGER",
    "score_coding_fit": "INTEGER",
    "score_ai_fit": "INTEGER",
    "score_budget": "INTEGER",
    "score_deadline": "INTEGER",
    "score_safety": "INTEGER",
    "score_client_lightness": "INTEGER",
    "score_requirement_clarity": "INTEGER",
    "score_revision_risk": "INTEGER",
    "score_continuity": "INTEGER",
    "score_monthly_goal": "INTEGER",
    "score_platform_fit": "INTEGER",
    "rank": "TEXT",
    "warnings": "TEXT",
    "positive_reasons": "TEXT",
    "application_prompt": "TEXT",
    "application_draft": "TEXT",
    "claude_code_prompt": "TEXT",
    "codex_prompt": "TEXT",
    "pre_apply_checklist": "TEXT",
    "delivery_checklist": "TEXT",
    "estimate_text": "TEXT",
    "created_at": "TEXT",
    "updated_at": "TEXT",
}


def _connect() -> sqlite3.Connection:
    """DB接続を返す。data/が無ければ作る。"""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """テーブルを作成し、必要なら不足カラムを追加する。"""
    conn = _connect()
    try:
        cur = conn.cursor()

        # jobsテーブル
        cols_sql = ", ".join(f"{name} {ddl}" for name, ddl in JOB_COLUMNS.items())
        cur.execute(f"CREATE TABLE IF NOT EXISTS jobs ({cols_sql})")

        # 既存テーブルに不足カラムがあれば追加(簡易マイグレーション)
        cur.execute("PRAGMA table_info(jobs)")
        existing = {row["name"] for row in cur.fetchall()}
        for name, ddl in JOB_COLUMNS.items():
            if name not in existing:
                # PRIMARY KEYは追加できないので除外
                if "PRIMARY KEY" in ddl:
                    continue
                cur.execute(f"ALTER TABLE jobs ADD COLUMN {name} {ddl}")

        # settingsテーブル(キー/値)
        cur.execute(
            "CREATE TABLE IF NOT EXISTS settings ("
            "key TEXT PRIMARY KEY, value TEXT)"
        )

        # 初期設定を投入(無いキーだけ)
        for k, v in DEFAULT_SETTINGS.items():
            cur.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (k, json.dumps(v)),
            )

        conn.commit()
    finally:
        conn.close()


# ---------- settings ----------

def get_setting(key: str, default=None):
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cur.fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except (json.JSONDecodeError, TypeError):
            return row["value"]
    finally:
        conn.close()


def set_setting(key: str, value) -> None:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )
        conn.commit()
    finally:
        conn.close()


def get_all_settings() -> dict:
    """全設定を辞書で返す(欠けはDEFAULT_SETTINGSで補完)。"""
    result = dict(DEFAULT_SETTINGS)
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT key, value FROM settings")
        for row in cur.fetchall():
            try:
                result[row["key"]] = json.loads(row["value"])
            except (json.JSONDecodeError, TypeError):
                result[row["key"]] = row["value"]
    finally:
        conn.close()
    return result


# ---------- jobs ----------

def _job_from_row(row: sqlite3.Row) -> Job:
    data = {k: row[k] for k in row.keys() if k in JOB_COLUMNS}
    # スコア系がNoneだとdataclassのintと型が合わないので補完
    for k in list(data.keys()):
        if k.startswith("score_") and data[k] is None:
            data[k] = 0
        if data[k] is None and k not in ("id",):
            data[k] = ""
    return Job(**data)


def insert_job(job: Job) -> int:
    job.created_at = job.created_at or now_str()
    job.updated_at = now_str()
    fields = [c for c in JOB_COLUMNS.keys() if c != "id"]
    placeholders = ", ".join("?" for _ in fields)
    values = [getattr(job, f) for f in fields]

    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            f"INSERT INTO jobs ({', '.join(fields)}) VALUES ({placeholders})",
            values,
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def update_job(job: Job) -> None:
    if job.id is None:
        raise ValueError("update_job: job.id が必要です")
    job.updated_at = now_str()
    fields = [c for c in JOB_COLUMNS.keys() if c != "id"]
    assignments = ", ".join(f"{f} = ?" for f in fields)
    values = [getattr(job, f) for f in fields] + [job.id]

    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(f"UPDATE jobs SET {assignments} WHERE id = ?", values)
        conn.commit()
    finally:
        conn.close()


def update_job_status(job_id: int, status: str) -> None:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?",
            (status, now_str(), job_id),
        )
        conn.commit()
    finally:
        conn.close()


def delete_job(job_id: int) -> None:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        conn.commit()
    finally:
        conn.close()


def get_job(job_id: int) -> Optional[Job]:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        row = cur.fetchone()
        if row is None:
            return None
        return _job_from_row(row)
    finally:
        conn.close()


def list_jobs() -> list[Job]:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM jobs ORDER BY id DESC")
        return [_job_from_row(r) for r in cur.fetchall()]
    finally:
        conn.close()
