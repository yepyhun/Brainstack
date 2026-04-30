from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Callable, Mapping, Protocol

HINDSIGHT_SPINE_ADAPTER_VERSION = "brainstack.hindsight_spine_adapter.v1"
PROPOSAL_ACTION_BATCH_SCHEMA = "brainstack.hindsight_proposal_action_batch.v1"
SUPPORTED_ACTIONS = {"create", "update", "delete_or_supersede", "ignore", "failed_batch"}
SUPPORTED_TARGET_KINDS = {
    "user_fact",
    "project_fact",
    "style_rule",
    "graph_relation",
    "temporal_event",
    "support_context",
}


class HindsightProposalClient(Protocol):
    def propose(self, source_batch: Mapping[str, Any]) -> Mapping[str, Any]:
        """Return a Hindsight-compatible proposal action batch."""


def _text(value: Any) -> str:
    return str(value or "").strip()


def _hash_json(value: Any, *, length: int = 32) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def build_hindsight_source_batch(
    *,
    session_id: str,
    scope: Mapping[str, Any],
    source_spans: list[Mapping[str, Any]],
    existing_memory_refs: list[Mapping[str, Any]] | None = None,
    budget: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema": "brainstack.hindsight_source_batch.v1",
        "session_id": _text(session_id),
        "scope": dict(scope),
        "source_spans": [dict(span) for span in source_spans],
        "existing_memory_refs": [dict(ref) for ref in (existing_memory_refs or [])],
        "budget": {
            "max_source_spans": int(_mapping(budget).get("max_source_spans") or 8),
            "max_output_proposals": int(_mapping(budget).get("max_output_proposals") or 8),
            "max_output_tokens": int(_mapping(budget).get("max_output_tokens") or 900),
            "timeout_seconds": float(_mapping(budget).get("timeout_seconds") or 15),
        },
    }


def unavailable_proposal_action_batch(*, reason: str, donor_version: str = "") -> dict[str, Any]:
    return {
        "schema": PROPOSAL_ACTION_BATCH_SCHEMA,
        "status": "unavailable",
        "operation_id": "",
        "donor": "hindsight",
        "donor_version": _text(donor_version),
        "adapter_version": HINDSIGHT_SPINE_ADAPTER_VERSION,
        "config_hash": "",
        "actions": [],
        "failure": {"reason_code": _text(reason) or "HINDSIGHT_UNAVAILABLE"},
        "critical_counters": {
            "assistant_authored_actions": 0,
            "missing_source_refs": 0,
            "unsupported_actions": 0,
        },
    }


