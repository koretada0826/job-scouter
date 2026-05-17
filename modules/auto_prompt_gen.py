"""
自動取込パイプライン用のプロンプト生成。
取得dict → Job dataclass 変換 → 既存 prompt_generator の各関数を呼ぶ。
"""
from __future__ import annotations
from .models import Job
from . import prompt_generator as pg

# 取得カテゴリ → アプリ内CATEGORIES へのマッピング
CATEGORY_MAP = {
    "システム開発": "Pythonツール",
    "Web開発": "Webサイト制作",
    "AI・機械学習": "Pythonツール",
    "データ処理": "データ整理 / CSV整形",
    "スクレイピング": "スクレイピング",
    "ライティング": "記事作成 / 構成作成",
    "デザイン": "バナー / 画像加工",
    "その他": "その他",
}


def _detect_category(job_dict: dict) -> str:
    """取得dict のカテゴリ + タイトル/説明から細かいカテゴリを推定。"""
    raw_cat = job_dict.get("category", "その他")
    text = (job_dict.get("title", "") + " " + job_dict.get("description", "")).lower()

    # 強いキーワードで判定優先
    if "lp制作" in text or "lp作成" in text or "ランディングページ" in text:
        return "LP制作"
    if "wordpress" in text or "ワードプレス" in text:
        return "WordPress修正"
    if "shopify" in text or "ec構築" in text:
        return "Shopify / EC"
    if "next.js" in text or "react" in text:
        return "React / Next.js"
    if "streamlit" in text:
        return "Streamlitアプリ"
    if "スクレイピング" in text or "クローリング" in text:
        return "スクレイピング"
    if "gas" in text or "google apps script" in text or "スプレッドシート" in text:
        return "GAS"
    if "vba" in text or "excel" in text and "自動" in text:
        return "Excel / VBA"
    if "python" in text:
        return "Pythonツール"
    if "csv" in text or "データ整理" in text or "データ抽出" in text:
        return "データ整理 / CSV整形"
    if "line" in text or "slack" in text:
        return "LINE / Slack通知"
    if "hp" in text or "ホームページ" in text:
        return "HP制作"
    if "記事" in text or "ライティング" in text or "seo" in text:
        return "記事作成 / 構成作成"
    if "バナー" in text or "画像加工" in text:
        return "バナー / 画像加工"

    return CATEGORY_MAP.get(raw_cat, "その他")


def _to_job(job_dict: dict, scoring: dict) -> Job:
    """取得dict + スコアリング → Job dataclass"""
    budget_max = job_dict.get("budget_max")
    budget_min = job_dict.get("budget_min")
    if budget_max and budget_min and budget_max != budget_min:
        budget_text = f"{budget_min:,}円〜{budget_max:,}円"
    elif budget_max:
        budget_text = f"{budget_max:,}円"
    else:
        budget_text = "予算非公開"
    btype = job_dict.get("budget_type") or ""
    if btype:
        budget_text = f"{btype}: {budget_text}"

    rank_to_letter = {"S": "S", "A": "A", "B+": "B", "B": "B", "C": "C", "D": "D"}

    return Job(
        platform=job_dict.get("source", ""),
        title=job_dict.get("title", ""),
        url=job_dict.get("url", ""),
        description=job_dict.get("description", "")[:4000],
        budget=budget_text,
        category=_detect_category(job_dict),
        rank=rank_to_letter.get(scoring.get("rank", "C"), "C"),
        score_total=scoring.get("score", 0),
        warnings="\n".join(scoring.get("landmine_tags", [])),
        positive_reasons=scoring.get("completion_reason", ""),
    )


def generate_prompts(job_dict: dict, scoring: dict) -> dict:
    """応募文+応募プロンプト+Claude Codeプロンプトを一括生成。
    Returns dict with keys:
      - application_draft  (完成版応募文)
      - application_prompt (AI用 応募文作成プロンプト)
      - claude_code_prompt (Claude Code 実行プロンプト)
    """
    job = _to_job(job_dict, scoring)
    return {
        "application_draft": pg.build_application_draft(job),
        "application_prompt": pg.build_application_prompt(job),
        "claude_code_prompt": pg.build_claude_code_prompt(job),
    }
