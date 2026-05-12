#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack import BrainstackMemoryProvider  # noqa: E402
from brainstack.canonical_memory_event import validate_canonical_memory_events  # noqa: E402
from brainstack.hindsight_public_api_bridge import HindsightPublicApiBridge  # noqa: E402
from brainstack.hindsight_spine_adapter import (  # noqa: E402
    HindsightSpineAdapter,
    build_hindsight_source_batch,
    normalize_proposal_action_batch,
    proposal_action_batch_status,
)

PHASE_DIR = ROOT / ".planning/phases/239-tier2-proof-gauntlet"
PUBLIC_SENTINEL = "PUBLIC_SAFE_SENTINEL_SHOULD_NOT_APPEAR"
DONOR_FETCH_ATTEMPTS = 3


def _default_donor_dir() -> Path:
    configured = os.environ.get("BRAINSTACK_HINDSIGHT_DONOR_DIR")
    if configured:
        return Path(configured).expanduser()
    return ROOT.parents[1] / "donor-first-review" / "hindsight"


def _json_dump(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def _fetch_donor_with_retry(donor_dir: Path) -> tuple[subprocess.CompletedProcess[str], list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    last: subprocess.CompletedProcess[str] | None = None
    for attempt in range(1, DONOR_FETCH_ATTEMPTS + 1):
        fetch = subprocess.run(
            ["git", "fetch", "origin", "--prune", "--quiet"],
            cwd=donor_dir,
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
        )
        attempts.append(
            {
                "attempt": attempt,
                "returncode": fetch.returncode,
                "stderr_tail": fetch.stderr[-240:],
            }
        )
        last = fetch
        if fetch.returncode == 0:
            break
    assert last is not None
    return last, attempts


def _provider(tmp_path: Path, extractor: Callable[..., Mapping[str, Any]], *, session_id: str = "tier2-sota") -> BrainstackMemoryProvider:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
            "tier2_transcript_limit": 8,
            "tier2_timeout_seconds": 2,
            "_tier2_extractor": extractor,
        }
    )
    provider.initialize(
        session_id,
        platform="test",
        user_id="user",
        agent_identity="agent-sota",
        agent_workspace="workspace",
    )
    assert provider._store is not None
    return provider


def _add_turn(provider: BrainstackMemoryProvider, *, session_id: str, content: str) -> None:
    assert provider._store is not None
    provider._store.add_transcript_entry(
        session_id=session_id,
        turn_number=1,
        kind="turn",
        content=content,
        source="public-gauntlet",
        metadata=provider._scoped_metadata(),
    )


def _run_case(
    root: Path,
    name: str,
    extractor: Callable[..., Mapping[str, Any]],
    *,
    transcript: str,
) -> dict[str, Any]:
    session_id = f"tier2-sota-{name}"
    provider = _provider(root / name, extractor, session_id=session_id)
    try:
        _add_turn(provider, session_id=session_id, content=transcript)
        result = provider._run_tier2_batch(session_id=session_id, turn_number=1, trigger_reason="idle_window")
        assert provider._store is not None
        receipts = provider._store.list_admission_receipts(limit=100)
        events = provider._store.list_canonical_memory_events(limit=100)
        event_payloads = [row["event"] for row in events]
        validation = validate_canonical_memory_events(event_payloads)
        return {
            "name": name,
            "result": result,
            "receipt_count": len(receipts),
            "canonical_event_count": len(events),
            "events": event_payloads,
            "validation_passed": validation.passed,
            "validation_issues": list(validation.issues),
            "raw_leak_in_plan": PUBLIC_SENTINEL in json.dumps(result.get("consolidation_plan") or {}, ensure_ascii=True),
            "raw_leak_in_events": PUBLIC_SENTINEL in json.dumps(event_payloads, ensure_ascii=True),
        }
    finally:
        provider.shutdown()


