# -*- coding: utf-8 -*-
"""応募文・Claude Code・Codex用プロンプト生成

このファイルは「ブラウザ版AIに貼るための長文プロンプトを案件ごとに作る係」です。
API課金は使いません。ユーザーがコピペでブラウザ版AIに渡して使う前提です。
"""

from __future__ import annotations

from .models import Job
from .utils import parse_budget, safe_text


# ---------- カテゴリ別の実装方針テンプレ ----------

CATEGORY_DEV_NOTES: dict[str, str] = {
    "LP制作": (
        "- ファーストビューに訴求コピーとCTAを明確に配置する\n"
        "- セクション構成: ヘッダー / FV / 課題提起 / 解決策 / 特長 / 事例 / 料金 / FAQ / お問い合わせ\n"
        "- レスポンシブ対応 (モバイル優先)\n"
        "- HTML / CSS / JavaScript, 必要に応じてReact/Next.js\n"
        "- 画像は著作権リスクのないダミーまたはAI生成プレースホルダ\n"
        "- SEO基本タグ・OGPを設定\n"
        "- フォームはダミー、または指定があれば実装\n"
        "- READMEに編集方法を明記"
    ),
    "HP制作": (
        "- トップ / 会社概要 / サービス / お知らせ / 問い合わせ などの構成\n"
        "- レスポンシブ対応\n"
        "- 修正しやすいテンプレ構成 (HTMLパーツ化)\n"
        "- ダミー画像・ダミーテキスト\n"
        "- 著作権リスクを避ける"
    ),
    "Webサイト制作": (
        "- ページ構成・遷移をまず定義\n"
        "- 共通ヘッダー/フッターをコンポーネント化\n"
        "- レスポンシブ\n"
        "- ダミーコンテンツで雛形を作り、確認後に差し替え"
    ),
    "WordPress修正": (
        "- 本番環境を直接触らない (まずローカル/ステージング)\n"
        "- バックアップ取得前提\n"
        "- 子テーマ または カスタムCSS優先\n"
        "- 変更箇所と差分を明示\n"
        "- 本番反映手順をREADMEに記載"
    ),
    "GAS": (
        "- シート構成・入力項目・出力項目を確定\n"
        "- メニュー追加・トリガー設定方法を記載\n"
        "- エラーハンドリング・ログ出力\n"
        "- 権限スコープ最小化\n"
        "- 利用者向けの使い方ドキュメント"
    ),
    "スプレッドシート自動化": (
        "- 元シート/結果シートを分離\n"
        "- 関数 / GAS のどちらで実装するか明示\n"
        "- 列が増えても壊れにくい設計\n"
        "- READMEに運用フローを記載"
    ),
    "Excel / VBA": (
        "- ファイル構成・シート構成を確定\n"
        "- マクロは標準モジュール/シートモジュールを使い分け\n"
        "- 保存形式 (.xlsm) と互換性を明記"
    ),
    "Pythonツール": (
        "- 要件→入出力定義→関数分割の順で設計\n"
        "- requirements.txt を用意\n"
        "- CLI または簡易UIを選ぶ\n"
        "- 例外処理とログ"
    ),
    "スクレイピング": (
        "- 対象URL/取得項目/保存形式 (CSV / SQLite) を明示\n"
        "- robots.txt と利用規約を必ず確認\n"
        "- アクセス頻度はsleep等で制限\n"
        "- 自動ログインは行わない\n"
        "- 個人情報や機密情報は取得しない\n"
        "- 例外処理と再試行\n"
        "- READMEに注意点と免責"
    ),
    "データ整理 / CSV整形": (
        "- 入力CSV→中間処理→出力CSVの構造を明示\n"
        "- 文字コード (UTF-8 / SJIS) を確認\n"
        "- pandas で実装\n"
        "- 件数とサンプルをREADMEに"
    ),
    "Streamlitアプリ": (
        "- app.py / requirements.txt / data/ で構成\n"
        "- SQLite or CSVで永続化\n"
        "- 入力フォーム / 一覧 / ダッシュボード\n"
        "- 起動: streamlit run app.py\n"
        "- READMEに起動方法と使い方"
    ),
    "React / Next.js": (
        "- ページ構成・コンポーネント設計を先に定義\n"
        "- Tailwind CSSの使用可否を確認\n"
        "- レスポンシブ\n"
        "- 環境変数 .env.local\n"
        "- 起動: npm run dev / build / start"
    ),
    "LINE / Slack通知": (
        "- Webhook URLは環境変数 (.env)\n"
        "- 秘密情報をコードに直書きしない\n"
        "- 通知条件とテスト通知\n"
        "- 例外処理\n"
        "- READMEに設定手順を明記"
    ),
    "記事作成 / 構成作成": (
        "- 構成案 / 見出し / 読者像 / 検索意図 / 差別化\n"
        "- AIっぽさを減らす言い回し\n"
        "- 事実確認が必要な箇所を明示\n"
        "- コピペ納品でなく、確認前提"
    ),
}


