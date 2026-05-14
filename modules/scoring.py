# -*- coding: utf-8 -*-
"""スコアリング処理

このファイルは「案件を点数化する係」です。
案件本文・予算・カテゴリ・納期・キーワードから12種類のスコアと
総合判定(S/A/B/C/D)・地雷警告・優先理由を計算します。
"""

from __future__ import annotations

import re
from typing import Optional

from .constants import (
    CATEGORY_CODING_FIT,
    CAUTION_ONLY_KEYWORDS,
    FATAL_KEYWORDS,
    HEAVY_NEGATIVE_KEYWORDS,
    POSITIVE_KEYWORDS,
    SCORE_WEIGHTS,
    WARNING_KEYWORDS,
)
from .models import Job
from .utils import contains_any, parse_budget


# ---------- 個別スコア ----------

def _clip(v: float) -> int:
    return int(max(0, min(100, round(v))))


def score_coding_fit(job: Job) -> int:
    """Claude Code / Codexで対応できるかの適性。"""
    base = CATEGORY_CODING_FIT.get(job.category, 55)
    text = f"{job.title}\n{job.description}"
    hits = contains_any(text, POSITIVE_KEYWORDS)
    base += min(15, len(hits) * 3)
    # AI禁止が含まれる案件は致命的に下げる
    if contains_any(text, FATAL_KEYWORDS):
        base = min(base, 10)
    return _clip(base)


def score_ai_fit(job: Job) -> int:
    """AI(自然言語→コード/文章)で実行しやすいか。"""
    base = 60
    text = f"{job.title}\n{job.description}"
    if contains_any(text, FATAL_KEYWORDS):
        return 5
    # 仕様が文字で書きやすいもの・コードで完結するもの
    coding_categories = {
        "LP制作", "HP制作", "Webサイト制作", "GAS",
        "スプレッドシート自動化", "Pythonツール", "スクレイピング",
        "データ整理 / CSV整形", "Streamlitアプリ", "React / Next.js",
        "LINE / Slack通知", "Excel / VBA",
    }
    if job.category in coding_categories:
        base += 20
    if job.category in {"バナー / 画像加工"}:
        base -= 30
    hits = contains_any(text, POSITIVE_KEYWORDS)
    base += min(15, len(hits) * 2)
    if "完全手作業" in text:
        base -= 30
    return _clip(base)


def score_budget(job: Job, min_budget: int = 5000) -> int:
    """単価の良さ。予算が高いほど高得点。"""
    amount = parse_budget(job.budget)
    if amount is None:
        # 予算不明はやや低めに
        return 45
    if amount < min_budget:
        return 15
    # 5000円: 30点, 1万: 45点, 3万: 65点, 5万: 75点, 10万: 85点, 30万+: 95点
    if amount < 10000:
        return _clip(30 + (amount - 5000) / 5000 * 15)
    if amount < 30000:
        return _clip(45 + (amount - 10000) / 20000 * 20)
    if amount < 50000:
        return _clip(65 + (amount - 30000) / 20000 * 10)
    if amount < 100000:
        return _clip(75 + (amount - 50000) / 50000 * 10)
    if amount < 300000:
        return _clip(85 + (amount - 100000) / 200000 * 10)
    return 95


def score_deadline(job: Job) -> int:
    """納期リスクの低さ(短いほど低得点)。"""
    text = f"{job.deadline}\n{job.description}"
    base = 65
    if re.search(r"本日|即日|今日中|数時間", text):
        base = 15
    elif re.search(r"明日|24時間", text):
        base = 30
    elif re.search(r"3日以内|3日間|72時間", text):
        base = 50
    elif re.search(r"1週間|7日", text):
        base = 70
    elif re.search(r"2週間|14日", text):
        base = 80
    elif re.search(r"1ヶ月|1か月|30日", text):
        base = 85
    return _clip(base)


def score_safety(job: Job) -> int:
    """地雷リスクの低さ(警告キーワードが多いほど下がる)。"""
    text = f"{job.title}\n{job.description}\n{job.client_memo}"
    base = 85
    hits = contains_any(text, WARNING_KEYWORDS)
    # CAUTION_ONLY は軽い減点
    light_count = sum(1 for h in hits if h in CAUTION_ONLY_KEYWORDS)
    heavy_count = sum(1 for h in hits if h in HEAVY_NEGATIVE_KEYWORDS)
    other_count = len(hits) - light_count - heavy_count
    base -= heavy_count * 18
    base -= other_count * 7
    base -= light_count * 3
    if contains_any(text, FATAL_KEYWORDS):
        base -= 60
    return _clip(base)


