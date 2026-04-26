from __future__ import annotations

import argparse
import json
import shutil
import statistics
import sys
import tempfile
import time
import types
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

if "agent.memory_provider" not in sys.modules:
    agent_module = types.ModuleType("agent")
    memory_provider_module = types.ModuleType("agent.memory_provider")

    class MemoryProvider:  # pragma: no cover - CLI shim for local replay outside Hermes.
        pass

    setattr(memory_provider_module, "MemoryProvider", MemoryProvider)
    sys.modules.setdefault("agent", agent_module)
    sys.modules.setdefault("agent.memory_provider", memory_provider_module)

from brainstack import BrainstackMemoryProvider  # noqa: E402
from brainstack.diagnostics import build_query_inspect  # noqa: E402
from brainstack.operating_truth import (  # noqa: E402
    CURRENT_ASSIGNMENT_AUTHORITY_SCHEMA,
    OPERATING_RECORD_ACTIVE_WORK,
    OPERATING_RECORD_LIVE_SYSTEM_STATE,
)


SESSION_ID = "brainstack-replay-session"
PRINCIPAL_SCOPE = "platform:test|user_id:user|agent_identity:agent-smoke|agent_workspace:workspace"

BoundaryVerdict = str


@dataclass(frozen=True)
class ReplayScenario:
    scenario_id: str
    query: str
    boundary_verdict: BoundaryVerdict
    expected_verdict: str
    seed: Callable[[BrainstackMemoryProvider], None]
    assert_result: Callable[[Mapping[str, Any]], list[str]]
    contract_id: str = "LEGACY"
    expected_answerable: bool = True
    lifecycle_seed: Callable[[BrainstackMemoryProvider], None] | None = None


def _provider(db_path: Path) -> BrainstackMemoryProvider:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(db_path),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
        }
    )
    provider.initialize(
        SESSION_ID,
        platform="test",
        user_id="user",
        agent_identity="agent-smoke",
        agent_workspace="workspace",
    )
    if provider._store is None:
        msg = "Brainstack provider did not initialize a store."
        raise RuntimeError(msg)
    return provider


