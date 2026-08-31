"""care-event-v1 → ParkinSync 日次行 インポータ（PoC / BEN-001）
care-event 配列を localDate で束ね、ParkinSync の日次スキーマ(master_schema_template.csv)の
Bowel / Movi / Med 列へマージする。欠測は欠測（None=空欄）のまま保持し、0埋めしない。
**source は問わない。** GutPacer と Medication Promise の export を混ぜて渡せる。
- Bowel: その日の観測された排便(bowel_movement, missingness=observed)の件数。
         観測0だが confirmed_none がある日は 0（＝確認された無し）。どちらも無ければ None（欠測）。
- Movi : その日の movicol_taken の doseSachets 合計。無ければ None（欠測）。
- Med  : その日の観測された服薬(medication_taken, missingness=observed)の**件数**。

  ⚠️ **記録が無い日を 0 にしない。**（2026-08-31）

  Bowel には `confirmed_none`（確認された無し）があるので「実測の0」と「欠測」を
  区別できる。**服薬にはそれが無い。** Medication Promise の export は
  `eventType` が `medication_taken` の const で、`missingness` も `observed` の
  const —— **「飲まなかった」を出す口がそもそも無い**（推測された未服薬は
  意図的に除外されている）。だから記録が無い日は「飲まなかった日」ではなく
  **「分からない日」**で、None（空欄）にする。

  0 になるのは、**別の source が「飲まなかった」を明示したとき**だけ:
  観測された `medication_missed`、または `medication_taken` の `confirmed_none`。
  **記録の不在を、事実として読ませない。**
"""
from __future__ import annotations
from collections import defaultdict

# ParkinSync master schema の対象列（他列はこのPoCでは触らない）
PARKINSYNC_COLUMNS = ["Date", "Bowel", "Movi", "Med"]


def import_to_daily(events: list[dict]) -> dict[str, dict]:
    """care-event 配列 → { 'YYYY-MM-DD': {Date, Bowel, Movi, Med} }"""
    by_day = defaultdict(list)
    for ev in events:
        by_day[ev["localDate"]].append(ev)

    rows: dict[str, dict] = {}
    for date in sorted(by_day):
        evs = by_day[date]
        bm_observed = [e for e in evs if e["eventType"] == "bowel_movement" and e["missingness"] == "observed"]
        bm_confirmed_none = [e for e in evs if e["eventType"] == "bowel_movement" and e["missingness"] == "confirmed_none"]
        movi = [e for e in evs if e["eventType"] == "movicol_taken" and e["missingness"] == "observed"]
        med_observed = [e for e in evs if e["eventType"] == "medication_taken" and e["missingness"] == "observed"]
        # **明示された「飲まなかった」だけ**を実測の0の根拠にする。
        med_absent_stated = [
            e for e in evs
            if (e["eventType"] == "medication_missed" and e["missingness"] == "observed")
            or (e["eventType"] == "medication_taken" and e["missingness"] == "confirmed_none")
        ]

        if bm_observed:
            bowel = len(bm_observed)
        elif bm_confirmed_none:
            bowel = 0            # 確認された無し = 実測の0
        else:
            bowel = None         # 欠測（空欄）

        movi_total = sum(int(e["payload"].get("doseSachets", 0)) for e in movi) if movi else None

        if med_observed:
            med = len(med_observed)
        elif med_absent_stated:
            med = 0              # 明示された未服薬 = 実測の0
        else:
            med = None           # 欠測（空欄）。**記録が無い日を0にしない**

        rows[date] = {"Date": date, "Bowel": bowel, "Movi": movi_total, "Med": med}
    return rows
