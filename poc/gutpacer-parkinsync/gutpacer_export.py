"""GutPacer → care-event-v1 エクスポータ（PoC / BEN-001）
GutPacer の日次排便・モビコールログを、共通契約 care-event-v1 のイベント配列に変換する。
本番実装ではなく、合成データで連携契約を証明するための最小変換。
"""
from __future__ import annotations
import hashlib

TRANSFORM_VERSION = "gutpacer-export/0.1"
EXPORT_VERSION = "poc-0.1"
TZ = "+09:00"  # JST。localDate は施設ローカル日


def _dt(date: str, time: str) -> str:
    return f"{date}T{time}:00{TZ}"


def _eid(*parts: str) -> str:
    return "gp-" + hashlib.sha1("|".join(parts).encode()).hexdigest()[:12]


def _base(day_date: str, patient: str, team: str, source: str, occurred: str) -> dict:
    return {
        "schemaVersion": "care-event/v1",
        "source": source,
        "patientId": patient,
        "careTeamId": team,
        "actorRole": "caregiver",
        "occurredAt": occurred,
        "recordedAt": occurred,
        "localDate": day_date,
        "consentScope": "care_support",
        "exportVersion": EXPORT_VERSION,
    }


def _provenance(source: str, record_id: str, recorded: str) -> dict:
    return {
        "source": source,
        "sourceRecordId": record_id,
        "recordedAt": recorded,
        "exportedAt": "2026-08-05T00:00:00+09:00",
        "transformVersion": TRANSFORM_VERSION,
    }


def export_care_events(gutpacer_log: dict) -> list[dict]:
    """GutPacer ログ → care-event-v1 イベント配列"""
    patient = gutpacer_log["patientId"]
    team = gutpacer_log["careTeamId"]
    source = gutpacer_log.get("source", "gutpacer")
    events: list[dict] = []

    for day in gutpacer_log["days"]:
        d = day["date"]
        bms = day.get("bowelMovements", [])
        movi = day.get("movicol", [])

        # 排便イベント（観測あり）
        for i, bm in enumerate(bms):
            occurred = _dt(d, bm["time"])
            rid = f"{d}#bm{i}"
            ev = _base(d, patient, team, source, occurred)
            ev.update({
                "eventId": _eid(source, rid),
                "eventType": "bowel_movement",
                "payload": {"bristol": bm.get("bristol"), "volumeMl": bm.get("volumeMl"), "time": bm["time"]},
                "missingness": "observed",
                "provenance": _provenance(source, rid, occurred),
            })
            events.append(ev)

        # 排便が0件 → 「確認された無し」(confirmed_none)。欠測(not_recorded)と区別する。
        if not bms:
            occurred = _dt(d, "23:59")
            rid = f"{d}#bm-none"
            ev = _base(d, patient, team, source, occurred)
            ev.update({
                "eventId": _eid(source, rid),
                "eventType": "bowel_movement",
                "payload": {},
                "missingness": "confirmed_none",
                "provenance": _provenance(source, rid, occurred),
            })
            events.append(ev)

        # モビコール（観測あり）。無い日は何も出さない＝ParkinSync側で欠測(空欄)扱い。
        for i, m in enumerate(movi):
            occurred = _dt(d, m["time"])
            rid = f"{d}#movi{i}"
            ev = _base(d, patient, team, source, occurred)
            ev.update({
                "eventId": _eid(source, rid),
                "eventType": "movicol_taken",
                "payload": {"doseSachets": m.get("doseSachets", 1), "time": m["time"]},
                "missingness": "observed",
                "provenance": _provenance(source, rid, occurred),
            })
            events.append(ev)

    return events


if __name__ == "__main__":
    import json, os
    here = os.path.dirname(__file__)
    log = json.load(open(os.path.join(here, "data", "gutpacer_synthetic.json")))
    evs = export_care_events(log)
    print(json.dumps(evs, ensure_ascii=False, indent=2))
