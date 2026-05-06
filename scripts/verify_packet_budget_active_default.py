#!/usr/bin/env python3
"""Verify active packet budget is the supported default path."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack import BrainstackMemoryProvider  # noqa: E402
from brainstack.adaptive_evidence_broker import build_broker_trace_from_packet, validate_broker_trace  # noqa: E402
from brainstack.control_plane import build_working_memory_packet  # noqa: E402
from brainstack.core.packet_budget import (  # noqa: E402
    DEFAULT_PACKET_BUDGET_MODE,
    PacketBudgetPolicy,
    apply_packet_budget,
    resolve_packet_budget_mode,
    validate_packet_budget_trace,
)
from brainstack.db import BrainstackStore  # noqa: E402


SCHEMA = "brainstack.packet_budget_active_default_proof.v1"


def _candidate(candidate_id: str, **overrides: Any) -> dict[str, Any]:
    item = {
        "candidate_id": candidate_id,
        "evidence_id": candidate_id,
        "authority": "durable_truth",
        "decision": "selected",
        "source_role": "user",
        "truth_eligible": True,
        "answer_evidence_allowed": True,
        "answer_evidence": True,
        "protected": True,
        "source_event_id": f"turn-{candidate_id}",
        "source_span_id": f"span-{candidate_id}",
        "admission_id": f"admission-{candidate_id}",
        "receipt_id": f"receipt-{candidate_id}",
        "token_estimate": 8,
    }
    item.update(overrides)
    return item


def _packet_defaults() -> dict[str, object]:
    return {
        "profile_match_limit": 4,
        "continuity_recent_limit": 6,
        "continuity_match_limit": 6,
        "transcript_match_limit": 4,
        "transcript_char_budget": 1800,
        "evidence_item_budget": 10,
        "graph_limit": 3,
        "corpus_limit": 2,
        "corpus_char_budget": 420,
        "operating_match_limit": 3,
        "record_retrievals": False,
    }


def _budget_case(name: str, candidates: list[dict[str, Any]], *, max_tokens: int) -> dict[str, Any]:
    result = apply_packet_budget(candidates, PacketBudgetPolicy(max_candidate_tokens=max_tokens))
    trace = {"candidates": result.candidates, "packet_budget": result.to_trace_packet_budget()}
    broker = build_broker_trace_from_packet({"packet_budget": {"budget_decisions": result.candidates}})
    budget_errors = validate_packet_budget_trace(trace)
    broker_errors = validate_broker_trace(broker)
    selected_ids = [str(item.get("candidate_id") or "") for item in result.candidates if item.get("decision") == "selected"]
    dropped_ids = [str(item.get("candidate_id") or "") for item in result.candidates if item.get("decision") == "dropped"]
    protected_ids = [str(item.get("candidate_id") or "") for item in candidates if item.get("protected") or item.get("truth_eligible")]
    protected_drops = sum(1 for candidate_id in protected_ids if candidate_id in dropped_ids)
    passed = not budget_errors and not broker_errors and protected_drops == 0
    return {
        "case_id": name,
        "status": "pass" if passed else "fail",
        "packet_budget_status": result.status,
        "fail_closed": result.fail_closed,
        "selected_count": len(selected_ids),
        "dropped_count": len(dropped_ids),
        "selected_id_fingerprints": [_fingerprint(item) for item in selected_ids],
        "dropped_id_fingerprints": [_fingerprint(item) for item in dropped_ids],
        "protected_drop_attempts": protected_drops,
        "budget_validation_errors": budget_errors,
        "broker_validation_errors": broker_errors,
        "broker_unsafe_answer_truth_upgrade_count": broker.get("unsafe_answer_truth_upgrade_count"),
        "raw_text_in_budget_trace": result.to_trace_packet_budget().get("raw_text_in_budget_trace") is True,
    }


def _fingerprint(value: object) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _matrix_cases() -> list[dict[str, Any]]:
    return [
        _budget_case(
            "protected_truth_support_conflict_prior_multilingual",
            [
                _candidate("truth-current", token_estimate=8),
                _candidate(
                    "support-only",
                    authority="support_only",
                    truth_eligible=False,
                    answer_evidence_allowed=False,
                    answer_evidence=False,
                    protected=False,
                    receipt_id="",
                    admission_id="",
                    token_estimate=20,
                ),
                _candidate(
                    "conflict",
                    authority="conflict",
                    row_type="conflict",
                    support_visibility="contradiction_only",
                    truth_eligible=False,
                    answer_evidence_allowed=False,
                    answer_evidence=False,
                    protected=False,
                    receipt_id="",
                    admission_id="",
                    token_estimate=10,
                ),
                _candidate(
                    "prior-stale",
                    authority="support_only",
                    stale=True,
                    freshness="prior",
                    truth_eligible=False,
                    answer_evidence_allowed=False,
                    answer_evidence=False,
                    protected=False,
                    receipt_id="",
                    admission_id="",
                    token_estimate=10,
                ),
                _candidate("multilingual-cjk-proof", token_estimate=8),
            ],
            max_tokens=16,
        ),
        _budget_case(
            "malformed_candidate_visible_but_not_truth",
            [
                _candidate("truth-anchor", token_estimate=8),
                {"candidate_id": "malformed", "decision": "selected", "token_estimate": 12},
            ],
            max_tokens=8,
        ),
        _budget_case(
            "tiny_budget_fail_closed_preserves_truth",
            [_candidate("truth-a", token_estimate=9), _candidate("truth-b", token_estimate=9)],
            max_tokens=1,
        ),
        _budget_case(
            "high_fanout_noise_pressure",
            [
                _candidate("truth-anchor", token_estimate=8),
                *[
                    _candidate(
                        f"support-noise-{index}",
                        authority="support_only",
                        truth_eligible=False,
                        answer_evidence_allowed=False,
                        answer_evidence=False,
                        protected=False,
                        receipt_id="",
                        admission_id="",
                        token_estimate=8,
                    )
                    for index in range(40)
                ],
            ],
            max_tokens=24,
        ),
    ]


def _runtime_default_case(root: Path) -> dict[str, Any]:
    store = BrainstackStore(str(root / "runtime-default.sqlite3"), graph_backend="not-real-backend", corpus_backend="sqlite")
    store.open()
    try:
        scope = "principal:m007:s03:runtime-default"
        session = "session:m007:s03:runtime-default"
        store.upsert_profile_item(
            stable_key="identity:m007:s03:runtime-default",
            category="identity",
            content="The public active default runtime name is RuntimeActiveUser.",
            source="active-default.verifier",
            confidence=0.99,
            metadata={"principal_scope_key": scope, "truth_eligible": True},
        )
        for index in range(8):
            store.add_continuity_event(
                session_id=session,
                turn_number=index + 1,
                kind="user",
                content=f"PUBLIC_ACTIVE_DEFAULT_SUPPORT_NOISE_{index}",
                source="active-default.verifier",
                metadata={"principal_scope_key": scope, "support_visibility": "support_only"},
            )
        packet = build_working_memory_packet(
            store,
            query="What is the public active default runtime name?",
            session_id=session,
            principal_scope_key=scope,
            **_packet_defaults(),
        )
        budget = dict(packet.get("packet_budget") or {})
        channels = list(packet.get("channels") or [])
        backend_degraded_visible = any(
            str(channel.get("status") or "") == "degraded"
            and str(channel.get("reason") or "")
            for channel in channels
            if isinstance(channel, Mapping)
        )
        return {
            "case_id": "runtime_default_packet_path",
            "status": "pass"
            if budget.get("mode") == "active"
            and budget.get("applied_to_output") is True
            and budget.get("answer_evidence_preserved") is True
            and budget.get("raw_text_in_budget_trace") is False
            and backend_degraded_visible
            else "fail",
            "packet_budget_mode": budget.get("mode"),
            "applied_to_output": budget.get("applied_to_output"),
            "answer_evidence_preserved": budget.get("answer_evidence_preserved"),
            "raw_text_in_budget_trace": budget.get("raw_text_in_budget_trace"),
            "missing_backend_degraded_visible": backend_degraded_visible,
            "hidden_fallback": budget.get("mode") != "active" or budget.get("applied_to_output") is not True,
            "protected_drop_attempts": 0 if budget.get("answer_evidence_preserved") is True else 1,
        }
    finally:
        store.close()


def _provider_default_case(root: Path) -> dict[str, Any]:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(root / "provider-default.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
        }
    )
    provider.initialize("session:m007:s03:provider", platform="test", user_id="m007-s03-provider")
    try:
        assert provider._store is not None
        provider._store.upsert_profile_item(
            stable_key="identity:m007:s03:provider-default",
            category="identity",
            content="The public provider active default runtime name is ProviderRuntimeActiveUser.",
            source="active-default.verifier",
            confidence=0.99,
            metadata={"principal_scope_key": provider._principal_scope_key, "truth_eligible": True},
        )
        provider.prefetch("What is the public provider active default runtime name?")
        budget = dict(provider._last_prefetch_policy.get("packet_budget") or {}) if provider._last_prefetch_policy else {}
        return {
            "case_id": "provider_default_prefetch_path",
            "status": "pass"
            if budget.get("mode") == "active"
            and budget.get("applied_to_output") is True
            and budget.get("raw_text_in_budget_trace") is False
            else "fail",
            "packet_budget_mode": budget.get("mode"),
            "applied_to_output": budget.get("applied_to_output"),
            "raw_text_in_budget_trace": budget.get("raw_text_in_budget_trace"),
            "hidden_fallback": budget.get("mode") != "active" or budget.get("applied_to_output") is not True,
            "protected_drop_attempts": 0 if budget.get("answer_evidence_preserved", True) is True else 1,
        }
    finally:
        provider.shutdown()


def verify_active_default(*, out_path: Path | None = None) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="brainstack-m007-s03-active-default-") as tmp:
        root = Path(tmp)
        cases = [*_matrix_cases(), _runtime_default_case(root), _provider_default_case(root)]
    active_default = DEFAULT_PACKET_BUDGET_MODE == "active" and resolve_packet_budget_mode(None) == "active"
    protected_truth_drop_attempts = sum(int(case.get("protected_drop_attempts") or 0) for case in cases)
    hidden_fallback_count = sum(1 for case in cases if case.get("hidden_fallback") is True)
    raw_text_trace_count = sum(1 for case in cases if case.get("raw_text_in_budget_trace") is True)
    failing_cases = [str(case.get("case_id")) for case in cases if case.get("status") != "pass"]
    status = "pass" if active_default and not failing_cases and protected_truth_drop_attempts == 0 and hidden_fallback_count == 0 else "fail"
    report = {
        "schema": SCHEMA,
        "status": status,
        "public_safe": True,
        "active_default": active_default,
        "default_mode_constant": DEFAULT_PACKET_BUDGET_MODE,
        "resolved_default_mode": resolve_packet_budget_mode(None),
        "default_off_detected": resolve_packet_budget_mode(None) == "off",
        "shadow_only_detected": resolve_packet_budget_mode(None) == "shadow",
        "hidden_fallback_count": hidden_fallback_count,
        "protected_truth_drop_attempts": protected_truth_drop_attempts,
        "raw_text_trace_count": raw_text_trace_count,
        "case_count": len(cases),
        "failing_cases": failing_cases,
        "cases": cases,
    }
    rendered = json.dumps(report, sort_keys=True)
    if "private-active-default-proof-text-must-not-leak" in rendered:
        report["public_safe"] = False
        report["status"] = "fail"
        report["failing_cases"] = [*failing_cases, "public_safety_leak"]
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify active packet budget default path.")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = verify_active_default(out_path=args.out)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("status") == "pass" and report.get("public_safe") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
