# -*- coding: utf-8 -*-
"""Streamlit用UI補助コンポーネント

このファイルは「UIで何回も使うパーツの置き場」です。
"""

from __future__ import annotations

import streamlit as st

from .constants import RANK_COLORS, RANK_DESCRIPTIONS
from .models import Job


def rank_badge(rank: str) -> str:
    """ランクのバッジ用HTML文字列を返す。"""
    color = RANK_COLORS.get(rank, "#6b7280")
    desc = RANK_DESCRIPTIONS.get(rank, "")
    return (
        f'<span style="background:{color};color:white;padding:2px 10px;'
        f'border-radius:12px;font-weight:bold;font-size:0.9em;">'
        f'{rank}</span> <span style="color:#374151;font-size:0.85em;">{desc}</span>'
    )


def score_bar(label: str, score: int) -> None:
    """0-100のスコアをラベル付きで表示。"""
    pct = max(0, min(100, int(score))) / 100
    if score >= 75:
        color = "#16a34a"
    elif score >= 55:
        color = "#2563eb"
    elif score >= 40:
        color = "#ca8a04"
    else:
        color = "#dc2626"
    html = f"""
    <div style='margin:4px 0;'>
      <div style='display:flex;justify-content:space-between;font-size:0.85em;'>
        <span>{label}</span><span><strong>{score}</strong>/100</span>
      </div>
      <div style='background:#e5e7eb;border-radius:6px;height:8px;'>
        <div style='width:{pct*100:.0f}%;background:{color};height:8px;border-radius:6px;'></div>
      </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def copyable_block(label: str, text: str, height: int = 300, key: str | None = None) -> None:
    """コピー用テキストエリア。"""
    st.markdown(f"**{label}** (テキスト枠内をクリック→Cmd/Ctrl+Aで全選択→Cmd/Ctrl+Cでコピー)")
    st.text_area(label, value=text or "", height=height, key=key, label_visibility="collapsed")


def job_summary_card(job: Job) -> None:
    """案件1件の概要カード。"""
    badge = rank_badge(job.rank)
    warning_count = len([w for w in (job.warnings or "").split("\n") if w.strip()])
    title = job.title or "(無題)"
    st.markdown(
        f"#### #{job.id}  {title}  &nbsp; {badge}",
        unsafe_allow_html=True,
    )
    cols = st.columns(5)
    cols[0].metric("総合スコア", job.score_total)
    cols[1].metric("プラットフォーム", job.platform or "-")
    cols[2].metric("予算", job.budget or "-")
    cols[3].metric("ステータス", job.status or "-")
    cols[4].metric("地雷警告", f"{warning_count}件")