def _run_memory_cases() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="brainstack-tier2-gauntlet-") as temp:
        root = Path(temp)

        def verified_profile(*args: Any, **kwargs: Any) -> Mapping[str, Any]:
            return {
                "profile_items": [
                    {
                        "category": "identity",
                        "slot": "identity:preferred_address_name",
                        "content": PUBLIC_SENTINEL,
                        "source_quote": f"My preferred name is {PUBLIC_SENTINEL}.",
                        "confidence": 0.98,
                        "metadata": {"source_role": "user"},
                    }
                ],
                "_meta": {"json_parse_status": "ok", "parse_context": "gauntlet"},
            }

        def assistant_claim(*args: Any, **kwargs: Any) -> Mapping[str, Any]:
            return {
                "profile_items": [
                    {
                        "category": "identity",
                        "slot": "identity:preferred_address_name",
                        "content": "Assistant Claim",
                        "source_quote": "Assistant invented this.",
                        "confidence": 0.99,
                        "metadata": {"source_role": "assistant"},
                    }
                ],
                "_meta": {"json_parse_status": "ok", "parse_context": "gauntlet"},
            }

        def unverified_user_claim(*args: Any, **kwargs: Any) -> Mapping[str, Any]:
            return {
                "profile_items": [
                    {
                        "category": "identity",
                        "slot": "identity:preferred_address_name",
                        "content": "Unverified",
                        "confidence": 0.90,
                        "metadata": {"source_role": "user"},
                    }
                ],
                "_meta": {"json_parse_status": "ok", "parse_context": "gauntlet"},
            }

        def graph_relation(*args: Any, **kwargs: Any) -> Mapping[str, Any]:
            return {
                "relations": [
                    {
                        "subject": "Project Alpha",
                        "predicate": "created_by",
                        "object": "Alex",
                        "source_quote": "Project Alpha was created by Alex.",
                        "confidence": 0.97,
                        "metadata": {"source_role": "user"},
                    }
                ],
                "_meta": {"json_parse_status": "ok", "parse_context": "gauntlet"},
            }

        def bloat(*args: Any, **kwargs: Any) -> Mapping[str, Any]:
            return {
                "profile_items": [
                    {
                        "category": "identity",
                        "slot": "identity:name",
                        "content": f"Noise {index}",
                        "source_quote": f"Noise {index}",
                        "confidence": 0.95,
                        "metadata": {"source_role": "user"},
                    }
                    for index in range(40)
                ],
                "_meta": {"json_parse_status": "ok", "parse_context": "gauntlet"},
            }

        verified = _run_case(
            root,
            "verified_profile",
            verified_profile,
            transcript=f"User: My preferred name is {PUBLIC_SENTINEL}.",
        )
        duplicate = _run_case(
            root,
            "verified_profile_duplicate",
            verified_profile,
            transcript=f"User: My preferred name is {PUBLIC_SENTINEL}.",
        )
        assistant = _run_case(root, "assistant_claim", assistant_claim, transcript="Assistant: Assistant invented this.")
        unverified = _run_case(root, "unverified_user_claim", unverified_user_claim, transcript="User: My preferred name is Different.")
        graph = _run_case(root, "graph_relation", graph_relation, transcript="User: Project Alpha was created by Alex.")
        bloat_case = _run_case(root, "bloat", bloat, transcript="User: Noise 0")
    all_events = verified["events"] + assistant["events"] + unverified["events"] + graph["events"] + bloat_case["events"]
    rebuild_snapshot = _projection_snapshot(all_events)
    rebuilt_snapshot = _projection_snapshot(json.loads(json.dumps(all_events, sort_keys=True)))
    return {
        "verified_profile": verified,
        "verified_profile_duplicate": duplicate,
        "assistant_claim": assistant,
        "unverified_user_claim": unverified,
        "graph_relation": graph,
        "bloat": bloat_case,
        "projection_rebuild": {
            "status": "pass" if rebuild_snapshot == rebuilt_snapshot else "fail",
            "snapshot": rebuild_snapshot,
            "rebuilt_snapshot": rebuilt_snapshot,
        },
    }


