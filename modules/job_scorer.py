"""
案件スコアリング + Claude完結度判定 + 自動取込フィルタ。

ユーザー方針:
- 「初心者歓迎」「ママさん歓迎」「コミュ力」等は除外しない、タグ記録のみ
- 除外するのは: 低単価 / 物理作業必須 / 専門資格必須 / 危険系
"""
from __future__ import annotations
from typing import TypedDict
from .constants import (
    AUTO_BLOCK_KEYWORDS,
    SOFT_FLAG_KEYWORDS,
    CLAUDE_NG_KEYWORDS,
    CLAUDE_OK_KEYWORDS,
    POSITIVE_KEYWORDS,
)

# 取り込み除外する最低報酬(円) - これ未満は明らかに割に合わない
MIN_BUDGET_BLOCK = 1000

# 警告レベル単価(タグ記録のみ、ブロックしない)
LOW_BUDGET_FLAG = 3000


class ScoringResult(TypedDict):
    score: int                 # 0-100
    rank: str                  # S / A / B+ / B / C / D
    claude_completable: str    # 確実完結 / 可能 / 微妙 / 不可
    completion_reason: str
    landmine_tags: list[str]
    should_block: bool
    block_reason: str
    completion_reason_short: str


def _text(job: dict) -> str:
    return " ".join(
        [
            job.get("title", ""),
            job.get("description", ""),
            job.get("raw_budget_text", ""),
        ]
    )


def _check_block(job: dict) -> tuple[bool, str]:
    """自動取込除外判定。True = 除外。"""
    text = _text(job)

    # 低単価ブロック (明示的に報酬がついてて MIN_BUDGET_BLOCK 未満)
    bmax = job.get("budget_max")
    if isinstance(bmax, (int, float)) and bmax < MIN_BUDGET_BLOCK:
        return True, f"低単価(報酬上限{bmax:,}円)"

    # AUTO_BLOCK_KEYWORDS
    for kw in AUTO_BLOCK_KEYWORDS:
        if kw in text:
            return True, f"論外条件({kw})"

    return False, ""


def _check_claude_completable(job: dict) -> tuple[str, str]:
    """Claude完結度を判定。"""
    text = _text(job)
    ng_hits = [kw for kw in CLAUDE_NG_KEYWORDS if kw in text]
    ok_hits = [kw for kw in CLAUDE_OK_KEYWORDS if kw in text]
    pos_hits = [kw for kw in POSITIVE_KEYWORDS if kw in text]

    ok_count = len(set(ok_hits)) + len(set(pos_hits))

    if len(ng_hits) >= 2:
        return "不可", f"NG多数: {', '.join(ng_hits[:3])}"
    if len(ng_hits) == 1:
        if ok_count >= 2:
            return "微妙", f"NG:{ng_hits[0]} / OK:{', '.join(list(set(ok_hits + pos_hits))[:3])}"
        return "不可", f"NG: {ng_hits[0]}"

    if ok_count >= 3:
        return "確実完結", f"OK多数: {', '.join(list(set(ok_hits + pos_hits))[:3])}"
    if ok_count >= 1:
        return "可能", f"OK: {', '.join(list(set(ok_hits + pos_hits))[:3])}"

    return "微妙", "判定材料不足(タイトル/説明から強い手がかりなし)"


def _check_landmine_tags(job: dict) -> list[str]:
    text = _text(job)
    tags = []
    for kw in SOFT_FLAG_KEYWORDS:
        if kw in text:
            tags.append(kw)
    # 低単価フラグ(ブロックしないライン)
    bmax = job.get("budget_max")
    if isinstance(bmax, (int, float)) and MIN_BUDGET_BLOCK <= bmax < LOW_BUDGET_FLAG:
        tags.append(f"低単価({bmax}円)")
    return list(dict.fromkeys(tags))


def _score(job: dict, claude_completable: str, landmine_tags: list[str]) -> int:
    """0-100でスコア算出。"""
    score = 50

    # 報酬による加点
    bmax = job.get("budget_max") or 0
    bmin = job.get("budget_min") or 0
    avg = (bmax + bmin) / 2 if (bmax and bmin) else (bmax or bmin)
    if avg >= 100000:
        score += 25
    elif avg >= 50000:
        score += 18
    elif avg >= 20000:
        score += 12
    elif avg >= 10000:
        score += 6
    elif avg >= 5000:
        score += 2
    elif avg > 0:
        score -= 5

    # Claude完結度
    score += {"確実完結": 20, "可能": 10, "微妙": -5, "不可": -20}.get(
        claude_completable, 0
    )

    # 警告タグ多すぎる
    score -= min(len(landmine_tags) * 2, 10)

    return max(0, min(100, score))


def _rank(score: int) -> str:
    if score >= 85:
        return "S"
    if score >= 70:
        return "A"
    if score >= 55:
        return "B+"
    if score >= 40:
        return "B"
    if score >= 25:
        return "C"
    return "D"


def score_with_detail(job: dict, detail_text: str) -> ScoringResult:
    """詳細ページの本文を反映して再判定。
    一覧では見えなかった「対面打合せ」「専門資格」「動画編集」等が出てきたら
    自動ブロックに格上げする。
    """
    # job を浅くコピーして、description を一覧+詳細の連結に置き換え
    job2 = dict(job)
    base_desc = job.get("description", "")
    job2["description"] = (base_desc + "\n\n" + detail_text)[:8000]
    return score_job(job2)


def score_job(job: dict) -> ScoringResult:
    """1案件を判定。"""
    blocked, block_reason = _check_block(job)
    completable, completion_reason = _check_claude_completable(job)
    landmines = _check_landmine_tags(job)
    score_val = _score(job, completable, landmines)
    rank = _rank(score_val)

    # Claude完結度が「可能」「確実完結」以外は自動ブロック
    if not blocked and completable not in ("可能", "確実完結"):
        blocked = True
        block_reason = f"Claude完結度:{completable}"

    # B+以下も自動ブロック(S/Aのみ通す)
    if not blocked and rank not in ("S", "A"):
        blocked = True
        block_reason = f"ランク不足({rank})"

    short = completion_reason[:80]

    return ScoringResult(
        score=score_val,
        rank=rank,
        claude_completable=completable,
        completion_reason=completion_reason,
        landmine_tags=landmines,
        should_block=blocked,
        block_reason=block_reason,
        completion_reason_short=short,
    )