def _category_dev_notes(category: str) -> str:
    return CATEGORY_DEV_NOTES.get(category, (
        "- 要件を分解し、入出力・成功条件を明確化\n"
        "- 必要に応じてMVPを先に作り、段階的に拡張\n"
        "- READMEに使い方を明記"
    ))


# ---------- 共通: 案件サマリ ----------

def _common_header(job: Job) -> str:
    return (
        f"【プラットフォーム】{safe_text(job.platform) or '未指定'}\n"
        f"【案件名】{safe_text(job.title) or '未指定'}\n"
        f"【案件URL】{safe_text(job.url) or '未指定'}\n"
        f"【予算】{safe_text(job.budget) or '未指定'}\n"
        f"【納期】{safe_text(job.deadline) or '未指定'}\n"
        f"【カテゴリ】{safe_text(job.category) or '未指定'}\n"
        f"【ステータス】{safe_text(job.status) or '未指定'}\n"
    )


def _description_block(job: Job) -> str:
    desc = safe_text(job.description).strip() or "(案件本文の貼り付けがありません)"
    return f"【案件本文(原文)】\n{desc}\n"


def _score_block(job: Job) -> str:
    return (
        "【スコア結果】\n"
        f"- 総合: {job.score_total} ({job.rank})\n"
        f"- Claude Code/Codex適性: {job.score_coding_fit}\n"
        f"- AI実行しやすさ: {job.score_ai_fit}\n"
        f"- 単価の良さ: {job.score_budget}\n"
        f"- 納期リスクの低さ: {job.score_deadline}\n"
        f"- 地雷リスクの低さ: {job.score_safety}\n"
        f"- クライアント対応の軽さ: {job.score_client_lightness}\n"
        f"- 要件明確度: {job.score_requirement_clarity}\n"
        f"- 修正地獄リスクの低さ: {job.score_revision_risk}\n"
        f"- 継続案件化: {job.score_continuity}\n"
        f"- 月30万円貢献度: {job.score_monthly_goal}\n"
        f"- プラットフォーム適性: {job.score_platform_fit}\n"
        f"【地雷警告】\n{safe_text(job.warnings) or '(なし)'}\n"
        f"【優先理由】\n{safe_text(job.positive_reasons) or '(なし)'}\n"
    )


# ---------- 応募文生成プロンプト(ブラウザ版AI貼り付け用) ----------

def build_application_prompt(job: Job) -> str:
    header = _common_header(job)
    return (
        "あなたはクラウドソーシングで月30万円を稼ぐベテランフリーランスです。\n"
        "以下のクラウドソーシング案件に対する応募準備を一気に行ってください。\n"
        "応募文はテンプレ感を減らし、案件本文を読んだ上で書いてください。\n"
        "AI禁止案件には応募してはいけません。AIを使う場合も「補助的に活用し、最終確認は私が行う」程度の自然な表現に留めてください。\n"
        "値段だけで勝負せず、納品物・進め方・修正範囲を明確にしてください。\n\n"
        f"{header}\n"
        f"{_description_block(job)}\n"
        f"{_score_block(job)}\n"
        "【出力してほしいもの(必ず全部)】\n"
        "1. 応募文(挨拶/案件理解/対応可能内容/進め方/確認事項/締め)\n"
        "2. 応募前に確認すべき質問(箇条書きで5〜10個)\n"
        "3. 推奨見積もり金額と算出根拠\n"
        "4. 最低受注ライン(これ以下では受けない金額)\n"
        "5. 想定作業時間(時間単位)\n"
        "6. 納品までの流れ(ステップで)\n"
        "7. 修正対応範囲の書き方(回数・範囲・追加料金条件)\n"
        "8. 地雷を避けるための注意点(この案件特有のもの)\n\n"
        "【方針】\n"
        "- テンプレ感を減らす\n"
        "- 案件内容をちゃんと読んでいる感じを出す\n"
        "- 初心者っぽく見せない / 偉そうにしない\n"
        "- 価格だけで勝負しない\n"
        "- 不明点は質問する\n"
        "- AI禁止の場合は応募中止を提案する\n"
    )


