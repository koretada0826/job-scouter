# -*- coding: utf-8 -*-
"""データクラス定義

このファイルは「案件1件分の形(設計図)」を定義する場所です。
DBの行とPython側のオブジェクトを行き来しやすくします。
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Job:
    """案件1件分のデータ。"""

    id: Optional[int] = None
    platform: str = ""
    title: str = ""
    url: str = ""
    description: str = ""
    budget: str = ""
    category: str = ""
    deadline: str = ""
    client_memo: str = ""
    memo: str = ""
    status: str = "未応募"

    # スコア(0-100)
    score_total: int = 0
    score_coding_fit: int = 0
    score_ai_fit: int = 0
    score_budget: int = 0
    score_deadline: int = 0
    score_safety: int = 0
    score_client_lightness: int = 0
    score_requirement_clarity: int = 0
    score_revision_risk: int = 0
    score_continuity: int = 0
    score_monthly_goal: int = 0
    score_platform_fit: int = 0

    rank: str = "C"

    # 警告/理由/プロンプト類は改行区切りの文字列で保存
    warnings: str = ""
    positive_reasons: str = ""
    application_prompt: str = ""
    application_draft: str = ""
    claude_code_prompt: str = ""
    codex_prompt: str = ""
    pre_apply_checklist: str = ""
    delivery_checklist: str = ""
    estimate_text: str = ""

    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
