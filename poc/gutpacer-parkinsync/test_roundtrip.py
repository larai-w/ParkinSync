"""BEN-001 連携PoC E2E往復テスト（合成データ）
GutPacer log → care-event-v1 export → schema validate → ParkinSync import → 検証。
成功基準 S1〜S4 を assert する。外部依存なし（python3 標準のみ）。

実行: python3 test_roundtrip.py   （全green で exit 0 / 失敗で exit 1）
"""
from __future__ import annotations
import json, os, sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)
from gutpacer_export import export_care_events
from parkinsync_import import import_to_daily
from validate import validate_all


def load_log():
    return json.load(open(os.path.join(HERE, "data", "gutpacer_synthetic.json")))


def main() -> int:
    log = load_log()

    # S1: E2E（export → import）が通る
    events = export_care_events(log)
    assert events, "S1: イベントが生成されない"

    # S2: 全イベントが care-event-v1 スキーマ検証を通過
    n = validate_all(events)
    print(f"  S2 schema validate: {n} events OK")

    # S2補足: バリデータが no-op でないこと（不正イベントを確実に弾く）
    from validate import validate_event, ValidationError
    bad = dict(events[0]); bad["eventType"] = "not_a_real_type"
    try:
        validate_event(bad); raise AssertionError("S2: 不正eventTypeが検証を通ってしまった")
    except ValidationError:
        pass
    bad2 = dict(events[0]); del bad2["provenance"]
    try:
        validate_event(bad2); raise AssertionError("S2: provenance欠落が検証を通ってしまった")
    except ValidationError:
        pass
    print("  S2 negative test: 不正イベントを正しく拒否 OK")

    rows = import_to_daily(events)

    # 期待値（合成データ設計に対応）
    expected = {
        "2026-08-01": {"Bowel": 2, "Movi": 1},   # 排便2 + モビ1
        "2026-08-02": {"Bowel": 0, "Movi": 2},   # 排便0(confirmed_none) + モビ2
        "2026-08-03": {"Bowel": 1, "Movi": None} # 排便1 + モビ欠測(空欄)
    }

    # S3: 取込の正確性（件数・値・欠測保持）
    for date, exp in expected.items():
        assert date in rows, f"S3: {date} が取り込まれていない"
        got = rows[date]
        assert got["Bowel"] == exp["Bowel"], f"S3: {date} Bowel 期待{exp['Bowel']} != {got['Bowel']}"
        assert got["Movi"] == exp["Movi"], f"S3: {date} Movi 期待{exp['Movi']} != {got['Movi']}"
    print(f"  S3 roundtrip values: {len(expected)} days OK")

    # S3補足: 欠測が0埋めされていないこと
    assert rows["2026-08-03"]["Movi"] is None, "S3: 欠測が0埋めされている（NGパターン）"
    assert rows["2026-08-02"]["Bowel"] == 0, "S3: confirmed_none が欠測扱いになっている（NGパターン）"
    print("  S3 missingness preserved: OK（confirmed_none=0 / not_recorded=None を区別）")

    # S4: 手作業ゼロ（このスクリプト1本でE2E再現）
    print(f"  S4 one-command E2E: OK（events={len(events)}, days={len(rows)}）")

    print("\n✅ PoC GREEN — S1〜S4 全通過")
    print("   ParkinSync 日次行:")
    for d in sorted(rows):
        print(f"     {rows[d]}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as e:
        print(f"\n❌ PoC FAILED: {e}")
        sys.exit(1)