# ---------- 応募文テンプレ下書き(アプリ内で生成) ----------

def build_application_draft(job: Job) -> str:
    platform = safe_text(job.platform) or "貴サイト"
    title = safe_text(job.title) or "本案件"
    cat = safe_text(job.category) or "ご依頼"
    deadline = safe_text(job.deadline) or "ご希望納期"
    return (
        f"はじめまして、ご提案ありがとうございます。\n"
        f"{platform}にて公開されている「{title}」の募集を拝見し、\n"
        f"{cat}領域の実装経験から、本件を確実に進められると考え応募いたします。\n\n"
        "【案件内容の理解】\n"
        "案件本文を拝読し、ご依頼の目的・成果物・必要な品質水準を把握しました。\n"
        "不明点については下部に質問としてまとめております。\n\n"
        "【対応可能な内容】\n"
        f"- {cat}の設計・実装・動作確認\n"
        "- 仕様の整理と進捗共有(チャットベース)\n"
        "- 納品前のチェックリストに基づく品質確認\n\n"
        "【進め方】\n"
        "1. ヒアリング・要件確認 (1-2往復)\n"
        "2. 仮実装・初稿提出\n"
        "3. フィードバックを反映\n"
        f"4. 最終納品 (目安: {deadline})\n\n"
        "【確認事項】\n"
        "- 想定している最終的な成果物の形式\n"
        "- 必要素材(画像・テキスト・アカウント等)のご提供有無\n"
        "- 修正対応の範囲・回数の目安\n"
        "- 連絡手段と確認頻度\n\n"
        "【最後に】\n"
        "必要に応じてAIツールも補助的に活用し、最終的な品質確認は私が行います。\n"
        "ご検討のほどよろしくお願いいたします。\n"
    )


# ---------- 応募前 / 納品前 チェックリスト ----------

def build_pre_apply_checklist(job: Job) -> str:
    items = [
        "AI利用禁止ではないか",
        "納期は現実的か",
        "修正回数は明記されているか",
        "納品形式は明確か",
        "必要素材はクライアント提供か",
        "サーバー/ドメイン/アカウント情報が必要か",
        "外部連絡 (LINE/電話/対面) が前提になっていないか",
        "単価と作業量が釣り合っているか",
        "自分の実績として公開可能か",
        "不明点を質問してから応募すべきか",
    ]
    return "\n".join(f"- [ ] {it}" for it in items)


def build_delivery_checklist(job: Job) -> str:
    items = [
        "要件を満たしているか",
        "ファイルが不足していないか",
        "起動方法がREADMEに書かれているか",
        "動作確認済みか",
        "不要なAPIキーや秘密情報が混入していないか",
        "ダミーデータと本番データが区別されているか",
        "著作権リスクのある画像や文章を使っていないか",
        "クライアントに確認すべき不明点が残っていないか",
        "納品形式が案件内容と合っているか",
    ]
    # カテゴリ別の追加
    extra: list[str] = []
    if job.category in {"LP制作", "HP制作", "Webサイト制作", "React / Next.js"}:
        extra += [
            "スマホ表示でレイアウト崩れがないか",
            "リンク切れ・画像切れがないか",
            "OGP/SEO基本タグが入っているか",
        ]
    if job.category in {"スクレイピング"}:
        extra += [
            "robots.txt / 利用規約に違反していないか",
            "アクセス頻度に配慮しているか (sleep等)",
            "個人情報を保存していないか",
        ]
    if job.category in {"LINE / Slack通知", "GAS", "Pythonツール"}:
        extra += [
            "シークレット情報が .env 経由か",
            "エラー時の挙動が定義されているか",
        ]
    return "\n".join(f"- [ ] {it}" for it in items + extra)


# ---------- 見積もり補助 ----------

