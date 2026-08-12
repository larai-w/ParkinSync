"""BEN-001 撤回→削除→検証テスト（合成データ）

同意撤回で当該仮名IDが消え、**再exportして不在をassertするところまで**成立するかを確かめる。
BEN-001 §7 の「削除の検証」が実装として動くことの証拠。実データには一切触れない。

実行: python3 test_withdraw.py   （全green で exit 0 / 失敗で exit 1）
外部依存なし（python3 標準のみ）。
"""
from __future__ import annotations
import copy, json, os, sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)
import withdraw as w

SUBJECT = "synthetic-patient-001"
FAILURES: list[str] = []


def load_log() -> dict:
    return json.load(open(os.path.join(HERE, "data", "gutpacer_synthetic.json"), encoding="utf-8"))


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  PASS  {name}")
    else:
        FAILURES.append(name)
        print(f"  FAIL  {name} {detail}")


def expect_refused(name: str, log: dict, allow_nonsynthetic: bool) -> None:
    try:
        w.check_gate(log, allow_nonsynthetic)
    except w.DeletionRefused:
        check(name, True)
        return
    check(name, False, "(拒否されるべきところが通ってしまった)")


def main() -> int:
    print("BEN-001 撤回→削除→検証（合成データ）")

    # S1: 既定は fail-closed。ゲートを開けない限り削除しない。
    os.environ.pop(w.GATE_ENV, None)
    expect_refused("S1 ゲートが閉じていれば削除しない", load_log(), False)

    # S2: 合成データでなければ、ゲートが開いていても拒否する。
    os.environ[w.GATE_ENV] = "1"
    real = copy.deepcopy(load_log())
    real.update(patientId="prod-patient-001", careTeamId="prod-household-001", source="gutpacer")
    expect_refused("S2 合成データでなければ拒否する", real, False)

    # S3: 消す前に影響範囲が分かる。
    scope = w.affected(load_log(), SUBJECT)
    check(
        "S3 影響範囲を消す前に数えられる",
        scope["matched"] and scope["days"] > 0 and scope["events"] > 0,
        f"(scope={scope})",
    )

    # S4: 撤回すると、再exportに1件も出ない（＝削除の検証が通る）。
    cleaned = w.withdraw(load_log(), SUBJECT)
    try:
        w.verify_absent(cleaned, SUBJECT)
        check("S4 撤回後は再exportに残らない", True)
    except AssertionError as e:
        check("S4 撤回後は再exportに残らない", False, f"({e})")

    # S5: 検証工程そのものが機能しているか（消していないのに通らないこと）。
    try:
        w.verify_absent(load_log(), SUBJECT)
        check("S5 削除漏れを検証が見逃さない", False, "(未削除なのに通ってしまった)")
    except AssertionError:
        check("S5 削除漏れを検証が見逃さない", True)

    # S6: 別人のデータを巻き込まない。
    untouched = w.withdraw(load_log(), "synthetic-patient-999")
    check("S6 別の仮名IDは巻き込まない", untouched["days"] == load_log()["days"])

    os.environ.pop(w.GATE_ENV, None)
    print()
    if FAILURES:
        print(f"NG: {len(FAILURES)} 件失敗 → {FAILURES}")
        return 1
    print("OK: 撤回→削除→検証がすべて成立")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
