# PoC: GutPacer → ParkinSync 連携（BEN-001）

**合成データで「GutPacerの排便/モビコール → care-event-v1 → ParkinSync日次(Bowel/Movi)」のE2Eを証明する最小PoC。**
設計は `../../poc-gutpacer-parkinsync-ben001.md`。外部依存なし（python3 標準のみ）。

## 実行
```
python3 test_roundtrip.py
```
全green で exit 0。

## 構成
| ファイル | 役割 |
|---|---|
| `data/gutpacer_synthetic.json` | 合成入力（3日: 排便2+モビ1 / 排便0(confirmed_none)+モビ2 / 排便1+モビ欠測） |
| `schema/care-event-v1.schema.json` | 共通契約（正本のコピー） |
| `gutpacer_export.py` | GutPacerログ → care-event-v1（producer） |
| `validate.py` | care-event-v1 最小スキーマ検証（依存ゼロ） |
| `parkinsync_import.py` | care-event → ParkinSync日次 Bowel/Movi（consumer） |
| `test_roundtrip.py` | E2E往復 + 検証（S1〜S4） |

## 成功基準の対応
| 基準 | 内容 | 本PoC |
|---|---|---|
| S1 | E2Eが1本通る | ✅ export→import |
| S2 | スキーマ検証（＋no-opでない） | ✅ validate_all + 負テスト |
| S3 | 件数・値・欠測保持 | ✅ 期待値assert（confirmed_none=0 / not_recorded=None を区別） |
| S4 | 手作業ゼロ・1コマンド再現 | ✅ `python3 test_roundtrip.py` |
| S5 | 記録時間削減の見立て | 📝 設計メモ §4（GutPacer入力がParkinSync再入力不要に） |

## 本番化との違い（非構成）
- 合成データのみ。本番DynamoDB/個人情報は使わない。
- バッチ変換のみ。常時同期・UI統合・ML解析は対象外（PoC後）。
- validate.py は依存ゼロの最小版。本番は jsonschema 等へ置換可。

## CI統合（済）
ParkinSync `.github/workflows/ci.yml` に `care-event-integration-poc` ジョブとして統合済み。
push/PR ごとに `python3 poc/gutpacer-parkinsync/test_roundtrip.py` を実行し、連携契約の破壊を fail-closed に検知する（S2/S4）。合成データのみ。
