"""Pragmatic real-world scenario tests for the current Brainstack layer."""

from pathlib import Path
import threading
import time

from plugins.memory.brainstack.extraction_pipeline import build_turn_ingest_plan
from plugins.memory.brainstack.provenance import merge_provenance, summarize_provenance
from plugins.memory.brainstack.reconciler import reconcile_tier2_candidates
from plugins.memory.brainstack.stable_memory_guardrails import should_admit_stable_memory
from plugins.memory.brainstack import BrainstackMemoryProvider
from plugins.memory.brainstack.temporal import normalize_temporal_fields, record_is_effective_at
from plugins.memory.brainstack.tier2_extractor import extract_tier2_candidates


def _make_provider(tmp_path, session_id):
    base = Path(tmp_path)
    provider = BrainstackMemoryProvider(config={"db_path": str(base / "brainstack.db")})
    provider.initialize(session_id, hermes_home=str(base))
    return provider


class TestBrainstackRealWorldFlows:
    def test_temporal_and_provenance_helpers_are_normalized_and_bounded(self):
        temporal = normalize_temporal_fields(
            observed_at="2026-04-11T10:00:00Z",
            valid_at="2026-04-11T10:05:00Z",
            supersedes="state-1",
        )
        assert temporal["observed_at"].startswith("2026-04-11T10:00:00")
        assert temporal["valid_from"].startswith("2026-04-11T10:05:00")
        assert temporal["supersedes"] == "state-1"

        effective = record_is_effective_at(
            {
                "valid_from": "2026-04-11T10:00:00+00:00",
                "valid_to": "2026-04-11T12:00:00+00:00",
                "metadata": {},
            },
            as_of="2026-04-11T11:00:00+00:00",
        )
        expired = record_is_effective_at(
            {
                "valid_from": "2026-04-11T10:00:00+00:00",
                "valid_to": "2026-04-11T12:00:00+00:00",
                "metadata": {},
            },
            as_of="2026-04-11T13:00:00+00:00",
        )
        assert effective is True
        assert expired is False

        provenance = merge_provenance(
            {"source_ids": ["tier2:test"], "turn_number": 1},
            {"source_ids": ["sync_turn", "tier2:test"], "admission_reason": "allowed"},
        )
        assert provenance["source_ids"] == ["sync_turn", "tier2:test"]
        assert summarize_provenance(provenance).startswith("sources=")

    def test_tier0_hygiene_rejects_known_noise_families_but_allows_direct_self_statement(self):
        blocked = {
            "markdown_table": "| Column | Value |\n| --- | --- |\n| Preference | concise |",
            "code_blob": "```python\nprint('prefer concise answers')\nreturn True\n```",
            "quoted_transcript_dump": "User: I prefer concise answers.\nAssistant: Noted.\nUser: We are working on Atlas.",
            "document_wrapper": (
                "Attached file\n"
                "File name: medical_notes.pdf\n"
                "Pages: 12-13\n"
                "Excerpt:\n"
                "The patient notes are listed here."
            ),
            "structured_technical_blob": (
                "# Architecture review\n"
                "- Tier-0 ingest hygiene\n"
                "- Tier-1 bootstrap extractor\n"
                "- Tier-2 multilingual worker\n"
                "- Reconciler slot\n"
                "- Write-policy slot"
            ),
        }

        for reason, content in blocked.items():
            decision = should_admit_stable_memory(fact_text=content)
            assert decision.allowed is False
            assert decision.reason == reason

        allowed = should_admit_stable_memory(
            fact_text="My name is Tomi. I prefer short Hungarian answers."
        )
        assert allowed.allowed is True
        assert allowed.reason == "allowed"

    def test_sync_turn_blocks_noise_profile_but_keeps_raw_transcript(self, tmp_path):
        provider = _make_provider(tmp_path, "session-noise")
        try:
            noise = (
                "| Graph | State |\n"
                "| --- | --- |\n"
                "| Preference | concise |\n"
                "| Project | Atlas |\n"
            )
            provider.sync_turn(noise, "Ignored.", session_id="session-noise")

            profile_rows = provider._store.list_profile_items(limit=10)
            transcript_rows = provider._store.recent_transcript(session_id="session-noise", limit=10)
            continuity_rows = provider._store.recent_continuity(session_id="session-noise", limit=10)

            assert profile_rows == []
            assert any("User:" in row["content"] for row in transcript_rows)
            assert any(row["kind"] == "turn" for row in continuity_rows)
        finally:
            provider.shutdown()

    def test_turn_ingest_plan_exposes_batch_schedule_seam(self):
        waiting = build_turn_ingest_plan(
            user_content="I prefer concise answers.",
            pending_turns=4,
            idle_seconds=5,
            idle_window_seconds=30,
            batch_turn_limit=5,
        )
        assert waiting.tier2_schedule.should_queue is False
        assert waiting.tier2_schedule.reason == "waiting_for_batch"
        assert waiting.tier2_schedule.pending_turns == 4

        queued = build_turn_ingest_plan(
            user_content="I prefer concise answers.",
            pending_turns=5,
            idle_seconds=5,
            idle_window_seconds=30,
            batch_turn_limit=5,
        )
        assert queued.tier2_schedule.should_queue is True
        assert queued.tier2_schedule.reason == "turn_batch_limit"
        assert queued.tier2_schedule.pending_turns == 0

    def test_cross_session_prefetch_recalls_preference_and_shared_work(self, tmp_path):
        writer = _make_provider(tmp_path, "session-a")
        try:
            writer.sync_turn(
                "My name is Laura. I prefer concise answers. We are working on Project Atlas.",
                "Understood. I will keep answers concise and continue Project Atlas.",
                session_id="session-a",
            )
            writer.on_session_end(
                [
                    {
                        "role": "user",
                        "content": "My name is Laura. I prefer concise answers. We are working on Project Atlas.",
                    },
                    {
                        "role": "assistant",
                        "content": "Understood. I will keep answers concise and continue Project Atlas.",
                    },
                ]
            )
        finally:
            writer.shutdown()

        reader = _make_provider(tmp_path, "session-b")
        try:
            block = reader.prefetch(
                "Do I prefer concise answers and what project are we working on?",
                session_id="session-b",
            )
            assert "## Brainstack Profile Match" in block
            assert "I prefer concise answers" in block
            assert "We are working on Project Atlas" in block
            assert "## Brainstack Continuity Match" in block
        finally:
            reader.shutdown()

    def test_temporal_graph_truth_shows_current_and_prior_state(self, tmp_path):
        provider = _make_provider(tmp_path, "session-graph")
        try:
            provider.sync_turn("Project Atlas is active.", "Noted.", session_id="session-graph")
            provider.sync_turn("Project Atlas is paused now.", "Noted, current status paused.", session_id="session-graph")

            block = provider.prefetch(
                "What is the current status of Project Atlas and what changed?",
                session_id="session-graph",
            )
            assert "## Brainstack Graph Truth" in block
            assert "[state:current] Project Atlas status=paused" in block
            assert "[state:prior] Project Atlas status=active" in block
        finally:
            provider.shutdown()

    def test_non_temporal_graph_query_prefers_current_truth_without_history_spam(self, tmp_path):
        provider = _make_provider(tmp_path, "session-graph-compact")
        try:
            provider.sync_turn("Project Atlas is active.", "Noted.", session_id="session-graph-compact")
            provider.sync_turn("Project Atlas is paused now.", "Noted.", session_id="session-graph-compact")

            block = provider.prefetch(
                "Project Atlas status?",
                session_id="session-graph-compact",
            )
            assert "[state:current] Project Atlas status=paused" in block
            assert "[state:prior] Project Atlas status=active" not in block
        finally:
            provider.shutdown()

    def test_corpus_recall_returns_relevant_bounded_document_sections(self, tmp_path):
        provider = _make_provider(tmp_path, "session-corpus")
        try:
            result = provider.ingest_corpus_document(
                title="Biochemistry Notes",
                content=(
                    "## Citrate cycle\n"
                    "The citrate cycle connects carbohydrate metabolism to ATP production.\n"
                    "## Glycolysis\n"
                    "Glycolysis happens in the cytosol."
                ),
                source="unit-test",
            )
            assert result["section_count"] >= 2

            block = provider.prefetch(
                "How does the citrate cycle connect to energy production?",
                session_id="session-corpus",
            )
            assert "## Brainstack Corpus Recall" in block
            assert "Biochemistry Notes > Citrate cycle" in block
            assert "ATP production" in block
            assert len(block) < 1600
        finally:
            provider.shutdown()

    def test_tier2_extractor_normalizes_multilingual_json_payload(self):
        def _fake_llm(**kwargs):
            return {
                "content": """
                {
                  "profile_items": [
                    {"category": "identity", "content": "User identity: Tomi", "slot": "identity:name", "confidence": 0.96},
                    {"category": "preference", "content": "Prefer Hungarian replies", "confidence": 0.91}
                  ],
                  "states": [
                    {"subject": "Tomi", "attribute": "location", "value": "Debrecen", "supersede": true, "confidence": 0.88}
                  ],
                  "relations": [
                    {"subject": "Tomi", "predicate": "works on", "object": "Brainstack integration", "confidence": 0.82}
                  ],
                  "continuity_summary": "Tomi currently lives in Debrecen and prefers Hungarian replies.",
                  "decisions": ["Brainstack remains the primary memory path."]
                }
                """
            }

        rows = [
            {
                "id": 1,
                "turn_number": 4,
                "kind": "turn",
                "content": "User: Tomi a nevem. Debrecenben élek.\nAssistant: Rendben.",
            }
        ]
        extracted = extract_tier2_candidates(rows, llm_caller=_fake_llm, transcript_limit=4)

        assert extracted["profile_items"][0]["slot"] == "identity:name"
        assert extracted["states"][0]["attribute"] == "location"
        assert extracted["relations"][0]["predicate"] == "works_on"
        assert "Debrecen" in extracted["continuity_summary"]
        assert extracted["decisions"] == ["Brainstack remains the primary memory path."]

    def test_tier2_reconciler_updates_current_state_and_surfaces_conflict(self, tmp_path):
        provider = _make_provider(tmp_path, "session-tier2-reconcile")
        try:
            reconcile_tier2_candidates(
                provider._store,
                session_id="session-tier2-reconcile",
                turn_number=1,
                source="tier2:test",
                extracted={
                    "profile_items": [{"category": "identity", "content": "User identity: Tomi", "slot": "identity:name", "confidence": 0.95}],
                    "states": [{"subject": "Tomi", "attribute": "location", "value": "Budapest", "supersede": False, "confidence": 0.9}],
                    "relations": [],
                    "continuity_summary": "",
                    "decisions": [],
                },
            )
            reconcile_tier2_candidates(
                provider._store,
                session_id="session-tier2-reconcile",
                turn_number=2,
                source="tier2:test",
                extracted={
                    "profile_items": [{"category": "identity", "content": "User identity: Tomi", "slot": "identity:name", "confidence": 0.95}],
                    "states": [{
                        "subject": "Tomi",
                        "attribute": "location",
                        "value": "Debrecen",
                        "supersede": True,
                        "confidence": 0.91,
                        "metadata": {"provenance": {"trace_id": "tier2-second-pass"}},
                    }],
                    "relations": [{"subject": "Tomi", "predicate": "works_on", "object": "Brainstack integration", "confidence": 0.82}],
                    "continuity_summary": "Tomi moved from Budapest to Debrecen.",
                    "decisions": ["Brainstack remains the memory owner."],
                },
            )
            report = reconcile_tier2_candidates(
                provider._store,
                session_id="session-tier2-reconcile",
                turn_number=3,
                source="tier2:test",
                extracted={
                    "profile_items": [],
                    "states": [{"subject": "Tomi", "attribute": "location", "value": "Szeged", "supersede": False, "confidence": 0.7}],
                    "relations": [{"subject": "Tomi", "predicate": "works_on", "object": "Brainstack integration", "confidence": 0.82}],
                    "continuity_summary": "Tomi still prefers Brainstack.",
                    "decisions": ["Brainstack remains the memory owner."],
                },
            )

            block = provider.prefetch("Where does Tomi live now and what changed?", session_id="session-tier2-reconcile")
            conflicts = provider._store.list_graph_conflicts(limit=10)

            assert "Debrecen" in block
            assert "Budapest" in block
            assert any(action["action"] == "CONFLICT" for action in report["actions"])
            assert any(conflict["candidate_value_text"] == "Szeged" for conflict in conflicts)
            current_location = next(
                row for row in provider._store.search_graph(query="Debrecen", limit=10)
                if row["row_type"] == "state" and row.get("is_current")
            )
            assert current_location["metadata"]["temporal"]["supersedes"]
            assert "tier2:test" in current_location["metadata"]["provenance"]["source_ids"]
        finally:
            provider.shutdown()

    def test_conflict_prefetch_surfaces_bounded_basis_when_provenance_expands(self, tmp_path):
        provider = _make_provider(tmp_path, "session-conflict-basis")
        try:
            reconcile_tier2_candidates(
                provider._store,
                session_id="session-conflict-basis",
                turn_number=1,
                source="tier2:test",
                extracted={
                    "profile_items": [],
                    "states": [{
                        "subject": "Tomi",
                        "attribute": "location",
                        "value": "Debrecen",
                        "supersede": False,
                        "confidence": 0.92,
                        "metadata": {"provenance": {"trace_id": "state-1"}},
                    }],
                    "relations": [],
                    "continuity_summary": "",
                    "decisions": [],
                },
            )
            reconcile_tier2_candidates(
                provider._store,
                session_id="session-conflict-basis",
                turn_number=2,
                source="tier2:test",
                extracted={
                    "profile_items": [],
                    "states": [{
                        "subject": "Tomi",
                        "attribute": "location",
                        "value": "Szeged",
                        "supersede": False,
                        "confidence": 0.51,
                        "metadata": {"provenance": {"trace_id": "state-2"}},
                    }],
                    "relations": [],
                    "continuity_summary": "",
                    "decisions": [],
                },
            )
            block = provider.prefetch("Where does Tomi live now?", session_id="session-conflict-basis")
            assert "[conflict] Tomi location current=Debrecen candidate=Szeged" in block
            assert "candidate_source=tier2:test" in block
            assert "sources=tier2:test" in block
        finally:
            provider.shutdown()

    def test_sync_turn_stays_non_blocking_when_tier2_runs_in_background(self, tmp_path):
        def _slow_extractor(rows, **kwargs):
            time.sleep(0.25)
            return {
                "profile_items": [{"category": "preference", "content": "Prefer Hungarian replies", "confidence": 0.9}],
                "states": [],
                "relations": [],
                "continuity_summary": "User prefers Hungarian replies.",
                "decisions": [],
            }

        base = Path(tmp_path)
        provider = BrainstackMemoryProvider(
            config={
                "db_path": str(base / "brainstack.db"),
                "tier2_batch_turn_limit": 1,
                "_tier2_extractor": _slow_extractor,
            }
        )
        provider.initialize("session-tier2-bg", hermes_home=str(base))
        try:
            start = time.monotonic()
            provider.sync_turn("Kérlek, magyarul válaszolj.", "Rendben.", session_id="session-tier2-bg")
            elapsed = time.monotonic() - start

            assert elapsed < 0.15
            assert provider._wait_for_tier2_worker(timeout=1.0) is True

            profile_rows = provider._store.list_profile_items(limit=10)
            assert any("Prefer Hungarian replies" == row["content"] for row in profile_rows)
        finally:
            provider.shutdown()

    def test_tier2_followup_work_is_not_dropped_while_worker_is_running(self, tmp_path):
        started = threading.Event()
        release = threading.Event()
        calls = []

        def _blocking_extractor(rows, **kwargs):
            batch_text = "\n".join(str(row["content"]) for row in rows)
            calls.append(batch_text)
            if len(calls) == 1:
                started.set()
                release.wait(timeout=1.0)
            if "Debrecenben élek" in batch_text:
                return {
                    "profile_items": [],
                    "states": [{"subject": "Tomi", "attribute": "location", "value": "Debrecen", "supersede": True, "confidence": 0.88}],
                    "relations": [],
                    "continuity_summary": "Tomi currently lives in Debrecen.",
                    "decisions": [],
                }
            return {
                "profile_items": [{"category": "identity", "content": "User identity: Tomi", "slot": "identity:name", "confidence": 0.95}],
                "states": [],
                "relations": [],
                "continuity_summary": "",
                "decisions": [],
            }

        base = Path(tmp_path)
        provider = BrainstackMemoryProvider(
            config={
                "db_path": str(base / "brainstack.db"),
                "tier2_batch_turn_limit": 1,
                "_tier2_extractor": _blocking_extractor,
            }
        )
        provider.initialize("session-followup", hermes_home=str(base))
        try:
            provider.sync_turn("Tomi a nevem.", "Ok.", session_id="session-followup")
            assert started.wait(timeout=1.0) is True

            provider.sync_turn("Debrecenben élek.", "Ok.", session_id="session-followup")
            release.set()

            assert provider._wait_for_tier2_worker(timeout=2.0) is True

            block = provider.prefetch("Hol lakik Tomi most?", session_id="session-followup")
            assert len(calls) >= 2
            assert any("Debrecenben élek" in batch for batch in calls)
            assert "Debrecen" in block
        finally:
            provider.shutdown()

    def test_on_session_end_flushes_pending_tier2_work(self, tmp_path):
        base = Path(tmp_path)
        provider = BrainstackMemoryProvider(
            config={
                "db_path": str(base / "brainstack.db"),
                "tier2_batch_turn_limit": 9,
                "_tier2_extractor": lambda rows, **kwargs: {
                    "profile_items": [{"category": "shared_work", "content": "We are working on Brainstack integration", "confidence": 0.84}],
                    "states": [],
                    "relations": [{"subject": "Tomi", "predicate": "works_on", "object": "Brainstack integration", "confidence": 0.82}],
                    "continuity_summary": "Current work focuses on Brainstack integration.",
                    "decisions": ["Built-in memory stays displaced."],
                },
            }
        )
        provider.initialize("session-end-flush", hermes_home=str(base))
        try:
            provider.sync_turn("Most a Brainstack integráción dolgozunk.", "Rendben.", session_id="session-end-flush")
            provider.on_session_end(
                [
                    {"role": "user", "content": "Most a Brainstack integráción dolgozunk."},
                    {"role": "assistant", "content": "Rendben."},
                ]
            )

            profile_rows = provider._store.list_profile_items(limit=10, categories=["shared_work"])
            graph_rows = provider._store.search_graph(query="Brainstack integration", limit=10)
            continuity_rows = provider._store.recent_continuity(session_id="session-end-flush", limit=10)

            assert any("Brainstack integration" in row["content"] for row in profile_rows)
            assert any(row["row_type"] == "relation" and row["object_value"] == "Brainstack integration" for row in graph_rows)
            assert any(row["kind"] == "decision" and "Built-in memory stays displaced" in row["content"] for row in continuity_rows)
            assert provider._pending_tier2_turns == 0
        finally:
            provider.shutdown()
