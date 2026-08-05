"""care-event-v1 最小バリデータ（外部依存ゼロ / PoC）
jsonschema を使わず、care-event-v1.schema.json の required・enum・const・pattern・
additionalProperties(false) と provenance の必須サブフィールドを検証する。
本番では jsonschema 等に置き換え可。ここでは CI 移植性のため依存を持たない。
"""
from __future__ import annotations
import json, os, re

_HERE = os.path.dirname(__file__)
_SCHEMA = json.load(open(os.path.join(_HERE, "schema", "care-event-v1.schema.json")))


class ValidationError(Exception):
    pass


def _check(cond: bool, msg: str):
    if not cond:
        raise ValidationError(msg)


def validate_event(ev: dict) -> None:
    props = _SCHEMA["properties"]
    # required
    for key in _SCHEMA["required"]:
        _check(key in ev, f"必須フィールド欠落: {key}")
    # additionalProperties: false（トップレベル）
    if _SCHEMA.get("additionalProperties") is False:
        extra = set(ev) - set(props)
        _check(not extra, f"未知フィールド: {sorted(extra)}")
    # const
    _check(ev["schemaVersion"] == props["schemaVersion"]["const"], "schemaVersion不一致")
    # enums
    _check(ev["eventType"] in props["eventType"]["enum"], f"eventType不正: {ev['eventType']}")
    _check(ev["missingness"] in props["missingness"]["enum"], f"missingness不正: {ev['missingness']}")
    _check(ev["consentScope"] in props["consentScope"]["enum"], f"consentScope不正: {ev['consentScope']}")
    if "actorRole" in ev:
        _check(ev["actorRole"] in props["actorRole"]["enum"], f"actorRole不正: {ev['actorRole']}")
    # pattern: localDate
    _check(re.match(props["localDate"]["pattern"], ev["localDate"]) is not None, "localDate形式不正")
    # payload は object
    _check(isinstance(ev["payload"], dict), "payloadはobject")
    # provenance の必須サブフィールド + additionalProperties:false
    prov_schema = props["provenance"]
    prov = ev["provenance"]
    _check(isinstance(prov, dict), "provenanceはobject")
    for key in prov_schema["required"]:
        _check(key in prov, f"provenance必須欠落: {key}")
    extra_prov = set(prov) - set(prov_schema["properties"])
    _check(not extra_prov, f"provenance未知フィールド: {sorted(extra_prov)}")


def validate_all(events: list[dict]) -> int:
    for i, ev in enumerate(events):
        try:
            validate_event(ev)
        except ValidationError as e:
            raise ValidationError(f"event[{i}] {ev.get('eventId','?')}: {e}") from None
    return len(events)