def build_estimate_text(job: Job, min_hourly_rate: int = 2000) -> str:
    amount = parse_budget(job.budget)
    if amount is None:
        budget_line = "予算情報なし (要確認)"
        recommend = "5万円〜(作業量に応じて要相談)"
        min_line = f"想定時給 {min_hourly_rate:,} 円 を割らないこと"
    else:
        recommend = f"{int(amount):,} 円 (案件記載の上限を採用)"
        min_line = f"{max(int(amount * 0.7), min_hourly_rate * 3):,} 円"
        budget_line = f"案件予算: {amount:,} 円"

    # 想定作業時間の目安
    category_hours = {
        "LP制作": "12〜24時間",
        "HP制作": "20〜40時間",
        "WordPress修正": "2〜8時間",
        "GAS": "4〜12時間",
        "スプレッドシート自動化": "3〜10時間",
        "Excel / VBA": "4〜12時間",
        "Pythonツール": "6〜20時間",
        "スクレイピング": "6〜20時間",
        "データ整理 / CSV整形": "2〜8時間",
        "Streamlitアプリ": "10〜30時間",
        "React / Next.js": "20〜60時間",
        "LINE / Slack通知": "3〜8時間",
        "記事作成 / 構成作成": "2〜6時間",
        "バナー / 画像加工": "1〜4時間",
    }
    hours = category_hours.get(job.category, "要見積")

    warn = ""
    if amount is not None and amount > 0:
        # 簡易時給換算 (中央目安)
        rough_hourly = amount // 10  # 10時間想定の暫定値
        if rough_hourly < min_hourly_rate:
            warn = (
                f"⚠ 想定時給が {min_hourly_rate:,} 円を下回る可能性があります。"
                f"値上げ提案または見送り判断を推奨します。\n"
            )

    return (
        f"{budget_line}\n"
        f"推奨見積もり: {recommend}\n"
        f"最低受注ライン: {min_line}\n"
        f"想定作業時間: {hours}\n"
        f"時給換算の目安: 想定最低時給 {min_hourly_rate:,} 円を下回らないこと\n"
        f"{warn}"
        "確認すべき項目:\n"
        "- 修正回数・範囲\n"
        "- 必要素材の提供有無\n"
        "- 納品形式・連絡頻度"
    )


# ---------- Claude Code 用実行プロンプト ----------

def build_claude_code_prompt(job: Job) -> str:
    header = _common_header(job)
    dev_notes = _category_dev_notes(job.category)
    return (
        "# あなたはプロの開発者です\n\n"
        "クラウドソーシングで受注した以下の案件を、Claude Codeで実装してください。\n"
        "いきなり実装に走らず、まず要件整理と仮定一覧を提示し、私の合図(「そのまま進めて」等)があれば\n"
        "合理的な仮定を置いてMVPまで一気に実装してください。\n\n"
        "## 1. 案件情報\n"
        f"{header}\n"
        f"{_description_block(job)}\n"
        "## 2. 作業目的 / 想定成果物\n"
        f"- 目的: 案件本文に書かれたゴールを満たす成果物を納品可能な状態に仕上げる\n"
        f"- カテゴリ: {safe_text(job.category) or '未指定'}\n"
        "- 想定成果物: コード一式 + README + 動作確認手順\n\n"
        "## 3. 案件要約\n"
        "案件本文を200字程度で要約し、ゴール・成果物・主要要件を箇条書きで再構成してください。\n\n"
        "## 4. 技術スタック (案)\n"
        f"{dev_notes}\n\n"
        "## 5. 機能要件 / 非機能要件\n"
        "- 機能要件: 案件本文から抽出して列挙\n"
        "- 非機能要件: パフォーマンス・セキュリティ・保守性・拡張性\n\n"
        "## 6. 制約条件\n"
        "- 本番環境への自動デプロイは行わない\n"
        "- 機密情報をコードに直書きしない (環境変数を使用)\n"
        "- 著作権リスクのある画像・文章を使わない\n"
        "- 法令・利用規約に違反する実装をしない\n\n"
        "## 7. 不明点 / 仮定一覧\n"
        "案件本文を読んで不明点を列挙し、それぞれに「現時点の仮定」をセットで提示してください。\n"
        "- 仮定してよい点: 動作環境・サンプルデータ・ダミー画像の使用 等\n"
        "- 仮定してはいけない点: 法務/医療/投資関連の専門判断、依頼者の本人情報、本番アカウント情報\n\n"
        "## 8. 実装方針 / ディレクトリ構成\n"
        "実装方針を箇条書きで提示し、ディレクトリ構成案をツリー形式で示してください。\n\n"
        "## 9. 実装タスク\n"
        "上記方針をタスクに分解し、順番に実装してください。\n"
        "各タスク完了時に動作確認方法を提示してください。\n\n"
        "## 10. 動作確認方法\n"
        "実行コマンドと、画面/出力での確認手順を記載してください。\n\n"
        "## 11. README作成\n"
        "概要 / インストール / 起動方法 / 使い方 / 注意点 をREADME.mdに作成してください。\n\n"
        "## 12. 納品前チェックリスト\n"
        f"{build_delivery_checklist(job)}\n\n"
        "## 13. 最終報告フォーマット\n"
        "- 作成/修正したファイル一覧\n"
        "- 実装した機能と未実装機能\n"
        "- 起動方法 / 動作確認結果\n"
        "- 残課題 / 想定リスク\n"
        "- 次のアクション提案\n"
    )


