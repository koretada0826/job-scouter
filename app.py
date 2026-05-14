# -*- coding: utf-8 -*-
"""AI案件ハンター — メインアプリ

Claude Code / Codexで対応できる案件だけを見極め、
応募から実行準備までを支援するローカル案件管理ツール。
"""

from __future__ import annotations

import re
from typing import Optional

import pandas as pd
import streamlit as st

from modules.constants import (
    CATEGORIES,
    DEFAULT_SETTINGS,
    PLATFORMS,
    RANKS,
    STATUSES,
)
from modules.database import (
    delete_job,
    get_all_settings,
    get_job,
    init_db,
    insert_job,
    list_jobs,
    set_setting,
    update_job,
    update_job_status,
)
from modules.models import Job
from modules.prompt_generator import apply_prompts
from modules.scoring import apply_scoring
from modules.ui_components import (
    copyable_block,
    job_summary_card,
    rank_badge,
    score_bar,
)
from modules.utils import parse_budget, truncate


# ---------- 共通セットアップ ----------

st.set_page_config(
    page_title="AI案件ハンター",
    page_icon="🎯",
    layout="wide",
)

init_db()


def _load_settings() -> dict:
    s = dict(DEFAULT_SETTINGS)
    s.update(get_all_settings() or {})
    return s


SETTINGS = _load_settings()


# ---------- サイドバー: ページ切替 ----------

st.sidebar.title("🎯 AI案件ハンター")
st.sidebar.caption(
    "Claude Code / Codexで対応できる案件だけを見極め、"
    "応募から実行準備まで支援するローカル案件管理ツール"
)

PAGE = st.sidebar.radio(
    "ページ",
    [
        "ダッシュボード",
        "案件登録",
        "案件一覧",
        "案件詳細",
        "応募支援",
        "実行プロンプト",
        "設定",
    ],
    key="page",
)


# ============================================================
# ダッシュボード
# ============================================================

