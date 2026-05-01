#!/usr/bin/env python3
"""Run exponentially hardening adversarial Tier2 decision scenarios.

Each round has 200 deterministic cases. Later rounds combine more languages,
domains, conflicting context, malformed shapes, authority attacks, and lifecycle
pressure. Failures are meant to drive fixes; the soak is not a substitute for
the total decision-machine proof.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.tier2_decision_core import (  # noqa: E402
    build_tier2_decision_plan,
    semantic_conformance_issues,
    validate_tier2_decision_plan,
)

SCHEMA = "brainstack.phase249.adversarial_soak.v1"
LANGUAGES = ("hu", "en", "de", "zh", "es", "fr", "ja", "ar")
DOMAINS = (
    "personal_style",
    "project_truth",
    "repo_reference",
    "medical_note",
    "finance_note",
    "legal_note",
    "discord_ops",
    "telegram_ops",
    "docker_runtime",
    "provider_auth",
    "graph_conflict",
    "continuity_task",
    "identity_collision",
    "quoted_claim",
    "tool_output",
    "migration",
)
SPEAKERS = ("user", "assistant", "quoted_assistant", "tool", "runtime", "operator", "unknown")
ACTIONS = ("create", "retain", "update", "correction", "delete", "invalidate", "expire", "merge_alias")
TARGET_KINDS = (
    "user_fact",
    "style_rule",
    "project_fact",
    "reference",
    "task_memory",
    "operating_memory",
    "graph_relation",
    "temporal_event",
    "support_context",
    "unknown_kind",
)


def _hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _scope(principal: str, workspace: str = "workspace-a") -> dict[str, str]:
    return {
        "tenant_id": "local",
        "principal_scope_key": principal,
        "workspace_scope_key": workspace,
        "session_id": "session-a",
        "project_id": "project-a",
    }


def _target_shape(target_kind: str, index: int, round_number: int) -> dict[str, Any]:
    value = f"sha256:{round_number}:{index}:{target_kind}"
    base: dict[str, Any] = {
        "target_kind": target_kind,
        "value_fingerprint": value,
        "source_span_ids": ["span-main"],
        "source_event_ids": ["event-main"],
    }
    if target_kind == "user_fact":
        base.update({"target_slot": "identity.preferred_address_name", "stable_key": "identity.preferred_address_name"})
    elif target_kind == "style_rule":
        base.update({"target_slot": "style.no_emoji", "stable_key": "style.no_emoji"})
    elif target_kind == "project_fact":
        base.update({"target_slot": "project.creator", "stable_key": "project.creator"})
    elif target_kind == "reference":
        base.update({"target_slot": "reference.repo", "stable_key": "reference.repo"})
    elif target_kind == "task_memory":
        base.update({"target_slot": "task.next", "stable_key": "task.next"})
    elif target_kind == "operating_memory":
        base.update({"target_slot": "operating.release_gate", "stable_key": "operating.release_gate"})
    elif target_kind == "graph_relation":
        predicate = "" if round_number >= 4 and index % 17 == 0 else "created_by"
        base.update(
            {
                "stable_key": "project.created_by",
                "relation_shape": {
                    "subject_ref": f"project:{index % 9}",
                    "predicate": predicate,
                    "object_ref": f"person:{index % 13}",
                    "direction": "forward",
                },
            }
        )
    elif target_kind == "temporal_event":
        if not (round_number >= 3 and index % 11 == 0):
            base.update({"target_slot": "timeline.event", "stable_key": "timeline.event"})
    elif target_kind == "support_context":
        base.update({"stable_key": "support.context"})
    return base


def _case(round_number: int, index: int) -> dict[str, Any]:
    language = LANGUAGES[(index + round_number) % len(LANGUAGES)]
    domain = DOMAINS[(index * (round_number + 1)) % len(DOMAINS)]
    speaker = SPEAKERS[(index + round_number * 3) % len(SPEAKERS)]
    action_name = ACTIONS[(index * 3 + round_number) % len(ACTIONS)]
    target_kind = TARGET_KINDS[(index * 5 + round_number) % len(TARGET_KINDS)]
    principal = "principal-b" if round_number >= 2 and index % 19 == 0 else "principal-a"
    workspace = "workspace-b" if round_number >= 5 and index % 23 == 0 else "workspace-a"
    source_event_missing = round_number >= 3 and index % 29 == 0
    source_span_missing = round_number >= 4 and index % 31 == 0
    malformed_actions = round_number >= 6 and index % 37 == 0
    action = _target_shape(target_kind, index, round_number)
    action["proposal_id"] = f"adv-{round_number}-{index}-{language}-{domain}"
    action["action"] = action_name
    if source_event_missing:
        action.pop("source_event_ids", None)
    spans: list[dict[str, Any]] = []
    if not source_span_missing:
        span = {
            "source_span_id": "span-main",
            "source_event_id": "event-main",
            "speaker": speaker,
            "assertion_speaker": speaker,
            "source_modality": "conversation",
            "scope": _scope(principal, workspace),
            "language": language,
            "domain": domain,
        }
        if source_event_missing:
            span.pop("source_event_id", None)
        spans.append(span)
    existing = []
    if round_number >= 2 and index % 7 == 0:
        existing.append(
            {
                "memory_ref": f"existing-{index}",
                "stable_key": str(action.get("stable_key") or action.get("target_slot") or action.get("target_kind")),
                "value_fingerprint": action.get("value_fingerprint") if index % 14 == 0 else "sha256:older-value",
            }
        )
    conflicts = []
    if round_number >= 2 and index % 13 == 0:
        conflicts.append({"stable_key": str(action.get("stable_key") or action.get("target_slot") or action.get("target_kind"))})
    actions: Any = [action]
    if malformed_actions:
        actions = [action, None, "bad-action", {"target_kind": ["bad", "shape"], "source_span_ids": [42, None]}]
    return {
        "case_id": f"r{round_number:02d}-{index:03d}",
        "language": language,
        "domain": domain,
        "packet": {
            "schema": "brainstack.tier2_decision_input.v1",
            "policy_version": f"phase249-adversarial-r{round_number}",
            "proposal_batch": {"actions": actions},
            "verified_source_spans": spans if not (round_number >= 7 and index % 41 == 0) else {"bad": "shape"},
            "scope": _scope("principal-a", "workspace-a"),
            "existing_memory_refs": existing if not (round_number >= 8 and index % 43 == 0) else "bad-existing",
            "graph_state_summary": {"unresolved_conflicts": conflicts},
            "budget_policy_summary": {"pressure": "high" if index % 3 == 0 else "normal"},
            "projection_contract_versions": {"graphiti": "min", "mempalace": "min"},
        },
    }


def _issues(packet: Mapping[str, Any]) -> list[str]:
    try:
        plan = build_tier2_decision_plan(packet)
    except Exception as exc:  # noqa: BLE001
        return [f"exception:{type(exc).__name__}:{exc}"]
    issues = validate_tier2_decision_plan(plan) + semantic_conformance_issues(plan)
    if build_tier2_decision_plan(packet) != plan:
        issues.append("nondeterministic_plan")
    for decision in plan.get("decisions", []):
        if not isinstance(decision, Mapping):
            issues.append("decision_not_mapping")
            continue
        authority = decision.get("authority") if isinstance(decision.get("authority"), Mapping) else {}
        source = decision.get("source") if isinstance(decision.get("source"), Mapping) else {}
        receipt = decision.get("receipt_requirement") if isinstance(decision.get("receipt_requirement"), Mapping) else {}
        decision_class = str(decision.get("decision_class") or "")
        durable = decision_class in {"durable_fact_candidate", "relation_candidate", "lifecycle_update_candidate"}
        speaker = str(source.get("assertion_speaker") or "")
        if durable:
            if authority.get("truth_eligible") is not True:
                issues.append("durable_without_truth_eligible")
            if receipt.get("required") is not True:
                issues.append("durable_without_receipt")
            if not source.get("source_span_ids") or not source.get("source_event_ids"):
                issues.append("durable_without_source_refs")
            if speaker in {"assistant", "quoted_assistant", "unknown"}:
                issues.append("durable_from_untrusted_speaker")
        if decision_class == "support_event" and authority.get("truth_eligible") is not False:
            issues.append("support_event_truth_eligible")
    return sorted(set(issues))


def _metamorphic_fuzz_cases(count: int) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for index in range(count):
        base = _case(10 + index % 30, index)
        packet = json.loads(json.dumps(base["packet"]))
        actions = packet.get("proposal_batch", {}).get("actions")
        if isinstance(actions, list) and actions:
            mutated_actions = []
            for repeat in range(1 + index % 4):
                for action in actions:
                    if isinstance(action, dict):
                        clone = dict(reversed(list(action.items())))
                        clone["proposal_id"] = f"{clone.get('proposal_id')}-m{repeat}-{index}"
                        if index % 5 == 0:
                            clone["unexpected_noise"] = {"depth": [index, {"repeat": repeat}]}
                        if index % 7 == 0:
                            clone["source_span_ids"] = list(reversed(clone.get("source_span_ids") or []))
                        mutated_actions.append(clone)
                    else:
                        mutated_actions.append(action)
            packet["proposal_batch"]["actions"] = mutated_actions
        if index % 6 == 0:
            packet["irrelevant_top_level_noise"] = {"x": [{"y": index}]}
        if index % 8 == 0:
            packet["verified_source_spans"] = list(reversed(packet.get("verified_source_spans") or []))
        cases.append({"case_id": f"meta-{index:04d}", "packet": packet})
    return cases


def run_soak(rounds: int = 10, cases_per_round: int = 200, metamorphic_cases: int = 1000) -> dict[str, Any]:
    round_reports = []
    failures = []
    for round_number in range(1, rounds + 1):
        round_failures = []
        fingerprints = set()
        for index in range(cases_per_round):
            case = _case(round_number, index)
            fingerprint = _hash(case["packet"])
            fingerprints.add(fingerprint)
            issues = _issues(case["packet"])
            if issues:
                item = {
                    "case_id": case["case_id"],
                    "round": round_number,
                    "language": case["language"],
                    "domain": case["domain"],
                    "packet_fingerprint": fingerprint,
                    "issues": issues,
                }
                round_failures.append(item)
                failures.append(item)
        round_reports.append(
            {
                "round": round_number,
                "case_count": cases_per_round,
                "unique_packet_fingerprints": len(fingerprints),
                "failure_count": len(round_failures),
                "complexity_level": round_number,
            }
        )
    metamorphic_failures = []
    for case in _metamorphic_fuzz_cases(metamorphic_cases):
        fingerprint = _hash(case["packet"])
        issues = _issues(case["packet"])
        if issues:
            item = {
                "case_id": case["case_id"],
                "packet_fingerprint": fingerprint,
                "issues": issues,
            }
            metamorphic_failures.append(item)
            failures.append(item)
    return {
        "schema": SCHEMA,
        "status": "pass" if not failures else "fail",
        "rounds": rounds,
        "cases_per_round": cases_per_round,
        "metamorphic_case_count": metamorphic_cases,
        "case_count": rounds * cases_per_round + metamorphic_cases,
        "failure_count": len(failures),
        "metamorphic_failure_count": len(metamorphic_failures),
        "round_reports": round_reports,
        "failures": failures[:80],
        "method": "exponentially_hardening_deterministic_adversarial_soak",
        "role": "bug discovery loop; failures require root-cause fixes and rerun",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=int, default=10)
    parser.add_argument("--cases-per-round", type=int, default=200)
    parser.add_argument("--metamorphic-cases", type=int, default=1000)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = run_soak(
        rounds=args.rounds,
        cases_per_round=args.cases_per_round,
        metamorphic_cases=args.metamorphic_cases,
    )
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n")
    print(text)
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
