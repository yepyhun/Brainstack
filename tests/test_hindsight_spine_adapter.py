from __future__ import annotations

from typing import Any, Mapping

from brainstack.hindsight_spine_adapter import (
    HINDSIGHT_SPINE_ADAPTER_VERSION,
    HindsightSpineAdapter,
    build_hindsight_source_batch,
    normalize_proposal_action_batch,
    proposal_action_batch_status,
)


class FakeHindsightClient:
    def propose(self, source_batch: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "status": "ok",
            "operation_id": "op_1",
            "donor_version": "fake-hindsight",
            "config_hash": "sha256:config",
            "actions": [
                {
                    "action": "create",
                    "target_kind": "user_fact",
                    "target_slot": "identity.preferred_address_name",
                    "stable_key": "identity:preferred_address_name",
                    "value_fingerprint": "sha256:value",
                    "confidence": 0.98,
                    "reason_code": "EXPLICIT_USER_FACT",
                    "source_span_ids": ["usrspan_1"],
                    "source_event_ids": ["event_1"],
                    "assertion_speaker": "user",
                }
            ],
        }


def test_hindsight_adapter_unconfigured_is_explicitly_unavailable() -> None:
    source_batch = build_hindsight_source_batch(
        session_id="session-a",
        scope={"principal_scope_key": "scope-a"},
        source_spans=[],
    )

    batch = HindsightSpineAdapter(client=None, donor_version="pinned-test").propose(source_batch)
    status = proposal_action_batch_status(batch)

    assert status["status"] == "unavailable"
    assert status["failure"]["reason_code"] == "HINDSIGHT_CLIENT_UNCONFIGURED"
    assert status["proposal_count"] == 0
    assert status["adapter_version"] == HINDSIGHT_SPINE_ADAPTER_VERSION


def test_hindsight_adapter_normalizes_thin_proposal_action_batch() -> None:
    source_batch = build_hindsight_source_batch(
        session_id="session-a",
        scope={"principal_scope_key": "scope-a"},
        source_spans=[{"source_span_id": "usrspan_1", "source_event_id": "event_1"}],
    )

    batch = HindsightSpineAdapter(client=FakeHindsightClient()).propose(source_batch)
    status = proposal_action_batch_status(batch)

    assert batch["schema"] == "brainstack.hindsight_proposal_action_batch.v1"
    assert batch["status"] == "ok"
    assert batch["actions"][0]["proposal_id"].startswith("hprop_")
    assert batch["actions"][0]["action"] == "create"
    assert batch["actions"][0]["target_kind"] == "user_fact"
    assert batch["actions"][0]["source_span_ids"] == ["usrspan_1"]
    assert batch["critical_counters"]["missing_source_refs"] == 0
    assert status["proposal_count"] == 1


def test_hindsight_adapter_marks_unsafe_actions_degraded() -> None:
    batch = normalize_proposal_action_batch(
        {
            "status": "ok",
            "operation_id": "op_2",
            "actions": [
                {
                    "action": "create",
                    "target_kind": "user_fact",
                    "target_slot": "identity.preferred_address_name",
                    "assertion_speaker": "assistant",
                },
                {
                    "action": "invent",
                    "target_kind": "unknown",
                    "source_span_ids": ["span_1"],
                },
            ],
        }
    )

    assert batch["status"] == "degraded"
    assert batch["critical_counters"]["assistant_authored_actions"] == 0
    assert batch["critical_counters"]["missing_source_refs"] == 0
    assert batch["critical_counters"]["unsupported_actions"] == 1
    assert batch["failure"]["reason_code"] == "HINDSIGHT_ASSISTANT_AUTHORED_ACTION_DROPPED"
    assert batch["failure"]["dropped_assistant_authored_actions"] == 1
    assert len(batch["actions"]) == 1
    assert batch["actions"][0]["action"] == "failed_batch"
    assert batch["actions"][0]["target_kind"] == "support_context"


def test_hindsight_adapter_preserves_lifecycle_actions_for_decision_core() -> None:
    batch = normalize_proposal_action_batch(
        {
            "status": "ok",
            "operation_id": "op_lifecycle",
            "actions": [
                {
                    "action": "correction",
                    "target_kind": "user_fact",
                    "target_slot": "identity.preferred_address_name",
                    "value_fingerprint": "sha256:corrected",
                    "source_span_ids": ["span_1"],
                    "source_event_ids": ["event_1"],
                    "assertion_speaker": "user",
                },
                {
                    "action": "supersede",
                    "target_kind": "project_fact",
                    "target_slot": "project.creator",
                    "value_fingerprint": "sha256:superseded",
                    "source_span_ids": ["span_1"],
                    "source_event_ids": ["event_1"],
                    "assertion_speaker": "user",
                },
            ],
        }
    )

    assert batch["status"] == "ok"
    assert batch["critical_counters"]["unsupported_actions"] == 0
    assert [action["action"] for action in batch["actions"]] == ["correction", "supersede"]


def test_hindsight_adapter_preserves_operating_memory_targets_for_decision_core() -> None:
    batch = normalize_proposal_action_batch(
        {
            "status": "ok",
            "operation_id": "op_operating_memory",
            "actions": [
                {
                    "action": "correction",
                    "target_kind": "operating_memory",
                    "target_slot": "operating.brainstack_diagnostics_output_shape",
                    "stable_key": "operating.brainstack_diagnostics_output_shape",
                    "value_fingerprint": "sha256:compact-diagnostics",
                    "source_span_ids": ["span_runtime"],
                    "source_event_ids": ["event_runtime"],
                    "assertion_speaker": "runtime",
                }
            ],
        }
    )

    assert batch["status"] == "ok"
    assert batch["critical_counters"]["unsupported_actions"] == 0
    assert batch["actions"][0]["target_kind"] == "operating_memory"
