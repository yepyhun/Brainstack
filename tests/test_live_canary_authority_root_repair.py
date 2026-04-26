from __future__ import annotations

import json
from pathlib import Path

from brainstack import BrainstackMemoryProvider
from brainstack.db import BrainstackStore
from brainstack.diagnostics import build_query_inspect
from brainstack.operating_context import build_operating_context_snapshot, render_operating_context_section
from brainstack.operating_truth import (
    CURRENT_ASSIGNMENT_AUTHORITY_SCHEMA,
    OPERATING_RECORD_ACTIVE_WORK,
    OPERATING_RECORD_LIVE_SYSTEM_STATE,
    OPERATING_RECORD_OPEN_DECISION,
    OPERATING_RECORD_RECENT_WORK_SUMMARY,
)


PRINCIPAL_SCOPE = "platform:test|user_id:user|agent_identity:agent-smoke|agent_workspace:workspace"


def _provider(tmp_path: Path) -> BrainstackMemoryProvider:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
        }
    )
    provider.initialize(
        "live-canary-session",
        platform="test",
        user_id="user",
        agent_identity="agent-smoke",
        agent_workspace="workspace",
    )
    assert provider._store is not None
    return provider


def _open_store(tmp_path: Path) -> BrainstackStore:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    return store


def test_tier2_open_decisions_are_not_promoted_to_operating_records(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        assert provider._store is not None
        promoted = provider._promote_open_decisions(
            decisions=[
                "Use session transcripts and Graph Truth for task determination when no workstream is assigned."
            ],
            source="tier2:idle_window:open_decision",
            metadata={"session_id": "live-canary-session", "turn_number": 4, "batch_reason": "idle_window"},
        )

        assert promoted == 0
        rows = provider._store.list_operating_records(
            principal_scope_key=provider._principal_scope_key,
            record_types=[OPERATING_RECORD_OPEN_DECISION],
            limit=10,
        )
        assert rows == []
        trace = provider._last_memory_operation_trace
        assert trace is not None
        assert trace["surface"] == "operating_open_decision_rejected"
    finally:
        provider.shutdown()


def test_session_consolidation_open_decisions_are_not_promoted_to_operating_records(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        assert provider._store is not None
        promoted = provider._promote_open_decisions(
            decisions=["Treat the current background project as the assigned workstream."],
            source="on_session_end:recent_work_consolidation",
            metadata={"session_id": "live-canary-session", "turn_number": 5},
        )

        assert promoted == 0
        rows = provider._store.list_operating_records(
            principal_scope_key=provider._principal_scope_key,
            record_types=[OPERATING_RECORD_OPEN_DECISION],
            limit=10,
        )
        assert rows == []
    finally:
        provider.shutdown()


def test_operating_current_assignment_authority_requires_typed_authority(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        assert provider._store is not None
        provider._store.upsert_operating_record(
            stable_key="operating:assignment:loose",
            principal_scope_key=provider._principal_scope_key,
            record_type=OPERATING_RECORD_ACTIVE_WORK,
            content="Zero-human research is the current assignment but lacks typed authority.",
            owner="brainstack.operating_truth",
            source="fixture:loose_assignment",
            metadata={
                "owner_role": "agent_assignment",
                "source_kind": "explicit_operating_truth",
                "workstream_id": "zero-human-research",
            },
        )

        loose_payload = json.loads(
            provider.handle_tool_call("brainstack_recall", {"query": "current assignment zero-human research"})
        )
        loose_operating = loose_payload["selected_evidence"].get("operating", [])
        assert loose_operating
        assert not any(card["current_assignment_authority"] for card in loose_operating)

        provider._store.upsert_operating_record(
            stable_key="operating:assignment:typed",
            principal_scope_key=provider._principal_scope_key,
            record_type=OPERATING_RECORD_ACTIVE_WORK,
            content="Zero-human research is the typed current assignment.",
            owner="brainstack.operating_truth",
            source="fixture:typed_assignment",
            metadata={
                "owner_role": "agent_assignment",
                "source_kind": "explicit_operating_truth",
                "workstream_id": "zero-human-research",
                "current_assignment_authority": True,
                "current_assignment_authority_schema": CURRENT_ASSIGNMENT_AUTHORITY_SCHEMA,
            },
        )

        typed_payload = json.loads(
            provider.handle_tool_call("brainstack_recall", {"query": "typed current assignment zero-human research"})
        )
        typed_operating = typed_payload["selected_evidence"].get("operating", [])
        assert any(card["current_assignment_authority"] for card in typed_operating)
    finally:
        provider.shutdown()


def test_workstream_recap_model_tool_rejects_operator_role_but_trusted_host_can_write(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        schemas = {schema["name"]: schema for schema in provider.get_tool_schemas()}
        recap_schema = schemas["brainstack_workstream_recap"]["parameters"]["properties"]["source_role"]
        assert recap_schema["enum"] == ["user"]

        rejected = json.loads(
            provider.handle_tool_call(
                "brainstack_workstream_recap",
                {
                    "workstream_id": "zero-human-research",
                    "summary": "Zero-human research is the agent assignment.",
                    "source_role": "operator",
                    "owner_role": "agent_assignment",
                    "source_kind": "explicit_operating_truth",
                },
            )
        )
        assert rejected["status"] == "rejected"
        assert {error["code"] for error in rejected["errors"]} == {"untrusted_operator_source_role"}

        committed = json.loads(
            provider.handle_tool_call(
                "brainstack_workstream_recap",
                {
                    "workstream_id": "zero-human-research",
                    "summary": "Zero-human research is the agent assignment.",
                    "source_role": "operator",
                    "owner_role": "agent_assignment",
                    "source_kind": "explicit_operating_truth",
                },
                trusted_write_origin="test_operator",
            )
        )
        assert committed["status"] == "committed"
        assert committed["write_invoker"] == "trusted_host"
        assert committed["trusted_write_origin"] == "test_operator"
    finally:
        provider.shutdown()


def test_tier2_background_operating_records_are_supporting_not_canonical(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        metadata = {"principal_scope_key": PRINCIPAL_SCOPE}
        store.upsert_operating_record(
            stable_key="operating:tier2:background-recent",
            principal_scope_key=PRINCIPAL_SCOPE,
            record_type=OPERATING_RECORD_RECENT_WORK_SUMMARY,
            content="Brainstack development and zero-human assignment are mixed background recap.",
            owner="brainstack.tier2",
            source="tier2:idle_window",
            metadata={**metadata, "batch_reason": "idle_window"},
        )
        store.upsert_operating_record(
            stable_key="operating:tier2:background-decision",
            principal_scope_key=PRINCIPAL_SCOPE,
            record_type=OPERATING_RECORD_OPEN_DECISION,
            content="Maybe Brainstack development is the agent assignment.",
            owner="brainstack.tier2",
            source="tier2:batch",
            metadata=metadata,
        )

        report = build_query_inspect(
            store,
            query="Brainstack development zero-human assignment",
            session_id="live-canary-session",
            principal_scope_key=PRINCIPAL_SCOPE,
            operating_match_limit=6,
            evidence_item_budget=12,
        )

        selected_operating_keys = {
            str(item["evidence_key"]).removeprefix("operating:")
            for item in report["selected_evidence"]["operating"]
        }
        assert "operating:tier2:background-recent" not in selected_operating_keys
        assert "operating:tier2:background-decision" not in selected_operating_keys
        suppressed = report["suppressed_evidence"]
        assert any(
            item["suppression_reason"].startswith("background_recent_work_summary:")
            and item["supporting_evidence_only"] is True
            for item in suppressed
        )
        assert any(
            item["suppression_reason"].startswith("background_open_decision:")
            and item["supporting_evidence_only"] is True
            for item in suppressed
        )
    finally:
        store.close()


def test_scoped_assignment_beats_runtime_state_and_keeps_project_status_separate(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        assert provider._store is not None
        provider._store.upsert_operating_record(
            stable_key="operating:runtime:pulse",
            principal_scope_key=PRINCIPAL_SCOPE,
            record_type=OPERATING_RECORD_LIVE_SYSTEM_STATE,
            content="Brainstack Proactive Pulse cron is running for runtime maintenance.",
            owner="brainstack.live_system_state",
            source="runtime_handoff:pulse",
            metadata={
                "principal_scope_key": PRINCIPAL_SCOPE,
                "owner_role": "runtime_system",
                "source_kind": "runtime_handoff",
            },
        )
        agent_assignment = json.loads(
            provider.handle_tool_call(
                "brainstack_workstream_recap",
                {
                    "workstream_id": "zero-human-research",
                    "summary": "Zero-human research is the agent assigned workstream.",
                    "source_role": "user",
                    "owner_role": "agent_assignment",
                    "source_kind": "explicit_operating_truth",
                },
            )
        )
        project_status = json.loads(
            provider.handle_tool_call(
                "brainstack_workstream_recap",
                {
                    "workstream_id": "brainstack-development",
                    "summary": "Brainstack development status belongs to the user project.",
                    "source_role": "user",
                    "owner_role": "user_project",
                    "source_kind": "explicit_operating_truth",
                },
            )
        )
        assert agent_assignment["status"] == "committed"
        assert project_status["status"] == "committed"

        assignment_report = build_query_inspect(
            provider._store,
            query="aktuális agent assigned workstream zero-human Brainstack pulse",
            session_id="live-canary-session",
            principal_scope_key=PRINCIPAL_SCOPE,
            operating_match_limit=6,
            evidence_item_budget=12,
        )
        selected_operating = assignment_report["selected_evidence"]["operating"]
        assert any(
            item["workstream_id"] == "zero-human-research" and item["owner_role"] == "agent_assignment"
            for item in selected_operating
        )
        assert not any(item["runtime_state_only"] for item in selected_operating)
        assert any(item["runtime_state_only"] for item in assignment_report["suppressed_evidence"])

        project_report = build_query_inspect(
            provider._store,
            query="Brainstack development project status user project",
            session_id="live-canary-session",
            principal_scope_key=PRINCIPAL_SCOPE,
            operating_match_limit=6,
            evidence_item_budget=12,
        )
        assert any(
            item["workstream_id"] == "brainstack-development" and item["owner_role"] == "user_project"
            for item in project_report["selected_evidence"]["operating"]
        )
    finally:
        provider.shutdown()


def test_operating_context_snapshot_excludes_background_from_current_work_blocks(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        metadata = {"principal_scope_key": PRINCIPAL_SCOPE}
        store.upsert_operating_record(
            stable_key="operating:tier2:background-recent",
            principal_scope_key=PRINCIPAL_SCOPE,
            record_type=OPERATING_RECORD_RECENT_WORK_SUMMARY,
            content="Background summary must not become current work.",
            owner="brainstack.tier2",
            source="tier2:idle_window",
            metadata={**metadata, "batch_reason": "idle_window"},
        )
        store.upsert_operating_record(
            stable_key="operating:tier2:background-decision",
            principal_scope_key=PRINCIPAL_SCOPE,
            record_type=OPERATING_RECORD_OPEN_DECISION,
            content="Background decision must not become an open decision.",
            owner="brainstack.tier2",
            source="tier2:batch",
            metadata=metadata,
        )
        store.upsert_operating_record(
            stable_key="operating:runtime:pulse",
            principal_scope_key=PRINCIPAL_SCOPE,
            record_type=OPERATING_RECORD_LIVE_SYSTEM_STATE,
            content="Brainstack pulse runtime is healthy.",
            owner="brainstack.live_system_state",
            source="runtime_handoff:pulse",
            metadata={**metadata, "owner_role": "runtime_system", "source_kind": "runtime_handoff"},
        )
        rows = store.list_operating_records(principal_scope_key=PRINCIPAL_SCOPE, limit=8)
        snapshot = build_operating_context_snapshot(
            principal_scope_key=PRINCIPAL_SCOPE,
            compiled_behavior_policy_record=None,
            profile_items=[],
            operating_rows=rows,
            task_rows=[],
            continuity_rows=[],
            lifecycle_state=None,
        )
        rendered = render_operating_context_section(snapshot, char_budget=1400)

        assert snapshot["recent_work_summary"] == ""
        assert snapshot["open_decisions"] == []
        assert "Brainstack pulse runtime is healthy." in snapshot["live_system_state"]
        assert "Supporting live runtime state (not workstream truth)" in rendered
        assert "Do not use this section to answer current user project status" in rendered
        assert "Proactive continuity rule" not in rendered
        assert "Background summary must not become current work" not in rendered
        assert "Background decision must not become an open decision" not in rendered
    finally:
        store.close()


def test_session_end_consolidation_open_decisions_are_supporting_not_authority(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        metadata = {"principal_scope_key": PRINCIPAL_SCOPE}
        store.upsert_operating_record(
            stable_key="operating:session-end:open-decision",
            principal_scope_key=PRINCIPAL_SCOPE,
            record_type=OPERATING_RECORD_OPEN_DECISION,
            content="Treat Kimi K2.6 availability as a memory-managed state.",
            owner="brainstack.session_consolidation",
            source="on_session_end:recent_work_consolidation",
            metadata=metadata,
        )
        rows = store.list_operating_records(principal_scope_key=PRINCIPAL_SCOPE, limit=8)
        snapshot = build_operating_context_snapshot(
            principal_scope_key=PRINCIPAL_SCOPE,
            compiled_behavior_policy_record=None,
            profile_items=[],
            operating_rows=rows,
            task_rows=[],
            continuity_rows=[],
            lifecycle_state=None,
        )
        rendered = render_operating_context_section(snapshot, char_budget=1400)

        assert snapshot["open_decisions"] == []
        assert "Treat Kimi K2.6 availability" not in rendered
        assert "Proactive continuity rule" not in rendered
    finally:
        store.close()


def test_background_shared_work_profile_does_not_render_as_stable_project_signal(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        snapshot = build_operating_context_snapshot(
            principal_scope_key=PRINCIPAL_SCOPE,
            compiled_behavior_policy_record=None,
            profile_items=[
                {
                    "category": "shared_work",
                    "stable_key": "shared_work:brainstack-development-status",
                    "content": "Brainstack development status vs zero-human workstream",
                    "source": "tier2:idle_window",
                    "metadata": {"source_kind": "tier2_idle_window"},
                },
                {
                    "category": "identity",
                    "stable_key": "identity:user",
                    "content": "LauraTom",
                    "source": "tier2:idle_window",
                },
            ],
            operating_rows=[],
            task_rows=[],
            continuity_rows=[],
            lifecycle_state=None,
        )
        rendered = render_operating_context_section(snapshot, char_budget=1400)

        assert snapshot["stable_profile_entries"] == [
            {"category": "identity", "stable_key": "identity:user", "content": "LauraTom"}
        ]
        assert "Brainstack development status vs zero-human workstream" not in rendered
        assert "[identity] LauraTom" in rendered
    finally:
        store.close()


def test_sync_turn_continuity_strips_prior_assistant_answer_from_model_packet(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.add_continuity_event(
            session_id="prior-canary",
            turn_number=1,
            kind="turn",
            content=(
                "user: [LauraTom] Emlékszel, mi a különbség a Brainstack fejlesztési státusz "
                "és a zero-human workstream között? Most melyik a te aktuális feladatod? | "
                "assistant: WRONG_ASSISTANT_ASSIGNMENT Brainstack development is active current work."
            ),
            source="sync_turn",
            metadata={"principal_scope_key": PRINCIPAL_SCOPE},
            created_at="2026-04-25T15:49:00+00:00",
        )

        report = build_query_inspect(
            store,
            query="Emlékszel Brainstack fejlesztési státusz zero-human workstream aktuális feladat",
            session_id="live-canary-session",
            principal_scope_key=PRINCIPAL_SCOPE,
            continuity_recent_limit=0,
            continuity_match_limit=4,
            transcript_match_limit=0,
            graph_limit=0,
            corpus_limit=0,
        )

        packet = report["final_packet"]["preview"]
        assert "WRONG_ASSISTANT_ASSIGNMENT" not in packet
        assert "Brainstack development is active current work" not in packet
        assert "Emlékszel, mi a különbség" in packet
    finally:
        store.close()


def test_operating_context_renders_active_work_before_runtime_state(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        metadata = {"principal_scope_key": PRINCIPAL_SCOPE}
        store.upsert_operating_record(
            stable_key="operating:active:zero-human",
            principal_scope_key=PRINCIPAL_SCOPE,
            record_type=OPERATING_RECORD_ACTIVE_WORK,
            content="Zero-human research is the current agent assignment.",
            owner="brainstack.operating_truth",
            source="explicit:user",
            metadata={**metadata, "owner_role": "agent_assignment"},
        )
        store.upsert_operating_record(
            stable_key="operating:runtime:pulse",
            principal_scope_key=PRINCIPAL_SCOPE,
            record_type=OPERATING_RECORD_LIVE_SYSTEM_STATE,
            content="Brainstack pulse runtime is healthy.",
            owner="brainstack.live_system_state",
            source="runtime_handoff:pulse",
            metadata={**metadata, "owner_role": "runtime_system", "source_kind": "runtime_handoff"},
        )

        rows = store.list_operating_records(principal_scope_key=PRINCIPAL_SCOPE, limit=8)
        snapshot = build_operating_context_snapshot(
            principal_scope_key=PRINCIPAL_SCOPE,
            compiled_behavior_policy_record=None,
            profile_items=[],
            operating_rows=rows,
            task_rows=[],
            continuity_rows=[],
            lifecycle_state=None,
        )
        rendered = render_operating_context_section(snapshot, char_budget=1600)

        current_index = rendered.index("Current work:")
        runtime_index = rendered.index("Supporting live runtime state")
        assert current_index < runtime_index
        assert "Zero-human research is the current agent assignment." in rendered
        assert snapshot["proactive_guidance"]
    finally:
        store.close()


def test_working_memory_labels_runtime_state_as_supporting_not_assignment(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.upsert_operating_record(
            stable_key="operating:runtime:pulse",
            principal_scope_key=PRINCIPAL_SCOPE,
            record_type=OPERATING_RECORD_LIVE_SYSTEM_STATE,
            content="Brainstack pulse runtime is healthy.",
            owner="brainstack.live_system_state",
            source="runtime_handoff:pulse",
            metadata={
                "principal_scope_key": PRINCIPAL_SCOPE,
                "owner_role": "runtime_system",
                "source_kind": "runtime_handoff",
            },
        )
        report = build_query_inspect(
            store,
            query="Brainstack pulse runtime health",
            session_id="live-canary-session",
            principal_scope_key=PRINCIPAL_SCOPE,
            operating_match_limit=6,
            evidence_item_budget=12,
        )
        preview = report["final_packet"]["preview"]
        assert "supporting runtime state (not assigned work)" in preview
        assert "not active workstream/project status" in preview
        assert "Supporting-only/runtime state is not active assignment" in preview
        assert "Only supporting Brainstack runtime/operating evidence matched this lookup" in preview
        assert "Use the committed Brainstack operating records below as authoritative" not in preview
        assert "[live system state]" not in preview
    finally:
        store.close()


def test_background_continuity_cannot_imply_current_assignment(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.add_continuity_event(
            session_id="prior-session",
            turn_number=1,
            kind="memory",
            content=(
                "A Brainstack alapműködésének része a Karpathy-féle LLM Wiki pattern, "
                "az Evolver önfejlesztő motor és a proaktív Heartbeat mechanizmus."
            ),
            source="on_memory_write:add:memory",
            metadata={"principal_scope_key": PRINCIPAL_SCOPE, "record_type": "builtin_memory"},
        )

        report = build_query_inspect(
            store,
            query="What is my current workstream or assignment for Brainstack Wiki Evolver Heartbeat?",
            session_id="live-canary-session",
            principal_scope_key=PRINCIPAL_SCOPE,
            continuity_match_limit=4,
            evidence_item_budget=12,
        )
        preview = report["final_packet"]["preview"]
        assert "If asked about current work, assignment, or workstream" in preview
        assert "no explicit task/operating record is shown" in preview
        assert "instead of inferring it from background evidence" in preview
        assert "Brainstack alapműködésének része" in preview
        assert "Use the committed Brainstack operating records below as authoritative" not in preview
    finally:
        store.close()


def test_assignment_lookup_suppresses_assistant_authored_transcript_residue(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.add_transcript_entry(
            session_id="prior-session",
            turn_number=1,
            kind="turn",
            content=(
                "User: [LauraTom] Emlékszel, mi a különbség a Brainstack fejlesztési státusz "
                "és a zero-human workstream között? Most melyik a te aktuális feladatod? "
                "Assistant: A Brainstack Graph Truth szerint a state:current most is "
                "brainstack development, tehát ez az aktuális feladatom."
            ),
            source="sync_turn",
            metadata={"principal_scope_key": PRINCIPAL_SCOPE},
        )
        store.add_continuity_event(
            session_id="prior-session",
            turn_number=1,
            kind="turn",
            content=(
                "user: current workstream? | assistant: Maybe Brainstack development "
                "is the current assigned workstream."
            ),
            source="sync_turn",
            metadata={"principal_scope_key": PRINCIPAL_SCOPE},
        )

        report = build_query_inspect(
            store,
            query="Most melyik az aktuális assigned workstream feladatod?",
            session_id="live-canary-session",
            principal_scope_key=PRINCIPAL_SCOPE,
            continuity_match_limit=6,
            transcript_match_limit=6,
            evidence_item_budget=12,
        )

        selected_transcript_ids = {
            int(item["id"]) for item in report["selected_evidence"]["transcript"] if str(item.get("id") or "").isdigit()
        }
        selected_continuity_ids = {
            int(item["id"])
            for item in report["selected_evidence"]["continuity_match"]
            if str(item.get("id") or "").isdigit()
        }
        assert selected_transcript_ids == set()
        assert selected_continuity_ids == set()
        assert any(
            item["suppression_reason"].startswith("assistant_authored_current_assignment_residue")
            for item in report["suppressed_evidence"]
        )
    finally:
        store.close()


def test_assignment_lookup_suppresses_tier2_graph_runtime_state(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.upsert_graph_state(
            subject_name="Tomi",
            attribute="testing_status",
            value_text="active testing of brainstack",
            source="tier2:idle_window",
            metadata={"principal_scope_key": PRINCIPAL_SCOPE, "source_kind": "tier2"},
        )

        report = build_query_inspect(
            store,
            query="Brainstack current assigned workstream feladat",
            session_id="live-canary-session",
            principal_scope_key=PRINCIPAL_SCOPE,
            graph_limit=6,
            evidence_item_budget=12,
        )

        assert report["selected_evidence"]["graph"] == []
        assert any(
            item["shelf"] == "graph"
            and item["suppression_reason"].startswith("tier2_graph_current_assignment_residue")
            for item in report["suppressed_evidence"]
        )
    finally:
        store.close()


def test_recall_tool_marks_runtime_and_profile_as_non_assignment_authority(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        assert provider._store is not None
        provider._store.upsert_profile_item(
            stable_key="shared_work:brainstack-development-status",
            category="shared_work",
            content="Brainstack development status and zero-human workstream",
            source="tier2:idle_window",
            confidence=0.8,
            metadata=provider._scoped_metadata({"source_kind": "tier2_idle_window"}),
        )
        provider._store.upsert_operating_record(
            stable_key="runtime:scheduler:pulse",
            principal_scope_key=PRINCIPAL_SCOPE,
            record_type=OPERATING_RECORD_LIVE_SYSTEM_STATE,
            content="Hermes scheduler job 'Brainstack Proactive Pulse' is scheduled.",
            owner="brainstack.live_system_state",
            source="runtime_handoff:pulse",
            metadata={
                "principal_scope_key": PRINCIPAL_SCOPE,
                "owner_role": "runtime_system",
                "source_kind": "runtime_handoff",
            },
        )

        payload = json.loads(
            provider.handle_tool_call(
                "brainstack_recall",
                {"query": "Brainstack development status zero-human workstream assigned task current"},
            )
        )

        assert payload["model_use_contract"]["primary_answer_source"] == "final_packet.preview"
        assert "Do not determine active work" in payload["model_use_contract"]["current_assignment_negative_rule"]
        assert "profile shared_work" in payload["model_use_contract"]["non_authority_sources"]
        assert (
            "graph/background facts without current_assignment_authority"
            in payload["model_use_contract"]["non_authority_sources"]
        )
        assert "runtime_state_only scheduler or pulse rows" in payload["model_use_contract"]["non_authority_sources"]
        profile_cards = payload["selected_evidence"].get("profile", [])
        operating_cards = payload["selected_evidence"].get("operating", [])
        assert profile_cards
        assert operating_cards
        assert not any(card["current_assignment_authority"] for card in profile_cards)
        assert not any(card["current_assignment_authority"] for card in operating_cards)
        assert all(card["supporting_evidence_only"] for card in operating_cards if card["runtime_state_only"])
    finally:
        provider.shutdown()


def test_unrelated_query_does_not_pull_recent_work_assignment(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        assert provider._store is not None
        committed = json.loads(
            provider.handle_tool_call(
                "brainstack_workstream_recap",
                {
                    "workstream_id": "zero-human-research",
                    "summary": "Zero-human research is the agent assigned workstream.",
                    "source_role": "user",
                    "owner_role": "agent_assignment",
                    "source_kind": "explicit_operating_truth",
                },
            )
        )
        assert committed["status"] == "committed"

        report = build_query_inspect(
            provider._store,
            query="How should corpus citations be handled in a memory packet?",
            session_id="live-canary-session",
            principal_scope_key=PRINCIPAL_SCOPE,
            operating_match_limit=6,
            evidence_item_budget=12,
        )

        assert report["selected_evidence"]["operating"] == []
    finally:
        provider.shutdown()


def test_recall_tool_does_not_surface_assignment_for_unrelated_query(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        committed = json.loads(
            provider.handle_tool_call(
                "brainstack_workstream_recap",
                {
                    "workstream_id": "zero-human-research",
                    "summary": "Zero-human research is the agent assigned workstream.",
                    "source_role": "user",
                    "owner_role": "agent_assignment",
                    "source_kind": "explicit_operating_truth",
                },
            )
        )
        assert committed["status"] == "committed"

        payload = json.loads(
            provider.handle_tool_call(
                "brainstack_recall",
                {"query": "How should corpus citations be handled in a memory packet?"},
            )
        )

        assert payload["model_use_contract"]["primary_answer_source"] == "final_packet.preview"
        assert "Do not determine active work" in payload["model_use_contract"]["current_assignment_negative_rule"]
        assert payload["selected_evidence"].get("operating", []) == []
    finally:
        provider.shutdown()
