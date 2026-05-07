#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.control_plane import build_working_memory_packet  # noqa: E402
from brainstack.db import BrainstackStore  # noqa: E402


REPORT_SCHEMA = "brainstack.store_concurrency_contract.v1"
PRINCIPAL_SCOPE = "principal:store-concurrency-contract"


def _sql_first_word(value: ast.AST) -> str:
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return value.value.strip().split(maxsplit=1)[0].upper() if value.value.strip() else ""
    return ""


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _classify_function(file: str, function: str, words: set[str], commit_count: int) -> str:
    if file.startswith("tests/") or "/tests/" in file:
        return "test_only"
    if "schema_migrations" in file or "db_schema" in file or function.startswith("_apply_"):
        return "migration_schema"
    if "style_source_hygiene" in file or "maintenance" in file or "repair" in function or "scrub" in function:
        return "repair_operator"
    if "publish_journal" in file or function.startswith(("_publish", "publish", "_upsert_publish")):
        return "projection_publish"
    if function.startswith("get_or_create"):
        return "write_helper_get_or_create"
    if function.startswith(("search", "list", "get", "recent", "compare")) and (words or commit_count):
        return "read_mutation_risk"
    return "runtime_write"


def _write_callsite_audit() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for path in sorted((ROOT / "brainstack").rglob("*.py")):
        relative = str(path.relative_to(ROOT))
        if "__pycache__" in relative:
            continue
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            words: set[str] = set()
            commit_count = 0
            for child in ast.walk(node):
                if not isinstance(child, ast.Call):
                    continue
                name = _call_name(child)
                if name == "commit":
                    commit_count += 1
                if name in {"execute", "executemany"} and child.args:
                    word = _sql_first_word(child.args[0])
                    if word in {"INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP", "VACUUM", "PRAGMA"}:
                        words.add(word)
            if not words and not commit_count:
                continue
            rows.append(
                {
                    "file": relative,
                    "function": node.name,
                    "line": int(node.lineno),
                    "class": _classify_function(relative, node.name, words, commit_count),
                    "sql_words": sorted(words),
                    "commit_count": commit_count,
                }
            )
    by_class = Counter(str(row["class"]) for row in rows)
    read_mutation = [row for row in rows if row["class"] == "read_mutation_risk"]
    runtime_write_map = [row for row in rows if row["class"] == "runtime_write"]
    write_helpers = [row for row in rows if row["class"] == "write_helper_get_or_create"]
    return {
        "callsite_count": len(rows),
        "by_class": dict(sorted(by_class.items())),
        "read_mutation_risk": read_mutation,
        "runtime_write_map": runtime_write_map,
        "write_helper_get_or_create": write_helpers,
        "lane_taxonomy": _lane_taxonomy(rows),
        "runtime_write_count": by_class.get("runtime_write", 0),
        "full_single_writer_safe_to_claim": False,
        "full_single_writer_blocker": "direct runtime commits still require a dedicated store-lane refactor",
        "store_lane_refactor_decision": {
            "status": "blocked_with_exact_refactor_map",
            "reason": "direct runtime commits are mapped but not routed through one lane yet",
            "required_next_step": "route or explicitly classify runtime_write_map entries before claiming a single writer",
        },
    }


