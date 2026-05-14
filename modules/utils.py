# -*- coding: utf-8 -*-
"""共通ユーティリティ

このファイルは「ちょっとした共通処理の道具箱」です。
予算の数値化や日付文字列の生成などをまとめています。
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional


def now_str() -> str:
    """現在時刻をISO風の文字列で返す。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_budget(text: str) -> Optional[int]:
    """予算文字列から代表値(円)を抽出する。

    例:
      "10,000円〜30,000円" -> 30000 (上限を採用)
      "5万円"             -> 50000
      "時給2000円"         -> 2000 (時給/単価不明はそのまま数値化)
      ""                   -> None
    """
    if not text:
        return None
    s = str(text)

    # 「万」を含む数字を円に変換
    man_matches = re.findall(r"(\d+(?:\.\d+)?)\s*万", s)
    man_values = [int(float(m) * 10000) for m in man_matches]

    # 通常の数値(カンマ込み)
    num_matches = re.findall(r"(\d{1,3}(?:,\d{3})+|\d+)", s.replace("万", " "))
    num_values: list[int] = []
    for m in num_matches:
        try:
            num_values.append(int(m.replace(",", "")))
        except ValueError:
            continue

    candidates = man_values + num_values
    if not candidates:
        return None

    # 「〜」「-」がある場合は上限側を採用
    return max(candidates)


def safe_text(text: Optional[str]) -> str:
    """Noneや空白を安全に文字列化する。"""
    if text is None:
        return ""
    return str(text)


def truncate(text: Optional[str], limit: int = 60) -> str:
    """一覧表示用に文字列を短く整える。"""
    s = safe_text(text).replace("\n", " ").strip()
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "…"


def contains_any(text: str, keywords: list[str]) -> list[str]:
    """テキストにキーワードが含まれていればそのリストを返す。"""
    if not text:
        return []
    found = []
    lower = text.lower()
    for kw in keywords:
        if kw.lower() in lower:
            found.append(kw)
    return found
