"""Proof-carrying provider request/response contracts for Gateway turns."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence

from gateway.context_budget import redact_model_facing_text


SCHEMA_VERSION = "hermes.proof_carrying_request.v1"

FAILURE_TAXONOMY = (
    "CONTRACT_COMPILE_FAILURE",
    "BUDGET_FAILURE",
    "PROFILE_SNAPSHOT_DRIFT",
    "PROVIDER_LATENCY_FAILURE",
    "FORBIDDEN_CLAIM",
    "WRONG_TOOL_CALL",
    "ILLEGAL_TOOL_LOAD",
    "TOOL_CLEANUP_FAILURE",
    "SIDE_EFFECT_APPROVAL_BYPASS",
    "STALE_RESPONSE",
    "DUPLICATE_EVENT",
    "UNEXPECTED_SIDE_EFFECT",
    "MEMORY_ANSWERABILITY_MISMATCH",
)


@dataclass(frozen=True)
class ExternalActionAudit:
    schema: str
    memory_mutations: tuple[str, ...]
    file_mutations: tuple[str, ...]
    external_actions: tuple[str, ...]
    side_effect_tool_calls: tuple[str, ...]
    unexpected_side_effects: bool
    read_only_clean: bool

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("memory_mutations", "file_mutations", "external_actions", "side_effect_tool_calls"):
            data[key] = list(data[key])
        return data


@dataclass(frozen=True)
class ProviderRequestContract:
    schema: str
    request_contract_id: str
    request_hash: str
    redacted_prompt_snapshot_ref: str
    turn_contract_id: str
    profile_snapshot_id: str
    static_prefix_hash: str
    brainstack_packet_id: str
    answerability_state: str
    allowed_claim_strength: str
    tool_profile: str
    model_profile: str
    slo_profile: str
    context_budget_id: str
    forbidden_claims: tuple[str, ...]
    answer_evidence_ids: tuple[str, ...]
    regression_family: str
    profile_tool_names: tuple[str, ...]
    tool_loader_available: bool
    allowed_tool_enum_hash: str
    allowed_tool_enum: tuple[str, ...]
    loaded_tool_names: tuple[str, ...]
    pinned_tool_names: tuple[str, ...]
    no_hidden_full_tool_fallback: bool
    external_action_audit: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in (
            "forbidden_claims",
            "answer_evidence_ids",
            "profile_tool_names",
            "allowed_tool_enum",
            "loaded_tool_names",
            "pinned_tool_names",
        ):
            data[key] = list(data[key])
        return data


@dataclass(frozen=True)
class ProviderResponseContract:
    schema: str
    request_contract_id: str
    contract_satisfied: bool
    latency_slo_satisfied: bool
    forbidden_claims_detected: tuple[str, ...]
    answer_evidence_used: tuple[str, ...]
    tool_calls_made: tuple[str, ...]
    degradation_policy_used: str
    tool_call_violations: tuple[str, ...]
    side_effect_violations: tuple[str, ...]
    failure_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in (
            "forbidden_claims_detected",
            "answer_evidence_used",
            "tool_calls_made",
            "tool_call_violations",
            "side_effect_violations",
            "failure_codes",
        ):
            data[key] = list(data[key])
        return data


def build_external_action_audit(
    *,
    memory_mutations: Sequence[str] = (),
    file_mutations: Sequence[str] = (),
    external_actions: Sequence[str] = (),
    side_effect_tool_calls: Sequence[str] = (),
) -> ExternalActionAudit:
    unexpected = bool(memory_mutations or file_mutations or external_actions or side_effect_tool_calls)
    return ExternalActionAudit(
        schema=SCHEMA_VERSION,
        memory_mutations=tuple(memory_mutations),
        file_mutations=tuple(file_mutations),
        external_actions=tuple(external_actions),
        side_effect_tool_calls=tuple(side_effect_tool_calls),
        unexpected_side_effects=unexpected,
        read_only_clean=not unexpected,
    )


def build_provider_request_contract(
    *,
    turn_contract: Mapping[str, Any] | Any,
    profile_snapshot: Mapping[str, Any],
    context_budget: Mapping[str, Any],
    answerability: Mapping[str, Any],
    answer_evidence: Sequence[Mapping[str, Any]] = (),
    prompt_snapshot: str = "",
    brainstack_packet_id: str | None = None,
    regression_family: str,
    tool_loader: Mapping[str, Any] | Any | None = None,
    loaded_tool_names: Sequence[str] = (),
    pinned_tool_names: Sequence[str] = (),
    external_action_audit: ExternalActionAudit | Mapping[str, Any] | None = None,
) -> ProviderRequestContract:
    contract = _as_mapping(turn_contract)
    loader = _as_mapping(tool_loader) if tool_loader is not None else {}
    audit = _audit_dict(external_action_audit)
    redacted_prompt = redact_model_facing_text(prompt_snapshot)
    redacted_prompt_ref = f"redacted_prompt_snapshot:{_hash_text(redacted_prompt)}"
    profile_tool_names = _sequence(profile_snapshot.get("tool_names", ()))
    forbidden = tuple(str(item) for item in contract.get("forbidden_claims", ()) or ())
    evidence_ids = _evidence_ids(answerability, answer_evidence)
    packet_id = brainstack_packet_id or f"brainstack_packet:{_hash_json({'a': answerability, 'e': evidence_ids})}"
    profile_snapshot_id = _profile_snapshot_id(profile_snapshot)
    context_budget_id = str(
        context_budget.get("context_budget_id")
        or context_budget.get("budget_id")
        or context_budget.get("prompt_assembly_hash")
        or f"context_budget:{_hash_json(context_budget)}"
    )
    static_prefix_hash = str(profile_snapshot.get("static_prefix_hash") or _hash_text(""))
    request_hash = _hash_json(
        {
            "turn_contract_id": contract.get("turn_contract_id"),
            "profile_snapshot_id": profile_snapshot_id,
            "static_prefix_hash": static_prefix_hash,
            "brainstack_packet_id": packet_id,
            "answerability_state": answerability.get("state"),
            "allowed_claim_strength": answerability.get("max_claim_strength"),
            "tool_profile": contract.get("allowed_tool_profile"),
            "model_profile": contract.get("allowed_model_profile"),
            "slo_profile": contract.get("latency_slo"),
            "context_budget_id": context_budget_id,
            "forbidden_claims": forbidden,
            "answer_evidence_ids": evidence_ids,
            "regression_family": regression_family,
            "tool_loader": loader,
            "redacted_prompt_ref": redacted_prompt_ref,
        }
    )
    return ProviderRequestContract(
        schema=SCHEMA_VERSION,
        request_contract_id=f"provider_request:{request_hash[:16]}",
        request_hash=request_hash,
        redacted_prompt_snapshot_ref=redacted_prompt_ref,
        turn_contract_id=str(contract.get("turn_contract_id", "")),
        profile_snapshot_id=profile_snapshot_id,
        static_prefix_hash=static_prefix_hash,
        brainstack_packet_id=packet_id,
        answerability_state=str(answerability.get("state", "unknown")),
        allowed_claim_strength=str(answerability.get("max_claim_strength", "none")),
        tool_profile=str(contract.get("allowed_tool_profile", "unknown")),
        model_profile=str(contract.get("allowed_model_profile", "unknown")),
        slo_profile=str(contract.get("latency_slo", "unknown")),
        context_budget_id=context_budget_id,
        forbidden_claims=forbidden,
        answer_evidence_ids=evidence_ids,
        regression_family=regression_family,
        profile_tool_names=profile_tool_names,
        tool_loader_available=bool(loader.get("loader_available", False)),
        allowed_tool_enum_hash=str(loader.get("allowed_tool_enum_hash", "")),
        allowed_tool_enum=_sequence(loader.get("allowed_tool_enum", ())),
        loaded_tool_names=tuple(str(name) for name in loaded_tool_names),
        pinned_tool_names=tuple(str(name) for name in pinned_tool_names),
        no_hidden_full_tool_fallback=_no_hidden_full_tool_fallback(contract, profile_tool_names),
        external_action_audit=audit,
    )


def build_provider_response_contract(
    request_contract: ProviderRequestContract | Mapping[str, Any],
    *,
    claims_made: Sequence[str] = (),
    answer_evidence_used: Sequence[str] = (),
    tool_calls_made: Sequence[str] = (),
    latency_slo_satisfied: bool,
    degradation_policy_used: str,
    external_action_audit: ExternalActionAudit | Mapping[str, Any] | None = None,
) -> ProviderResponseContract:
    request = _as_mapping(request_contract)
    forbidden_claims = set(str(item) for item in request.get("forbidden_claims", ()) or ())
    claim_set = set(str(item) for item in claims_made)
    forbidden_detected = tuple(sorted(forbidden_claims & claim_set))
    allowed_tools = set(str(item) for item in request.get("profile_tool_names", ()) or ())
    allowed_tools.update(str(item) for item in request.get("allowed_tool_enum", ()) or ())
    tool_calls = tuple(str(name) for name in tool_calls_made)
    tool_violations = tuple(sorted(name for name in tool_calls if name not in allowed_tools))
    audit = _audit_dict(external_action_audit) if external_action_audit is not None else request.get("external_action_audit", {})
    side_effect_violations = tuple(str(name) for name in audit.get("side_effect_tool_calls", ()) or ())
    failure_codes = _failure_codes(
        latency_slo_satisfied=latency_slo_satisfied,
        forbidden_detected=forbidden_detected,
        tool_violations=tool_violations,
        audit=audit,
        no_hidden_full_tool_fallback=bool(request.get("no_hidden_full_tool_fallback", False)),
    )
    return ProviderResponseContract(
        schema=SCHEMA_VERSION,
        request_contract_id=str(request.get("request_contract_id", "")),
        contract_satisfied=not failure_codes,
        latency_slo_satisfied=latency_slo_satisfied,
        forbidden_claims_detected=forbidden_detected,
        answer_evidence_used=tuple(str(item) for item in answer_evidence_used),
        tool_calls_made=tool_calls,
        degradation_policy_used=degradation_policy_used,
        tool_call_violations=tool_violations,
        side_effect_violations=side_effect_violations,
        failure_codes=failure_codes,
    )


def build_regression_result(name: str, *, passed: bool, family: str, details: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "family": family,
        "passed": passed,
        "details": dict(details),
    }


def _failure_codes(
    *,
    latency_slo_satisfied: bool,
    forbidden_detected: Sequence[str],
    tool_violations: Sequence[str],
    audit: Mapping[str, Any],
    no_hidden_full_tool_fallback: bool,
) -> tuple[str, ...]:
    codes: list[str] = []
    if not latency_slo_satisfied:
        codes.append("PROVIDER_LATENCY_FAILURE")
    if forbidden_detected:
        codes.append("FORBIDDEN_CLAIM")
    if tool_violations:
        codes.append("WRONG_TOOL_CALL")
    if bool(audit.get("unexpected_side_effects", False)):
        codes.append("UNEXPECTED_SIDE_EFFECT")
    if not no_hidden_full_tool_fallback:
        codes.append("PROFILE_SNAPSHOT_DRIFT")
    return tuple(codes)


def _no_hidden_full_tool_fallback(contract: Mapping[str, Any], profile_tool_names: Sequence[str]) -> bool:
    profile = str(contract.get("allowed_tool_profile", ""))
    if profile in {"conversation_direct", "none"}:
        return len(profile_tool_names) == 0
    if profile in {"conversation_tools", "conversation"}:
        heavy_names = {"terminal", "process", "execute_code", "write_file", "patch", "web_search", "browser", "deploy"}
        return not any(name in heavy_names for name in profile_tool_names)
    return True


def _audit_dict(value: ExternalActionAudit | Mapping[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return build_external_action_audit().to_dict()
    if isinstance(value, ExternalActionAudit):
        return value.to_dict()
    return dict(value)


def _profile_snapshot_id(profile_snapshot: Mapping[str, Any]) -> str:
    name = str(profile_snapshot.get("profile_name", "unknown"))
    version = str(profile_snapshot.get("profile_version", "unknown"))
    schema_hash = str(profile_snapshot.get("tool_schema_hash", ""))
    return f"{name}:{version}:{schema_hash[:16]}"


def _evidence_ids(answerability: Mapping[str, Any], answer_evidence: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    values: list[str] = []
    raw = answerability.get("answer_evidence_ids") or answerability.get("evidence_ids") or ()
    if isinstance(raw, str):
        raw = (raw,)
    for item in raw:
        _append_unique(values, str(item))
    for evidence in answer_evidence:
        for key in ("evidence_id", "id", "candidate_id", "stable_key"):
            value = evidence.get(key)
            if value:
                _append_unique(values, str(value))
                break
    return tuple(values)


def _sequence(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value)


def _as_mapping(value: Mapping[str, Any] | Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if hasattr(value, "to_dict"):
        mapped = value.to_dict()
        if isinstance(mapped, Mapping):
            return mapped
    return {}


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


def _hash_text(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _hash_json(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