def _lane_class_for_row(row: Mapping[str, Any]) -> str:
    file = str(row.get("file") or "")
    function = str(row.get("function") or "")
    class_name = str(row.get("class") or "")
    if class_name in {"test_only", "migration_schema", "repair_operator", "projection_publish", "write_helper_get_or_create"}:
        return class_name
    if file.startswith("brainstack/db.py"):
        return "store_open_bootstrap"
    if file.startswith("brainstack/db_migrations.py"):
        return "migration_schema"
    if file.startswith("brainstack/provider/explicit_capture.py"):
        return "explicit_capture_transaction"
    if file.startswith("brainstack/source_sync_spine.py"):
        return "source_sync_projection"
    if file.startswith("brainstack/storage/current_truth_l0_store.py"):
        return "projection_current_truth_l0"
    if file.startswith("brainstack/storage/semantic_index_store.py"):
        return "semantic_or_tier2_index"
    if file.startswith("brainstack/storage/telemetry_store.py"):
        return "retrieval_telemetry"
    if file.startswith("brainstack/storage/canonical_memory_events.py"):
        return "canonical_event_write"
    if file.startswith("brainstack/storage/admission_receipts.py"):
        return "admission_receipt_write"
    if file.startswith("brainstack/storage/profile_store.py"):
        if function.startswith(("upsert_profile_item", "upsert_behavior_contract", "apply_behavior_policy_correction")):
            return "profile_behavior_durable_write"
        return "profile_behavior_internal_write"
    if file.startswith("brainstack/storage/profile_read_store.py"):
        if function.startswith("record_profile_retrievals"):
            return "retrieval_telemetry"
        return "repair_operator"
    if file.startswith("brainstack/storage/task_store.py"):
        return "task_durable_write"
    if file.startswith("brainstack/storage/operating_store.py"):
        return "operating_durable_write"
    if file.startswith("brainstack/storage/graph_state"):
        return "graph_durable_or_relation_write"
    if file.startswith("brainstack/storage/corpus_store.py"):
        return "corpus_write"
    if file.startswith("brainstack/storage/continuity_store.py"):
        return "continuity_write"
    if file.startswith("brainstack/storage/proactive_store.py"):
        return "proactive_write"
    if file.startswith("brainstack/storage/publish_journal_store.py"):
        return "publish_journal_write"
    if file.startswith("brainstack/storage/schema_migrations.py"):
        return "migration_schema"
    if file.startswith("brainstack/storage/projection_writer.py"):
        return "projection_writer"
    return "unknown"


def _lane_taxonomy(rows: list[dict[str, Any]]) -> dict[str, Any]:
    lane_rows: list[dict[str, Any]] = []
    for row in rows:
        lane_class = _lane_class_for_row(row)
        lane_rows.append(
            {
                "file": row["file"],
                "function": row["function"],
                "line": row["line"],
                "lane_class": lane_class,
                "write_class": row["class"],
            }
        )
    by_lane = Counter(str(row["lane_class"]) for row in lane_rows)
    unknown = [row for row in lane_rows if row["lane_class"] == "unknown"]
    return {
        "by_lane": dict(sorted(by_lane.items())),
        "unknown_lane_count": len(unknown),
        "unknown": unknown,
        "rows": lane_rows,
        "status": "mapped" if not unknown else "unknown_lanes_present",
    }


def _profile_metadata(store: BrainstackStore, row_id: int) -> dict[str, Any]:
    row = store.conn.execute("SELECT metadata_json FROM profile_items WHERE id = ?", (row_id,)).fetchone()
    if row is None:
        return {}
    try:
        return json.loads(str(row["metadata_json"] or "{}"))
    except (TypeError, ValueError):
        return {}


def _packet(store: BrainstackStore, *, record_retrievals: bool | None = None) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if record_retrievals is not None:
        kwargs["record_retrievals"] = record_retrievals
    return build_working_memory_packet(
        store,
        query="direct concise public fixture response style",
        session_id="session:store-concurrency-contract",
        principal_scope_key=PRINCIPAL_SCOPE,
        profile_match_limit=6,
        continuity_recent_limit=0,
        continuity_match_limit=0,
        transcript_match_limit=0,
        transcript_char_budget=0,
        evidence_item_budget=4,
        graph_limit=0,
        corpus_limit=0,
        corpus_char_budget=0,
        adaptive_route_signals={"required_evidence_classes": ["profile"]},
        **kwargs,
    )


