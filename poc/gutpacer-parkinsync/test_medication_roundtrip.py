"""BEN-001 連携PoC: Medication Promise → ParkinSync 日次（合成データ）

**なぜ要るか**（2026-08-31）

GutPacer 側は producer も consumer も揃っていたが、**Medication Promise は
producer だけだった。** 本番の `GET /api/records/export` は care-event/v1 の
服薬サブセットを出しているのに、ParkinSync 側に受ける口が無く、
`parkinsync_import.py` は `bowel_movement` と `movicol_taken` しか見ていなかった。

このテストは2つを確かめる:

1. **MP の export（`medication-promise-export/v1`）が、正本の care-event/v1 で
   そのまま検証を通ること。** MP は正本を丸写しせず「服薬だけの狭い版」を
   持っているので、**狭めたつもりが外れていないか**を消費側から測る。
2. **2つの source を混ぜて1本の日次行になること。** これが BEN-001 の
   「介護記録の統合化」で言っている統合そのもの。

実行: python3 test_medication_roundtrip.py （全green で exit 0 / 失敗で exit 1）
合成データのみ。実データは同意の記録（DEC-015）が前提。
"""
from __future__ import annotations
import json, os, sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)
from gutpacer_export import export_care_events
from parkinsync_import import import_to_daily
from validate import validate_all, validate_event, ValidationError

MP_EXPORT = os.path.join(HERE, "data", "medication_promise_synthetic_export.json")
GP_LOG = os.path.join(HERE, "data", "gutpacer_synthetic.json")


def load_mp_records() -> list[dict]:
    """MP の export 封筒から records を取り出す。**封筒ごと渡さない。**"""
    doc = json.load(open(MP_EXPORT, encoding="utf-8"))
    assert doc["schemaVersion"] == "medication-promise-export/v1", "封筒の版が違う"
    assert doc["recordCount"] == len(doc["records"]), "recordCount と実件数が合わない"
    return doc["records"]


def main() -> int:
    mp_events = load_mp_records()

    # S1: MP の export が取り込める形で存在する
    assert mp_events, "S1: MP イベントが空"

    # S2: MP の狭い版が、**正本の** care-event/v1 検証を通る
    n = validate_all(mp_events)
    print(f"  S2 canonical schema validate: {n} MP events OK")

    # S2補足: 検証が no-op でないこと
    bad = dict(mp_events[0]); bad["missingness"] = "not_a_real_value"
    try:
        validate_event(bad); raise AssertionError("S2: 不正 missingness が通ってしまった")
    except ValidationError:
        pass
    print("  S2 negative test: 不正イベントを正しく拒否 OK")

    # S3: 服薬は「その日の件数」
    rows = import_to_daily(mp_events)
    assert rows["2026-08-01"]["Med"] == 3, f"S3: 8/01 Med 期待3 != {rows['2026-08-01']['Med']}"
    assert rows["2026-08-02"]["Med"] == 1, f"S3: 8/02 Med 期待1 != {rows['2026-08-02']['Med']}"
    print("  S3 medication counts: OK（3件 / 1件）")

    # S3補足: **記録が無い日を0にしない。**
    # MP は「飲まなかった」を出す口を持たない（eventType も missingness も const）。
    # 記録の不在は「飲まなかった」ではなく「分からない」。
    assert "2026-08-03" not in rows, "S3: 記録の無い日に行が生えている"

    # 別の source が明示したときだけ 0 になる
    missed = dict(mp_events[0])
    missed.update({"eventId": "x-missed-1", "eventType": "medication_missed",
                   "localDate": "2026-08-04",
                   "occurredAt": "2026-08-04T08:00:00+09:00",
                   "recordedAt": "2026-08-04T08:00:00+09:00"})
    r = import_to_daily([missed])
    assert r["2026-08-04"]["Med"] == 0, "S3: 明示された未服薬が0になっていない"
    print("  S3 missingness preserved: OK（記録なし=None / 明示された未服薬=0）")

    # S3補足2: 2つの source を混ぜて1本の日次行になる（＝BEN-001 の統合）
    merged = import_to_daily(export_care_events(json.load(open(GP_LOG, encoding="utf-8"))) + mp_events)
    expected = {
        "2026-08-01": {"Bowel": 2, "Movi": 1,    "Med": 3},
        "2026-08-02": {"Bowel": 0, "Movi": 2,    "Med": 1},
        "2026-08-03": {"Bowel": 1, "Movi": None, "Med": None},  # 服薬は欠測のまま
    }
    for date, exp in expected.items():
        got = merged[date]
        for col, want in exp.items():
            assert got[col] == want, f"S3: {date} {col} 期待{want} != {got[col]}"
    print(f"  S3 two-source merge: {len(expected)} days OK（gutpacer + medication-promise）")

    # S4: 手作業ゼロ（このスクリプト1本で再現）
    print(f"  S4 one-command: OK（MP events={len(mp_events)}, merged days={len(merged)}）")

    print("\n✅ MP 連携 GREEN — S1〜S4 全通過")
    print("   ParkinSync 日次行（2 source 統合後）:")
    for d in sorted(merged):
        print(f"     {merged[d]}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as e:
        print(f"\n❌ FAILED: {e}")
        sys.exit(1)
