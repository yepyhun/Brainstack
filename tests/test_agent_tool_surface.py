from __future__ import annotations

import json
from pathlib import Path

from brainstack import BrainstackMemoryProvider
from scripts.run_persistent_bloat_soak import PRIVATE_SOAK_SENTINEL, seed_persistent_bloat_soak

RAW_TEXT_SENTINEL_KEYS = (
    "raw_text",
    "raw_private_text",
    "full_prompt",
    "prompt_text",
    "message_text",
    "full_text",
    "raw_output",
    "private_value",
)


def _provider(tmp_path: Path) -> BrainstackMemoryProvider:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
        }
    )
    provider.initialize(
        "tool-session",
        platform="test",
        user_id="user",
        agent_identity="agent-smoke",
        agent_workspace="workspace",
    )
    assert provider._store is not None
    return provider


def test_agent_tool_surface_exposes_read_tools_and_schema_gated_capture_tools(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        schemas = provider.get_tool_schemas()
        names = {schema["name"] for schema in schemas}

        assert {
            "brainstack_recall",
            "brainstack_inspect",
            "brainstack_stats",
            "brainstack_proactive_status",
            "brainstack_proactive_list",
            "brainstack_proactive_inspect",
        }.issubset(names)
        assert "brainstack_proactive_control" not in names
        lifecycle = provider.lifecycle_status()
        operator_names = {schema["name"] for schema in lifecycle["operator_only_tools"]}
        assert "brainstack_proactive_control" in operator_names
        assert "brainstack_remember" in names
        assert "brainstack_supersede" in names
        assert "brainstack_invalidate" not in names
        assert "brainstack_consolidate" in names
        assert "runtime_handoff_update" not in names
        for schema in schemas:
            if schema["name"] in {"brainstack_recall", "brainstack_inspect", "brainstack_stats"}:
                assert str(schema.get("x_brainstack_tool_class", "")).startswith("read_only_memory")
            if schema["name"] in {"brainstack_remember", "brainstack_supersede"}:
                assert schema.get("x_brainstack_tool_class") == "explicit_memory_write"
            if schema["name"] == "brainstack_consolidate":
                assert schema.get("x_brainstack_tool_class") == "bounded_memory_maintenance"
            if schema["name"] == "brainstack_proactive_status":
                assert schema.get("x_brainstack_tool_class") == "read_only_proactive_status"
            if schema["name"] == "brainstack_proactive_list":
                assert schema.get("x_brainstack_tool_class") == "read_only_proactive_items"
            if schema["name"] == "brainstack_proactive_inspect":
                assert schema.get("x_brainstack_tool_class") == "read_only_proactive_item_diagnostics"
        operator_schemas = lifecycle["operator_only_tools"]
        for schema in operator_schemas:
            if schema["name"] == "brainstack_proactive_control":
                assert schema.get("x_brainstack_tool_class") == "explicit_proactive_control"
    finally:
        provider.shutdown()


def test_brainstack_recall_tool_returns_evidence_without_mutating_profile(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        assert provider._store is not None
        provider._store.upsert_profile_item(
            stable_key="identity:name",
            category="identity",
            content="ExampleUser uses Brainstack as the memory kernel.",
            source="tool-test",
            confidence=0.99,
            metadata=provider._scoped_metadata(),
        )
        before = provider._store.conn.execute(
            "SELECT metadata_json, updated_at FROM profile_items WHERE content LIKE '%memory kernel%'"
        ).fetchone()

        payload = json.loads(provider.handle_tool_call("brainstack_recall", {"query": "ExampleUser memory kernel"}))

        after = provider._store.conn.execute(
            "SELECT metadata_json, updated_at FROM profile_items WHERE content LIKE '%memory kernel%'"
        ).fetchone()
        assert before is not None and after is not None
        assert dict(before) == dict(after)
        assert payload["schema"] == "brainstack.tool_recall.v1"
        assert payload["read_only"] is True
        assert payload["model_use_contract"]["primary_answer_source"] == "final_packet.preview"
        assert "current_assignment_authority=true" in payload["model_use_contract"]["current_assignment_rule"]
        assert "Do not determine active work" in payload["model_use_contract"]["current_assignment_negative_rule"]
        assert (
            "graph/background facts without current_assignment_authority"
            in payload["model_use_contract"]["non_authority_sources"]
        )
        assert "evidence_count" not in payload
        assert payload["diagnostic_evidence_count"] >= 1
        assert payload["answerable_evidence_count"] >= 1
        assert payload["memory_answerability"]["can_answer"] is True
        assert payload["memory_answerability"]["max_claim_strength"] == "memory_truth"
        assert payload["diagnostic_detail_tool"] == "brainstack_inspect"
        assert payload["selected_evidence"]["profile"]
        assert payload["selected_evidence"]["profile"][0]["current_assignment_authority"] is False
        assert "suppressed_evidence" not in payload
        assert "retrieval_candidates" not in payload
        assert "global_allocator_shadow" not in payload
        assert len(json.dumps(payload, ensure_ascii=False)) < 7000
        assert "ExampleUser" in payload["final_packet"]["preview"]
        raw_payload = provider.handle_tool_call("brainstack_recall", {"query": "ExampleUser memory kernel"})
        assert raw_payload.index('"final_packet"') < raw_payload.index('"selected_evidence"')
    finally:
        provider.shutdown()


def test_disabled_memory_write_tools_return_explicit_phase_gate(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        payload = json.loads(
            provider.handle_tool_call(
                "brainstack_invalidate",
                {"content": "do not write this through a disabled tool"},
            )
        )
        assert payload["schema"] == "brainstack.tool_error.v1"
        assert payload["error_code"] == "tool_disabled_pending_contract"
        assert payload["read_only"] is False
    finally:
        provider.shutdown()


def test_brainstack_stats_tool_wraps_doctor_report(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        assert provider._store is not None
        seed_persistent_bloat_soak(provider._store, iterations=8)
        before_counts = {
            "profile_items": provider._store.conn.execute("SELECT COUNT(*) AS count FROM profile_items").fetchone()["count"],
            "canonical_memory_events": provider._store.conn.execute(
                "SELECT COUNT(*) AS count FROM canonical_memory_events"
            ).fetchone()["count"],
        }

        payload = json.loads(provider.handle_tool_call("brainstack_stats", {"strict": True}))

        after_counts = {
            "profile_items": provider._store.conn.execute("SELECT COUNT(*) AS count FROM profile_items").fetchone()["count"],
            "canonical_memory_events": provider._store.conn.execute(
                "SELECT COUNT(*) AS count FROM canonical_memory_events"
            ).fetchone()["count"],
        }
        rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        bloat = payload["persistent_bloat"]
        assert before_counts == after_counts
        assert payload["schema"] == "brainstack.tool_stats.v1"
        assert payload["read_only"] is True
        assert payload["lifecycle"]["schema"] == "brainstack.provider_lifecycle.v1"
        assert "maintenance" in payload
        assert payload["backend_health"]["schema"] == "brainstack.backend_health_contract.v1"
        assert payload["report"]["schema"] == "brainstack.memory_kernel_doctor.v1"
        assert payload["report"]["strict"] is True
        assert bloat["schema"] == "brainstack.persistent_bloat_report.v1"
        assert bloat["read_only"] is True
        assert bloat["public_safe"] is True
        assert isinstance(bloat["issue_count"], int)
        assert set(bloat["metrics"]) >= {
            "write_amplification",
            "duplicate_strength_inflation",
            "support_only_accumulation",
            "active_packet_growth",
            "stale_prior_retention",
            "projection_rebuild_size",
        }
        assert "policy_preview" in bloat
        assert "critical_counters" in bloat
        assert PRIVATE_SOAK_SENTINEL not in rendered
        for forbidden_key in RAW_TEXT_SENTINEL_KEYS:
            assert f'"{forbidden_key}"' not in rendered
    finally:
        provider.shutdown()