def score_client_lightness(job: Job) -> int:
    """クライアント対応の軽さ(連絡頻度・打合せの少なさ)。"""
    text = f"{job.description}\n{job.client_memo}"
    base = 70
    if re.search(r"対面|常駐|出社", text):
        base -= 40
    if re.search(r"電話|テレカン|MTG|ミーティング", text):
        base -= 15
    if re.search(r"毎日連絡|デイリー", text):
        base -= 15
    if re.search(r"土日対応|深夜対応", text):
        base -= 15
    if re.search(r"チャットのみ|テキストのみ", text):
        base += 10
    return _clip(base)


def score_requirement_clarity(job: Job) -> int:
    """要件明確度。文章量・箇条書きなどから推定。"""
    text = job.description or ""
    length = len(text)
    base = 30
    if length > 200:
        base += 15
    if length > 600:
        base += 15
    if length > 1200:
        base += 10
    # 箇条書きが多いと明確と仮定
    bullets = len(re.findall(r"[\-・●▼□◆◇○]\s|\d+[.)]", text))
    base += min(20, bullets * 3)
    if re.search(r"要件|仕様|機能一覧|納品物|成果物", text):
        base += 10
    if re.search(r"ご相談|応相談|未定|要相談", text):
        base -= 15
    return _clip(base)


def score_revision_risk(job: Job) -> int:
    """修正地獄リスクの低さ。"""
    text = f"{job.title}\n{job.description}"
    base = 70
    if "修正無制限" in text:
        base = 5
    if re.search(r"修正回数(?:は)?未定|修正多め", text):
        base -= 25
    if re.search(r"修正(?:は)?\s*(\d+)\s*回", text):
        m = re.search(r"修正(?:は)?\s*(\d+)\s*回", text)
        try:
            n = int(m.group(1))
            if n <= 2:
                base += 10
            elif n >= 5:
                base -= 15
        except (TypeError, ValueError):
            pass
    return _clip(base)


def score_continuity(job: Job) -> int:
    """継続案件化の可能性。"""
    text = f"{job.title}\n{job.description}"
    base = 40
    if re.search(r"継続|長期|定期|月次|毎月|複数案件", text):
        base += 35
    if re.search(r"単発|スポット|一度のみ", text):
        base -= 15
    return _clip(base)


def score_monthly_goal(job: Job) -> int:
    """月30万円への貢献度(1案件の貢献度)。"""
    amount = parse_budget(job.budget)
    if amount is None:
        return 40
    # 30万のうちどれだけ占めるか(%)を0-100にマップ
    ratio = amount / 300000
    if ratio >= 1.0:
        return 95
    return _clip(20 + ratio * 80)


def score_platform_fit(job: Job) -> int:
    """プラットフォーム適性。"""
    if job.platform == "クラウドワークス":
        return 75
    if job.platform == "ランサーズ":
        return 75
    return 60


# ---------- 警告 / 優先理由 ----------

def build_warnings(job: Job) -> list[str]:
    """地雷ポイントを自然言語で列挙する。"""
    text = f"{job.title}\n{job.description}\n{job.client_memo}".lower()
    warnings: list[str] = []
    amount = parse_budget(job.budget)

    if amount is not None and amount < 5000:
        warnings.append("単価が安すぎる可能性があります")
    if "修正無制限" in text:
        warnings.append("修正回数が多くなりそうです (修正無制限の記載)")
    if re.search(r"本日|即日|今日中", text):
        warnings.append("納期が短すぎる可能性があります")
    if contains_any(text, FATAL_KEYWORDS):
        warnings.append("AI利用禁止の可能性があります")
    if "完全手作業" in text:
        warnings.append("完全手作業前提の可能性があります")
    if re.search(r"資格|薬機法|医療|法律|税務|投資助言", text):
        warnings.append("専門資格や高度な実務経験が必要そうです")
    if re.search(r"無償|テスト無料", text):
        warnings.append("無償テストの可能性があります")
    if re.search(r"対面|常駐|電話", text):
        warnings.append("対面・電話対応が必要そうです")
    if re.search(r"コンペ|当選報酬", text):
        warnings.append("コンペ形式のため受注確度が低い可能性があります")
    if re.search(r"nda|秘密保持", text):
        warnings.append("責任範囲が重い可能性があります (NDA/秘密保持)")
    if re.search(r"低単価大量|大量作業|大量に", text):
        warnings.append("低単価大量作業の可能性があります")
    if re.search(r"毎日連絡|デイリー|土日対応|深夜対応", text):
        warnings.append("連絡負荷が高い可能性があります")
    if re.search(r"応相談|未定|要相談", text) and amount is None:
        warnings.append("作業範囲が曖昧です (要件・予算ともに要相談)")
    return warnings