def _projection_snapshot(events: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    snapshot: list[dict[str, Any]] = []
    for event in events:
        event_group = event.get("event") if isinstance(event.get("event"), Mapping) else {}
        claim = event.get("claim") if isinstance(event.get("claim"), Mapping) else {}
        authority = event.get("authority") if isinstance(event.get("authority"), Mapping) else {}
        projection = event.get("projection") if isinstance(event.get("projection"), Mapping) else {}
        snapshot.append(
            {
                "idempotency_key": str(event_group.get("idempotency_key") or ""),
                "event_type": str(event_group.get("event_type") or ""),
                "stable_fact_id": str(claim.get("stable_fact_id") or ""),
                "target_slot": str(claim.get("target_slot") or ""),
                "truth_eligible": bool(authority.get("truth_eligible")),
                "support_visibility": str(authority.get("support_visibility") or ""),
                "budget_class": str(projection.get("budget_class") or ""),
                "authority_critical": bool(projection.get("authority_critical")),
            }
        )
    return sorted(snapshot, key=lambda item: item["idempotency_key"])


class _FakeHindsightClient:
    def propose(self, source_batch: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "status": "ok",
            "operation_id": "gauntlet-fake",
            "donor_version": "local-fake",
            "config_hash": "sha256:config",
            "actions": [
                {
                    "action": "create",
                    "target_kind": "user_fact",
                    "target_slot": "identity.preferred_address_name",
                    "value_fingerprint": "sha256:value",
                    "source_span_ids": ["usrspan_1"],
                    "source_event_ids": ["event_1"],
                    "assertion_speaker": "user",
                    "confidence": 0.99,
                }
            ],
        }


class _FakeHindsightPublicMemoryClient:
    def retain_memories(
        self,
        *,
        bank_id: str,
        items: list[Mapping[str, Any]],
        document_tags: list[str] | None = None,
        async_mode: bool = True,
    ) -> Mapping[str, Any]:
        return {
            "success": True,
            "bank_id": bank_id,
            "items_count": len(items),
            "async": async_mode,
            "operation_id": "gauntlet-public-retain",
            "operation_ids": [],
        }

    def trigger_consolidation(self, *, bank_id: str) -> Mapping[str, Any]:
        return {"operation_id": f"gauntlet-public-consolidate:{bank_id}"}

    def recall_memories(
        self,
        *,
        bank_id: str,
        query: str,
        budget: str = "low",
        max_tokens: int = 900,
        trace: bool = True,
        tags: list[str] | None = None,
    ) -> Mapping[str, Any]:
        return {
            "results": [
                {
                    "id": "gauntlet-public-memory",
                    "text": "The user explicitly provided a durable public-safe profile fact.",
                    "type": "observation",
                    "metadata": {
                        "source_span_id": "usrspan_1",
                        "source_event_id": "event_1",
                        "assertion_speaker": "user",
                        "brainstack_target_kind": "user_fact",
                        "brainstack_target_slot": "identity.preferred_address_name",
                        "confidence": 0.99,
                    },
                    "source_fact_ids": ["gauntlet-source-fact"],
                    "tags": list(tags or []),
                }
            ],
            "trace": {"mode": "public-api-bridge"},
        }


def _adapter_cases() -> dict[str, Any]:
    source_batch = build_hindsight_source_batch(
        session_id="gauntlet",
        scope={"principal_scope_key": "scope-a"},
        source_spans=[
            {
                "source_span_id": "usrspan_1",
                "source_event_id": "event_1",
                "speaker": "user",
                "text": "The user explicitly provided a durable public-safe profile fact.",
            }
        ],
    )
    unavailable = HindsightSpineAdapter(client=None, donor_version="not-configured").propose(source_batch)
    fake = HindsightSpineAdapter(client=_FakeHindsightClient()).propose(source_batch)
    public_bridge = HindsightPublicApiBridge(
        client=_FakeHindsightPublicMemoryClient(),
        bank_id="gauntlet-bank",
        donor_version="openapi-public-bridge",
    ).propose(source_batch)
    unsafe = normalize_proposal_action_batch(
        {
            "status": "ok",
            "operation_id": "unsafe",
            "actions": [
                {
                    "action": "create",
                    "target_kind": "user_fact",
                    "assertion_speaker": "assistant",
                }
            ],
        }
    )
    return {
        "unavailable": proposal_action_batch_status(unavailable),
        "fake": proposal_action_batch_status(fake),
        "public_bridge": proposal_action_batch_status(public_bridge),
        "public_bridge_batch": public_bridge,
        "unsafe": proposal_action_batch_status(unsafe),
    }


def _donor_rehearsal(donor_dir: Path) -> dict[str, Any]:
    if not donor_dir.exists():
        return {"status": "blocked", "reason": "hindsight_donor_clone_missing"}
    head = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=donor_dir,
        text=True,
        capture_output=True,
        check=False,
    ).stdout.strip()
    fetch, fetch_attempts = _fetch_donor_with_retry(donor_dir)
    behind = subprocess.run(
        ["git", "rev-list", "--count", "HEAD..origin/main"],
        cwd=donor_dir,
        text=True,
        capture_output=True,
        check=False,
    ).stdout.strip()
    openapi_source = "worktree"
    openapi_text = ""
    if fetch.returncode == 0:
        origin_openapi = subprocess.run(
            ["git", "show", "origin/main:hindsight-docs/static/openapi.json"],
            cwd=donor_dir,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        if origin_openapi.returncode == 0 and origin_openapi.stdout.strip():
            openapi_text = origin_openapi.stdout
            openapi_source = "origin/main"
    if not openapi_text:
        openapi = donor_dir / "hindsight-docs/static/openapi.json"
        openapi_text = openapi.read_text(encoding="utf-8") if openapi.exists() else "{}"
    api = json.loads(openapi_text)
    operations = []
    for path, methods in (api.get("paths") or {}).items():
        for method, spec in methods.items():
            operations.append(
                {
                    "method": method,
                    "path": path,
                    "operation_id": spec.get("operationId"),
                    "summary": spec.get("summary"),
                }
            )
    direct_proposal_surface = [
        item
        for item in operations
        if any(
            token in f"{item.get('operation_id')} {item.get('summary')} {item.get('path')}".lower()
            for token in ("proposal", "action_batch", "candidate")
        )
    ]
    required_public_bridge_ops = {
        "retain_memories",
        "recall_memories",
        "trigger_consolidation",
        "get_observation_history",
        "get_graph",
    }
    operation_ids = {str(item.get("operation_id") or "") for item in operations}
    public_bridge_surface = sorted(required_public_bridge_ops & operation_ids)
    missing_public_bridge_ops = sorted(required_public_bridge_ops - operation_ids)
    status = "pass" if fetch.returncode == 0 and openapi_source == "origin/main" else "blocked"
    proposal_surface = bool(direct_proposal_surface) or not missing_public_bridge_ops
    if not proposal_surface:
        status = "blocked"
    return {
        "status": status,
        "head": head,
        "fetch_returncode": fetch.returncode,
        "fetch_attempts": fetch_attempts,
        "behind_origin_main": behind,
        "openapi_source": openapi_source,
        "memory_operations": [
            item
            for item in operations
            if any(token in str(item.get("path")).lower() for token in ("memories", "retain", "recall", "consolid"))
        ],
        "proposal_surface": proposal_surface,
        "proposal_surface_mode": "direct_proposal_endpoint" if direct_proposal_surface else "public_api_bridge",
        "direct_proposal_surface": direct_proposal_surface,
        "public_bridge_surface": public_bridge_surface,
        "missing_public_bridge_ops": missing_public_bridge_ops,
        "blocker": "" if proposal_surface else "hindsight_public_bridge_surface_not_found",
    }


def _critical_counters(memory: Mapping[str, Any], adapter: Mapping[str, Any], donor: Mapping[str, Any]) -> dict[str, int]:
    verified = memory["verified_profile"]
    assistant = memory["assistant_claim"]
    unverified = memory["unverified_user_claim"]
    graph = memory["graph_relation"]
    bloat = memory["bloat"]
    events = verified["events"] + assistant["events"] + unverified["events"] + graph["events"] + bloat["events"]
    invalid_event_count = sum(0 if case["validation_passed"] else 1 for case in (verified, assistant, unverified, graph, bloat))
    multihop_missing = 0
    for event in graph["events"]:
        projection = event.get("projection") if isinstance(event.get("projection"), Mapping) else {}
        hints = projection.get("projection_hints") if isinstance(projection.get("projection_hints"), Mapping) else {}
        if not hints.get("multihop_ready"):
            multihop_missing += 1
    return {
        "false_durable_write": int(unverified["result"].get("writes_performed") or 0),
        "assistant_authored_durable_truth": int(assistant["result"].get("writes_performed") or 0),
        "unverified_tier2_durable_write": int(unverified["result"].get("writes_performed") or 0),
        "missing_canonical_event_for_verified_write": 0
        if int(verified["result"].get("writes_performed") or 0) == verified["canonical_event_count"]
        else 1,
        "invalid_canonical_event": invalid_event_count,
        "raw_private_value_leak": int(any(case["raw_leak_in_plan"] or case["raw_leak_in_events"] for case in (verified, assistant, unverified, graph, bloat))),
        "bloat_durable_write": int(bloat["result"].get("writes_performed") or 0),
        "adapter_unsafe_action_accepted": 0 if adapter["unsafe"]["status"] == "degraded" else 1,
        "hindsight_public_bridge_proof_missing": 0 if adapter["public_bridge"]["status"] == "ok" and donor.get("proposal_surface") else 1,
        "projection_rebuild_mismatch": 0 if memory["projection_rebuild"]["status"] == "pass" else 1,
        "multi_hop_readiness_missing": multihop_missing,
        "direct_hindsight_proposal_surface_missing": 0 if donor.get("proposal_surface") else 1,
        "canonical_event_count": len(events),
    }


def _eligibility(memory: Mapping[str, Any], adapter: Mapping[str, Any], donor: Mapping[str, Any]) -> dict[str, Any]:
    counters = _critical_counters(memory, adapter, donor)
    blocking_counters = {key: value for key, value in counters.items() if key != "canonical_event_count"}
    blockers = [key for key, value in blocking_counters.items() if value != 0]
    proof_families = {
        "safety_critical_counters": not any(
            counters[key]
            for key in (
                "false_durable_write",
                "assistant_authored_durable_truth",
                "unverified_tier2_durable_write",
                "adapter_unsafe_action_accepted",
                "hindsight_public_bridge_proof_missing",
            )
        ),
        "canonical_event_and_projection_readiness": counters["invalid_canonical_event"] == 0
        and counters["missing_canonical_event_for_verified_write"] == 0,
        "bloat_and_token_discipline": counters["bloat_durable_write"] == 0,
        "event_replay_and_projection_rebuild": counters["projection_rebuild_mismatch"] == 0,
        "scope_and_leak_resistance": counters["raw_private_value_leak"] == 0,
        "multi_hop_preservation": counters["multi_hop_readiness_missing"] == 0,
        "hindsight_update_rehearsal": donor.get("status") == "pass",
    }
    return {
        "schema": "brainstack.tier2_sota_eligibility_packet.v1",
        "status": "pass" if not blockers and all(proof_families.values()) else "blocked",
        "sota_candidate": not blockers and all(proof_families.values()),
        "phase_240_allowed": not blockers and all(proof_families.values()),
        "blockers": blockers,
        "critical_counters": counters,
        "proof_families": proof_families,
        "claim_boundary": {
            "claimed_if_pass": "supported Brainstack Tier2 memory-kernel path is SOTA-candidate",
            "not_claimed": [
                "global KG-RAG SOTA",
                "CatRAG/HippoRAG retrieval equivalence",
                "full Hermes product readiness",
            ],
        },
    }


def _markdown_report(title: str, packet: Mapping[str, Any], extra: Mapping[str, Any] | None = None) -> str:
    lines = [f"# {title}", "", f"Status: {packet.get('status', 'unknown')}", ""]
    if packet.get("blockers"):
        lines.append("## Blockers")
        lines.extend(f"- {item}" for item in packet["blockers"])
        lines.append("")
    lines.append("## Critical Counters")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(packet.get("critical_counters", {}), ensure_ascii=True, indent=2, sort_keys=True))
    lines.append("```")
    if extra:
        lines.append("")
        lines.append("## Evidence")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(extra, ensure_ascii=True, indent=2, sort_keys=True)[:8000])
        lines.append("```")
    return "\n".join(lines)