# ---------- Codex 用実行プロンプト ----------

def build_codex_prompt(job: Job) -> str:
    header = _common_header(job)
    dev_notes = _category_dev_notes(job.category)
    return (
        "# ゴール\n\n"
        "以下のクラウドソーシング案件を実装し、納品可能な状態に仕上げる。\n\n"
        "## 案件情報\n"
        f"{header}\n"
        f"{_description_block(job)}\n"
        "## 作業目的 / 想定成果物\n"
        f"- カテゴリ: {safe_text(job.category) or '未指定'}\n"
        "- 想定成果物: コード一式 + README + 動作確認手順\n\n"
        "## 技術スタック / 実装方針\n"
        f"{dev_notes}\n\n"
        "## 機能要件 / 非機能要件\n"
        "- 機能要件: 案件本文から抽出し列挙\n"
        "- 非機能要件: セキュリティ・保守性・パフォーマンス\n\n"
        "## 制約条件\n"
        "- 機密情報の直書き禁止 (環境変数を使用)\n"
        "- 自動ログイン / 自動応募 / 自動契約 は禁止\n"
        "- 著作権リスクのある素材を使わない\n\n"
        "## 不明点 / 仮定\n"
        "- 不明点を列挙し、仮定を明示する\n"
        "- 仮定してよい点: ダミーデータ・サンプル画像\n"
        "- 仮定してはいけない点: 法務/医療判断、本番アカウント情報\n\n"
        "## 作成 / 修正するファイル\n"
        "- 想定ディレクトリ構成をツリーで提示\n"
        "- 各ファイルの責務を1行で説明\n\n"
        "## 実装タスク一覧\n"
        "1. プロジェクト雛形作成\n"
        "2. 主要機能の実装\n"
        "3. 動作確認・修正\n"
        "4. README作成\n\n"
        "## 受け入れ条件\n"
        "- 起動コマンドが動く\n"
        "- 主要機能が要件を満たす\n"
        "- READMEがある\n"
        "- 不要なシークレット情報を含まない\n\n"
        "## テスト / 動作確認コマンド\n"
        "- 環境構築コマンドと起動コマンドを記載\n"
        "- 想定する入力/出力例を示す\n\n"
        "## 注意点\n"
        "- 本番環境への自動デプロイは行わない\n"
        "- robots.txt や利用規約を尊重 (スクレイピング系)\n"
        "- 修正範囲を超えるファイルを勝手に書き換えない\n\n"
        "## 最終報告フォーマット\n"
        "- 作成/修正ファイル一覧\n"
        "- 動作確認結果\n"
        "- 残課題 / 想定リスク\n"
        "- 次のアクション提案\n"
    )


# ---------- 全部まとめてJobへ反映 ----------

def apply_prompts(job: Job, settings: dict | None = None) -> Job:
    settings = settings or {}
    min_hourly_rate = int(settings.get("min_hourly_rate", 2000))
    job.application_prompt = build_application_prompt(job)
    job.application_draft = build_application_draft(job)
    job.claude_code_prompt = build_claude_code_prompt(job)
    job.codex_prompt = build_codex_prompt(job)
    job.pre_apply_checklist = build_pre_apply_checklist(job)
    job.delivery_checklist = build_delivery_checklist(job)
    job.estimate_text = build_estimate_text(job, min_hourly_rate=min_hourly_rate)
    return job
