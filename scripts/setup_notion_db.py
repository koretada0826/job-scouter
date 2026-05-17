"""
Notionに案件管理データベースを1回だけ作成するスクリプト。
作成後、DATABASE_IDを.envに自動追記する。
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from notion_client import Client

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

TOKEN = os.environ["NOTION_TOKEN"]
PARENT_PAGE_ID = os.environ["NOTION_PARENT_PAGE_ID"]

notion = Client(auth=TOKEN)

DB_SCHEMA = {
    "案件名": {"title": {}},
    "スコア": {"number": {"format": "number"}},
    "判定": {
        "select": {
            "options": [
                {"name": "S", "color": "red"},
                {"name": "A", "color": "orange"},
                {"name": "B+", "color": "yellow"},
                {"name": "B", "color": "green"},
                {"name": "C", "color": "blue"},
                {"name": "D", "color": "gray"},
            ]
        }
    },
    "Claude完結度": {
        "select": {
            "options": [
                {"name": "確実完結", "color": "green"},
                {"name": "可能", "color": "blue"},
                {"name": "微妙", "color": "yellow"},
                {"name": "不可", "color": "gray"},
            ]
        }
    },
    "完結理由": {"rich_text": {}},
    "報酬": {"number": {"format": "yen"}},
    "報酬タイプ": {
        "select": {
            "options": [
                {"name": "固定", "color": "default"},
                {"name": "時給", "color": "blue"},
                {"name": "出来高", "color": "purple"},
            ]
        }
    },
    "取得元": {
        "select": {
            "options": [
                {"name": "クラウドワークス", "color": "orange"},
                {"name": "ランサーズ", "color": "blue"},
                {"name": "ココナラ", "color": "pink"},
            ]
        }
    },
    "案件ID": {"rich_text": {}},
    "URL": {"url": {}},
    "カテゴリ": {
        "select": {
            "options": [
                {"name": "システム開発", "color": "red"},
                {"name": "Web開発", "color": "orange"},
                {"name": "AI・機械学習", "color": "purple"},
                {"name": "データ処理", "color": "blue"},
                {"name": "スクレイピング", "color": "green"},
                {"name": "ライティング", "color": "yellow"},
                {"name": "その他", "color": "gray"},
            ]
        }
    },
    "ステータス": {
        "status": {
            "options": [
                {"name": "未確認", "color": "default"},
                {"name": "応募候補", "color": "yellow"},
                {"name": "応募済み", "color": "blue"},
                {"name": "返信あり", "color": "purple"},
                {"name": "契約", "color": "green"},
                {"name": "納品済み", "color": "pink"},
                {"name": "却下", "color": "gray"},
            ],
            "groups": [
                {"name": "未対応", "color": "gray", "option_ids": []},
                {"name": "進行中", "color": "blue", "option_ids": []},
                {"name": "完了", "color": "green", "option_ids": []},
            ],
        }
    },
    "地雷タグ": {"multi_select": {"options": []}},
    "説明": {"rich_text": {}},
    "応募テンプレ": {"rich_text": {}},
    "取込便": {
        "select": {
            "options": [
                {"name": "朝便", "color": "yellow"},
                {"name": "昼便", "color": "orange"},
                {"name": "夜便", "color": "purple"},
            ]
        }
    },
}


def create_database():
    print("Creating database in parent page:", PARENT_PAGE_ID)
    try:
        response = notion.databases.create(
            parent={"type": "page_id", "page_id": PARENT_PAGE_ID},
            title=[{"type": "text", "text": {"content": "案件一覧"}}],
            properties=DB_SCHEMA,
        )
    except Exception as exc:
        if "status" not in DB_SCHEMA["ステータス"]:
            raise
        print("⚠️  status property creation failed, retrying with select...")
        DB_SCHEMA["ステータス"] = {
            "select": {
                "options": [
                    {"name": "未確認", "color": "default"},
                    {"name": "応募候補", "color": "yellow"},
                    {"name": "応募済み", "color": "blue"},
                    {"name": "返信あり", "color": "purple"},
                    {"name": "契約", "color": "green"},
                    {"name": "納品済み", "color": "pink"},
                    {"name": "却下", "color": "gray"},
                ]
            }
        }
        response = notion.databases.create(
            parent={"type": "page_id", "page_id": PARENT_PAGE_ID},
            title=[{"type": "text", "text": {"content": "案件一覧"}}],
            properties=DB_SCHEMA,
        )

    db_id = response["id"]
    db_url = response["url"]
    print(f"\n✅ Database created!")
    print(f"   ID:  {db_id}")
    print(f"   URL: {db_url}")
    return db_id, db_url


def update_env(db_id: str):
    env_path = ROOT / ".env"
    content = env_path.read_text()
    if "NOTION_DATABASE_ID=" in content:
        lines = []
        for line in content.splitlines():
            if line.startswith("NOTION_DATABASE_ID="):
                lines.append(f"NOTION_DATABASE_ID={db_id}")
            else:
                lines.append(line)
        env_path.write_text("\n".join(lines) + "\n")
    else:
        env_path.write_text(content + f"\nNOTION_DATABASE_ID={db_id}\n")
    print(f"\n✅ .env updated with NOTION_DATABASE_ID")


if __name__ == "__main__":
    db_id, db_url = create_database()
    update_env(db_id)
    print(f"\n👉 Open in Notion: {db_url}")
