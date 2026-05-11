#!/usr/bin/env python3
"""Verify brainstack_recall stays compact while inspect keeps full detail."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.provider_diagnostics import (  # noqa: E402
    MODEL_FACING_RECALL_BUDGET,
    handle_brainstack_inspect,
    handle_brainstack_recall,
)

MODEL_FACING_RECALL_RENDER_BUDGET_BYTES = 6000


def _fixture_report() -> dict[str, Any]:
    long_text = "Agent-facing recall must stay compact. " * 90
    parity = {
        "host_receipt_id": "host-fixture",
        "projection_status": "pending",
        "divergence_status": "diverged",
        "parity_observable": "observable_diverged",
        "event_type": "profile_write",
        "raw_debug_note": "inspect-only parity payload",
    }
    rows = [
        {
            "evidence_key": f"profile:fixture:{index}",
            "shelf": "profile",
            "row_type": "profile",
            "stable_key": f"preference:fixture:{index}",
            "source": "phase-294-fixture",
            "authority_level": "explicit_user_memory",
            "excerpt": f"{long_text} row={index}",
            "semantic_anchor_text": f"{long_text} semantic-anchor={index}",
            "literal_tokens": [{"class": "debug_marker", "value": f"RAW-LITERAL-{index}-{n}"} for n in range(20)],
            "explicit_truth_parity": parity,
            "source_envelope": {"raw": long_text},
            "projection_status": "pending",
            "divergence_status": "diverged",
            "parity_observable": "observable_diverged",
            "bounded_scope_only": True,
        }
        for index in range(5)
    ]
    return {
        "schema": "brainstack.query_inspect.v1",
        "routing": {"route": "profile"},
        "channels": [{"name": "profile", "status": "ok", "candidate_count": len(rows)}],
        "selected_evidence": {"profile": rows},
        "final_packet": {
            "sections": ["Profile"],
            "char_count": len(long_text),
            "preview": long_text,
            "explicit_truth_parity": [parity],
        },
        "memory_answerability": {
            "can_answer": True,
            "reason_code": "ANSWERABLE",
            "max_claim_strength": "memory_truth",
            "answer_evidence_ids": ["profile:fixture:0"],
        },
    }


def _contains_key(value: Any, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_contains_key(child, key) for child in value.values())
    if isinstance(value, list):
        return any(_contains_key(child, key) for child in value)
    return False


def build_proof() -> dict[str, Any]:
    report = _fixture_report()

    def query_inspect(**_: Any) -> dict[str, Any]:
        return report

    recall = handle_brainstack_recall(
        args={"query": "phase 294 recall budget fixture"},
        principal_scope_key="principal:phase-294",
        session_id="session:phase-294",
        query_inspect=query_inspect,
    )
    inspect = handle_brainstack_inspect(
        args={"query": "phase 294 recall budget fixture"},
        principal_scope_key="principal:phase-294",
        session_id="session:phase-294",
        query_inspect=query_inspect,
    )
    rendered_recall = json.dumps(recall, ensure_ascii=False, sort_keys=True)
    rendered_inspect = json.dumps(inspect, ensure_ascii=False, sort_keys=True)
    first_card = (recall.get("selected_evidence") or {}).get("profile", [{}])[0]
    source_status = first_card.get("source_status") if isinstance(first_card, dict) else {}
    proof = {
        "bounded_model_facing": recall.get("bounded_model_facing") is True,
        "budget_contract_exported": (recall.get("budget_contract") or {}).get("schema")
        == "brainstack.recall_detail_budget.v1",
        "budget_basis_declared": (recall.get("budget_contract") or {}).get("budget_basis")
        == MODEL_FACING_RECALL_BUDGET.budget_basis,
        "compact_under_budget": len(rendered_recall) < MODEL_FACING_RECALL_RENDER_BUDGET_BYTES,
        "preview_under_budget": len((recall.get("final_packet") or {}).get("preview") or "")
        <= MODEL_FACING_RECALL_BUDGET.preview_char_limit,
        "literal_tokens_omitted_from_recall": not _contains_key(recall, "literal_tokens"),
        "explicit_truth_parity_omitted_from_recall": not _contains_key(recall, "explicit_truth_parity"),
        "inspect_handle_present": bool(first_card.get("inspect", {}).get("handle")) if isinstance(first_card, dict) else False,
        "source_conflict_status_visible": (
            isinstance(source_status, dict)
            and source_status.get("projection_status") == "pending"
            and source_status.get("divergence_status") == "diverged"
            and source_status.get("parity_detail_available") is True
        ),
        "inspect_retains_literal_tokens": '"literal_tokens"' in rendered_inspect,
        "inspect_retains_explicit_truth_parity": '"explicit_truth_parity"' in rendered_inspect,
        "answerability_preserved": (recall.get("memory_answerability") or {}).get("can_answer") is True
        and (recall.get("memory_answerability") or {}).get("answer_evidence_ids") == ["profile:fixture:0"],
    }
    issues = [{"code": key} for key, value in proof.items() if value is not True]
    return {
        "schema": "brainstack.model_facing_recall_budget_proof.v1",
        "status": "pass" if not issues else "fail",
        "public_safe": True,
        "recall_bytes": len(rendered_recall),
        "inspect_bytes": len(rendered_inspect),
        "proof": proof,
        "issues": issues,
    }


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