def _read_path_mutation_probe() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="brainstack-store-concurrency-") as temp:
        store = BrainstackStore(str(Path(temp) / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
        store.open()
        try:
            row_id = store.upsert_profile_item(
                stable_key="preference.public_fixture_style",
                category="style_preference",
                content="Use direct concise public fixture response style.",
                source="user_explicit",
                confidence=0.99,
                metadata={"principal_scope_key": PRINCIPAL_SCOPE, "target_slot": "preference.public_fixture_style"},
            )
            before = _profile_metadata(store, row_id)
            _packet(store)
            after_default = _profile_metadata(store, row_id)
            _packet(store, record_retrievals=True)
            after_opt_in = _profile_metadata(store, row_id)
        finally:
            store.close()
    return {
        "default_packet_mutated_retrieval_telemetry": "retrieval_telemetry" in after_default
        and after_default.get("retrieval_telemetry") != before.get("retrieval_telemetry"),
        "explicit_opt_in_retrieval_telemetry_written": "retrieval_telemetry" in after_opt_in,
        "default_before_keys": sorted(before.keys()),
        "default_after_keys": sorted(after_default.keys()),
    }


def _compiled_behavior_policy_read_probe() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="brainstack-compiled-policy-read-") as temp:
        store = BrainstackStore(str(Path(temp) / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
        store.open()
        try:
            store.upsert_behavior_contract(
                stable_key="preference:style_contract",
                category="style_preference",
                content="Fixture Contract\n\nGeneral:\n- Use direct concise public fixture language.",
                source="user_explicit",
                confidence=0.99,
                metadata={"principal_scope_key": PRINCIPAL_SCOPE, "source_role": "user"},
            )
            store.conn.execute("DELETE FROM compiled_behavior_policies WHERE principal_scope_key = ?", (PRINCIPAL_SCOPE,))
            store.conn.commit()
            before_count = int(store.conn.execute("SELECT COUNT(*) FROM compiled_behavior_policies").fetchone()[0])
            direct_record = store.get_compiled_behavior_policy(principal_scope_key=PRINCIPAL_SCOPE)
            after_direct_count = int(store.conn.execute("SELECT COUNT(*) FROM compiled_behavior_policies").fetchone()[0])
            _packet(store)
            after_packet_count = int(store.conn.execute("SELECT COUNT(*) FROM compiled_behavior_policies").fetchone()[0])
        finally:
            store.close()
    return {
        "compiled_record_returned": isinstance(direct_record, dict) and bool(direct_record.get("policy")),
        "direct_read_created_durable_row": after_direct_count != before_count,
        "packet_read_created_durable_row": after_packet_count != before_count,
        "before_count": before_count,
        "after_direct_count": after_direct_count,
        "after_packet_count": after_packet_count,
    }


def build_report() -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    read_probe = _read_path_mutation_probe()
    compiled_probe = _compiled_behavior_policy_read_probe()
    audit = _write_callsite_audit()
    if read_probe["default_packet_mutated_retrieval_telemetry"]:
        issues.append({"code": "default_packet_build_mutated_retrieval_telemetry"})
    if not read_probe["explicit_opt_in_retrieval_telemetry_written"]:
        issues.append({"code": "explicit_opt_in_retrieval_telemetry_not_written"})
    if not compiled_probe["compiled_record_returned"]:
        issues.append({"code": "compiled_behavior_policy_read_projection_missing"})
    if compiled_probe["direct_read_created_durable_row"]:
        issues.append({"code": "compiled_behavior_policy_direct_read_created_durable_row"})
    if compiled_probe["packet_read_created_durable_row"]:
        issues.append({"code": "compiled_behavior_policy_packet_read_created_durable_row"})
    lane_taxonomy = audit.get("lane_taxonomy") if isinstance(audit.get("lane_taxonomy"), dict) else {}
    if int(lane_taxonomy.get("unknown_lane_count") or 0) != 0:
        issues.append({"code": "store_write_lane_taxonomy_unknown_entries"})
    return {
        "schema": REPORT_SCHEMA,
        "status": "pass" if not issues else "fail",
        "issues": issues,
        "public_safe": True,
        "read_path_mutation_probe": read_probe,
        "compiled_behavior_policy_read_probe": compiled_probe,
        "write_callsite_audit": audit,
        "single_writer_queue": {
            "status": "not_claimed",
            "reason": audit["full_single_writer_blocker"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = build_report()
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    else:
        print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