def _metadata(extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {"principal_scope_key": PRINCIPAL_SCOPE, **dict(extra or {})}


def _inspect(provider: BrainstackMemoryProvider, query: str) -> dict[str, Any]:
    if provider._store is None:
        msg = "Brainstack provider store is unavailable."
        raise RuntimeError(msg)
    return build_query_inspect(
        provider._store,
        query=query,
        session_id=SESSION_ID,
        principal_scope_key=PRINCIPAL_SCOPE,
        continuity_recent_limit=4,
        continuity_match_limit=6,
        transcript_match_limit=6,
        transcript_char_budget=900,
        evidence_item_budget=16,
        graph_limit=8,
        corpus_limit=2,
        operating_match_limit=8,
    )


def _selected(report: Mapping[str, Any], shelf: str) -> list[dict[str, Any]]:
    selected = report.get("selected_evidence")
    if not isinstance(selected, Mapping):
        return []
    rows = selected.get(shelf)
    return [dict(row) for row in rows] if isinstance(rows, list) else []


def _suppressed(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = report.get("suppressed_evidence")
    return [dict(row) for row in rows] if isinstance(rows, list) else []


def _packet_preview(report: Mapping[str, Any]) -> str:
    packet = report.get("final_packet")
    if not isinstance(packet, Mapping):
        return ""
    return str(packet.get("preview") or "")


def _has_current_assignment_authority(report: Mapping[str, Any]) -> bool:
    if _selected(report, "task"):
        return True
    for row in _selected(report, "operating"):
        if row.get("runtime_state_only") or row.get("supporting_evidence_only"):
            continue
        if (
            row.get("current_assignment_authority")
            and str(row.get("current_assignment_authority_schema") or "") == CURRENT_ASSIGNMENT_AUTHORITY_SCHEMA
        ):
            return True
    return False


def _selected_counts(report: Mapping[str, Any]) -> dict[str, int]:
    selected = report.get("selected_evidence")
    if not isinstance(selected, Mapping):
        return {}
    return {str(shelf): len(rows or []) for shelf, rows in selected.items() if isinstance(rows, list)}


def _suppressed_reasons(report: Mapping[str, Any], *, limit: int = 10) -> list[str]:
    reasons: list[str] = []
    for row in _suppressed(report):
        reason = str(row.get("suppression_reason") or "")
        if reason and reason not in reasons:
            reasons.append(reason)
        if len(reasons) >= limit:
            break
    return reasons


def _selected_total(report: Mapping[str, Any]) -> int:
    return sum(_selected_counts(report).values())


def _selected_text(report: Mapping[str, Any]) -> str:
    chunks: list[str] = []
    for shelf in ("profile", "task", "operating", "continuity_match", "continuity_recent", "transcript", "graph", "corpus"):
        for row in _selected(report, shelf):
            chunks.extend(
                [
                    str(row.get("stable_key") or ""),
                    str(row.get("excerpt") or ""),
                    str(row.get("object_value") or ""),
                    str(row.get("citation_id") or ""),
                    str(row.get("content") or ""),
                ]
            )
    chunks.append(_packet_preview(report))
    return "\n".join(chunk for chunk in chunks if chunk)


def _memory_answerability(report: Mapping[str, Any], scenario: ReplayScenario) -> dict[str, Any]:
    raw_answerability = report.get("memory_answerability")
    if isinstance(raw_answerability, Mapping):
        payload = dict(raw_answerability)
    else:
        payload = {
            "schema": "brainstack.memory_answerability.v1",
            "can_answer": False,
            "reason": "missing_runtime_answerability",
            "reason_code": "NO_CANDIDATES",
            "answer_evidence_ids": [],
            "supporting_context_ids": [],
        }
    payload["expected_can_answer"] = scenario.expected_answerable
    payload["selected_evidence_count"] = _selected_total(report)
    return payload


def _hook_coverage(*, mode: str) -> dict[str, str]:
    if mode == "full_lifecycle":
        return {
            "provider_init": "real",
            "user_event_ingest": "real",
            "after_turn_capture": "real",
            "on_pre_compress": "real",
            "on_session_end": "real",
            "restart_reopen": "real",
            "query_inspect": "real",
            "final_packet": "real",
            "coverage_verdict": "full",
        }
    return {
        "provider_init": "real",
        "user_event_ingest": "simulated",
        "after_turn_capture": "omitted",
        "on_pre_compress": "omitted",
        "on_session_end": "omitted",
        "restart_reopen": "real",
        "query_inspect": "real",
        "final_packet": "real",
        "coverage_verdict": "synthetic",
    }


def _lifecycle_messages(scenario: ReplayScenario) -> list[dict[str, str]]:
    del scenario
    return [
        {"role": "user", "content": "Lifecycle replay neutral user event."},
        {"role": "assistant", "content": "Lifecycle replay acknowledgement without durable user truth."},
    ]


def _run_lifecycle_hooks(provider: BrainstackMemoryProvider, scenario: ReplayScenario) -> None:
    messages = _lifecycle_messages(scenario)
    provider.sync_turn(
        user_content=messages[0]["content"],
        assistant_content=messages[1]["content"],
        session_id=SESSION_ID,
    )
    provider.on_pre_compress(messages)
    provider.on_session_end(messages)


def _first_broken_stage(failures: list[str]) -> str:
    if not failures:
        return "none"
    first = failures[0]
    if "authority" in first or "assignment" in first:
        return "promotion"
    if "selected" in first or "recall" in first or "evidence" in first:
        return "retrieval"
    if "packet" in first or "answerability" in first:
        return "render"
    if "duplicate" in first or "write" in first:
        return "store"
    return "unknown"


def _assert_receipt_committed(payload: Mapping[str, Any], *, surface: str) -> None:
    if payload.get("status") != "committed":
        msg = f"{surface} did not commit: {payload!r}"
        raise RuntimeError(msg)


def _remember_profile(
    provider: BrainstackMemoryProvider,
    *,
    stable_key: str,
    category: str,
    content: str,
    authority_class: str = "explicit_current_fact",
) -> None:
    payload = json.loads(
        provider.handle_tool_call(
            "brainstack_remember",
            {
                "shelf": "profile",
                "stable_key": stable_key,
                "category": category,
                "content": content,
                "source_role": "user",
                "authority_class": authority_class,
                "confidence": 0.99,
            },
        )
    )
    _assert_receipt_committed(payload, surface="brainstack_remember")


def _seed_runtime_pulse(provider: BrainstackMemoryProvider) -> None:
    assert provider._store is not None
    provider._store.upsert_operating_record(
        stable_key="runtime:scheduler:pulse",
        principal_scope_key=PRINCIPAL_SCOPE,
        record_type=OPERATING_RECORD_LIVE_SYSTEM_STATE,
        content="Brainstack Proactive Pulse scheduler job is running every ten minutes.",
        owner="brainstack.live_system_state",
        source="runtime_handoff:pulse",
        metadata=_metadata({"owner_role": "runtime_system", "source_kind": "runtime_handoff"}),
    )


def _seed_background_profile(provider: BrainstackMemoryProvider) -> None:
    assert provider._store is not None
    provider._store.upsert_profile_item(
        stable_key="shared_work:brainstack-zero-human-definition",
        category="shared_work",
        content="Brainstack development status and zero-human workstream are separate concepts.",
        source="tier2:idle_window",
        confidence=0.8,
        metadata=provider._scoped_metadata({"source_kind": "tier2_idle_window"}),
    )


def _seed_background_continuity(provider: BrainstackMemoryProvider) -> None:
    assert provider._store is not None
    provider._store.add_continuity_event(
        session_id="prior-session",
        turn_number=1,
        kind="memory",
        content=(
            "Brainstack background context mentions the Wiki, Evolver, Heartbeat, "
            "and zero-human research definitions, but it is not an assigned task."
        ),
        source="on_memory_write:add:memory",
        metadata=_metadata({"record_type": "builtin_memory"}),
    )


def _seed_wrong_assistant_residue(provider: BrainstackMemoryProvider) -> None:
    assert provider._store is not None
    provider._store.add_transcript_entry(
        session_id="prior-session",
        turn_number=1,
        kind="turn",
        content=(
            "User: What is your current assignment? Assistant: WRONG_ASSISTANT_ASSIGNMENT "
            "Brainstack development is active current work."
        ),
        source="sync_turn",
        metadata=_metadata(),
    )
    provider._store.add_continuity_event(
        session_id="prior-session",
        turn_number=1,
        kind="turn",
        content="user: current workstream? | assistant: Brainstack development is the current assigned workstream.",
        source="sync_turn",
        metadata=_metadata(),
    )


def _seed_tier2_graph_runtime_state(provider: BrainstackMemoryProvider) -> None:
    assert provider._store is not None
    provider._store.upsert_graph_state(
        subject_name="Tomi",
        attribute="testing_status",
        value_text="active testing of brainstack",
        source="tier2:idle_window",
        metadata=_metadata({"source_kind": "tier2"}),
    )


def _seed_explicit_assignment(provider: BrainstackMemoryProvider) -> None:
    _seed_runtime_pulse(provider)
    assert provider._store is not None
    provider._store.upsert_operating_record(
        stable_key="operating:current-assignment:zero-human-research",
        principal_scope_key=PRINCIPAL_SCOPE,
        record_type=OPERATING_RECORD_ACTIVE_WORK,
        content="Zero-human research is the typed current assigned workstream.",
        owner="brainstack.operating_truth",
        source="explicit:user:current_assignment",
        metadata=_metadata(
            {
                "workstream_id": "zero-human-research",
                "owner_role": "agent_assignment",
                "source_kind": "explicit_operating_truth",
                "source_role": "user",
                "current_assignment_authority": True,
                "current_assignment_authority_schema": CURRENT_ASSIGNMENT_AUTHORITY_SCHEMA,
            }
        ),
    )


def _seed_stale_time_bound_graph(provider: BrainstackMemoryProvider) -> None:
    assert provider._store is not None
    provider._store.upsert_graph_state(
        subject_name="Kimi K2.6 Access Window",
        attribute="availability",
        value_text="15 hours remaining",
        source="explicit:user",
        metadata=_metadata(
            {
                "source_kind": "explicit",
                "temporal": {
                    "observed_at": "2026-04-23T12:00:00+00:00",
                    "valid_from": "2026-04-23T12:00:00+00:00",
                },
            }
        ),
    )


def _seed_background_definition(provider: BrainstackMemoryProvider) -> None:
    _seed_background_profile(provider)
    _seed_background_continuity(provider)


def _seed_exact_literal_marker(provider: BrainstackMemoryProvider) -> None:
    _remember_profile(
        provider,
        stable_key="debug_marker:1231231X",
        category="debug_marker",
        content="Tomi debug marker is 1231231X.",
    )
    assert provider._store is not None
    provider._store.add_transcript_entry(
        session_id="noise-session",
        turn_number=1,
        kind="turn",
        content="Assistant guessed wrong marker 1231231Y.",
        source="sync_turn",
        metadata=_metadata({"source_role": "assistant"}),
    )


def _seed_prior_question_event(provider: BrainstackMemoryProvider) -> None:
    assert provider._store is not None
    content = (
        "User asked: Ha nincs explicit assigned workstream rogzítve, mibol dontod el, "
        "hogy min dolgozol most?"
    )
    provider._store.add_transcript_entry(
        session_id="prior-question-session",
        turn_number=7,
        kind="turn",
        content=content,
        source="host_transcript_capture",
        metadata=_metadata({"event_type": "user_question", "source_role": "user"}),
    )
    provider._store.add_continuity_event(
        session_id="prior-question-session",
        turn_number=7,
        kind="user_question",
        content=content,
        source="host_transcript_capture",
        metadata=_metadata({"event_type": "user_question", "source_role": "user"}),
    )


def _seed_supersession(provider: BrainstackMemoryProvider) -> None:
    assert provider._store is not None
    provider._store.upsert_graph_state(
        subject_name="Debug Preference",
        attribute="marker",
        value_text="1231231Y",
        source="explicit:user",
        metadata=_metadata({"source_role": "user"}),
    )
    provider._store.upsert_graph_state(
        subject_name="Debug Preference",
        attribute="marker",
        value_text="1231231X",
        source="explicit:user:correction",
        supersede=True,
        metadata=_metadata({"source_role": "user", "supersedes": "1231231Y"}),
    )


def _seed_graph_conflict(provider: BrainstackMemoryProvider) -> None:
    assert provider._store is not None
    provider._store.upsert_graph_state(
        subject_name="Release Train",
        attribute="status",
        value_text="green",
        source="explicit:user:graphiti-conflict",
        metadata=_metadata({"source_role": "user"}),
    )
    provider._store.upsert_graph_state(
        subject_name="Release Train",
        attribute="status",
        value_text="red",
        source="explicit:user:graphiti-conflict",
        metadata=_metadata({"source_role": "user"}),
    )


def _seed_graph_alias_scope(provider: BrainstackMemoryProvider) -> None:
    assert provider._store is not None
    provider._store.upsert_graph_state(
        subject_name="Aurora",
        attribute="deployment",
        value_text="green",
        source="explicit:user:graphiti-alias",
        metadata=_metadata({"source_role": "user"}),
    )
    provider._store.get_or_create_entity("Project Aurora")
    provider._store.merge_entity_alias(alias_name="Project Aurora", target_name="Aurora")
    provider._store.upsert_graph_state(
        subject_name="Aurora",
        attribute="deployment",
        value_text="OTHER_SCOPE_RED",
        source="explicit:user:graphiti-alias",
        metadata={
            "principal_scope_key": "platform:test|user_id:other|agent_identity:agent-smoke|agent_workspace:workspace",
            "source_role": "user",
        },
    )


def _seed_hindsight_bank_isolation(provider: BrainstackMemoryProvider) -> None:
    assert provider._store is not None
    provider._store.upsert_operating_record(
        stable_key="operating:current-assignment:alpha-bank",
        principal_scope_key=PRINCIPAL_SCOPE,
        record_type=OPERATING_RECORD_ACTIVE_WORK,
        content="Alpha bank is the typed current memory bank for retained deployment work.",
        owner="brainstack.operating_truth",
        source="explicit:user:current_assignment",
        metadata=_metadata(
            {
                "workstream_id": "alpha-bank",
                "owner_role": "agent_assignment",
                "source_kind": "explicit_operating_truth",
                "source_role": "user",
                "current_assignment_authority": True,
                "current_assignment_authority_schema": CURRENT_ASSIGNMENT_AUTHORITY_SCHEMA,
            }
        ),
    )
    provider._store.add_continuity_event(
        session_id="alpha-bank-session",
        turn_number=1,
        kind="tier2_summary",
        content="Alpha bank retained lifecycle marker AX-777 for deployment follow-up.",
        source="tier2:reflect",
        metadata=_metadata({"workstream_id": "alpha-bank", "source_role": "tier2"}),
    )
    provider._store.add_continuity_event(
        session_id="beta-bank-session",
        turn_number=1,
        kind="tier2_summary",
        content="Beta bank retained lifecycle marker BETA-SECRET for deployment follow-up.",
        source="tier2:reflect",
        metadata=_metadata({"workstream_id": "beta-bank", "source_role": "tier2"}),
    )


def _seed_paraphrase_fact(provider: BrainstackMemoryProvider) -> None:
    _remember_profile(
        provider,
        stable_key="preference:answer_style",
        category="preference",
        content="User prefers concise Hungarian debugging answers with exact evidence.",
    )


def _seed_corpus_citation(provider: BrainstackMemoryProvider) -> None:
    provider.ingest_corpus_document(
        title="Brainstack Release Notes",
        content="Corpus answers must carry citation id cite-release-42 and bounded source text.",
        source="fixture:release-notes",
        doc_kind="markdown",
        metadata={"source_adapter": "fixture", "source_id": "release-notes"},
    )


def _corpus_source_payload(
    *,
    stable_key: str,
    content: str,
    source_uri: str = "fixture://mempalace-source",
) -> dict[str, Any]:
    return {
        "source_adapter": "replay_fixture",
        "source_id": stable_key,
        "stable_key": stable_key,
        "title": "MemPalace Replay Source",
        "doc_kind": "project_note",
        "source_uri": source_uri,
        "content": content,
        "metadata": {
            "principal_scope_key": PRINCIPAL_SCOPE,
            "authority_class": "corpus",
            "provenance_class": "replay_fixture",
        },
    }


def _seed_mempalace_stale_reingest(provider: BrainstackMemoryProvider) -> None:
    assert provider._store is not None
    provider._store.ingest_corpus_source(
        _corpus_source_payload(stable_key="doc:mempalace-lifecycle", content="OldCorpusNeedle body is stale.")
    )
    provider._store.ingest_corpus_source(
        _corpus_source_payload(stable_key="doc:mempalace-lifecycle", content="NewCorpusNeedle body is current.")
    )


def _seed_mempalace_private_path(provider: BrainstackMemoryProvider) -> None:
    assert provider._store is not None
    provider._store.ingest_corpus_source(
        _corpus_source_payload(
            stable_key="doc:mempalace-private",
            content="PrivatePathNeedle source text must be cited without leaking local path.",
            source_uri="/private/redacted/secrets/mempalace-notes.md",
        )
    )


def _seed_mempalace_duplicate_idempotence(provider: BrainstackMemoryProvider) -> None:
    assert provider._store is not None
    payload = _corpus_source_payload(
        stable_key="doc:mempalace-duplicate",
        content="DuplicateNeedle source text should remain a single cited section.",
    )
    provider._store.ingest_corpus_source(payload)
    provider._store.ingest_corpus_source(payload)


def _seed_scope_isolation(provider: BrainstackMemoryProvider) -> None:
    assert provider._store is not None
    provider._store.upsert_profile_item(
        stable_key="secret_marker:own",
        category="debug_marker",
        content="Same-scope marker is 1231231X.",
        source="explicit:user",
        confidence=0.99,
        metadata=provider._scoped_metadata({"source_role": "user"}),
    )
    provider._store.upsert_profile_item(
        stable_key="secret_marker:other",
        category="debug_marker",
        content="OTHER_SCOPE_SECRET marker must not leak.",
        source="explicit:user",
        confidence=0.99,
        metadata={"principal_scope_key": "platform:test|user_id:other|agent_identity:agent-smoke|agent_workspace:workspace"},
    )


def _seed_authority_packet_budget(provider: BrainstackMemoryProvider) -> None:
    _remember_profile(
        provider,
        stable_key="preference:packet_priority",
        category="preference",
        content="Authoritative packet priority is concise exact evidence.",
    )
    assert provider._store is not None
    provider._store.add_transcript_entry(
        session_id="noise-session",
        turn_number=3,
        kind="turn",
        content=("noise " * 180) + "low authority transcript says packet priority is verbose noise",
        source="sync_turn",
        metadata=_metadata({"source_role": "assistant"}),
    )


def _seed_no_evidence(_: BrainstackMemoryProvider) -> None:
    return


def _seed_idempotent_lifecycle(provider: BrainstackMemoryProvider) -> None:
    _seed_paraphrase_fact(provider)
    _seed_paraphrase_fact(provider)


def _seed_dirty_distractors(provider: BrainstackMemoryProvider) -> None:
    assert provider._store is not None
    provider._store.upsert_profile_item(
        stable_key="dirty:wrong-scope-marker",
        category="debug_marker",
        content="OTHER_SCOPE_DIRTY marker is 1231231Y.",
        source="dirty.fixture",
        confidence=0.5,
        metadata={"principal_scope_key": "platform:test|user_id:dirty|agent_identity:agent-smoke|agent_workspace:workspace"},
    )
    provider._store.add_transcript_entry(
        session_id="dirty-assistant-session",
        turn_number=1,
        kind="turn",
        content="Assistant residue says Brainstack development is the assigned task and marker maybe 1231231Y.",
        source="sync_turn",
        metadata=_metadata({"source_role": "assistant"}),
    )
    provider._store.add_continuity_event(
        session_id="dirty-tier2-session",
        turn_number=2,
        kind="tier2_summary",
        content="Tier-2 background summary mentions Brainstack development and zero-human research.",
        source="tier2:idle_window",
        metadata=_metadata({"source_role": "tier2", "source_kind": "tier2_idle_window"}),
    )
    provider._store.upsert_graph_state(
        subject_name="Dirty Background State",
        attribute="assignment",
        value_text="Brainstack development",
        source="tier2:idle_window",
        metadata=_metadata({"source_kind": "tier2"}),
    )
    provider._store.ingest_corpus_source(
        _corpus_source_payload(
            stable_key="doc:dirty-distractor",
            content="Dirty corpus distractor mentions zero-human, assignment, 1231231Y, and Brainstack.",
            source_uri="fixture://dirty-distractor",
        )
    )


def _expect_no_assignment_authority(report: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    if _has_current_assignment_authority(report):
        failures.append("current assignment authority was selected without explicit assignment")
    return failures


def _expect_background_guard(report: Mapping[str, Any]) -> list[str]:
    failures = _expect_no_assignment_authority(report)
    preview = _packet_preview(report)
    if "no explicit task/operating record is shown" not in preview:
        failures.append("final packet did not warn against inferring current work from background evidence")
    return failures


def _expect_explicit_assignment(report: Mapping[str, Any]) -> list[str]:
    rows = _selected(report, "operating")
    if any(row.get("current_assignment_authority") and row.get("workstream_id") == "zero-human-research" for row in rows):
        return []
    return ["explicit agent assignment was not selected as operating authority"]


def _expect_runtime_supporting_only(report: Mapping[str, Any]) -> list[str]:
    failures = _expect_no_assignment_authority(report)
    rows = _selected(report, "operating")
    if not rows:
        failures.append("runtime state was not visible as supporting evidence")
    if any(not row.get("runtime_state_only") for row in rows):
        failures.append("runtime state selected without runtime_state_only marker")
    preview = _packet_preview(report)
    if "Supporting-only/runtime state is not active assignment" not in preview:
        failures.append("final packet did not mark runtime state as non-assignment")
    return failures


def _expect_assistant_residue_suppressed(report: Mapping[str, Any]) -> list[str]:
    failures = _expect_no_assignment_authority(report)
    selected_ids = _selected(report, "transcript") + _selected(report, "continuity_match")
    if selected_ids:
        failures.append("assistant-authored current-assignment residue was selected")
    if not any(
        str(row.get("suppression_reason") or "").startswith("assistant_authored_current_assignment_residue")
        for row in _suppressed(report)
    ):
        failures.append("assistant-authored current-assignment residue was not trace-suppressed")
    return failures


def _expect_tier2_graph_suppressed(report: Mapping[str, Any]) -> list[str]:
    failures = _expect_no_assignment_authority(report)
    if _selected(report, "graph"):
        failures.append("Tier-2 graph runtime state was selected for current-assignment lookup")
    if not any(
        str(row.get("suppression_reason") or "").startswith("tier2_graph_current_assignment_residue")
        for row in _suppressed(report)
    ):
        failures.append("Tier-2 graph current-assignment residue was not trace-suppressed")
    return failures


def _expect_expired_graph_not_current(report: Mapping[str, Any]) -> list[str]:
    graph_rows = _selected(report, "graph")
    if not graph_rows:
        return ["expired time-bound graph evidence was not visible for temporal answer support"]
    if not any(row.get("fact_class") == "explicit_state_expired" for row in graph_rows):
        return ["time-bound graph evidence was not classified as explicit_state_expired"]
    if any(row.get("fact_class") == "explicit_state_current" for row in graph_rows):
        return ["expired time-bound graph evidence was also exposed as current"]
    return []


def _expect_unrelated_no_assignment(report: Mapping[str, Any]) -> list[str]:
    failures = _expect_no_assignment_authority(report)
    if _selected(report, "operating"):
        failures.append("unrelated query selected operating assignment evidence")
    return failures


def _expect_exact_literal_marker(report: Mapping[str, Any]) -> list[str]:
    text = _selected_text(report)
    failures: list[str] = []
    profile_rows = _selected(report, "profile")
    if not any(row.get("stable_key") == "debug_marker:1231231X" for row in profile_rows):
        failures.append("exact literal profile marker 1231231X was not selected")
    if "1231231X" not in text:
        failures.append("raw literal 1231231X missing from selected evidence/packet")
    if any(str(row.get("stable_key") or "").endswith("1231231Y") for row in profile_rows):
        failures.append("distractor literal 1231231Y won profile authority")
    return failures


def _expect_prior_question_event(report: Mapping[str, Any]) -> list[str]:
    failures = _expect_no_assignment_authority(report)
    rows = _selected(report, "transcript") + _selected(report, "continuity_match")
    text = _selected_text(report)
    if not rows or "explicit assigned workstream" not in text:
        failures.append("prior question event was not recallable from transcript/continuity evidence")
    if len(rows) > 4:
        failures.append("prior question event recall was not bounded")
    return failures


def _expect_supersession(report: Mapping[str, Any]) -> list[str]:
    rows = _selected(report, "graph")
    current = [row for row in rows if row.get("fact_class") == "explicit_state_current"]
    prior = [row for row in rows if row.get("fact_class") == "explicit_state_prior"]
    if not any(row.get("object_value") == "1231231X" for row in current):
        return ["supersession current value 1231231X was not selected"]
    if not any(row.get("object_value") == "1231231Y" for row in prior):
        return ["supersession prior value 1231231Y was not retained"]
    return []


def _expect_graph_conflict(report: Mapping[str, Any]) -> list[str]:
    failures = _expect_no_assignment_authority(report)
    rows = _selected(report, "graph")
    conflict_rows = [row for row in rows if row.get("row_type") == "conflict" or row.get("fact_class") == "conflict"]
    if not conflict_rows:
        failures.append("graph current/current conflict was not surfaced")
    elif not any(row.get("conflict_value") == "red" for row in conflict_rows):
        failures.append("graph conflict value red was not preserved")
    if any(row.get("current_assignment_authority") for row in rows):
        failures.append("graph conflict row exposed current_assignment_authority")
    raw_answerability = report.get("memory_answerability")
    answerability: Mapping[str, Any] = raw_answerability if isinstance(raw_answerability, Mapping) else {}
    if "[conflict]" not in _packet_preview(report) and answerability.get("state") != "conflicted":
        failures.append("graph conflict packet marker missing")
    return failures


def _expect_graph_alias_scope(report: Mapping[str, Any]) -> list[str]:
    failures = _expect_no_assignment_authority(report)
    rows = _selected(report, "graph")
    if not any(
        row.get("subject") == "Aurora"
        and row.get("matched_alias") == "Project Aurora"
        and row.get("match_mode") == "alias_lexical"
        and row.get("object_value") == "green"
        for row in rows
    ):
        failures.append("graph alias did not resolve to same-scope canonical entity")
    if "OTHER_SCOPE_RED" in _selected_text(report):
        failures.append("graph alias leaked other-scope value")
    return failures


def _expect_hindsight_bank_isolation(report: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    text = _selected_text(report)
    rows = _selected(report, "continuity_match") + _selected(report, "continuity_recent")
    if "AX-777" not in text or not any(row.get("workstream_id") == "alpha-bank" for row in rows):
        failures.append("same-bank retained continuity evidence was not selected")
    if "BETA-SECRET" in text:
        failures.append("different memory bank continuity evidence leaked into packet")
    if not any("workstream_bank_mismatch" in str(row.get("suppression_reason") or "") for row in _suppressed(report)):
        failures.append("different memory bank evidence was not trace-suppressed")
    return failures


def _expect_no_evidence(report: Mapping[str, Any]) -> list[str]:
    raw_answerability = report.get("memory_answerability")
    answerability: Mapping[str, Any] = raw_answerability if isinstance(raw_answerability, Mapping) else {}
    if answerability.get("can_answer"):
        return ["unsupported query was answerable from memory"]
    if answerability.get("answer_evidence_ids"):
        return ["unsupported query exposed answer evidence"]
    return []


def _expect_paraphrase_fact(report: Mapping[str, Any]) -> list[str]:
    if any(row.get("stable_key") == "preference:answer_style" for row in _selected(report, "profile")):
        return []
    return ["paraphrased durable profile fact did not select same stable key"]


def _expect_idempotent_profile_fact(report: Mapping[str, Any]) -> list[str]:
    rows = [row for row in _selected(report, "profile") if row.get("stable_key") == "preference:answer_style"]
    if len(rows) != 1:
        return ["idempotent lifecycle profile fact did not collapse to one selected stable key"]
    return []


def _expect_corpus_citation(report: Mapping[str, Any]) -> list[str]:
    rows = _selected(report, "corpus")
    if not rows:
        return ["corpus citation evidence was not selected"]
    if not any(row.get("citation_id") for row in rows):
        return ["corpus citation_id missing"]
    if "cite-release-42" not in _selected_text(report):
        return ["corpus cited source text missing"]
    return []


def _expect_mempalace_stale_reingest(report: Mapping[str, Any]) -> list[str]:
    rows = _selected(report, "corpus")
    text = _selected_text(report)
    failures: list[str] = []
    if not rows:
        failures.append("reingested corpus source was not selected")
    if "NewCorpusNeedle" not in text:
        failures.append("current reingested corpus section missing")
    if "OldCorpusNeedle" in text:
        failures.append("stale corpus section survived reingest")
    if not any(row.get("citation_id") == "doc:mempalace-lifecycle#s0" for row in rows):
        failures.append("stable corpus citation id missing after reingest")
    return failures


def _expect_mempalace_private_path(report: Mapping[str, Any]) -> list[str]:
    rows = _selected(report, "corpus")
    text = _selected_text(report)
    private_path = "/private/redacted/secrets/mempalace-notes.md"
    failures: list[str] = []
    if not rows:
        failures.append("private-path corpus source was not selected")
        return failures
    taxonomy = rows[0].get("corpus_taxonomy") if isinstance(rows[0], Mapping) else {}
    if not isinstance(taxonomy, Mapping) or taxonomy.get("source_uri_redacted") is not True:
        failures.append("private source URI was not marked redacted")
    if private_path in text or private_path in str(rows):
        failures.append("private local path leaked into corpus evidence")
    if not rows[0].get("source_display_id"):
        failures.append("redacted corpus source display id missing")
    return failures


def _expect_mempalace_duplicate_idempotence(report: Mapping[str, Any]) -> list[str]:
    rows = _selected(report, "corpus")
    citation_hits = [row for row in rows if row.get("citation_id") == "doc:mempalace-duplicate#s0"]
    if len(citation_hits) != 1:
        return ["duplicate corpus ingest did not collapse to one stable citation"]
    if "DuplicateNeedle" not in _selected_text(report):
        return ["duplicate corpus source text missing from selected evidence"]
    return []


def _expect_scope_isolation(report: Mapping[str, Any]) -> list[str]:
    text = _selected_text(report)
    if "OTHER_SCOPE_SECRET" in text:
        return ["cross-scope private marker leaked"]
    if "1231231X" not in text:
        return ["same-scope marker was not selected"]
    return []


def _expect_authority_packet_budget(report: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    if not any(row.get("stable_key") == "preference:packet_priority" for row in _selected(report, "profile")):
        failures.append("authority profile fact was drowned by lower-authority packet noise")
    packet_chars = int((report.get("final_packet") or {}).get("char_count") or 0) if isinstance(report.get("final_packet"), Mapping) else 0
    if packet_chars > 2200:
        failures.append("packet exceeded bounded budget")
    return failures


def scenarios() -> list[ReplayScenario]:
    return [
        ReplayScenario(
            "no_explicit_assignment_background_context",
            "What is my current workstream or assignment for Brainstack Wiki Evolver Heartbeat?",
            "brainstack_selection",
            "background evidence remains supporting; no current assignment authority",
            _seed_background_definition,
            _expect_background_guard,
            contract_id="BMT-ASSIGNMENT",
            expected_answerable=False,
        ),
        ReplayScenario(
            "explicit_assignment_beats_runtime_pulse",
            "aktuális agent assigned workstream zero-human Brainstack pulse",
            "brainstack_selection",
            "explicit agent_assignment operating record wins over runtime pulse",
            _seed_explicit_assignment,
            _expect_explicit_assignment,
            contract_id="G-AUTHORITY",
        ),
        ReplayScenario(
            "runtime_pulse_supporting_only",
            "Does the Brainstack Proactive Pulse mean Brainstack development is my current assigned task?",
            "packet_contract",
            "runtime scheduler state is visible only as supporting evidence",
            _seed_runtime_pulse,
            _expect_runtime_supporting_only,
            contract_id="BMT-ASSIGNMENT",
        ),
        ReplayScenario(
            "assistant_authored_assignment_residue",
            "Most melyik az aktuális assigned workstream feladatod?",
            "contaminated_memory_data",
            "assistant-authored prior answer residue is suppressed",
            _seed_wrong_assistant_residue,
            _expect_assistant_residue_suppressed,
            contract_id="G-AUTHORITY",
            expected_answerable=False,
        ),
        ReplayScenario(
            "tier2_graph_runtime_state",
            "Brainstack current assigned workstream feladat",
            "contaminated_memory_data",
            "Tier-2 graph runtime state cannot become current-assignment authority",
            _seed_tier2_graph_runtime_state,
            _expect_tier2_graph_suppressed,
            contract_id="G-AUTHORITY",
            expected_answerable=False,
        ),
        ReplayScenario(
            "stale_time_bound_truth",
            "Tegnap elott azt mondtam, Kimi K2.6 meg 15 oraig hasznalhato. Ez most ervenyes?",
            "brainstack_selection",
            "time-bound duration is exposed as expired historical support, not current truth",
            _seed_stale_time_bound_graph,
            _expect_expired_graph_not_current,
            contract_id="BMT-SUPERSESSION",
        ),
        ReplayScenario(
            "workstream_definition_not_assignment",
            "What is my current assigned workstream for zero-human income work?",
            "packet_contract",
            "workstream definition alone is not assignment authority",
            _seed_background_definition,
            _expect_background_guard,
            contract_id="BMT-ASSIGNMENT",
            expected_answerable=False,
        ),
        ReplayScenario(
            "unrelated_query_no_assignment_drag",
            "How should corpus citations be handled in a memory packet?",
            "brainstack_selection",
            "unrelated query does not drag assignment state into packet",
            _seed_explicit_assignment,
            _expect_unrelated_no_assignment,
            contract_id="G-PACKET",
            expected_answerable=False,
        ),
        ReplayScenario(
            "exact_literal_marker_distractor",
            "A korabbi debug marker 1231231X vagy 1231231Y volt?",
            "basic_memory_truth",
            "exact literal marker recall preserves raw value and beats distractor",
            _seed_exact_literal_marker,
            _expect_exact_literal_marker,
            contract_id="BMT-LITERAL",
        ),
        ReplayScenario(
            "prior_question_bounded_event_recall",
            "Megkerdeztem mar, mibol dontod el min dolgozol explicit assigned workstream nelkul?",
            "basic_memory_truth",
            "prior question recall uses bounded transcript/continuity event evidence",
            _seed_prior_question_event,
            _expect_prior_question_event,
            contract_id="BMT-PRIOR-EVENT",
        ),
        ReplayScenario(
            "correction_supersession_current_prior",
            "Mi a current debug marker es mi volt prior?",
            "basic_memory_truth",
            "correction demotes prior and keeps current/prior graph truth explainable",
            _seed_supersession,
            _expect_supersession,
            contract_id="BMT-SUPERSESSION",
        ),
        ReplayScenario(
            "graph_conflict_surfaces_not_assignment",
            "Release Train status conflict red green",
            "donor_layer_l2",
            "Graphiti-aligned current/current conflict surfaces without assignment promotion",
            _seed_graph_conflict,
            _expect_graph_conflict,
            contract_id="L2-GRAPH-CONFLICT",
        ),
        ReplayScenario(
            "graph_alias_scope_guard",
            "Project Aurora deployment status",
            "donor_layer_l2",
            "Graphiti-aligned alias lookup resolves canonical entity without cross-scope leak",
            _seed_graph_alias_scope,
            _expect_graph_alias_scope,
            contract_id="L2-GRAPH-ALIAS",
        ),
        ReplayScenario(
            "hindsight_memory_bank_isolation",
            "Alpha bank retained deployment marker follow-up",
            "donor_layer_l1",
            "Hindsight-aligned memory bank isolation keeps beta-bank continuity out of active alpha-bank recall",
            _seed_hindsight_bank_isolation,
            _expect_hindsight_bank_isolation,
            contract_id="L1-HINDSIGHT-BANK",
        ),
        ReplayScenario(
            "unsupported_query_no_memory_truth",
            "zeta omega durable memory unsupported thing",
            "basic_memory_truth",
            "unsupported query returns no memory truth",
            _seed_no_evidence,
            _expect_no_evidence,
            contract_id="BMT-NO-EVIDENCE",
            expected_answerable=False,
        ),
        ReplayScenario(
            "paraphrase_durable_profile_fact",
            "milyen valaszstilust szeret a user?",
            "basic_memory_truth",
            "paraphrased durable profile fact returns same stable key",
            _seed_paraphrase_fact,
            _expect_paraphrase_fact,
            contract_id="BMT-PARAPHRASE",
        ),
        ReplayScenario(
            "corpus_citation_bounded_recall",
            "citation id release 42 corpus answers",
            "donor_layer_l3",
            "corpus recall returns citation id and bounded source text",
            _seed_corpus_citation,
            _expect_corpus_citation,
            contract_id="G-PACKET",
        ),
        ReplayScenario(
            "mempalace_stale_reingest_lifecycle",
            "NewCorpusNeedle current corpus source citation",
            "donor_layer_l3",
            "MemPalace-aligned source reingest hides stale sections and keeps stable citation",
            _seed_mempalace_stale_reingest,
            _expect_mempalace_stale_reingest,
            contract_id="L3-MEMPALACE-LIFECYCLE",
        ),
        ReplayScenario(
            "mempalace_private_path_redaction",
            "PrivatePathNeedle cited source without local path",
            "donor_layer_l3",
            "MemPalace-aligned local-first source hides private local path",
            _seed_mempalace_private_path,
            _expect_mempalace_private_path,
            contract_id="L3-MEMPALACE-REDACTION",
        ),
        ReplayScenario(
            "mempalace_duplicate_source_idempotence",
            "DuplicateNeedle single cited section",
            "donor_layer_l3",
            "MemPalace-aligned duplicate source ingest stays idempotent",
            _seed_mempalace_duplicate_idempotence,
            _expect_mempalace_duplicate_idempotence,
            contract_id="L3-MEMPALACE-IDEMPOTENCE",
        ),
        ReplayScenario(
            "cross_scope_marker_isolation",
            "debug marker secret 1231231X OTHER_SCOPE_SECRET",
            "cross_layer",
            "same-scope marker recalls while other-scope marker stays hidden",
            _seed_scope_isolation,
            _expect_scope_isolation,
            contract_id="G-SCOPE",
        ),
        ReplayScenario(
            "authority_packet_budget",
            "packet priority concise exact evidence verbose noise",
            "cross_layer",
            "explicit profile fact survives lower-authority packet pressure",
            _seed_authority_packet_budget,
            _expect_authority_packet_budget,
            contract_id="G-PACKET",
        ),
        ReplayScenario(
            "lifecycle_idempotency_duplicate_guard",
            "milyen valaszstilust szeret a user concise Hungarian debugging exact evidence?",
            "lifecycle",
            "replaying same lifecycle seed twice does not duplicate durable profile evidence",
            _seed_idempotent_lifecycle,
            _expect_idempotent_profile_fact,
            contract_id="G-RECEIPT",
        ),
    ]


def _run_scenario(scenario: ReplayScenario, *, mode: str, fixture_variant: str) -> dict[str, Any]:
    tempdir = Path(tempfile.mkdtemp(prefix=f"brainstack-replay-{scenario.scenario_id}-"))
    provider: BrainstackMemoryProvider | None = None
    start = time.perf_counter()
    try:
        db_path = tempdir / "brainstack.sqlite3"
        provider = _provider(db_path)
        seed = scenario.lifecycle_seed if mode == "full_lifecycle" and scenario.lifecycle_seed is not None else scenario.seed
        seed(provider)
        if fixture_variant == "dirty":
            _seed_dirty_distractors(provider)
        write_receipt = dict(getattr(provider, "_last_write_receipt", {}) or {})
        immediate_report = _inspect(provider, scenario.query)
        immediate_failures = scenario.assert_result(immediate_report)
        lifecycle_steps = ["seeded_store", "restart", "recall", "packet"]
        if mode == "full_lifecycle":
            lifecycle_steps = [
                "user_event",
                "after_turn_capture",
                "on_pre_compress",
                "on_session_end",
                "restart",
                "recall",
                "packet",
            ]
            _run_lifecycle_hooks(provider, scenario)
            provider.shutdown()
            provider = _provider(db_path)
        report = _inspect(provider, scenario.query)
        elapsed_ms = (time.perf_counter() - start) * 1000
        failures = scenario.assert_result(report)
        if not immediate_failures and failures:
            failures.append("post-session/restart recall regressed from immediate recall")
        answerability = _memory_answerability(report, scenario)
        if not scenario.expected_answerable and answerability["can_answer"]:
            failures.append("memory_answerability allowed unsupported/non-authority answer")
        first_broken_stage = _first_broken_stage(failures)
        return {
            "schema": "brainstack.replay_scenario_result.v1",
            "scenario_id": scenario.scenario_id,
            "contract_id": scenario.contract_id,
            "mode": mode,
            "fixture_variant": fixture_variant,
            "boundary_verdict": scenario.boundary_verdict,
            "query": scenario.query,
            "latency_ms": round(elapsed_ms, 3),
            "expected_verdict": scenario.expected_verdict,
            "actual_verdict": "pass" if not failures else "fail",
            "passed": not failures,
            "failures": failures,
            "first_broken_stage": first_broken_stage,
            "memory_answerability": answerability,
            "hook_coverage": _hook_coverage(mode=mode),
            "checkpoints": {
                "immediate": {
                    "selected_count": _selected_total(immediate_report),
                    "answerability": _memory_answerability(immediate_report, scenario),
                    "failures": immediate_failures,
                },
                "post_session_restart": {
                    "selected_count": _selected_total(report),
                    "answerability": answerability,
                    "failures": failures,
                },
                "post_session_equal_or_safer": not failures or bool(immediate_failures),
            },
            "transaction_chain": {
                "schema": "brainstack.memory_transaction_autopsy.v1",
                "scenario_id": scenario.scenario_id,
                "mode": mode,
                "fixture_variant": fixture_variant,
                "steps": lifecycle_steps,
                "write_receipt_status": str(write_receipt.get("status") or "none"),
                "write_receipt_id": str(write_receipt.get("receipt_id") or write_receipt.get("write_id") or ""),
                "scope_key": PRINCIPAL_SCOPE,
                "selected_count": _selected_total(report),
                "suppressed_count": len(_suppressed(report)),
                "first_broken_stage": first_broken_stage,
            },
            "trace_fixture": {
                "query": scenario.query,
                "selected_counts": _selected_counts(report),
                "suppressed_count": len(_suppressed(report)),
                "suppressed_reasons": _suppressed_reasons(report),
                "authority_reason": "current_assignment_authority_present"
                if _has_current_assignment_authority(report)
                else "no_current_assignment_authority",
                "latency_bucket": "ok" if elapsed_ms < 750 else "slow",
                "packet_char_count": int((report.get("final_packet") or {}).get("char_count") or 0)
                if isinstance(report.get("final_packet"), Mapping)
                else 0,
            },
        }
    finally:
        if provider is not None:
            provider.shutdown()
        shutil.rmtree(tempdir, ignore_errors=True)


def run_replay(selected_ids: Iterable[str] | None = None, *, repeat: int = 1) -> dict[str, Any]:
    selected = set(selected_ids or [])
    scenario_list = [scenario for scenario in scenarios() if not selected or scenario.scenario_id in selected]
    if not scenario_list:
        msg = f"No replay scenarios matched: {sorted(selected)}"
        raise ValueError(msg)
    results: list[dict[str, Any]] = []
    for _ in range(max(1, repeat)):
        for scenario in scenario_list:
            for fixture_variant in ("clean", "dirty"):
                for mode in ("seeded_store", "full_lifecycle"):
                    results.append(_run_scenario(scenario, mode=mode, fixture_variant=fixture_variant))
    latencies = [float(result["latency_ms"]) for result in results]
    passed = [result for result in results if result["passed"]]
    failed = [result for result in results if not result["passed"]]
    p50 = statistics.median(latencies) if latencies else 0.0
    p95 = sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)] if latencies else 0.0
    return {
        "schema": "brainstack.memory_replay_report.v1",
        "repeat": max(1, repeat),
        "summary": {
            "scenario_count": len(results),
            "scenario_class_count": len(scenario_list),
            "passed": len(passed),
            "failed": len(failed),
            "p50_latency_ms": round(p50, 3),
            "p95_latency_ms": round(p95, 3),
            "max_latency_ms": round(max(latencies), 3) if latencies else 0.0,
            "modes": ["seeded_store", "full_lifecycle"],
            "fixture_variants": ["clean", "dirty"],
            "hook_coverage_verdicts": sorted(
                {
                    str(result.get("hook_coverage", {}).get("coverage_verdict") or "")
                    for result in results
                    if isinstance(result.get("hook_coverage"), Mapping)
                }
            ),
        },
        "results": results,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary_raw = report.get("summary")
    summary: Mapping[str, Any] = summary_raw if isinstance(summary_raw, Mapping) else {}
    lines = [
        "# Brainstack Deterministic Memory Replay",
        "",
        "## Summary",
        "",
        f"- scenarios: {summary.get('scenario_count', 0)}",
        f"- passed: {summary.get('passed', 0)}",
        f"- failed: {summary.get('failed', 0)}",
        f"- p50_latency_ms: {summary.get('p50_latency_ms', 0)}",
        f"- p95_latency_ms: {summary.get('p95_latency_ms', 0)}",
        f"- max_latency_ms: {summary.get('max_latency_ms', 0)}",
        "",
        "## Results",
        "",
    ]
    for result in report.get("results", []):
        if not isinstance(result, Mapping):
            continue
        trace_raw = result.get("trace_fixture")
        trace: Mapping[str, Any] = trace_raw if isinstance(trace_raw, Mapping) else {}
        lines.extend(
            [
                f"### {result.get('scenario_id')}",
                "",
                f"- mode: {result.get('mode')}",
                f"- fixture_variant: {result.get('fixture_variant')}",
                f"- contract_id: {result.get('contract_id')}",
                f"- actual_verdict: {result.get('actual_verdict')}",
                f"- boundary_verdict: {result.get('boundary_verdict')}",
                f"- hook_coverage: `{json.dumps(result.get('hook_coverage', {}), sort_keys=True)}`",
                f"- first_broken_stage: {result.get('first_broken_stage')}",
                f"- memory_answerability: `{json.dumps(result.get('memory_answerability', {}), sort_keys=True)}`",
                f"- latency_ms: {result.get('latency_ms')}",
                f"- authority_reason: {trace.get('authority_reason')}",
                f"- selected_counts: `{json.dumps(trace.get('selected_counts', {}), sort_keys=True)}`",
                f"- suppressed_count: {trace.get('suppressed_count', 0)}",
                f"- suppressed_reasons: `{json.dumps(trace.get('suppressed_reasons', []), sort_keys=True)}`",
                f"- failures: `{json.dumps(result.get('failures', []), sort_keys=True)}`",
                "",
            ]
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic Brainstack memory replay canaries.")
    parser.add_argument("--output", type=Path, help="Write JSON report to this path.")
    parser.add_argument("--markdown", type=Path, help="Write markdown report to this path.")
    parser.add_argument("--scenario", action="append", default=[], help="Run only this scenario id; repeatable.")
    parser.add_argument("--repeat", type=int, default=1, help="Repeat scenario set for soak-style local replay.")
    args = parser.parse_args()

    report = run_replay(args.scenario, repeat=args.repeat)
    payload = json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(render_markdown(report) + "\n", encoding="utf-8")
    return 0 if int(report["summary"]["failed"]) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
