# ruff: noqa: E402

from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from tests._host_import_shims import install_host_import_shims

install_host_import_shims(hermes_home=REPO_ROOT)

from brainstack import BrainstackMemoryProvider
from brainstack.extraction_pipeline import build_turn_ingest_plan


def _make_provider(tmp_path: Path, session_id: str) -> BrainstackMemoryProvider:
    provider = BrainstackMemoryProvider(
        config={
            "db_path": str(tmp_path / "brainstack.db"),
            "graph_backend": "none",
            "corpus_backend": "none",
        }
    )
    provider.initialize(
        session_id,
        hermes_home=str(tmp_path),
        user_id="user-1",
        platform="discord",
        agent_identity="assistant-main",
        agent_workspace="workspace-a",
    )
    return provider


def test_live_turn_ingest_keeps_graph_empty_without_explicit_typed_evidence():
    plan = build_turn_ingest_plan(
        user_content="Project Atlas is active now. Laura is in Budapest.",
        pending_turns=0,
        idle_seconds=60.0,
        idle_window_seconds=30,
        batch_turn_limit=5,
    )

    assert plan.graph_evidence_items == []


def test_tier2_typed_service_provider_claims_still_surface_exact_graph_value(tmp_path: Path) -> None:
    provider = _make_provider(tmp_path, "phase40.3-tier2-graph")
    try:
        provider.sync_turn(
            "Jegyezd meg: Móni címe Kassák Lajos 87 44es kapucsengő 4em.",
            "Megjegyeztem.",
            session_id="phase40.3-tier2-graph",
        )
        trace = provider.graph_ingress_trace()
        assert trace is not None
        assert trace["status"] == "skipped_no_typed_graph_evidence"

        def _fake_tier2_extractor(transcript_rows, **kwargs):
            return {
                "profile_items": [],
                "style_contract": None,
                "states": [],
                "relations": [],
                "inferred_relations": [],
                "typed_entities": [
                    {
                        "turn_number": 1,
                        "name": "Móni",
                        "entity_type": "service_provider",
                        "subject": "User",
                        "attributes": {
                            "address": "Kassák Lajos 87 44es kapucsengő 4em",
                            "category": "talpmasszázs",
                        },
                        "confidence": 0.86,
                        "metadata": {"event_turn_number": 1, "source": "tier2_transcript_rule"},
                    }
                ],
                "temporal_events": [],
                "continuity_summary": "",
                "decisions": [],
                "_meta": {
                    "json_parse_status": "json_object",
                    "parse_context": "turns=[1]",
                    "raw_payload_preview": "{\"typed_entities\": 1}",
                    "raw_payload_tail": "{\"typed_entities\": 1}",
                    "raw_payload_length": 21,
                },
            }

        provider._config["_tier2_extractor"] = _fake_tier2_extractor
        result = provider._run_tier2_batch(
            session_id="phase40.3-tier2-graph",
            turn_number=1,
            trigger_reason="unit-test-flush",
        )

        assert result["status"] == "ok"
        rows = provider._store.search_graph(query="Móni Kassák talpmasszázs", limit=20)
        assert any(
            row["row_type"] == "state"
            and row["subject"] == "Móni"
            and row["predicate"] == "entity_type"
            and row["object_value"] == "service_provider"
            for row in rows
        )
        assert any(
            row["row_type"] == "state"
            and row["subject"] == "Móni"
            and row["predicate"] == "owner_subject"
            and row["object_value"] == "User"
            for row in rows
        )
        assert any(
            row["row_type"] == "state"
            and row["subject"] == "Móni"
            and row["predicate"] == "address"
            and "Kassák Lajos 87" in row["object_value"]
            for row in rows
        )
    finally:
        provider.shutdown()
