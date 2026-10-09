"""Versioned, ordered master-ledger baseline; unrelated to care-event/FHIR versions."""
from __future__ import annotations

CONTRACT_ID = "parkinsync-master-ledger/v1"
# Preserve this v1 baseline when introducing a separately reviewed future version.
COLUMNS = ('Processed', 'Date', 'Day', 'Morning', 'Lunch', 'Evening', 'Bedtime', 'Bedtime_2', 'Bowel', 'Movi', 'Emerg_Call', 'Ryusei_Eme', 'Condition_C', 'Condition_Num', 'Daily_Notes', 'Weather_Summary', 'Weather_Avg', 'Weather_Min', 'Weather_Max', 'Weather_Condition', 'Switchbot_Summary', 'Switchbot_Avg', 'Switchbot_Min', 'Switchbot_Max', 'File_Name')


def validate_columns(columns: list[str]) -> None:
    if tuple(columns) != COLUMNS:
        raise ValueError(f"master-ledger columns must exactly match {CONTRACT_ID}")


def validate_manifest(manifest: dict) -> None:
    if manifest.get("master_ledger_contract") != CONTRACT_ID:
        raise ValueError(f"master-ledger manifest must declare {CONTRACT_ID}")