def run(*, phase_dir: Path, donor_dir: Path, artifact_prefix: str = "239") -> dict[str, Any]:
    memory = _run_memory_cases()
    adapter = _adapter_cases()
    donor = _donor_rehearsal(donor_dir)
    packet = _eligibility(memory, adapter, donor)
    _json_dump(phase_dir / f"{artifact_prefix}-SOTA-ELIGIBILITY-PACKET.json", packet)
    _json_dump(phase_dir / f"{artifact_prefix}-GAUNTLET-RAW.json", {"memory": memory, "adapter": adapter, "donor": donor})
    _write_text(
        phase_dir / f"{artifact_prefix}-GAUNTLET-REPORT.md",
        _markdown_report(f"Phase {artifact_prefix} Tier2 Proof Gauntlet", packet),
    )
    _write_text(
        phase_dir / f"{artifact_prefix}-SEMANTIC-CONFORMANCE-REPORT.md",
        _markdown_report(
            f"Phase {artifact_prefix} Semantic Conformance Report",
            {
                "status": "pass" if packet["proof_families"]["canonical_event_and_projection_readiness"] else "blocked",
                "critical_counters": {
                    "invalid_canonical_event": packet["critical_counters"]["invalid_canonical_event"],
                    "missing_canonical_event_for_verified_write": packet["critical_counters"]["missing_canonical_event_for_verified_write"],
                },
                "blockers": [
                    item
                    for item in packet["blockers"]
                    if item in {"invalid_canonical_event", "missing_canonical_event_for_verified_write"}
                ],
            },
            {"validated_event_count": packet["critical_counters"]["canonical_event_count"]},
        ),
    )
    _write_text(
        phase_dir / f"{artifact_prefix}-PROJECTION-REBUILD-REPORT.md",
        _markdown_report(
            f"Phase {artifact_prefix} Projection Rebuild Report",
            {
                "status": memory["projection_rebuild"]["status"],
                "critical_counters": {
                    "projection_rebuild_mismatch": packet["critical_counters"]["projection_rebuild_mismatch"]
                },
                "blockers": ["projection_rebuild_mismatch"]
                if packet["critical_counters"]["projection_rebuild_mismatch"]
                else [],
            },
            memory["projection_rebuild"],
        ),
    )
    _write_text(
        phase_dir / f"{artifact_prefix}-HINDSIGHT-UPDATE-REHEARSAL.md",
        _markdown_report(
            f"Phase {artifact_prefix} Hindsight Update Rehearsal",
            {
                "status": donor["status"],
                "critical_counters": {
                    "direct_hindsight_proposal_surface_missing": packet["critical_counters"][
                        "direct_hindsight_proposal_surface_missing"
                    ]
                },
                "blockers": [donor["blocker"]] if donor.get("blocker") else [],
            },
            donor,
        ),
    )
    return packet


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase-dir", type=Path, default=PHASE_DIR)
    parser.add_argument("--donor-dir", type=Path, default=_default_donor_dir())
    parser.add_argument("--artifact-prefix", default="239")
    args = parser.parse_args()
    packet = run(phase_dir=args.phase_dir, donor_dir=args.donor_dir, artifact_prefix=args.artifact_prefix)
    print(json.dumps(packet, ensure_ascii=True, indent=2, sort_keys=True))
    return 0 if packet["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