def build_positive_reasons(job: Job, scores: dict[str, int]) -> list[str]:
    """応募候補の理由を自然言語で列挙する。"""
    reasons: list[str] = []
    text = f"{job.title}\n{job.description}".lower()
    if scores["coding_fit"] >= 75:
        reasons.append("Claude Code / Codexで実装しやすい内容です")
    if scores["requirement_clarity"] >= 65:
        reasons.append("要件が比較的明確です")
    if job.category in {"LP制作", "HP制作", "Webサイト制作", "GAS",
                        "Streamlitアプリ", "React / Next.js",
                        "スプレッドシート自動化"}:
        reasons.append("成果物がコード・Webページ・スプレッドシートなど明確です")
    amount = parse_budget(job.budget)
    if amount is not None and amount < 30000 and amount >= 5000:
        reasons.append("作業範囲が小さく、初回実績作りに向いています")
    if scores["budget"] >= 60 and scores["safety"] >= 60:
        reasons.append("単価と作業量のバランスが良い可能性があります")
    if scores["continuity"] >= 70:
        reasons.append("継続案件化しやすいジャンルです")
    if scores["monthly_goal"] >= 70:
        reasons.append("月30万円に近づきやすい単価帯です")
    return reasons


# ---------- 総合スコア / ランク ----------

def calc_all_scores(job: Job, min_budget: int = 5000) -> dict[str, int]:
    return {
        "coding_fit": score_coding_fit(job),
        "ai_fit": score_ai_fit(job),
        "budget": score_budget(job, min_budget=min_budget),
        "deadline": score_deadline(job),
        "safety": score_safety(job),
        "client_lightness": score_client_lightness(job),
        "requirement_clarity": score_requirement_clarity(job),
        "revision_risk": score_revision_risk(job),
        "continuity": score_continuity(job),
        "monthly_goal": score_monthly_goal(job),
        "platform_fit": score_platform_fit(job),
    }


def calc_total_score(scores: dict[str, int]) -> int:
    total = 0.0
    for k, w in SCORE_WEIGHTS.items():
        total += scores.get(k, 0) * w
    return _clip(total)


def decide_rank(total: int, warnings: list[str], scores: dict[str, int],
                thresholds: Optional[dict[str, int]] = None) -> str:
    """総合判定 S/A/B/C/D を決める。"""
    th = thresholds or {
        "rank_s_threshold": 80,
        "rank_a_threshold": 70,
        "rank_b_threshold": 55,
        "rank_c_threshold": 40,
    }

    # Dの強制条件(致命警告)
    fatal_signals = [
        "AI利用禁止の可能性があります",
        "無償テストの可能性があります",
        "修正回数が多くなりそうです (修正無制限の記載)",
        "専門資格や高度な実務経験が必要そうです",
    ]
    if any(w in warnings for w in fatal_signals):
        return "D"
    if scores.get("safety", 100) < 25:
        return "D"
    if scores.get("budget", 100) < 20:
        return "D"

    if total >= th["rank_s_threshold"] and scores.get("safety", 0) >= 60 \
            and scores.get("coding_fit", 0) >= 70:
        return "S"
    if total >= th["rank_a_threshold"]:
        return "A"
    if total >= th["rank_b_threshold"]:
        return "B"
    if total >= th["rank_c_threshold"]:
        return "C"
    return "D"


def apply_scoring(job: Job, settings: Optional[dict] = None) -> Job:
    """Jobオブジェクトに対しスコア群を計算してフィールドに書き込む。"""
    settings = settings or {}
    min_budget = int(settings.get("min_budget", 5000))
    thresholds = {
        "rank_s_threshold": int(settings.get("rank_s_threshold", 80)),
        "rank_a_threshold": int(settings.get("rank_a_threshold", 70)),
        "rank_b_threshold": int(settings.get("rank_b_threshold", 55)),
        "rank_c_threshold": int(settings.get("rank_c_threshold", 40)),
    }

    scores = calc_all_scores(job, min_budget=min_budget)
    total = calc_total_score(scores)
    warnings = build_warnings(job)
    reasons = build_positive_reasons(job, scores)
    rank = decide_rank(total, warnings, scores, thresholds=thresholds)

    job.score_coding_fit = scores["coding_fit"]
    job.score_ai_fit = scores["ai_fit"]
    job.score_budget = scores["budget"]
    job.score_deadline = scores["deadline"]
    job.score_safety = scores["safety"]
    job.score_client_lightness = scores["client_lightness"]
    job.score_requirement_clarity = scores["requirement_clarity"]
    job.score_revision_risk = scores["revision_risk"]
    job.score_continuity = scores["continuity"]
    job.score_monthly_goal = scores["monthly_goal"]
    job.score_platform_fit = scores["platform_fit"]
    job.score_total = total
    job.rank = rank
    job.warnings = "\n".join(warnings)
    job.positive_reasons = "\n".join(reasons)
    return job
