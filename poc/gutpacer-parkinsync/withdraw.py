"""同意撤回 → 削除 → 検証（BEN-001 §7 / COMP-01）。

設計上の要求（`veai-private/governance/ben-001-real-data-governance-design.md` §6-7）:

  「撤回時: 当該仮名IDの全レコード＋対応表エントリを削除 → **削除の検証**
   （再exportして不在をassert）。MedPromise #47 gated deletion と同じ
   fail-closed／人間ゲート方式を踏襲。」

このモジュールはその手順を実行可能にする。削除は**取り消せない**ので、
既定は fail-closed（何もしない）。実行には明示的なゲートが要る。

  DELETION_ENABLED=1 python3 withdraw.py --subject <仮名ID> --dry-run  # 影響範囲だけ見る
  DELETION_ENABLED=1 python3 withdraw.py --subject <仮名ID>            # 実行

合成データ以外に対しては使わない（`--allow-nonsynthetic` を明示しない限り拒否する）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_LOG = os.path.join(HERE, "data", "gutpacer_synthetic.json")
# 仮名⇔氏名の対応表。実運用では非公開領域に置く。PoCでは存在しない場合もある。
DEFAULT_MAP = os.path.join(HERE, "data", "pseudonym_map.json")

GATE_ENV = "DELETION_ENABLED"


class DeletionRefused(RuntimeError):
    """ゲートが開いていない、または対象が合成データでない。"""


def _load(path: str) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _is_synthetic(log: dict) -> bool:
    """合成データかどうか。patientId/source に synthetic の印があるかで判断する。"""
    marks = f"{log.get('patientId','')} {log.get('careTeamId','')} {log.get('source','')}"
    return "synthetic" in marks.lower()


def check_gate(log: dict, allow_nonsynthetic: bool) -> None:
    """fail-closed。条件が揃わなければ何もせず落とす。"""
    if os.environ.get(GATE_ENV) != "1":
        raise DeletionRefused(
            f"削除ゲートが閉じています。実行するなら {GATE_ENV}=1 を明示してください。"
        )
    if not _is_synthetic(log) and not allow_nonsynthetic:
        raise DeletionRefused(
            "合成データではありません。実データの削除は --allow-nonsynthetic の明示と "
            "オーナーの承認が要ります（BEN-001 §5: 削除は別IAM・MFA必須）。"
        )


def affected(log: dict, subject: str) -> dict:
    """削除するとどれだけ消えるかを、消す前に数える。"""
    if log.get("patientId") != subject:
        return {"subject": subject, "matched": False, "days": 0, "events": 0}
    days = log.get("days", [])
    events = sum(len(d.get("bowelMovements", [])) + len(d.get("movicol", [])) for d in days)
    return {"subject": subject, "matched": True, "days": len(days), "events": events}


def withdraw(log: dict, subject: str) -> dict:
    """当該仮名IDのレコードを落とす。他の subject のデータには触れない。"""
    if log.get("patientId") != subject:
        return log  # 対象外はそのまま返す（誤って全消しにしない）
    cleaned = dict(log)
    cleaned["days"] = []
    cleaned["withdrawn"] = True
    return cleaned


def drop_mapping(map_path: str, subject: str) -> bool:
    """仮名⇔氏名の対応表から当該エントリを消す。無ければ False。"""
    if not os.path.exists(map_path):
        return False
    mapping = _load(map_path)
    if subject not in mapping:
        return False
    del mapping[subject]
    with open(map_path, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)
    return True


def verify_absent(log: dict, subject: str) -> None:
    """削除の検証。再exportして、当該仮名IDが1件も出ないことを確かめる。

    「消したつもり」で終わらせないための工程。ここが通って初めて撤回は完了する。
    """
    from gutpacer_export import export_care_events

    events = export_care_events(log)
    leaked = [e for e in events if e.get("patientId") == subject]
    if leaked:
        raise AssertionError(
            f"削除が不完全です: 再exportに {len(leaked)} 件残っています（subject={subject}）"
        )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="同意撤回 → 削除 → 検証")
    ap.add_argument("--subject", required=True, help="撤回する仮名ID")
    ap.add_argument("--log", default=DEFAULT_LOG)
    ap.add_argument("--map", default=DEFAULT_MAP)
    ap.add_argument("--dry-run", action="store_true", help="影響範囲だけ出して何も消さない")
    ap.add_argument("--allow-nonsynthetic", action="store_true")
    args = ap.parse_args(argv)

    log = _load(args.log)
    scope = affected(log, args.subject)
    print(f"影響範囲: {json.dumps(scope, ensure_ascii=False)}")
    if not scope["matched"]:
        print("対象の仮名IDはこのログに存在しません。何もしません。")
        return 0

    if args.dry_run:
        print("dry-run のため削除しません。")
        return 0

    try:
        check_gate(log, args.allow_nonsynthetic)
    except DeletionRefused as e:
        print(f"拒否: {e}", file=sys.stderr)
        return 2

    cleaned = withdraw(log, args.subject)
    with open(args.log, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)
    dropped = drop_mapping(args.map, args.subject)

    verify_absent(cleaned, args.subject)
    print(f"削除OK / 対応表エントリ削除: {dropped} / 再exportで不在を確認しました。")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    raise SystemExit(main())
