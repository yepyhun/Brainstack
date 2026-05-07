from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Mapping

from .active_preference_contract import DELIVERY_REASON_EXPLICIT_MEMORY_INSPECTION
from .profile_prompt_policy import (
    is_demotable_behavior_profile_source_item,
    profile_prompt_source_key,
)
from .retrieval import build_system_prompt_projection
from .storage.store_runtime import (
    _annotate_principal_scope,
    _merge_record_metadata,
    _profile_row_to_dict,
    utc_now_iso,
)
from .style_contract import STYLE_CONTRACT_SLOT, list_style_contract_rules


STYLE_SOURCE_HYGIENE_MAINTENANCE_CLASS = "style_source_hygiene"
STYLE_SOURCE_HYGIENE_SCHEMA = "brainstack.style_source_hygiene.v1"
STYLE_SOURCE_HYGIENE_REASON_CODE = "LEGACY_BEHAVIOR_PROFILE_SOURCE_DEMOTED"


def _public_row_ref(item: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "row_id": int(item.get("id") or 0),
        "stable_key": str(item.get("stable_key") or "").strip(),
        "category": str(item.get("category") or "").strip(),
        "principal_scope_match": bool(item.get("same_principal") or item.get("same_personal_scope")),
        "content_sha256_12": hashlib.sha256(str(item.get("content") or "").encode("utf-8")).hexdigest()[:12],
        "content_char_count": len(str(item.get("content") or "")),
    }


def _canonical_card_state(store: Any, *, principal_scope_key: str) -> Dict[str, Any]:
    row = store.get_profile_item(stable_key=STYLE_CONTRACT_SLOT, principal_scope_key=principal_scope_key)
    if not isinstance(row, Mapping):
        return {
            "present": False,
            "stable_key": STYLE_CONTRACT_SLOT,
            "rule_count": 0,
            "content_sha256": "",
            "content_char_count": 0,
        }
    metadata = row.get("metadata") if isinstance(row.get("metadata"), Mapping) else {}
    content = str(row.get("content") or "")
    return {
        "present": True,
        "stable_key": STYLE_CONTRACT_SLOT,
        "rule_count": len(list_style_contract_rules(raw_text=content, metadata=metadata)),
        "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "content_char_count": len(content),
    }


def _candidate_rows(store: Any, *, principal_scope_key: str) -> list[Dict[str, Any]]:
    rows = store.conn.execute(
        """
        SELECT id, stable_key, logical_stable_key, principal_scope_key, category, content, source,
               confidence, metadata_json, updated_at, active
        FROM profile_items
        WHERE active = 1
        ORDER BY updated_at DESC, id DESC
        """
    ).fetchall()
    candidates: list[Dict[str, Any]] = []
    for row in rows:
        item = _profile_row_to_dict(row)
        if not _annotate_principal_scope(item, principal_scope_key=principal_scope_key):
            continue
        if not is_demotable_behavior_profile_source_item(item):
            continue
        if not item.get("same_principal"):
            continue
        candidates.append(item)
    return candidates


def _backup_open_sqlite_db(store: Any, *, backup_path: str | None = None) -> str:
    db_path = Path(str(getattr(store, "_db_path", "") or "")).expanduser()
    if not db_path:
        raise RuntimeError("sqlite_db_path_required_for_backup")
    if not db_path.exists():
        raise RuntimeError("sqlite_db_path_missing_for_backup")
    if backup_path:
        target = Path(backup_path).expanduser()
    else:
        stamp = utc_now_iso().replace(":", "").replace("-", "").replace(".", "_").replace("+", "Z")
        target = db_path.with_name(f"{db_path.name}.pre-style-source-hygiene-{stamp}.bak")
    target.parent.mkdir(parents=True, exist_ok=True)
    destination = sqlite3.connect(str(target))
    try:
        store.conn.backup(destination)
    finally:
        destination.close()
    return str(target)


