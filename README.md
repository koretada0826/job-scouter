# 🎯 Job Scouter — AI案件ハンター

クラウドソーシング案件を1日3回 **自動取得**し、**LLM完結可能な案件のみ** をフィルタして **Notion + Gmail** に届ける、副業フリーランス向けの自動化システム。

![Status](https://img.shields.io/badge/status-運用中-brightgreen)
![Stack](https://img.shields.io/badge/stack-Python%20%7C%20Playwright%20%7C%20Notion%20API%20%7C%20Gmail%20SMTP-blue)
![Schedule](https://img.shields.io/badge/cron-7:00%20%2F%2012:00%20%2F%2019:00-orange)

---

## 🌟 何を解決するか

副業で月50万円稼ぐには **1日20〜30件** の応募が必要。しかし:

- 3サイト(クラウドワークス/ランサーズ/ココナラ)を毎日チェックするのは時間泥棒
- 案件タイトルだけでは **対面打合せ・専門資格・低単価** の地雷が見えない
- 応募文を1件ずつ書くと **1日が終わる**

このツールは **取得・判定・通知・応募文生成** までを完全自動化し、**朝メールを見るだけ** で済む状態を作る。

---

## ⚙️ システム構成

```
[macOS launchd] (朝7:00 / 昼12:00 / 夜19:00)
        ↓
[Python バッチ司令塔]
        ├── [ランサーズ Fetcher]  requests + BeautifulSoup
        ├── [ココナラ Fetcher]    requests + BeautifulSoup (Nuxt.js SSR)
        └── [クラウドワークス Fetcher] Playwright + Chromium (Vue.js SPA)
        ↓
[一次スコアリング] キーワードマッチ12項目 + Claude完結度判定
        ├── 低単価 / 物理作業 / 専門資格 / 学生歓迎(タグ記録)
        └── S/A/B+/B/C/D ランク + 地雷タグ multi_select
        ↓
[詳細ページ取得] S/A候補のみ・30秒間隔の行儀の良いクロール
        ↓
[再スコアリング] 詳細本文込みで再判定 → B+以下は除外
        ↓
[プロンプト生成]
        ├── 応募文(完成版) — そのままコピペ送信可
        ├── 応募文プロンプト — claude.ai/ChatGPTに貼ってオーダーメイド版生成
        └── Claude Code実行プロンプト — 採用後の実装指示文
        ↓
[Notion API] 16列のDBに自動INSERT (data_sources エンドポイント / 2025-09版API対応)
        ↓
[Gmail SMTP] HTML折りたたみメールで koretada.i@gmail.com に通知
```

---

## 🚀 主要機能

### 1. 規約遵守スクレイピング設計

| 項目 | 仕様 |
|---|---|
| 一覧取得 | 1リクエスト60秒間隔 |
| 詳細取得 | 1リクエスト30秒間隔 |
| User-Agent | `KoretaScraper/1.0 (contact: koretada.i@gmail.com)` (連絡先明示) |
| 取得対象 | **ログイン不要の公開ページのみ** |
| 自動ログイン | **しない**(規約・セキュリティ両面で禁止) |
| robots.txt | 厳守 |

### 2. Claude完結度判定

タイトル+説明本文をキーワードマッチし、以下に分類:

- **確実完結**:Python/API/スクレイピング/CRUD等の明示的キーワード3個以上
- **可能**:OKワード1〜2個・NGワードなし
- **微妙**:NGワード1個 + OKワード少量
- **不可**:NGワード2個以上(動画編集・対面打合せ・専門資格等)

**Notion登録は「確実完結」「可能」のみ。それ以外は1次・2次フィルタで除外。**

### 3. 自動ブロック対象(配信されない)

- 物理作業必須(配送・撮影・対面打合せ)
- 専門資格必須(行政書士・宅建・医療資格)
- ID/PW共有/アカウント引き渡し
- MLM・ネットワークビジネス・情報商材
- 報酬1000円未満 / 時給換算で明らかに割に合わない案件

### 4. プロンプト3種類を自動生成

各案件ごとに以下が**メール本文内** と **Notion DB** に保存:

1. **応募文(完成版)** — 即送信可能なテンプレ応募文
2. **応募文プロンプト** — claude.ai/ChatGPTに貼って案件特化型の応募文を生成
3. **Claude Code実行プロンプト** — 受注後にClaude Codeへ貼って実装開始

### 5. Gmail HTML 折りたたみメール

```
件名:【朝便】案件スカウト 19件 (S6/A13)
本文:
  ▼ S/95 ランサーズ ¥100,000 WordPress×OpenAI API連携  [タップ▼]
     ▶ Claude完結度・判定理由・地雷タグ
     ▶ 案件URL
     ▶ 📝 応募文(コピペ可)
     ▶ 🤖 応募文プロンプト(コピペ可)
     ▶ ⚙️ Claude Code実行プロンプト(コピペ可)
```

---

## 🛠 技術スタック

| レイヤー | 技術 |
|---|---|
| 言語 | Python 3.12 |
| スクレイピング(SSR) | `requests` + `BeautifulSoup` |
| スクレイピング(SPA) | `Playwright` + headless Chromium |
| 判定ロジック | 自前のキーワードマッチエンジン(外部API不使用) |
| DB | Notion API (2025-09 `data_sources` エンドポイント) |
| 通知 | Gmail SMTP + アプリパスワード |
| スケジューラ | macOS `launchd`(plist 配置) |
| 設定管理 | `python-dotenv` + `.gitignore` で `.env` 完全除外 |

**有料LLM API不使用**:OpenAI / Anthropic API は呼んでいません(コスト¥0で運用)。

---

## 🔐 セキュリティ設計

| 項目 | 対策 |
|---|---|
| Notion token / Gmail パスワード | `.env` に格納、Git追跡対象外 |
| `.gitignore` | `.env`, `.env.local`, `logs/`, `data/database.sqlite`, `__pycache__` 全除外 |
| メール宛先 | コード側でハードコード(誤送信防止) |
| クラウドソーシング ログイン情報 | **コードに一切持たない**(公開ページのみアクセス) |
| 取得した案件本文 | GitHubコミット禁止(著作権リスク回避) |
| スクリプト暴走防止 | リクエスト間隔ハードコード・リトライ最大3回・タイムアウト30秒 |

---

## 📦 セットアップ

### 1. 依存インストール

```bash
git clone https://github.com/koretada0826/job-scouter.git
cd job-scouter
pip install -r requirements.txt
playwright install chromium
```

### 2. `.env` を作成

```bash
cp .env.example .env  # サンプル化予定
# 以下を埋める
# NOTION_TOKEN=ntn_xxxx
# NOTION_DATABASE_ID=xxxx
# NOTION_DATA_SOURCE_ID=xxxx
# NOTION_PARENT_PAGE_ID=xxxx
# GMAIL_FROM=xxx@gmail.com
# GMAIL_APP_PASSWORD=xxxx
# GMAIL_TO=xxx@gmail.com
```

### 3. Notion 親ページに Integration を招待

1. Notion で「案件スカウト」ページを作成
2. 右上「...」→「Connections」→ 作成した Integration を追加
3. ページURLから page_id を取得 → `.env` の `NOTION_PARENT_PAGE_ID` に設定

### 4. Notion DB 自動生成

```bash
python scripts/setup_notion_db.py
```

### 5. テスト実行

```bash
python scripts/batch_pickup.py 朝便 --test
```

### 6. launchd 登録

```bash
cp launchd/com.koretada.scout-batch.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.koretada.scout-batch.plist
```

これで毎日 7:00 / 12:00 / 19:00 に自動稼働。

---

## 📁 ディレクトリ構成

```
job-scouter/
├── scripts/
│   ├── batch_pickup.py          # 司令塔: 取得→判定→詳細→生成→保存→送信
│   └── setup_notion_db.py       # 初回のNotion DB自動構築
├── modules/
│   ├── constants.py             # フィルタキーワード辞書
│   ├── job_scorer.py            # スコアリング + Claude完結度判定
│   ├── auto_prompt_gen.py       # 応募文・実行プロンプト生成
│   ├── notion_writer.py         # Notion API I/O(2025-09エンドポイント対応)
│   ├── mail_sender.py           # Gmail HTML折りたたみメール
│   ├── prompt_generator.py      # プロンプトテンプレ(旧Streamlit版から流用)
│   ├── models.py                # Job dataclass
│   └── fetchers/
│       ├── lancers_fetcher.py   # ランサーズ取得(requests)
│       ├── coconala_fetcher.py  # ココナラ取得(requests)
│       ├── cw_fetcher.py        # クラウドワークス取得(Playwright)
│       └── detail_fetcher.py    # 詳細ページ取得(共通インターフェース)
└── app.py                       # 旧Streamlit版(手動登録モード用に温存)
```

---

## 📈 運用実績(2026-05-17 稼働開始)

- 1便あたり取得数:約120件/サイト × 3サイト = **約360件/便**
- フィルタ通過率:**約15〜20%**(S/A判定のみ)
- 1日Notion登録数:**30〜50件**
- メール送信:1日最大3回(新着なしの場合スキップ)
- BAN実績:**0件**(行儀の良いクロール設計が機能)

---

## 🎓 思想

1. **自動応募はしない** — クラウドソーシング規約遵守
2. **最終判断は人間** — Notionで自分の目で確認してから応募
3. **コスト¥0で運用** — 有料LLM API不使用、Gmail SMTP・Notion 無料枠で完結
4. **規約・著作権リスク回避** — 公開ページのみ・低頻度・取得本文は GitHub に上げない

---

## 📸 スクリーンショット

(ポートフォリオ用追加予定)

- Gmail受信画面(朝便メール)
- Notion DB 一覧ビュー
- Notion DB 案件詳細(プロンプト3種展開)
- 月別/カテゴリ別 ダッシュボード

---

## 📝 ライセンス

個人開発・ポートフォリオ目的。コードの再利用はご自由に。

---

## 👤 作者

**飯田 是侃 (Koretada Iida)**
- GitHub: [@koretada0826](https://github.com/koretada0826)
- 副業フリーランス・Python × LLM 活用領域
