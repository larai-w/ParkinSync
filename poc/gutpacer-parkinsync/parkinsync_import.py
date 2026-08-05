"""care-event-v1 → ParkinSync 日次行 インポータ（PoC / BEN-001）
care-event 配列を localDate で束ね、ParkinSync の日次スキーマ(master_schema_template.csv)の
Bowel / Movi 列へマージする。欠測は欠測（None=空欄）のまま保持し、0埋めしない。
- Bowel: その日の観測された排便(bowel_movement, missingness=observed)の件数。
         観測0だが confirmed_none がある日は 0（＝確認された無し）。どちらも無ければ None（欠測）。
- Movi : その日の movicol_taken の doseSachets 合計。無ければ None（欠測）。
"""
from __future__ import annotations
from collections import defaultdict

# ParkinSync master schema の対象列（他列はこのPoCでは触らない）
PARKINSYNC_COLUMNS = ["Date", "Bowel", "Movi"]


def import_to_daily(events: list[dict]) -> dict[str, dict]:
    """care-event 配列 → { 'YYYY-MM-DD': {Date, Bowel, Movi} }"""
    by_day = defaultdict(list)
    for ev in events:
        by_day[ev["localDate"]].append(ev)

    rows: dict[str, dict] = {}
    for date in sorted(by_day):
        evs = by_day[date]
        bm_observed = [e for e in evs if e["eventType"] == "bowel_movement" and e["missingness"] == "observed"]
        bm_confirmed_none = [e for e in evs if e["eventType"] == "bowel_movement" and e["missingness"] == "confirmed_none"]
        movi = [e for e in evs if e["eventType"] == "movicol_taken" and e["missingness"] == "observed"]

        if bm_observed:
            bowel = len(bm_observed)
        elif bm_confirmed_none:
            bowel = 0            # 確認された無し = 実測の0
        else:
            bowel = None         # 欠測（空欄）

        movi_total = sum(int(e["payload"].get("doseSachets", 0)) for e in movi) if movi else None

        rows[date] = {"Date": date, "Bowel": bowel, "Movi": movi_total}
    return rows