def page_dashboard():
    st.title("📊 ダッシュボード")
    st.caption("登録された案件の状況を一目で把握する画面です。")

    jobs = list_jobs()
    if not jobs:
        st.info("まだ案件が登録されていません。サイドバーの「案件登録」から登録してください。")
        return

    # 各種件数
    total = len(jobs)
    rank_counts = {r: 0 for r in RANKS}
    status_counts: dict[str, int] = {}
    platform_counts: dict[str, int] = {}
    platform_sa_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    warning_total = 0
    budgets: list[int] = []
    won = 0
    delivered = 0
    declined = 0
    applied = 0

    for j in jobs:
        rank_counts[j.rank] = rank_counts.get(j.rank, 0) + 1
        status_counts[j.status] = status_counts.get(j.status, 0) + 1
        platform_counts[j.platform] = platform_counts.get(j.platform, 0) + 1
        if j.rank in {"S", "A"}:
            platform_sa_counts[j.platform] = platform_sa_counts.get(j.platform, 0) + 1
        category_counts[j.category] = category_counts.get(j.category, 0) + 1
        warning_total += len([w for w in (j.warnings or "").split("\n") if w.strip()])
        b = parse_budget(j.budget)
        if b:
            budgets.append(b)
        if j.status in {"応募済み", "返信あり", "条件確認中", "受注", "作業中", "納品済み", "検収済み"}:
            applied += 1
        if j.status in {"受注", "作業中", "納品済み", "検収済み"}:
            won += 1
        if j.status in {"納品済み", "検収済み"}:
            delivered += 1
        if j.status in {"失注", "見送り"}:
            declined += 1

    # KPI
    c = st.columns(5)
    c[0].metric("登録案件数", total)
    c[1].metric("応募済み", applied)
    c[2].metric("受注", won)
    c[3].metric("納品済み", delivered)
    c[4].metric("見送り/失注", declined)

    c2 = st.columns(5)
    for i, r in enumerate(RANKS):
        c2[i].metric(f"{r}判定", rank_counts.get(r, 0))

    st.divider()

    # 月30万円目標
    st.subheader("💰 月30万円目標との差分")
    avg_budget = int(sum(budgets) / len(budgets)) if budgets else 0
    won_sum = 0
    for j in jobs:
        if j.status in {"受注", "作業中", "納品済み", "検収済み"}:
            b = parse_budget(j.budget)
            if b:
                won_sum += b
    goal = int(SETTINGS.get("monthly_goal", 300000))
    diff = goal - won_sum
    needed = "—"
    if avg_budget > 0:
        needed = max(0, -(-diff // avg_budget))  # 切り上げ
    cc = st.columns(4)
    cc[0].metric("目標", f"{goal:,} 円")
    cc[1].metric("受注合計(想定)", f"{won_sum:,} 円")
    cc[2].metric("残差額", f"{max(diff,0):,} 円")
    cc[3].metric("平均予算", f"{avg_budget:,} 円")
    st.caption(
        f"平均受注単価 {avg_budget:,} 円なら、月30万円達成にあと **{needed}** 件必要(目安)。"
    )

    st.divider()

    # プラットフォーム別 / カテゴリ別
    pc1, pc2 = st.columns(2)
    with pc1:
        st.subheader("プラットフォーム別")
        if platform_counts:
            df_p = pd.DataFrame({
                "件数": platform_counts,
                "S/A案件": [platform_sa_counts.get(k, 0) for k in platform_counts.keys()],
            })
            st.bar_chart(df_p)
        else:
            st.caption("データなし")
    with pc2:
        st.subheader("カテゴリ別")
        if category_counts:
            df_c = pd.DataFrame({"件数": category_counts})
            st.bar_chart(df_c)
        else:
            st.caption("データなし")

    st.subheader("ステータス別")
    if status_counts:
        st.bar_chart(pd.DataFrame({"件数": status_counts}))

    st.divider()

    # 今日確認すべき案件
    st.subheader("🚀 今日確認すべき案件 (S/A・未応募・地雷警告少)")
    today_list = []
    for j in jobs:
        if j.rank not in {"S", "A"}:
            continue
        if j.status != "未応募":
            continue
        warn_count = len([w for w in (j.warnings or "").split("\n") if w.strip()])
        if warn_count > 2:
            continue
        b = parse_budget(j.budget)
        if b is not None and b < int(SETTINGS.get("min_budget", 5000)):
            continue
        # 納期が極端に短い案件を除外
        if re.search(r"本日|即日", j.deadline + j.description):
            continue
        today_list.append(j)

    if not today_list:
        st.caption("今日アクションすべきS/A案件はありません。")
    else:
        for j in today_list[:10]:
            with st.container(border=True):
                cols = st.columns([6, 2, 2, 2])
                with cols[0]:
                    st.markdown(
                        f"**#{j.id}** {j.title}  &nbsp;{rank_badge(j.rank)}",
                        unsafe_allow_html=True,
                    )
                    st.caption(f"{j.platform} / {j.category} / 予算: {j.budget or '-'} / 納期: {j.deadline or '-'}")
                    if j.positive_reasons:
                        st.success(j.positive_reasons.split("\n")[0])
                cols[1].metric("総合", j.score_total)
                with cols[2]:
                    st.write("次のアクション:")
                with cols[3]:
                    st.write("・応募文プロンプトをコピー\n・条件を確認\n・見送り判断")


# ============================================================
# 案件登録
# ============================================================

def _build_job_from_form(form_data: dict, job_id: Optional[int] = None) -> Job:
    job = Job(
        id=job_id,
        platform=form_data["platform"],
        title=form_data["title"].strip(),
        url=form_data["url"].strip(),
        description=form_data["description"],
        budget=form_data["budget"].strip(),
        category=form_data["category"],
        deadline=form_data["deadline"].strip(),
        client_memo=form_data["client_memo"],
        memo=form_data["memo"],
        status=form_data.get("status", "未応募"),
    )
    apply_scoring(job, settings=SETTINGS)
    apply_prompts(job, settings=SETTINGS)
    return job


def page_register():
    st.title("📝 案件登録")
    st.caption(
        "クラウドワークス・ランサーズなどで見つけた案件本文を貼り付けて登録します。"
        " 登録時にスコアリングと各種プロンプトが自動生成されます。"
    )

    with st.form("register_form", clear_on_submit=False):
        col1, col2 = st.columns(2)
        with col1:
            platform = st.selectbox("プラットフォーム *", PLATFORMS, index=0)
            title = st.text_input("案件名 *")
            url = st.text_input("案件URL")
            category = st.selectbox("カテゴリ *", CATEGORIES, index=0)
            budget = st.text_input("予算 (例: 30,000円〜50,000円)")
            deadline = st.text_input("納期 (例: 2週間以内 / 2026-06-30 等)")
        with col2:
            description = st.text_area(
                "案件本文 *",
                height=260,
                placeholder="案件ページの本文をコピペしてください。ここを元にスコア・プロンプトが作られます。",
            )
            client_memo = st.text_area("クライアント情報メモ", height=80)
            memo = st.text_area("自由メモ", height=80)

        submit = st.form_submit_button("登録する", type="primary")

    if submit:
        if not title.strip() or not description.strip():
            st.error("案件名と案件本文は必須です。")
            return
        job = _build_job_from_form({
            "platform": platform,
            "title": title,
            "url": url,
            "description": description,
            "budget": budget,
            "category": category,
            "deadline": deadline,
            "client_memo": client_memo,
            "memo": memo,
        })
        new_id = insert_job(job)
        st.success(f"案件 #{new_id} 「{job.title}」を登録しました。総合判定: {job.rank} / {job.score_total}点")
        st.balloons()

        # 直後にサマリ表示
        job.id = new_id
        st.divider()
        job_summary_card(job)
        with st.expander("地雷警告 / 優先理由"):
            st.write("**地雷警告**")
            st.code(job.warnings or "(なし)")
            st.write("**優先理由**")
            st.code(job.positive_reasons or "(なし)")


# ============================================================
# 案件一覧
# ============================================================

def page_list():
    st.title("📋 案件一覧")
    jobs = list_jobs()
    if not jobs:
        st.info("案件が登録されていません。「案件登録」から登録してください。")
        return

    # 絞り込み
    with st.expander("絞り込み / 並び替え", expanded=True):
        c = st.columns(4)
        f_platform = c[0].multiselect("プラットフォーム", PLATFORMS, default=[])
        f_category = c[1].multiselect("カテゴリ", CATEGORIES, default=[])
        f_status = c[2].multiselect("ステータス", STATUSES, default=[])
        f_rank = c[3].multiselect("総合判定", RANKS, default=[])

        c2 = st.columns(4)
        keyword = c2[0].text_input("キーワード(案件名/本文)")
        only_sa = c2[1].checkbox("S/A案件のみ")
        only_warn = c2[2].checkbox("地雷警告ありのみ")
        only_unsubmitted = c2[3].checkbox("未応募のみ")

        c3 = st.columns(2)
        sort_key = c3[0].selectbox(
            "並び替え",
            ["登録日時(新しい順)", "総合スコア(高い順)", "予算(高い順)",
             "地雷警告数(多い順)", "判定ランク(良い順)"],
            index=0,
        )

    def _passes_filter(j: Job) -> bool:
        if f_platform and j.platform not in f_platform:
            return False
        if f_category and j.category not in f_category:
            return False
        if f_status and j.status not in f_status:
            return False
        if f_rank and j.rank not in f_rank:
            return False
        if keyword:
            kw = keyword.lower()
            if kw not in (j.title or "").lower() and kw not in (j.description or "").lower():
                return False
        if only_sa and j.rank not in {"S", "A"}:
            return False
        if only_warn and not (j.warnings or "").strip():
            return False
        if only_unsubmitted and j.status != "未応募":
            return False
        return True

    filtered = [j for j in jobs if _passes_filter(j)]

    def _warn_count(j: Job) -> int:
        return len([w for w in (j.warnings or "").split("\n") if w.strip()])

    rank_order = {r: i for i, r in enumerate(RANKS)}
    if sort_key.startswith("総合スコア"):
        filtered.sort(key=lambda j: j.score_total, reverse=True)
    elif sort_key.startswith("予算"):
        filtered.sort(key=lambda j: parse_budget(j.budget) or 0, reverse=True)
    elif sort_key.startswith("地雷警告数"):
        filtered.sort(key=_warn_count, reverse=True)
    elif sort_key.startswith("判定ランク"):
        filtered.sort(key=lambda j: rank_order.get(j.rank, 99))
    else:
        filtered.sort(key=lambda j: j.id or 0, reverse=True)

    st.caption(f"該当: {len(filtered)} 件 / 全 {len(jobs)} 件")

    # 表形式
    rows = []
    for j in filtered:
        warn_n = _warn_count(j)
        rows.append({
            "ID": j.id,
            "判定": j.rank,
            "総合": j.score_total,
            "プラットフォーム": j.platform,
            "案件名": truncate(j.title, 40),
            "カテゴリ": j.category,
            "予算": j.budget,
            "納期": j.deadline,
            "ステータス": j.status,
            "地雷警告": warn_n,
            "登録日時": j.created_at,
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("詳細表示 / アクション")

    # 個別カード
    for j in filtered[:50]:
        bg = "#fef2f2" if j.rank == "D" else ("#f0fdf4" if j.rank in {"S", "A"} else "#ffffff")
        with st.container(border=True):
            st.markdown(
                f"<div style='background:{bg};padding:8px;border-radius:6px;'>",
                unsafe_allow_html=True,
            )
            job_summary_card(j)
            if j.rank == "D":
                st.error("⚠ D判定です。応募非推奨。")
            elif j.rank in {"S", "A"} and j.positive_reasons:
                st.success(j.positive_reasons.split("\n")[0])
            if (j.warnings or "").strip():
                with st.expander(f"地雷警告 {_warn_count(j)} 件を見る"):
                    st.code(j.warnings)
            cols = st.columns([1, 1, 1, 3])
            if cols[0].button("詳細", key=f"detail_{j.id}"):
                st.session_state["selected_job_id"] = j.id
                st.session_state["page"] = "案件詳細"
                st.rerun()
            if cols[1].button("応募支援", key=f"apply_{j.id}"):
                st.session_state["selected_job_id"] = j.id
                st.session_state["page"] = "応募支援"
                st.rerun()
            if cols[2].button("実行プロンプト", key=f"exec_{j.id}"):
                st.session_state["selected_job_id"] = j.id
                st.session_state["page"] = "実行プロンプト"
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)


# ============================================================
# 案件詳細
# ============================================================

def _job_selector() -> Optional[Job]:
    jobs = list_jobs()
    if not jobs:
        st.info("案件が登録されていません。")
        return None
    options = {f"#{j.id} | {j.rank} | {truncate(j.title, 40)}": j.id for j in jobs}
    default_id = st.session_state.get("selected_job_id")
    default_key = None
    if default_id is not None:
        for k, v in options.items():
            if v == default_id:
                default_key = k
                break
    keys = list(options.keys())
    idx = keys.index(default_key) if default_key in keys else 0
    selected = st.selectbox("案件を選択", keys, index=idx)
    job_id = options[selected]
    st.session_state["selected_job_id"] = job_id
    return get_job(job_id)


def page_detail():
    st.title("🔍 案件詳細")
    job = _job_selector()
    if not job:
        return

    st.markdown("---")
    job_summary_card(job)

    c1, c2 = st.columns([2, 1])
    with c1:
        st.subheader("案件本文 (原文)")
        st.text_area("description_view", value=job.description, height=240,
                     label_visibility="collapsed", disabled=True)
        st.subheader("案件URL")
        if job.url:
            st.markdown(f"[{job.url}]({job.url})")
        else:
            st.caption("(未入力)")
        st.subheader("メモ")
        st.write("**クライアント情報:** ", job.client_memo or "(なし)")
        st.write("**自由メモ:** ", job.memo or "(なし)")

    with c2:
        st.subheader("スコア内訳")
        score_bar("Claude Code / Codex適性", job.score_coding_fit)
        score_bar("AI実行しやすさ", job.score_ai_fit)
        score_bar("単価の良さ", job.score_budget)
        score_bar("納期リスクの低さ", job.score_deadline)
        score_bar("地雷リスクの低さ", job.score_safety)
        score_bar("クライアント対応の軽さ", job.score_client_lightness)
        score_bar("要件明確度", job.score_requirement_clarity)
        score_bar("修正地獄リスクの低さ", job.score_revision_risk)
        score_bar("継続案件化", job.score_continuity)
        score_bar("月30万円貢献度", job.score_monthly_goal)
        score_bar("プラットフォーム適性", job.score_platform_fit)
        score_bar("総合スコア", job.score_total)

    st.divider()

    # ステータス変更
    st.subheader("ステータス変更")
    new_status = st.selectbox(
        "ステータス",
        STATUSES,
        index=STATUSES.index(job.status) if job.status in STATUSES else 0,
        key=f"status_{job.id}",
    )
    cc = st.columns(3)
    if cc[0].button("ステータスを保存", type="primary"):
        update_job_status(job.id, new_status)
        st.success(f"ステータスを「{new_status}」に変更しました。")
        st.rerun()

    # 再スコアリング
    if cc[1].button("再スコアリング(現在の設定で計算しなおす)"):
        apply_scoring(job, settings=SETTINGS)
        apply_prompts(job, settings=SETTINGS)
        update_job(job)
        st.success("再スコアリングしました。")
        st.rerun()

    # 削除
    if cc[2].button("この案件を削除", type="secondary"):
        delete_job(job.id)
        st.session_state["selected_job_id"] = None
        st.warning("案件を削除しました。")
        st.rerun()

    st.divider()
    st.subheader("⚠ 地雷警告 / ✅ 優先理由")
    cw, cp = st.columns(2)
    with cw:
        st.write("**地雷警告**")
        if (job.warnings or "").strip():
            for w in job.warnings.split("\n"):
                if w.strip():
                    st.error(w)
        else:
            st.caption("(なし)")
    with cp:
        st.write("**優先理由**")
        if (job.positive_reasons or "").strip():
            for r in job.positive_reasons.split("\n"):
                if r.strip():
                    st.success(r)
        else:
            st.caption("(なし)")

    st.divider()
    st.subheader("💰 見積もり補助")
    st.code(job.estimate_text or "(未生成)")

    st.subheader("📌 応募前チェックリスト")
    st.code(job.pre_apply_checklist or "(未生成)")
    st.subheader("📦 納品前チェックリスト")
    st.code(job.delivery_checklist or "(未生成)")


# ============================================================
# 応募支援
# ============================================================

def page_apply_support():
    st.title("📨 応募支援")
    st.caption(
        "ブラウザ版ChatGPT / Claudeに貼って使う応募文生成プロンプトと、"
        "アプリ内で作ったテンプレ下書きを表示します。"
    )
    job = _job_selector()
    if not job:
        return

    st.markdown("---")
    job_summary_card(job)

    if job.rank == "D":
        st.error("⚠ この案件はD判定です。応募は推奨されません。")

    st.divider()
    st.subheader("① 応募前チェックリスト")
    st.code(job.pre_apply_checklist or "(未生成)")

    st.subheader("② ブラウザ版AIに貼る『応募文生成プロンプト』")
    copyable_block(
        "応募文生成プロンプト (ChatGPT / Claudeのチャットに貼って使う)",
        job.application_prompt or "",
        height=420,
        key=f"appl_prompt_{job.id}",
    )

    st.subheader("③ アプリ内テンプレ応募文下書き")
    copyable_block(
        "応募文 下書き (アプリ内テンプレ)",
        job.application_draft or "",
        height=320,
        key=f"appl_draft_{job.id}",
    )

    st.subheader("④ 見積もり補助")
    st.code(job.estimate_text or "(未生成)")

    st.info(
        "応募はこのアプリからは行いません。"
        " 上記プロンプトをコピー → ブラウザ版AIで応募文を仕上げ → 自分の手でクラウドソーシングサイトから応募してください。"
    )


# ============================================================
# 実行プロンプト
# ============================================================

def page_exec_prompt():
    st.title("⚡ 実行プロンプト")
    st.caption("受注後、Claude Code / Codexに貼って実装を開始するための長文プロンプトを表示します。")
    job = _job_selector()
    if not job:
        return

    st.markdown("---")
    job_summary_card(job)

    tab1, tab2, tab3 = st.tabs(["Claude Code 用", "Codex 用", "納品前チェック"])
    with tab1:
        copyable_block(
            "Claude Code 用実行プロンプト",
            job.claude_code_prompt or "",
            height=560,
            key=f"cc_prompt_{job.id}",
        )
    with tab2:
        copyable_block(
            "Codex 用実行プロンプト",
            job.codex_prompt or "",
            height=560,
            key=f"codex_prompt_{job.id}",
        )
    with tab3:
        st.code(job.delivery_checklist or "(未生成)")


# ============================================================
# 設定
# ============================================================

def page_settings():
    st.title("⚙ 設定")
    st.caption("スコア計算と判定の基準値を変更できます。変更後は各案件の再スコアリングで反映されます。")

    s = _load_settings()

    with st.form("settings_form"):
        c = st.columns(2)
        with c[0]:
            min_budget = st.number_input(
                "最低単価 (円)", min_value=0, value=int(s.get("min_budget", 5000)), step=1000,
            )
            rank_s = st.number_input(
                "S判定しきい値", min_value=0, max_value=100,
                value=int(s.get("rank_s_threshold", 80)),
            )
            rank_a = st.number_input(
                "A判定しきい値", min_value=0, max_value=100,
                value=int(s.get("rank_a_threshold", 70)),
            )
            rank_b = st.number_input(
                "B判定しきい値", min_value=0, max_value=100,
                value=int(s.get("rank_b_threshold", 55)),
            )
            rank_c = st.number_input(
                "C判定しきい値", min_value=0, max_value=100,
                value=int(s.get("rank_c_threshold", 40)),
            )
        with c[1]:
            monthly_goal = st.number_input(
                "月間売上目標 (円)", min_value=0, value=int(s.get("monthly_goal", 300000)), step=10000,
            )
            min_hourly = st.number_input(
                "想定最低時給 (円)", min_value=0, value=int(s.get("min_hourly_rate", 2000)), step=500,
            )

        submitted = st.form_submit_button("保存", type="primary")
    if submitted:
        set_setting("min_budget", int(min_budget))
        set_setting("rank_s_threshold", int(rank_s))
        set_setting("rank_a_threshold", int(rank_a))
        set_setting("rank_b_threshold", int(rank_b))
        set_setting("rank_c_threshold", int(rank_c))
        set_setting("monthly_goal", int(monthly_goal))
        set_setting("min_hourly_rate", int(min_hourly))
        st.success("設定を保存しました。各案件は「案件詳細 → 再スコアリング」で反映されます。")

    st.divider()
    if st.button("すべての案件を新しい設定で一括再スコアリング"):
        jobs = list_jobs()
        new_settings = _load_settings()
        for j in jobs:
            apply_scoring(j, settings=new_settings)
            apply_prompts(j, settings=new_settings)
            update_job(j)
        st.success(f"{len(jobs)} 件を再スコアリングしました。")


# ============================================================
# ルーター
# ============================================================

if PAGE == "ダッシュボード":
    page_dashboard()
elif PAGE == "案件登録":
    page_register()
elif PAGE == "案件一覧":
    page_list()
elif PAGE == "案件詳細":
    page_detail()
elif PAGE == "応募支援":
    page_apply_support()
elif PAGE == "実行プロンプト":
    page_exec_prompt()
elif PAGE == "設定":
    page_settings()


# ---------- フッター: 重要メッセージ ----------

st.sidebar.divider()
st.sidebar.caption(
    "⚠ このアプリは自動応募・自動契約・自動納品を行いません。"
    " 最終判断と実行は必ず人間が行ってください。"
)