def run_style_source_hygiene_repair(
    store: Any,
    *,
    principal_scope_key: str,
    apply: bool = False,
    explicit_user_request: bool = False,
    backup_path: str | None = None,
    expose_backup_path: bool = False,
) -> Dict[str, Any]:
    scope = str(principal_scope_key or "").strip()
    before = _canonical_card_state(store, principal_scope_key=scope)
    candidates = _candidate_rows(store, principal_scope_key=scope) if scope else []
    receipt: Dict[str, Any] = {
        "schema": STYLE_SOURCE_HYGIENE_SCHEMA,
        "maintenance_class": STYLE_SOURCE_HYGIENE_MAINTENANCE_CLASS,
        "mode": "apply" if apply else "dry_run",
        "status": "ok",
        "principal_scope_present": bool(scope),
        "candidate_count": len(candidates),
        "candidate_refs": [_public_row_ref(item) for item in candidates],
        "canonical_card_before": {
            key: value for key, value in before.items() if key != "content_sha256"
        },
        "canonical_card_hash_before": before.get("content_sha256", ""),
        "demoted_count": 0,
        "demoted_refs": [],
        "backup_path": "",
        "backup_created": False,
        "backup_ref": "",
        "no_op_reasons": [],
        "issues": [],
        "public_safe": True,
        "truth_mutation": False,
        "raw_history_deleted": False,
        "creates_behavior_authority": False,
    }
    if not scope:
        receipt["status"] = "rejected" if apply else "ok"
        receipt["no_op_reasons"].append("principal_scope_required")
        return receipt
    if not before.get("present"):
        receipt["status"] = "rejected" if apply else "ok"
        receipt["no_op_reasons"].append("active_canonical_style_contract_required")
        return receipt
    if not apply:
        if not candidates:
            receipt["no_op_reasons"].append("no_legacy_behavior_profile_sources")
        return receipt
    if not explicit_user_request:
        receipt["status"] = "rejected"
        receipt["no_op_reasons"].append("explicit_user_request_required")
        return receipt

    now = utc_now_iso()
    demoted: list[Dict[str, Any]] = []
    backup = ""
    before_behavior_contract_rows = 0
    before_compiled_policy_rows = 0
    try:
        backup = _backup_open_sqlite_db(store, backup_path=backup_path)
        before_behavior_contract_rows = int(
            store.conn.execute("SELECT COUNT(*) FROM behavior_contracts").fetchone()[0]
        )
        before_compiled_policy_rows = int(
            store.conn.execute("SELECT COUNT(*) FROM compiled_behavior_policies").fetchone()[0]
        )
        store.conn.execute("BEGIN IMMEDIATE")
        for item in candidates:
            row_id = int(item.get("id") or 0)
            if row_id <= 0:
                continue
            metadata = _merge_record_metadata(
                json.dumps(item.get("metadata") or {}, ensure_ascii=True, sort_keys=True),
                {
                    "repair_action": "demote_legacy_behavior_profile_source",
                    "repair_reason_code": STYLE_SOURCE_HYGIENE_REASON_CODE,
                    "repair_scope": scope,
                    "repair_demoted_at": now,
                    "source_only": True,
                    "prompt_authority": False,
                    "canonical_style_contract_stable_key": STYLE_CONTRACT_SLOT,
                    "source_profile_stable_key": profile_prompt_source_key(item),
                },
                source="brainstack_consolidate:style_source_hygiene",
            )
            cursor = store.conn.execute(
                """
                UPDATE profile_items
                SET active = 0, metadata_json = ?, updated_at = ?
                WHERE id = ? AND active = 1
                """,
                (json.dumps(metadata, ensure_ascii=True, sort_keys=True), now, row_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("legacy_behavior_profile_source_changed_before_repair")
            store.conn.execute("DELETE FROM profile_fts WHERE rowid = ?", (row_id,))
            demoted.append(_public_row_ref(item))
        after = _canonical_card_state(store, principal_scope_key=scope)
        if after.get("content_sha256") != before.get("content_sha256"):
            raise RuntimeError("canonical_style_contract_changed")
        if int(after.get("rule_count") or 0) != int(before.get("rule_count") or 0):
            raise RuntimeError("canonical_style_contract_rule_count_changed")
        projection = build_system_prompt_projection(
            store,
            profile_limit=8,
            principal_scope_key=scope,
            delivery_reason=DELIVERY_REASON_EXPLICIT_MEMORY_INSPECTION,
        )
        delivery = projection.get("active_preference_delivery_inspect")
        delivery = delivery if isinstance(delivery, Mapping) else {}
        if delivery.get("source_stable_key") != STYLE_CONTRACT_SLOT:
            raise RuntimeError("active_card_source_slot_mismatch")
        if str(delivery.get("delivery_status") or "") != "delivered_full":
            raise RuntimeError("active_card_not_delivered_full_after_repair")
    except Exception as exc:
        try:
            store.conn.rollback()
        except Exception:
            pass
        receipt["status"] = "failed"
        receipt["issues"].append(str(exc))
        receipt["backup_created"] = bool(backup)
        receipt["backup_ref"] = Path(backup).name if backup else ""
        if expose_backup_path:
            receipt["backup_path"] = backup
        return receipt
    store.conn.commit()

    after = _canonical_card_state(store, principal_scope_key=scope)
    remaining = _candidate_rows(store, principal_scope_key=scope)
    after_behavior_contract_rows = int(
        store.conn.execute("SELECT COUNT(*) FROM behavior_contracts").fetchone()[0]
    )
    after_compiled_policy_rows = int(
        store.conn.execute("SELECT COUNT(*) FROM compiled_behavior_policies").fetchone()[0]
    )
    receipt.update(
        {
            "status": "applied",
            "backup_created": bool(backup),
            "backup_ref": Path(backup).name if backup else "",
            "demoted_count": len(demoted),
            "demoted_refs": demoted,
            "remaining_candidate_count": len(remaining),
            "canonical_card_after": {
                key: value for key, value in after.items() if key != "content_sha256"
            },
            "canonical_card_hash_after": after.get("content_sha256", ""),
            "final_state_proof": {
                "canonical_card_unchanged": after.get("content_sha256") == before.get("content_sha256"),
                "canonical_rule_count_unchanged": int(after.get("rule_count") or 0) == int(before.get("rule_count") or 0),
                "legacy_behavior_sources_active": len(remaining),
                "behavior_contract_rows_created": max(0, after_behavior_contract_rows - before_behavior_contract_rows),
                "compiled_behavior_policy_rows_created": max(0, after_compiled_policy_rows - before_compiled_policy_rows),
            },
        }
    )
    if expose_backup_path:
        receipt["backup_path"] = backup
    if not demoted:
        receipt["no_op_reasons"].append("no_legacy_behavior_profile_sources")
    return receipt
