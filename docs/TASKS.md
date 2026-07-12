# ParkinSync タスクリスト

最終更新: 2026-07-12
ロードマップ全体は [DEVELOPMENT_STRATEGY.md](DEVELOPMENT_STRATEGY.md) を参照。

---

## 人間がやること（手動タスク）

### すぐ（今週中）

| # | タスク | 所要時間 | 手順 |
|---|---|---|---|
| H-1 | **GitHub リポジトリ作成 & push** | **約5分** | ターミナルで `gh repo create ParkinSync --private --source=. --push`。push すると GitHub Actions が自動で回り始める（テスト + SAM 検証）。 |
| H-2 | **Python 3.12 をローカルにインストール** | **約10分** | `brew install python@3.12` → `.venv` を 3.12 で再作成：`python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt`。本番 Lambda のランタイムと合わせるため。 |
| H-3 | **実際の手書きログ画像を5〜10枚用意する** | **約30分** | 実際に使っている紙ログを写真撮影 → `tests/fixtures/` に保存。OCR 精度の実測に使う（タスク8の前提）。ファイル名に日付を入れると良い例：`2026-04_log_day1.jpg` |

### 1〜2週間以内

| # | タスク | 所要時間 | 手順 |
|---|---|---|---|
| H-4 | **AWS Secrets Manager にシークレットを登録** | **約30分** | AWS コンソールで `ParkinSync/Production/GoogleCredentials` という名前のシークレットを作成。JSON に Google サービスアカウントキー一式と `"VISUAL_CROSSING_KEY": "your-key"` を含める。サービスアカウントには対象スプレッドシートの編集権限を付与しておく。 |
| H-5 | **初回 SAM デプロイ** | **約30分** | `brew install aws-sam-cli` → `sam build && sam deploy --guided`（初回のみ `--guided`。以降は `./deploy.sh sam`）。デプロイ後、テスト画像を S3 にアップロードして動作確認。 |
| H-6 | **SNS トピックを作成して通知先を登録** | **約15分** | AWS コンソールで SNS トピック（スタンダード型）を作成 → 自分のメールアドレスをサブスクライブ → トピック ARN を SAM パラメータ `SnsTopicArn` に設定して再デプロイ。OCR 失敗時にメール通知が届くようになる。 |

### 1ヶ月以内（Phase 0 完了条件）

| # | タスク | 所要時間 | 手順 |
|---|---|---|---|
| H-7 | **実ログ 30 枚以上でOCR精度を検証** | **2〜3時間（断続的）** | 実際の手書き画像を S3 にアップロード → Sheets に入った結果と原本を目視で突き合わせ → 読み取れなかったセルを記録。自動確定率 90% が目標。結果を `tests/fixtures/` に保存するとタスク8（回帰テスト化）に活用できる。 |
| H-8 | **Word テンプレートの日付列フォーマットを確認** | **約15分** | `design/log_template_2026_04.docx` を開いて Date 列（A列）の実際の記入フォーマットを確認。「20th」のような日付のみ形式か、「April 20」のように月を書くか。月なし形式なら、ファイル名に `2026-04_` プレフィックスを付ける運用ルールを決める（コードはそれを自動で読む）。 |

---

## 自動化済み（Claudeが実施）

### 2026-07-08 実施

| # | タスク | 内容 |
|---|---|---|
| 1 | 日付パースの汎用化 | April/May 固定 → 全12ヶ月・日本語・数値・ISO 対応。`LOG_YEAR` 環境変数で年を上書き可能 |
| 2 | 設定の環境変数化 | `SPREADSHEET_ID` / `SECRET_ID` / `WEATHER_LAT` / `WEATHER_LON` を env から読み込み |
| 3 | IaC 化とデプロイ整備 | `requirements.txt` / `deploy.sh` を実装、AWS SAM `template.yaml` を新規作成 |
| 4 | CI/CD 構築 | git 初期化・`.gitignore` 作成・GitHub Actions ワークフロー（テスト + `sam validate`）|
| 5 | ドキュメント整備 | `README.md`・本ファイル（`docs/TASKS.md`）を作成 |

### 2026-07-12 実施

| # | タスク | 内容 |
|---|---|---|
| 6 | OCR 失敗時のリカバリ | テーブル未検出・例外時に `review/` プレフィックスへ S3 コピー + SNS 通知（`SNS_TOPIC_ARN` 設定時）|
| 7 | Sheets 書き込みの冪等性 | 処理済み画像に S3 オブジェクトタグ `ParkinSync-Status=processed` を付与。再トリガー時はスキップ |
| 9 | 日付列の月補完対応 | `20th` のような日付のみ形式を、ファイル名または `LOG_MONTH` 環境変数から月を補完して変換 |
| - | SAM template 更新 | 新環境変数・S3 タグ権限・SNS 権限を追加 |
| - | テスト拡充 | 計 26 件（全件パス）。新規追加: 冪等性・隔離通知・日付補完・月推定 |

---

## 次のタスク（Phase 0 残り）

| # | タスク | 担当 | 優先度 |
|---|---|---|---|
| 8 | 実サンプルでの OCR 精度測定・回帰テスト化 | 人間（H-7）+ Claude | **最高** — 最大リスクの検証 |
| 10 | Python ランタイム統一（3.12） | 人間（H-2） | 高 |
| 11 | `review/` フォルダの内容を確認・修正するワークフロー整備 | Claude | 中 |