def normalize_proposal_action_batch(raw: Mapping[str, Any]) -> dict[str, Any]:
    actions: list[dict[str, Any]] = []
    dropped_assistant_authored_actions = 0
    counters = {
        "assistant_authored_actions": 0,
        "missing_source_refs": 0,
        "unsupported_actions": 0,
    }
    for index, raw_action in enumerate(_list(raw.get("actions"))):
        if not isinstance(raw_action, Mapping):
            counters["unsupported_actions"] += 1
            continue
        action = _text(raw_action.get("action"))
        target_kind = _text(raw_action.get("target_kind"))
        source_span_ids = [_text(item) for item in _list(raw_action.get("source_span_ids")) if _text(item)]
        assertion_speaker = _text(raw_action.get("assertion_speaker") or raw_action.get("source_role")).lower()
        if assertion_speaker in {"assistant", "quoted_assistant"}:
            dropped_assistant_authored_actions += 1
            continue
        if action not in SUPPORTED_ACTIONS or target_kind not in SUPPORTED_TARGET_KINDS:
            counters["unsupported_actions"] += 1
        if not source_span_ids:
            counters["missing_source_refs"] += 1
        proposal_seed = {
            "operation_id": raw.get("operation_id"),
            "index": index,
            "action": action,
            "target_kind": target_kind,
            "target_slot": raw_action.get("target_slot"),
            "value_fingerprint": raw_action.get("value_fingerprint") or raw_action.get("normalized_value_hash"),
            "source_span_ids": source_span_ids,
        }
        actions.append(
            {
                "proposal_id": _text(raw_action.get("proposal_id")) or "hprop_" + _hash_json(proposal_seed, length=24).removeprefix("sha256:"),
                "action": action if action in SUPPORTED_ACTIONS else "failed_batch",
                "target_kind": target_kind if target_kind in SUPPORTED_TARGET_KINDS else "support_context",
                "target_slot": _text(raw_action.get("target_slot")),
                "stable_key": _text(raw_action.get("stable_key")),
                "value_fingerprint": _text(raw_action.get("value_fingerprint") or raw_action.get("normalized_value_hash")),
                "confidence": float(raw_action.get("confidence") or 0.0),
                "reason_code": _text(raw_action.get("reason_code")) or "HINDSIGHT_PROPOSAL",
                "source_span_ids": source_span_ids,
                "source_event_ids": [_text(item) for item in _list(raw_action.get("source_event_ids")) if _text(item)],
                "related_memory_refs": [dict(item) for item in _list(raw_action.get("related_memory_refs")) if isinstance(item, Mapping)],
                "assertion_speaker": assertion_speaker or "unknown",
                "support_visibility": _text(raw_action.get("support_visibility")) or "inspect_only",
            }
        )
    status = _text(raw.get("status")) or ("ok" if actions else "empty")
    failure = dict(_mapping(raw.get("failure")))
    if dropped_assistant_authored_actions:
        status = "degraded"
        failure.setdefault("reason_code", "HINDSIGHT_ASSISTANT_AUTHORED_ACTION_DROPPED")
        failure["dropped_assistant_authored_actions"] = dropped_assistant_authored_actions
    if any(counters.values()) and status == "ok":
        status = "degraded"
    return {
        "schema": PROPOSAL_ACTION_BATCH_SCHEMA,
        "status": status,
        "operation_id": _text(raw.get("operation_id")),
        "donor": "hindsight",
        "donor_version": _text(raw.get("donor_version")),
        "adapter_version": HINDSIGHT_SPINE_ADAPTER_VERSION,
        "config_hash": _text(raw.get("config_hash")),
        "actions": actions,
        "failure": failure,
        "critical_counters": counters,
    }


@dataclass(frozen=True)
class HindsightSpineAdapter:
    client: HindsightProposalClient | None = None
    config_hash_builder: Callable[[Mapping[str, Any]], str] | None = None
    donor_version: str = ""

    def propose(self, source_batch: Mapping[str, Any]) -> dict[str, Any]:
        if self.client is None:
            return unavailable_proposal_action_batch(
                reason="HINDSIGHT_CLIENT_UNCONFIGURED",
                donor_version=self.donor_version,
            )
        try:
            raw = self.client.propose(source_batch)
        except Exception as exc:
            return unavailable_proposal_action_batch(
                reason=f"HINDSIGHT_CLIENT_FAILED:{type(exc).__name__}",
                donor_version=self.donor_version,
            )
        normalized = normalize_proposal_action_batch(raw)
        if not normalized.get("config_hash") and self.config_hash_builder is not None:
            normalized["config_hash"] = self.config_hash_builder(source_batch)
        return normalized


def proposal_action_batch_status(batch: Mapping[str, Any]) -> dict[str, Any]:
    counters = dict(_mapping(batch.get("critical_counters")))
    return {
        "schema": "brainstack.hindsight_adapter_status.v1",
        "status": _text(batch.get("status")) or "unknown",
        "donor": _text(batch.get("donor")) or "hindsight",
        "donor_version": _text(batch.get("donor_version")),
        "adapter_version": _text(batch.get("adapter_version")) or HINDSIGHT_SPINE_ADAPTER_VERSION,
        "proposal_count": len(_list(batch.get("actions"))),
        "failure": dict(_mapping(batch.get("failure"))),
        "critical_counters": {
            "assistant_authored_actions": int(counters.get("assistant_authored_actions") or 0),
            "missing_source_refs": int(counters.get("missing_source_refs") or 0),
            "unsupported_actions": int(counters.get("unsupported_actions") or 0),
        },
    }
