# ParkinSync タスクリスト

最終更新: 2026-07-08
ロードマップ全体は [DEVELOPMENT_STRATEGY.md](DEVELOPMENT_STRATEGY.md) を参照。

## 完了（2026-07-08 実施分）

| # | タスク | 内容 | 状態 |
|---|---|---|---|
| 1 | 日付パースの汎用化 | April/May 固定 → 全12ヶ月（英語フル/省略形 + 序数）、日本語（4月20日）、数値（4/20）、ISO（2026-04-20）対応。`parse_log_date()` として分離、年は `LOG_YEAR` 環境変数で設定可（デフォルト: JST 現在年）。パース不能時は API を呼ばず "Weather N/A" | ✅ 完了 |
| 2 | 設定の環境変数化 | `SPREADSHEET_ID` / `SECRET_ID` / `WEATHER_LAT` / `WEATHER_LON` を環境変数から読み込み（従来値をデフォルトに維持し後方互換） | ✅ 完了 |
| 3 | IaC 化とデプロイ整備 | 空だった `requirements.txt`・`deploy.sh` を実装。AWS SAM `template.yaml` 新規作成（Lambda + S3 トリガー + 最小権限 IAM + バケット暗号化/公開ブロック）。`deploy.sh` は `sam` / `zip` の2モード | ✅ 完了 |
| 4 | CI/CD 構築 | git リポジトリ初期化、`.gitignore` 作成、GitHub Actions（`.github/workflows/ci.yml`: push/PR ごとにユニットテスト + `sam validate`）| ✅ 完了（リモート push は手動、下記参照） |
| 5 | ドキュメント整備 | 空だった `README.md` にアーキテクチャ・セットアップ・テスト・デプロイ手順を記載。本ファイル（TASKS.md）作成 | ✅ 完了 |

補足: テストは 10 件全件パス（日付パース 8 件を新規追加）。壊れていた `.venv`（別マシン由来）は Python 3.9 で再作成済み。

## CI/CD を完全稼働させるための残り手順（手動）

1. GitHub にリポジトリを作成: `gh repo create ParkinSync --private --source=. --push`
2. push すると Actions が自動実行される（テスト + SAM 検証)
3. （任意）デプロイ自動化: AWS の OIDC ロールを設定し、main への merge で `sam deploy` するジョブを追加

## 次のタスク（Phase 0 残り — 優先順）

| # | タスク | 備考 |
|---|---|---|
| 6 | OCR 失敗時のリカバリ | 失敗画像を「要手動確認」プレフィックスに退避し SNS/LINE Notify で通知 |
| 7 | Sheets 書き込みの冪等性 | 同一画像の再処理で二重登録しない（画像ハッシュ + 日付キー） |
| 8 | 実サンプルでの OCR 精度測定 | 手書きログ 100 枚を目標にフィクスチャ収集 → 回帰テスト化。**最重要リスクの検証** |
| 9 | 日付列の実フォーマット対応 | 現行 Word テンプレの Date 列は「20th」形式（月なし）。ファイル名 or `LOG_MONTH` からの月補完が必要 |
| 10 | Python ランタイム統一 | 本番 Lambda は python3.12。ローカルは 3.9 しかないため、開発機への 3.12 導入を推奨 |
