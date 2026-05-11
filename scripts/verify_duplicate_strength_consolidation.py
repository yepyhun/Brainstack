#!/usr/bin/env python3
"""Prove exact duplicate evidence cannot inflate model-facing memory strength."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.control_plane import build_working_memory_packet  # noqa: E402
from brainstack.core.packet_budget import PacketBudgetPolicy, apply_packet_budget  # noqa: E402
from brainstack.core.reason_codes import ReasonCode  # noqa: E402
from brainstack.core.trace import AUTHORITY_RECEIPT_BACKED, DECISION_SELECTED, make_evidence_candidate  # noqa: E402
from brainstack.db import BrainstackStore  # noqa: E402
from brainstack.maintenance import run_bounded_maintenance  # noqa: E402
from brainstack.persistent_bloat import build_persistent_bloat_report  # noqa: E402


def _packet_defaults() -> dict[str, object]:
    return {
        "profile_match_limit": 6,
        "continuity_recent_limit": 0,
        "continuity_match_limit": 0,
        "transcript_match_limit": 0,
        "transcript_char_budget": 0,
        "evidence_item_budget": 8,
        "graph_limit": 0,
        "corpus_limit": 0,
        "corpus_char_budget": 0,
        "operating_match_limit": 0,
        "record_retrievals": False,
    }


def _receipt_candidate(candidate_id: str, raw_value: str) -> dict[str, Any]:
    return make_evidence_candidate(
        candidate_id=candidate_id,
        shelf="profile",
        target_slot="preference.memory_style",
        source_role="user",
        authority=AUTHORITY_RECEIPT_BACKED,
        decision=DECISION_SELECTED,
        reason_code=ReasonCode.SELECTED_RECEIPT_BACKED_FACT.value,
        truth_eligible=True,
        model_facing_allowed=True,
        answer_evidence_allowed=True,
        raw_value=raw_value,
        token_estimate=8,
    )


def build_proof() -> dict[str, Any]:
    root = Path(tempfile.mkdtemp(prefix="brainstack-duplicate-strength-"))
    store = BrainstackStore(str(root / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    try:
        scope = "principal:phase-295"
        session = "session:phase-295"
        duplicate_content = "Duplicate strength proof user prefers compact memory."
        for stable_key in ("preference:duplicate:a", "preference:duplicate:b"):
            store.upsert_profile_item(
                stable_key=stable_key,
                category="preference",
                content=duplicate_content,
                source="phase-295-fixture",
                confidence=0.99,
                metadata={"principal_scope_key": scope, "truth_eligible": True},
            )

        packet = build_working_memory_packet(
            store,
            query="compact memory duplicate strength proof",
            session_id=session,
            principal_scope_key=scope,
            **_packet_defaults(),
        )
        budget_decisions = list((packet.get("packet_budget") or {}).get("budget_decisions") or [])
        duplicate_drops = [
            item
            for item in budget_decisions
            if item.get("reason_code") == ReasonCode.DROPPED_BUDGET_DUPLICATE_LOWER_AUTHORITY.value
        ]
        bloat = build_persistent_bloat_report(store, principal_scope_key=scope)
        maintenance_dry_run = run_bounded_maintenance(
            store,
            apply=False,
            maintenance_class="profile_duplicate_content",
            principal_scope_key=scope,
        )
        before_rows = store.conn.execute("SELECT COUNT(*) AS count FROM profile_items").fetchone()["count"]
        maintenance_apply = run_bounded_maintenance(
            store,
            apply=True,
            maintenance_class="profile_duplicate_content",
            principal_scope_key=scope,
        )
        after_rows = store.conn.execute("SELECT COUNT(*) AS count FROM profile_items").fetchone()["count"]

        near_duplicate_result = apply_packet_budget(
            [
                _receipt_candidate("near-a", "Compact memory, but keep inspect detail."),
                _receipt_candidate("near-b", "Compact memory, and keep conflict status."),
            ],
            PacketBudgetPolicy(max_candidate_tokens=16),
        )
        near_selected = [
            item.get("candidate_id")
            for item in near_duplicate_result.candidates
            if item.get("decision") == "selected"
        ]

        proof = {
            "dirty_live_shaped_profile_duplicate_fixture": before_rows == 2,
            "exact_duplicate_selected_once": len(packet.get("profile_items") or []) == 1,
            "exact_duplicate_rendered_once": str(packet.get("block") or "").count(duplicate_content) == 1,
            "exact_duplicate_budget_drop_reported": len(duplicate_drops) == 1,
            "answer_evidence_preserved": (packet.get("packet_budget") or {}).get("answer_evidence_preserved") is True,
            "bloat_reports_duplicate_strength": (
                (bloat.get("metrics") or {})
                .get("duplicate_strength_inflation", {})
                .get("profile_duplicate_groups", 0)
                >= 1
            ),
            "dry_run_reports_review_only_duplicate": any(
                item.get("maintenance_class") == "profile_duplicate_content"
                and item.get("apply_supported") is False
                and int(item.get("candidate_count") or 0) >= 1
                for item in (maintenance_dry_run.get("dry_run") or {}).get("candidates", [])
            ),
            "unsafe_apply_rejected_without_mutation": (
                maintenance_apply.get("status") == "rejected"
                and "persistent_bloat_cleanup_requires_explicit_review" in maintenance_apply.get("no_op_reasons", [])
                and before_rows == after_rows
            ),
            "near_duplicate_not_auto_merged": set(near_selected) == {"near-a", "near-b"},
        }
        issues = [{"code": key} for key, value in proof.items() if value is not True]
        return {
            "schema": "brainstack.duplicate_strength_consolidation_proof.v1",
            "status": "pass" if not issues else "fail",
            "public_safe": True,
            "proof": proof,
            "issues": issues,
            "diagnostics": {
                "profile_rows_before_apply": before_rows,
                "profile_rows_after_apply": after_rows,
                "budget_duplicate_drop_count": len(duplicate_drops),
                "packet_profile_item_count": len(packet.get("profile_items") or []),
                "near_duplicate_selected": near_selected,
            },
        }
    finally:
        store.close()
        shutil.rmtree(root, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    result = build_proof()
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    else:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
