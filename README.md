# ParkinSync

パーキンソン病介護記録のデジタル化パイプライン。介護者が紙のログに記録し、写真を撮ってアップロードするだけで、OCR・気象データ付加・スプレッドシート集約までを全自動で行います。

## アーキテクチャ

```
紙の介護ログ（design/ の Word テンプレート）
      │  画像/PDF を S3 にアップロード
      ▼
AWS Lambda (src/lambda_function.py)
      │  1. Amazon Textract で表構造 OCR
      │  2. Visual Crossing API で当日の気象データを付加
      ▼
Google Sheets に自動追記（JST タイムスタンプ付き 13 列）
```

記録項目: 服薬（朝・昼・夕・就寝前）、排便/モビコール、転倒回数、緊急コール、体調スコア（1–5, OFF/ON）、自由記述メモ。

## セットアップ（ローカル開発）

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## テスト

```bash
source set_test_env.sh          # ダミー AWS 認証情報を設定してテスト実行
# または
PYTHONPATH=src AWS_DEFAULT_REGION=us-east-1 AWS_ACCESS_KEY_ID=testing \
  AWS_SECRET_ACCESS_KEY=testing .venv/bin/python -m unittest discover -s tests -v
```

CI: GitHub Actions（`.github/workflows/ci.yml`）が push / PR ごとにユニットテストと SAM テンプレート検証を実行します。

## デプロイ

インフラは AWS SAM（`template.yaml`）で管理します。

```bash
# 初回
sam build && sam deploy --guided

# 2 回目以降
./deploy.sh sam

# 既存 Lambda のコードだけ更新する場合
./deploy.sh zip
```

## 設定（環境変数）

| 変数 | デフォルト | 説明 |
|---|---|---|
| `SPREADSHEET_ID` | （本番シート ID） | 書き込み先 Google Spreadsheet |
| `SECRET_ID` | `ParkinSync/Production/GoogleCredentials` | Google 認証情報と Visual Crossing キーを格納した Secrets Manager シークレット |
| `WEATHER_LAT` / `WEATHER_LON` | `35.38` / `134.67`（兵庫） | 気象データ取得座標 |
| `LOG_YEAR` | 実行時の JST 年 | 年なし日付（例: "April 20"）に補完する年 |

シークレットの JSON にはGoogle サービスアカウントのキー一式と `VISUAL_CROSSING_KEY` を含めてください。

## ディレクトリ構成

```
src/         Lambda 本体 + ランタイム依存定義
tests/       ユニットテスト
design/      紙ログの Word テンプレート生成スクリプト
docs/        戦略ドキュメント・タスクリスト
template.yaml  AWS SAM テンプレート（IaC）
deploy.sh    デプロイスクリプト
```

## 関連ドキュメント

- [開発・マーケティング戦略](docs/DEVELOPMENT_STRATEGY.md)
- [タスクリスト](docs/TASKS.md)
