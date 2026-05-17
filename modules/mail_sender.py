"""
Gmail SMTP でレポートメールを送信。
- 宛先は環境変数 GMAIL_TO (絶対的にここだけ)
- アプリパスワード経由(本体パスワードは使わない)
- HTML 折りたたみ(<details>)で1件ずつ詳細を見せる
"""
from __future__ import annotations
import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from html import escape

log = logging.getLogger(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465

GMAIL_FROM = os.environ.get("GMAIL_FROM", "")
GMAIL_TO = os.environ.get("GMAIL_TO", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "")

# Notion 案件ページの直リンク(取込便を見るためのDBビュー)
NOTION_DB_URL = (
    f"https://www.notion.so/{os.environ.get('NOTION_DATABASE_ID', '').replace('-', '')}"
)


def _normalize_items(jobs_input: list) -> list[tuple[dict, dict, dict]]:
    """`(job, scoring)` も `(job, scoring, prompts)` も受け付け、3要素タプルに揃える。"""
    out = []
    for item in jobs_input:
        if len(item) == 3:
            out.append((item[0], item[1], item[2] or {}))
        else:
            out.append((item[0], item[1], {}))
    return out


def _build_html(jobs_input: list, batch_label: str) -> str:
    jobs_with_prompts = _normalize_items(jobs_input)
    today = datetime.now().strftime("%Y/%m/%d %H:%M")
    n_s = sum(1 for _, s, _ in jobs_with_prompts if s["rank"] == "S")
    n_a = sum(1 for _, s, _ in jobs_with_prompts if s["rank"] == "A")

    header = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, sans-serif; color: #222; line-height: 1.6;">
      <h2 style="border-bottom: 2px solid #2563eb; padding-bottom: 8px;">
        【{batch_label}】案件スカウト {today}
      </h2>
      <p>新着 <b>{len(jobs_with_prompts)}件</b>(S {n_s} / A {n_a})が Notion に登録されました。</p>
      <p><a href="{NOTION_DB_URL}" style="background:#2563eb;color:#fff;padding:8px 16px;border-radius:6px;text-decoration:none;display:inline-block;">▶ Notion で全件を見る</a></p>
      <hr>
    """

    sorted_jobs = sorted(
        jobs_with_prompts, key=lambda x: x[1]["score"], reverse=True
    )

    items_html = []
    for job, scoring, prompts in sorted_jobs:
        title = escape(job.get("title", ""))
        rank = scoring["rank"]
        score = scoring["score"]
        source = escape(job.get("source", ""))
        budget = job.get("budget_max")
        budget_text = f"¥{budget:,}" if budget else "報酬非公開"
        url = escape(job.get("url", ""))
        reason = escape(scoring.get("completion_reason", ""))
        completable = escape(scoring.get("claude_completable", ""))
        landmines = scoring.get("landmine_tags", [])
        landmines_html = "".join(
            f'<span style="background:#fef3c7;border:1px solid #facc15;color:#854d0e;padding:2px 8px;border-radius:12px;margin-right:4px;font-size:12px;">{escape(t)}</span>'
            for t in landmines
        )
        rank_color = {"S": "#dc2626", "A": "#ea580c"}.get(rank, "#6b7280")

        # プロンプトブロック生成
        prompt_blocks_html = ""
        for label, key, icon, hint in [
            ("応募文(完成版・コピペでそのまま送信可)", "application_draft", "📝",
             "応募欄にそのまま貼り付け"),
            ("応募文プロンプト(無料Claude/ChatGPTに貼ってオーダーメイド版を生成)", "application_prompt", "🤖",
             "個人の無料Claude.aiまたはChatGPTに貼る(借り物Claude不可)"),
            ("Claude Code実行プロンプト(採用後の作業指示文)", "claude_code_prompt", "⚙️",
             "受注後、Claude Codeに貼って実装"),
        ]:
            content = prompts.get(key, "")
            if not content:
                continue
            prompt_blocks_html += f"""
            <details style="margin-top:8px;border:1px solid #f3f4f6;border-radius:6px;padding:8px;background:#fafafa;">
              <summary style="cursor:pointer;font-weight:600;color:#374151;">{icon} {escape(label)}</summary>
              <p style="color:#6b7280;font-size:12px;margin:6px 0;">{escape(hint)}</p>
              <div style="background:#fff;border:1px solid #e5e7eb;border-radius:4px;padding:10px;font-family:ui-monospace,Menlo,monospace;font-size:12px;white-space:pre-wrap;word-break:break-word;max-height:400px;overflow:auto;">{escape(content)}</div>
            </details>
            """

        items_html.append(
            f"""
        <details style="border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px; margin-bottom: 8px;">
          <summary style="cursor: pointer; font-weight: 600; list-style: none;">
            <span style="background:{rank_color};color:#fff;padding:2px 10px;border-radius:4px;font-size:13px;margin-right:8px;">{rank}/{score}</span>
            <span style="color:#9ca3af;font-size:13px;margin-right:8px;">{source}</span>
            <span style="color:#16a34a;font-size:13px;margin-right:8px;">{budget_text}</span>
            {title}
          </summary>
          <div style="margin-top: 12px; padding-left: 8px; border-left: 3px solid #e5e7eb;">
            <p><b>Claude完結度:</b> {completable}</p>
            <p><b>判定理由:</b> {reason}</p>
            {f'<p><b>地雷タグ:</b> {landmines_html}</p>' if landmines else ''}
            <p><a href="{url}" style="color:#2563eb;" target="_blank">▶ 案件ページを開く</a></p>
            {prompt_blocks_html}
          </div>
        </details>
        """
        )

    footer = """
      <hr>
      <p style="color:#9ca3af; font-size: 12px;">
        ⚠️ 応募前に必ず詳細ページで「対面打合せ」「専門資格」等のNG条件がないか確認してください。<br>
        🤖 案件スカウター(自動取込ジョブ)
      </p>
    </div>
    """
    return header + "".join(items_html) + footer


def _build_text(jobs_input: list, batch_label: str) -> str:
    """HTMLメール非対応クライアント用のプレーンテキスト版。"""
    jobs_with_prompts = _normalize_items(jobs_input)
    today = datetime.now().strftime("%Y/%m/%d %H:%M")
    lines = [f"【{batch_label}】案件スカウト {today}", ""]
    lines.append(f"新着 {len(jobs_with_prompts)}件")
    lines.append(f"Notion: {NOTION_DB_URL}")
    lines.append("")
    sorted_jobs = sorted(
        jobs_with_prompts, key=lambda x: x[1]["score"], reverse=True
    )
    for job, scoring, _ in sorted_jobs:
        budget = job.get("budget_max")
        budget_text = f"¥{budget:,}" if budget else "非公開"
        lines.append(
            f"[{scoring['rank']}/{scoring['score']}] {job['source']} {budget_text}"
        )
        lines.append(f"  {job['title']}")
        lines.append(f"  {job['url']}")
        lines.append(f"  完結度: {scoring['claude_completable']}")
        lines.append(f"  理由: {scoring['completion_reason'][:100]}")
        lines.append("")
    return "\n".join(lines)


def send_summary_email(
    jobs_with_scoring: list, batch_label: str
) -> bool:
    """便ごとのサマリーメールを送信。"""
    # 宛先ハードコード(.env 上書き防止)
    to_addr = GMAIL_TO or "koretada.i@gmail.com"
    if to_addr != "koretada.i@gmail.com":
        log.error("GMAIL_TO must be koretada.i@gmail.com, got: %s", to_addr)
        return False

    if not GMAIL_FROM or not GMAIL_APP_PASSWORD:
        log.error("GMAIL_FROM / GMAIL_APP_PASSWORD not set")
        return False

    if not jobs_with_scoring:
        log.info("No jobs to email")
        return True

    items = _normalize_items(jobs_with_scoring)
    n_s = sum(1 for _, s, _ in items if s["rank"] == "S")
    n_a = sum(1 for _, s, _ in items if s["rank"] == "A")
    subject = f"【{batch_label}】案件スカウト {len(items)}件 (S{n_s}/A{n_a})"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_FROM
    msg["To"] = to_addr

    msg.attach(MIMEText(_build_text(jobs_with_scoring, batch_label), "plain", "utf-8"))
    msg.attach(MIMEText(_build_html(jobs_with_scoring, batch_label), "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.login(GMAIL_FROM, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_FROM, [to_addr], msg.as_string())
        log.info("Email sent to %s: %s", to_addr, subject)
        return True
    except Exception as exc:
        log.exception("Email send failed: %s", exc)
        return False
