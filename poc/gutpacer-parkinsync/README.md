# PoC: GutPacer / Medication Promise → ParkinSync 連携（BEN-001）

**合成データで「GutPacerの排便/モビコール ＋ Medication Promiseの服薬 → care-event-v1 → ParkinSync日次(Bowel/Movi/Med)」のE2Eを証明する最小PoC。**
設計は `../../poc-gutpacer-parkinsync-ben001.md`。外部依存なし（python3 標準のみ）。

## 実行
```
python3 test_roundtrip.py             # GutPacer 経路
python3 test_medication_roundtrip.py  # Medication Promise 経路 + 2 source 統合
```
全green で exit 0。

## 構成
| ファイル | 役割 |
|---|---|
| `data/gutpacer_synthetic.json` | 合成入力（3日: 排便2+モビ1 / 排便0(confirmed_none)+モビ2 / 排便1+モビ欠測） |
| `schema/care-event-v1.schema.json` | 共通契約（正本のコピー） |
| `check_schema_drift.py` | GutPacer repoの正本と意味的に一致することを検査 |
| `test_schema_drift.py` | 整形差を許容し、契約値の変更を検出するguardの負テスト |
| `gutpacer_export.py` | GutPacerログ → care-event-v1（producer） |
| `validate.py` | care-event-v1 最小スキーマ検証（依存ゼロ） |
| `parkinsync_import.py` | care-event → ParkinSync日次 Bowel/Movi/Med（consumer・source非依存） |
| `data/medication_promise_synthetic_export.json` | 合成入力（MP の `medication-promise-export/v1` 封筒。3回/1回/記録なし の3日） |
| `test_roundtrip.py` | GutPacer 経路の E2E往復 + 検証（S1〜S4） |
| `test_medication_roundtrip.py` | MP 経路の検証 + **2 source を混ぜた日次行**（S1〜S4） |

## 成功基準の対応
| 基準 | 内容 | 本PoC |
|---|---|---|
| S1 | E2Eが1本通る | ✅ export→import |
| S2 | スキーマ検証（＋no-opでない） | ✅ validate_all + 負テスト |
| S3 | 件数・値・欠測保持 | ✅ 期待値assert（confirmed_none=0 / not_recorded=None を区別） |
| S4 | 手作業ゼロ・1コマンド再現 | ✅ `python3 test_roundtrip.py` |
| S5 | 記録時間削減の見立て | 📝 設計メモ §4（GutPacer入力がParkinSync再入力不要に） |

## 服薬（Med）の数え方

**その日の観測された `medication_taken` の件数。**（2026-08-31 オーナー決定）

⚠️ **記録が無い日を 0 にしない。**

Bowel には `confirmed_none`（確認された無し）があるので「実測の0」と「欠測」を
区別できる。**服薬にはそれが無い。** Medication Promise の export は `eventType` が
`medication_taken` の const、`missingness` も `observed` の const で、
**「飲まなかった」を出す口がそもそも無い**（推測された未服薬は意図的に除外）。

だから記録が無い日は「飲まなかった日」ではなく **「分からない日」** で、空欄にする。
0 になるのは、別の source が観測された `medication_missed` または
`medication_taken` の `confirmed_none` を明示したときだけ。
**記録の不在を、事実として読ませない。**

## 本番化との違い（非構成）
- 合成データのみ。本番DynamoDB/個人情報は使わない。
- バッチ変換のみ。常時同期・UI統合・ML解析は対象外（PoC後）。
- validate.py は依存ゼロの最小版。本番は jsonschema 等へ置換可。

## モビコール包数（Movi）の欠測

`Movi` は観測された `movicol_taken` の `payload.doseSachets` の日次合計。
全観測の包数が数値で分かる場合だけ合計し、1件でも不明・null・不正値があれば
日次合計を `None`（空欄）にする。分かっている分だけを日次総量として出さない。
数値の小数部分は保持し、文字列・真偽値・負数・非有限値を包数へ変換しない。

GutPacerのruntime exportは服用枠を記録するが `doseSachets` を持たない。
枠数を包数として補わず、包数不明を0にしない。このPoCの合成producerが
包数を持つことは、runtime exportが同じ項目を持つ証拠ではない。
この変換は本番Masterへの取込みや記録の重複排除を実装するものではない。

回帰検査（repo rootから）:
`python3 -m unittest discover -s tests -p test_poc_movicol_missingness.py -v`

## CI統合（済）
ParkinSync `.github/workflows/ci.yml` に `care-event-integration-poc` ジョブとして統合済み。
push/PR ごとにGutPacer repoのcanonical schemaをcheckoutし、JSONの整形、object key順、
`required` / `enum`の配列順を除いて本コピーと一致することを先に検査する。その後
`python3 poc/gutpacer-parkinsync/test_roundtrip.py` を実行し、連携契約の破壊を
fail-closedに検知する（S2/S4）。合成データのみ。
