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


def _make_provider(tmp_path, session_id, **init_kwargs):
    base = Path(tmp_path)
    provider = BrainstackMemoryProvider(config={"db_path": str(base / "brainstack.db")})
    provider.initialize(session_id, hermes_home=str(base), **init_kwargs)
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
        assert waiting.profile_candidates == []

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
        assert queued.profile_candidates == []

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
            assert "## Brainstack Continuity Match" in block
            assert "I prefer concise answers" in block
            assert "We are working on Project Atlas" in block
        finally:
            reader.shutdown()

    def test_same_session_prefetch_surfaces_fresh_style_preferences_through_recent_continuity(self, tmp_path):
        provider = _make_provider(tmp_path, "session-style")
        try:
            provider.sync_turn(
                (
                    "Tominak hívnak 19 éves vagyok. "
                    "Nem developer vagyok, kerüld a szakzsargont, "
                    "könnyen megérthetően fogalmazz. "
                    "Ne használj emojikat."
                ),
                "Értettem.",
                session_id="session-style",
            )

            block = provider.prefetch(
                "Segíts átgondolni a BrainStack projekt következő lépését.",
                session_id="session-style",
            )

            assert "## Brainstack Recent Continuity" in block or "## Brainstack Continuity Match" in block
            assert "kerüld a szakzsargont" in block
            assert "Ne használj emojikat" in block
            assert "## Brainstack Profile Match" not in block
        finally:
            provider.shutdown()

    def test_initialize_resets_stale_session_runtime_state(self, tmp_path):
        provider = _make_provider(tmp_path, "session-a", user_id="user-a", platform="discord")
        try:
            provider._turn_counter = 9
            provider._last_prefetch_policy = {"route": "fact"}
            provider._last_prefetch_routing = {"mode": "temporal"}
            provider._last_prefetch_channels = [{"name": "graph"}]
            provider._last_prefetch_debug = {"selected_rows": {"matched": []}}
            provider._last_tier2_schedule = {"reason": "waiting_for_batch"}
            provider._last_tier2_batch_result = {"status": "ok"}
            provider._tier2_batch_history = [{"status": "ok"}]
            provider._pending_tier2_turns = 3
            provider._last_turn_monotonic = 123.0
            provider._tier2_followup_requested = True
            provider._tier2_running = True
            provider.initialize("session-b", hermes_home=str(tmp_path), user_id="user-b", platform="discord")

            assert provider._session_id == "session-b"
            assert provider._turn_counter == 0
            assert provider._last_prefetch_policy is None
            assert provider._last_prefetch_routing is None
            assert provider._last_prefetch_channels == []
            assert provider._last_prefetch_debug is None
            assert provider._last_tier2_schedule is None
            assert provider._last_tier2_batch_result is None
            assert provider._tier2_batch_history == []
            assert provider._pending_tier2_turns == 0
            assert provider._last_turn_monotonic is None
            assert provider._tier2_followup_requested is False
            assert provider._tier2_running is False
            assert provider._principal_scope_key == "platform:discord|user_id:user-b"
        finally:
            provider.shutdown()

    def test_initialize_refuses_to_reset_runtime_state_while_tier2_worker_is_still_running(self, tmp_path, monkeypatch):
        provider = _make_provider(tmp_path, "session-a", user_id="user-a", platform="discord")
        original_store = provider._store
        try:
            provider._turn_counter = 4
            provider._pending_tier2_turns = 2
            provider._tier2_running = True
            monkeypatch.setattr(provider, "_wait_for_tier2_worker", lambda **kwargs: False)

            try:
                provider.initialize("session-b", hermes_home=str(tmp_path), user_id="user-b", platform="discord")
            except RuntimeError as exc:
                assert "Tier-2 worker is still running" in str(exc)
            else:
                raise AssertionError("initialize should fail closed while the Tier-2 worker is still running")

            assert provider._store is original_store
            assert provider._session_id == "session-a"
            assert provider._turn_counter == 4
            assert provider._pending_tier2_turns == 2
            assert provider._tier2_running is True
            assert provider._principal_scope_key == "platform:discord|user_id:user-a"
        finally:
            monkeypatch.setattr(provider, "_wait_for_tier2_worker", lambda **kwargs: True)
            provider.shutdown()

    def test_shutdown_refuses_to_reset_runtime_state_while_tier2_worker_is_still_running(self, tmp_path, monkeypatch):
        provider = _make_provider(tmp_path, "session-a", user_id="user-a", platform="discord")
        original_store = provider._store
        try:
            provider._turn_counter = 4
            provider._pending_tier2_turns = 2
            provider._tier2_running = True
            monkeypatch.setattr(provider, "_wait_for_tier2_worker", lambda **kwargs: False)

            provider.shutdown()

            assert provider._store is original_store
            assert provider._session_id == "session-a"
            assert provider._turn_counter == 4
            assert provider._pending_tier2_turns == 2
            assert provider._tier2_running is True
        finally:
            monkeypatch.setattr(provider, "_wait_for_tier2_worker", lambda **kwargs: True)
            provider.shutdown()

    def test_cross_session_prefetch_stays_within_same_principal_scope(self, tmp_path):
        writer_a = _make_provider(tmp_path, "session-a", user_id="user-a", platform="discord")
        try:
            writer_a.sync_turn(
                "My usual coffee order is an oat flat white, extra hot, with no vanilla syrup.",
                "Understood.",
                session_id="session-a",
            )
        finally:
            writer_a.shutdown()

        writer_b = _make_provider(tmp_path, "session-b", user_id="user-b", platform="discord")
        try:
            writer_b.sync_turn(
                "My usual coffee order is a vanilla cold brew with caramel foam.",
                "Understood.",
                session_id="session-b",
            )
        finally:
            writer_b.shutdown()

        reader = _make_provider(tmp_path, "session-c", user_id="user-a", platform="discord")
        try:
            block = reader.prefetch(
                "What is my usual coffee order?",
                session_id="session-c",
            )
            assert "oat flat white" in block
            assert "vanilla cold brew" not in block
        finally:
            reader.shutdown()

    def test_cross_session_graph_truth_stays_within_same_principal_scope(self, tmp_path):
        writer_a = _make_provider(tmp_path, "session-graph-a", user_id="user-a", platform="discord")
        try:
            writer_a.sync_turn("Project Atlas is active now.", "Understood.", session_id="session-graph-a")
        finally:
            writer_a.shutdown()

        writer_b = _make_provider(tmp_path, "session-graph-b", user_id="user-b", platform="discord")
        try:
            writer_b.sync_turn("Project Atlas is archived now.", "Understood.", session_id="session-graph-b")
        finally:
            writer_b.shutdown()

        reader = _make_provider(tmp_path, "session-graph-c", user_id="user-a", platform="discord")
        try:
            graph_rows = reader._store.search_graph(
                query="Project Atlas status",
                principal_scope_key=reader._principal_scope_key,
                limit=10,
            )
            assert graph_rows
            assert any(
                row.get("predicate") == "status" and str(row.get("object_value") or "") == "active"
                for row in graph_rows
            )
            assert not any(str(row.get("object_value") or "") == "archived" for row in graph_rows)
        finally:
            reader.shutdown()

    def test_system_prompt_block_stays_within_same_principal_scope(self, tmp_path):
        writer_a = _make_provider(tmp_path, "session-prompt-a", user_id="user-a", platform="discord")
        try:
            writer_a.on_memory_write("add", "user", "I prefer concise answers.")
        finally:
            writer_a.shutdown()

        writer_b = _make_provider(tmp_path, "session-prompt-b", user_id="user-b", platform="discord")
        try:
            writer_b.on_memory_write("add", "user", "I prefer extremely detailed answers with lots of examples.")
        finally:
            writer_b.shutdown()

        reader = _make_provider(tmp_path, "session-prompt-c", user_id="user-a", platform="discord")
        try:
            block = reader.system_prompt_block()
            assert "I prefer concise answers." in block
            assert "extremely detailed answers" not in block
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

    def test_tier2_extractor_normalizes_bounded_inferred_relations(self):
        def _fake_llm(**kwargs):
            return {
                "content": """
                {
                  "profile_items": [],
                  "states": [],
                  "relations": [],
                  "inferred_relations": [
                    {
                      "subject": "Tomi",
                      "predicate": "depends on",
                      "object": "Hermes Bestie",
                      "confidence": 0.61,
                      "reason": "BrainStack was described as Tomi's project and as integrated into Hermes Bestie."
                    }
                  ],
                  "continuity_summary": "",
                  "decisions": []
                }
                """
            }

        rows = [
            {
                "id": 1,
                "turn_number": 5,
                "kind": "turn",
                "content": "User: A BrainStacken dolgozom, és ezt kötjük rá a Hermes Bestie-re.\nAssistant: Rendben.",
            }
        ]
        extracted = extract_tier2_candidates(rows, llm_caller=_fake_llm, transcript_limit=4)

        assert extracted["inferred_relations"][0]["predicate"] == "depends_on"
        assert extracted["inferred_relations"][0]["metadata"]["inference_reason"].startswith("BrainStack")

    def test_tier2_extractor_normalizes_temporal_events_against_real_turns(self):
        def _fake_llm(**kwargs):
            return {
                "content": """
                {
                  "profile_items": [],
                  "states": [],
                  "relations": [],
                  "inferred_relations": [],
                  "temporal_events": [
                    {"turn_number": 11, "content": "Family trip to Muir Woods National Monument", "confidence": 0.88},
                    {"turn_number": 99, "content": "Invalid event outside the batch", "confidence": 0.9},
                    {"turn_number": 12, "content": "", "confidence": 0.7}
                  ],
                  "continuity_summary": "",
                  "decisions": []
                }
                """
            }

        rows = [
            {
                "id": 1,
                "turn_number": 11,
                "kind": "turn",
                "created_at": "2026-04-11T09:15:00Z",
                "content": "User: We went to Muir Woods National Monument with family.\nAssistant: Nice.",
            },
            {
                "id": 2,
                "turn_number": 12,
                "kind": "turn",
                "created_at": "2026-04-12T10:30:00Z",
                "content": "User: I also planned Yosemite later.\nAssistant: Noted.",
            },
        ]

        extracted = extract_tier2_candidates(rows, llm_caller=_fake_llm, transcript_limit=4)

        assert extracted["temporal_events"] == [
            {
                "turn_number": 11,
                "content": "Family trip to Muir Woods National Monument",
                "confidence": 0.88,
                "metadata": {"event_turn_number": 11},
                "temporal": {"observed_at": "2026-04-11T09:15:00Z"},
            }
        ]

    def test_tier2_extractor_normalizes_typed_entities_against_real_turns(self):
        def _fake_llm(**kwargs):
            return {
                "content": """
                {
                  "profile_items": [],
                  "states": [],
                  "relations": [],
                  "inferred_relations": [],
                  "typed_entities": [
                    {
                      "turn_number": 84,
                      "name": "Yellowstone family road trip",
                      "entity_type": "road trip",
                      "subject": "User",
                      "attributes": {
                        "distance miles": "1,200 miles",
                        "destination": "Yellowstone National Park"
                      },
                      "confidence": 0.91
                    },
                    {
                      "turn_number": 99,
                      "name": "Invalid outside batch",
                      "entity_type": "road trip",
                      "attributes": {"distance_miles": "300"}
                    }
                  ],
                  "temporal_events": [],
                  "continuity_summary": "",
                  "decisions": []
                }
                """
            }

        rows = [
            {
                "id": 1,
                "turn_number": 84,
                "kind": "turn",
                "created_at": "2026-04-11T09:15:00Z",
                "content": "User: I just got back from Yellowstone with my family after a 1,200 mile road trip.\nAssistant: Nice.",
            }
        ]

        extracted = extract_tier2_candidates(rows, llm_caller=_fake_llm, transcript_limit=4)

        assert extracted["typed_entities"] == [
            {
                "turn_number": 84,
                "name": "Yellowstone family road trip",
                "entity_type": "road_trip",
                "subject": "User",
                "attributes": {
                    "distance_miles": "1200",
                    "destination": "Yellowstone National Park",
                },
                "confidence": 0.91,
                "metadata": {"event_turn_number": 84},
                "temporal": {"observed_at": "2026-04-11T09:15:00Z"},
            }
        ]

    def test_tier2_extractor_empty_batch_keeps_temporal_events_schema(self):
        extracted = extract_tier2_candidates([], llm_caller=lambda **kwargs: {"content": "{}"})

        assert extracted["temporal_events"] == []
        assert extracted["inferred_relations"] == []
        assert extracted["typed_entities"] == []

    def test_tier2_extractor_repairs_truncated_json_tail(self):
        truncated = (
            '{"profile_items":[],"states":[],"relations":[],"inferred_relations":[],"temporal_events":'
            '[{"turn_number":230,"content":"Solo camping trip to Yosemite National Park","confidence":0.95},'
            '{"turn_number":233,"content":"Bear canister confirmed for John Muir Wilderness","confidence":0.9}],'
            '"continuity_summary":"Trip planning context","decisions":["Plan Eastern Sierra route"'
        )

        response = type(
            "Response",
            (),
            {
                "choices": [
                    type(
                        "Choice",
                        (),
                        {"message": type("Message", (), {"content": truncated})()},
                    )()
                ]
            },
        )()

        extracted = extract_tier2_candidates(
            [
                {
                    "turn_number": 230,
                    "kind": "turn",
                    "created_at": "2026-04-13T11:00:00Z",
                    "content": "User: I just got back from Yosemite and I'm planning Eastern Sierra next.\nAssistant: Noted.",
                },
                {
                    "turn_number": 233,
                    "kind": "turn",
                    "created_at": "2026-04-13T11:10:00Z",
                    "content": "User: I already have a bear canister for John Muir Wilderness.\nAssistant: Good.",
                },
            ],
            llm_caller=lambda **kwargs: response,
        )

        assert extracted["_meta"]["json_parse_status"] == "json_repaired"
        assert [item["turn_number"] for item in extracted["temporal_events"]] == [230, 233]
        assert extracted["continuity_summary"] == "Trip planning context"

    def test_tier2_extractor_uses_reasoning_content_when_message_content_empty(self):
        response = type(
            "Response",
            (),
            {
                "choices": [
                    type(
                        "Choice",
                        (),
                        {
                            "message": type(
                                "Message",
                                (),
                                {
                                    "content": "",
                                    "reasoning_content": (
                                        '{"profile_items":[],"states":[],"relations":[],"inferred_relations":[],'
                                        '"temporal_events":[{"turn_number":230,"content":"Returned from Yosemite trip","confidence":0.9}],'
                                        '"continuity_summary":"","decisions":[]}'
                                    ),
                                },
                            )(),
                        },
                    )()
                ]
            },
        )()

        extracted = extract_tier2_candidates(
            [
                {
                    "turn_number": 230,
                    "kind": "turn",
                    "created_at": "2026-04-13T11:00:00Z",
                    "content": "User: I got back from Yosemite yesterday.\nAssistant: Noted.",
                },
            ],
            llm_caller=lambda **kwargs: response,
        )

        assert extracted["_meta"]["json_parse_status"] == "json_object"
        assert extracted["temporal_events"][0]["turn_number"] == 230

    def test_tier2_extractor_prompt_guides_background_trip_context_into_temporal_events(self):
        captured = {}

        def _fake_llm(**kwargs):
            captured["system"] = kwargs["messages"][0]["content"]
            return {"content": "{}"}

        rows = [
            {
                "turn_number": 211,
                "kind": "turn",
                "content": (
                    "User: I recently got back from a solo camping trip to Yosemite and from a road trip to Big Sur and Monterey, "
                    "and now I need better camping gear recommendations.\nAssistant: Sure."
                ),
            }
        ]

        extract_tier2_candidates(rows, llm_caller=_fake_llm, transcript_limit=4)

        prompt = captured["system"]
        assert "concrete prior trip" in prompt
        assert "real-world experiences, visits, trips" in prompt
        assert '"typed_entities"' in prompt
        assert "do not replace temporal_events with typed_entities" in prompt

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

    def test_tier2_reconciler_persists_temporal_events_as_continuity_rows(self, tmp_path):
        provider = _make_provider(tmp_path, "session-tier2-temporal")
        try:
            report = reconcile_tier2_candidates(
                provider._store,
                session_id="session-tier2-temporal",
                turn_number=20,
                source="tier2:test",
                extracted={
                    "profile_items": [],
                    "states": [],
                    "relations": [],
                    "inferred_relations": [],
                    "temporal_events": [
                        {
                            "turn_number": 18,
                            "content": "Family trip to Muir Woods National Monument",
                            "confidence": 0.87,
                            "metadata": {"event_turn_number": 18},
                            "temporal": {"observed_at": "2026-04-11T09:15:00Z"},
                        }
                    ],
                    "continuity_summary": "",
                    "decisions": [],
                },
            )

            continuity_rows = provider._store.recent_continuity(session_id="session-tier2-temporal", limit=10)
            temporal_row = next(row for row in continuity_rows if row["kind"] == "temporal_event")

            assert any(
                action["kind"] == "continuity"
                and action["action"] == "ADD"
                and action["type"] == "temporal_event"
                for action in report["actions"]
            )
            assert temporal_row["turn_number"] == 18
            assert temporal_row["content"] == "Family trip to Muir Woods National Monument"
            assert temporal_row["metadata"]["event_turn_number"] == 18
            assert temporal_row["metadata"]["temporal"]["observed_at"].startswith("2026-04-11T09:15:00")
        finally:
            provider.shutdown()

    def test_tier2_reconciler_persists_typed_entities_as_graph_states(self, tmp_path):
        provider = _make_provider(tmp_path, "session-tier2-typed")
        try:
            report = reconcile_tier2_candidates(
                provider._store,
                session_id="session-tier2-typed",
                turn_number=84,
                source="tier2:test",
                extracted={
                    "profile_items": [],
                    "states": [],
                    "relations": [],
                    "inferred_relations": [],
                    "typed_entities": [
                        {
                            "turn_number": 84,
                            "name": "Yellowstone family road trip",
                            "entity_type": "road_trip",
                            "subject": "User",
                            "attributes": {
                                "distance_miles": "1200",
                                "destination": "Yellowstone National Park",
                            },
                            "confidence": 0.91,
                            "metadata": {"event_turn_number": 84},
                            "temporal": {"observed_at": "2026-04-11T09:15:00Z"},
                        }
                    ],
                    "temporal_events": [],
                    "continuity_summary": "",
                    "decisions": [],
                },
            )

            graph_rows = provider._store.search_graph(
                query="Yellowstone road trip 1200 miles",
                limit=20,
            )

            assert any(action["kind"] == "typed_entity" for action in report["actions"])
            assert any(
                row["row_type"] == "state"
                and row["subject"] == "Yellowstone family road trip"
                and row["predicate"] == "entity_type"
                and row["object_value"] == "road_trip"
                for row in graph_rows
            )
            assert any(
                row["row_type"] == "state"
                and row["subject"] == "Yellowstone family road trip"
                and row["predicate"] == "distance_miles"
                and row["object_value"] == "1200"
                for row in graph_rows
            )
            assert any(
                row["row_type"] == "state"
                and row["subject"] == "Yellowstone family road trip"
                and row["predicate"] == "owner_subject"
                and row["object_value"] == "User"
                for row in graph_rows
            )
        finally:
            provider.shutdown()

    def test_store_search_temporal_continuity_surfaces_cross_session_events_without_overlap_filter(self, tmp_path):
        provider = _make_provider(tmp_path, "session-temporal-search")
        try:
            reconcile_tier2_candidates(
                provider._store,
                session_id="seed-session-a",
                turn_number=20,
                source="tier2:test",
                extracted={
                    "profile_items": [],
                    "states": [],
                    "relations": [],
                    "inferred_relations": [],
                    "temporal_events": [
                        {
                            "turn_number": 18,
                            "content": "Family trip to Muir Woods National Monument",
                            "confidence": 0.87,
                            "metadata": {"event_turn_number": 18},
                            "temporal": {"observed_at": "2026-04-11T09:15:00Z"},
                        }
                    ],
                    "continuity_summary": "",
                    "decisions": [],
                },
            )
            reconcile_tier2_candidates(
                provider._store,
                session_id="seed-session-b",
                turn_number=230,
                source="tier2:test",
                extracted={
                    "profile_items": [],
                    "states": [],
                    "relations": [],
                    "inferred_relations": [],
                    "temporal_events": [
                        {
                            "turn_number": 230,
                            "content": "Solo camping trip to Yosemite National Park",
                            "confidence": 0.93,
                            "metadata": {"event_turn_number": 230},
                            "temporal": {"observed_at": "2026-04-13T11:00:00Z"},
                        }
                    ],
                    "continuity_summary": "",
                    "decisions": [],
                },
            )

            rows = provider._store.search_temporal_continuity(
                query="What is the order of the three trips I took in the past three months?",
                session_id="prefetch-session",
                limit=5,
            )

            assert [row["content"] for row in rows[:2]] == [
                "Solo camping trip to Yosemite National Park",
                "Family trip to Muir Woods National Monument",
            ]
            assert rows[0]["same_session"] is False
            assert rows[0]["kind"] == "temporal_event"
        finally:
            provider.shutdown()

    def test_store_search_temporal_continuity_can_semantically_rerank_bounded_pool(self, tmp_path):
        class FakeSemanticBackend:
            target_name = "test.semantic"

            def score_texts(self, *, query: str, texts: list[str]) -> list[float]:
                scores = []
                for text in texts:
                    normalized = str(text or "").lower()
                    if "muir woods" in normalized:
                        scores.append(0.95)
                    elif "big sur" in normalized or "monterey" in normalized:
                        scores.append(0.91)
                    elif "yosemite" in normalized:
                        scores.append(0.83)
                    else:
                        scores.append(0.05)
                return scores

            def close(self) -> None:
                pass

        provider = _make_provider(tmp_path, "session-temporal-semantic")
        try:
            provider._store._corpus_backend = FakeSemanticBackend()

            reconcile_tier2_candidates(
                provider._store,
                session_id="seed-session-a",
                turn_number=20,
                source="tier2:test",
                extracted={
                    "profile_items": [],
                    "states": [],
                    "relations": [],
                    "inferred_relations": [],
                    "temporal_events": [
                        {
                            "turn_number": 18,
                            "content": "Family trip to Muir Woods National Monument",
                            "confidence": 0.87,
                            "metadata": {"event_turn_number": 18},
                            "temporal": {"observed_at": "2026-04-11T09:15:00Z"},
                        }
                    ],
                    "continuity_summary": "",
                    "decisions": [],
                },
            )
            reconcile_tier2_candidates(
                provider._store,
                session_id="seed-session-b",
                turn_number=230,
                source="tier2:test",
                extracted={
                    "profile_items": [],
                    "states": [],
                    "relations": [],
                    "inferred_relations": [],
                    "temporal_events": [
                        {
                            "turn_number": 230,
                            "content": "Solo camping trip to Yosemite National Park",
                            "confidence": 0.93,
                            "metadata": {"event_turn_number": 230},
                            "temporal": {"observed_at": "2026-04-13T11:00:00Z"},
                        },
                        {
                            "turn_number": 140,
                            "content": "Road trip to Big Sur and Monterey",
                            "confidence": 0.89,
                            "metadata": {"event_turn_number": 140},
                            "temporal": {"observed_at": "2026-04-12T08:00:00Z"},
                        },
                    ],
                    "continuity_summary": "",
                    "decisions": [],
                },
            )

            rows = provider._store.search_temporal_continuity(
                query="What is the order of the three trips I took in the past three months?",
                session_id="prefetch-session",
                limit=3,
            )

            assert [row["content"] for row in rows] == [
                "Family trip to Muir Woods National Monument",
                "Road trip to Big Sur and Monterey",
                "Solo camping trip to Yosemite National Park",
            ]
            assert rows[0]["semantic_score"] > rows[1]["semantic_score"] > rows[2]["semantic_score"]
        finally:
            provider.shutdown()

    def test_provider_tier2_batch_result_exposes_parse_and_write_telemetry(self, tmp_path):
        provider = _make_provider(tmp_path, "session-tier2-batch-result")
        try:
            provider.sync_turn(
                "I took a family trip to Muir Woods National Monument.",
                "Noted.",
                session_id="session-tier2-batch-result",
                event_time="2026-04-11T09:15:00Z",
            )
            provider._config["_tier2_extractor"] = lambda transcript_entries, **kwargs: {
                "profile_items": [],
                "states": [],
                "relations": [],
                "inferred_relations": [],
                "temporal_events": [
                    {
                        "turn_number": int(transcript_entries[-1]["turn_number"]),
                        "content": "Family trip to Muir Woods National Monument",
                        "confidence": 0.87,
                        "metadata": {"event_turn_number": int(transcript_entries[-1]["turn_number"])},
                        "temporal": {"observed_at": "2026-04-11T09:15:00Z"},
                    }
                ],
                "continuity_summary": "",
                "decisions": [],
                "_meta": {
                    "json_parse_status": "json_object",
                    "parse_context": "turns=[1]",
                    "raw_payload_preview": "{\"temporal_events\": [{\"turn_number\": 1}]}",
                    "raw_payload_tail": "{\"temporal_events\": [{\"turn_number\": 1}]}",
                    "raw_payload_length": 41,
                },
            }

            result = provider._run_tier2_batch(
                session_id="session-tier2-batch-result",
                turn_number=1,
                trigger_reason="unit-test-flush",
            )

            assert result["status"] == "ok"
            assert result["json_parse_status"] == "json_object"
            assert result["parse_context"] == "turns=[1]"
            assert result["raw_payload_preview"].startswith("{")
            assert result["raw_payload_tail"].endswith("}]}")
            assert result["raw_payload_length"] == 41
            assert result["transcript_turn_numbers"] == [1]
            assert result["extracted_counts"]["temporal_events"] == 1
            assert result["writes_performed"] >= 1
            assert result["action_counts"]["ADD"] >= 1
            assert provider._last_tier2_batch_result["trigger_reason"] == "unit-test-flush"
            assert provider._tier2_batch_history[-1]["json_parse_status"] == "json_object"
        finally:
            provider.shutdown()

    def test_explicit_truth_beats_inferred_relation_and_inferred_is_packaged_separately(self, tmp_path):
        provider = _make_provider(tmp_path, "session-inferred")
        try:
            reconcile_tier2_candidates(
                provider._store,
                session_id="session-inferred",
                turn_number=1,
                source="tier2:test",
                extracted={
                    "profile_items": [{"category": "identity", "content": "User identity: Tomi", "slot": "identity:name", "confidence": 0.95}],
                    "states": [],
                    "relations": [{"subject": "Tomi", "predicate": "works_on", "object": "BrainStack", "confidence": 0.9}],
                    "inferred_relations": [
                        {
                            "subject": "BrainStack",
                            "predicate": "depends_on",
                            "object": "Hermes Bestie",
                            "confidence": 0.61,
                            "metadata": {"inference_reason": "The project was described as being hooked into Hermes Bestie."},
                        }
                    ],
                    "continuity_summary": "Tomi works on BrainStack and it is being connected to Hermes Bestie.",
                    "decisions": [],
                },
            )

            rows = provider._store.search_graph(query="BrainStack Hermes Bestie", limit=10)
            explicit_index = next(index for index, row in enumerate(rows) if row["row_type"] == "relation")
            inferred_index = next(index for index, row in enumerate(rows) if row["row_type"] == "inferred_relation")
            assert explicit_index < inferred_index

            block = provider.prefetch(
                "How am I related to BrainStack and what is it connected to?",
                session_id="session-inferred",
            )
            assert "### Current Truth" in block
            assert "### Inferred Links" in block
            assert "[relation:explicit] Tomi works_on BrainStack" in block
            assert "[relation:inferred] BrainStack depends_on Hermes Bestie" in block
        finally:
            provider.shutdown()

    def test_explicit_relation_shadows_matching_inferred_relation(self, tmp_path):
        provider = _make_provider(tmp_path, "session-shadow")
        try:
            reconcile_tier2_candidates(
                provider._store,
                session_id="session-shadow",
                turn_number=1,
                source="tier2:test",
                extracted={
                    "profile_items": [],
                    "states": [],
                    "relations": [],
                    "inferred_relations": [
                        {
                            "subject": "BrainStack",
                            "predicate": "integrates_with",
                            "object": "Hermes Bestie",
                            "confidence": 0.63,
                            "metadata": {"inference_reason": "Stable project context implied the integration."},
                        }
                    ],
                    "continuity_summary": "",
                    "decisions": [],
                },
            )
            reconcile_tier2_candidates(
                provider._store,
                session_id="session-shadow",
                turn_number=2,
                source="tier2:test",
                extracted={
                    "profile_items": [],
                    "states": [],
                    "relations": [
                        {
                            "subject": "BrainStack",
                            "predicate": "integrates_with",
                            "object": "Hermes Bestie",
                            "confidence": 0.89,
                        }
                    ],
                    "inferred_relations": [],
                    "continuity_summary": "",
                    "decisions": [],
                },
            )

            graph_rows = provider._store.search_graph(query="BrainStack Hermes Bestie", limit=10)
            assert any(row["row_type"] == "relation" for row in graph_rows)
            assert not any(row["row_type"] == "inferred_relation" for row in graph_rows)
        finally:
            provider.shutdown()

    def test_reconciler_merges_user_alias_into_named_graph_relation(self, tmp_path):
        provider = _make_provider(tmp_path, "session-alias")
        try:
            reconcile_tier2_candidates(
                provider._store,
                session_id="session-alias",
                turn_number=1,
                source="tier2:test",
                extracted={
                    "profile_items": [
                        {
                            "category": "identity",
                            "content": "User identity: Tomi",
                            "slot": "identity:name",
                            "confidence": 0.95,
                        }
                    ],
                    "states": [],
                    "relations": [],
                    "continuity_summary": "",
                    "decisions": [],
                },
            )
            reconcile_tier2_candidates(
                provider._store,
                session_id="session-alias",
                turn_number=2,
                source="tier2:test",
                extracted={
                    "profile_items": [],
                    "states": [],
                    "relations": [
                        {
                            "subject": "User",
                            "predicate": "leads",
                            "object": "BrainStack",
                            "confidence": 0.88,
                        }
                    ],
                    "continuity_summary": "",
                    "decisions": [],
                },
            )

            graph_rows = provider._store.search_graph(query="BrainStack", limit=10)
            assert any(
                row.get("row_type") == "relation"
                and row.get("subject") == "Tomi"
                and row.get("predicate") == "leads"
                and row.get("object_value") == "BrainStack"
                for row in graph_rows
            )
            assert not any(
                row.get("row_type") == "relation"
                and row.get("subject") == "User"
                and row.get("predicate") == "leads"
                and row.get("object_value") == "BrainStack"
                for row in graph_rows
            )
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

            # The extractor sleeps for 0.25s. The sync path should return well
            # before that even on a loaded CI/dev box, without requiring an
            # unrealistically tight sub-150ms ceiling.
            assert elapsed < 0.22
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

    def test_everyday_recall_survives_small_talk_and_still_brings_back_preference_and_shared_work(self, tmp_path):
        base = Path(tmp_path)
        provider = BrainstackMemoryProvider(
            config={
                "db_path": str(base / "brainstack.db"),
                "tier2_batch_turn_limit": 1,
                "_tier2_extractor": lambda rows, **kwargs: {
                    "profile_items": [
                        {"category": "preference", "content": "Prefer short Hungarian replies", "confidence": 0.93},
                        {"category": "shared_work", "content": "We are rebuilding Brainstack into Hermes Bestie", "confidence": 0.87},
                    ],
                    "states": [],
                    "relations": [{"subject": "Tomi", "predicate": "works_on", "object": "Brainstack into Hermes Bestie", "confidence": 0.84}],
                    "continuity_summary": "Tomi prefers short Hungarian replies and current work is the Brainstack plus Hermes Bestie rebuild.",
                    "decisions": ["Brainstack remains the only memory owner."],
                },
            }
        )
        provider.initialize("session-everyday-focus", hermes_home=str(base))
        try:
            provider.sync_turn(
                "Kérlek röviden és magyarul válaszolj. Most a Brainstacket rakjuk be a Hermes Bestie-be.",
                "Rendben.",
                session_id="session-everyday-focus",
            )
            provider.sync_turn(
                "Közben ma mit egyek ebédre?",
                "Valami könnyűt.",
                session_id="session-everyday-focus",
            )
            assert provider._wait_for_tier2_worker(timeout=1.0) is True

            block = provider.prefetch(
                "Do I prefer short Hungarian replies and what are we rebuilding right now?",
                session_id="session-everyday-focus",
            )

            assert "## Brainstack Profile Match" in block
            assert "Prefer short Hungarian replies" in block
            assert "Brainstack into Hermes Bestie" in block
            assert "## Brainstack Continuity Match" in block
        finally:
            provider.shutdown()

    def test_everyday_recall_surfaces_relationships_not_just_flat_facts(self, tmp_path):
        base = Path(tmp_path)
        provider = BrainstackMemoryProvider(
            config={
                "db_path": str(base / "brainstack.db"),
                "tier2_batch_turn_limit": 1,
                "_tier2_extractor": lambda rows, **kwargs: {
                    "profile_items": [],
                    "states": [],
                    "relations": [
                        {"subject": "Tomi", "predicate": "works_on", "object": "Brainstack", "confidence": 0.9},
                        {"subject": "Brainstack", "predicate": "integrates_with", "object": "Hermes Bestie", "confidence": 0.86},
                    ],
                    "continuity_summary": "Tomi is working on Brainstack and Brainstack is being integrated with Hermes Bestie.",
                    "decisions": [],
                },
            }
        )
        provider.initialize("session-everyday-relations", hermes_home=str(base))
        try:
            provider.sync_turn(
                "Most a Brainstacken dolgozom, és ezt kötjük rá a Hermes Bestie-re.",
                "Értettem.",
                session_id="session-everyday-relations",
            )
            assert provider._wait_for_tier2_worker(timeout=1.0) is True

            block = provider.prefetch(
                "Milyen kapcsolatban állok a Brainstackkel, és az mivel van összekötve?",
                session_id="session-everyday-relations",
            )

            assert "## Brainstack Graph Truth" in block
            assert "[relation:explicit] Tomi works_on Brainstack" in block
            assert "[relation:explicit] Brainstack integrates_with Hermes Bestie" in block
        finally:
            provider.shutdown()

    def test_everyday_recall_keeps_correction_believable_after_ordinary_follow_up(self, tmp_path):
        base = Path(tmp_path)
        provider = BrainstackMemoryProvider(
            config={
                "db_path": str(base / "brainstack.db"),
                "tier2_batch_turn_limit": 1,
                "_tier2_extractor": lambda rows, **kwargs: {
                    "profile_items": [{"category": "identity", "content": "User identity: Tomi", "slot": "identity:name", "confidence": 0.96}],
                    "states": [
                        {"subject": "Tomi", "attribute": "location", "value": "Budapest", "supersede": False, "confidence": 0.84},
                        {"subject": "Tomi", "attribute": "location", "value": "Debrecen", "supersede": True, "confidence": 0.91},
                    ] if any("Debrecenben" in row["content"] for row in rows) else [
                        {"subject": "Tomi", "attribute": "location", "value": "Budapest", "supersede": False, "confidence": 0.84},
                    ],
                    "relations": [{"subject": "Tomi", "predicate": "works_on", "object": "Brainstack", "confidence": 0.8}],
                    "continuity_summary": "Tomi corrected the location from Budapest to Debrecen while continuing the same work.",
                    "decisions": [],
                },
            }
        )
        provider.initialize("session-everyday-correction", hermes_home=str(base))
        try:
            provider.sync_turn("Budapesten élek és a Brainstacken dolgozom.", "Rendben.", session_id="session-everyday-correction")
            provider.sync_turn("Javítás: már Debrecenben élek.", "Frissítve.", session_id="session-everyday-correction")
            provider.sync_turn("Egyébként szeretem a zöld teát.", "Ok.", session_id="session-everyday-correction")
            assert provider._wait_for_tier2_worker(timeout=1.0) is True

            current_block = provider.prefetch("Tomi location", session_id="session-everyday-correction")
            changed_block = provider.prefetch(
                "Hol élek most és mi változott korábban?",
                session_id="session-everyday-correction",
            )

            assert "[state:current] Tomi location=Debrecen" in current_block
            assert "[state:prior] Tomi location=Budapest" not in current_block
            assert "Debrecen" in changed_block
            assert "[state:prior] Tomi location=Budapest" in changed_block
            assert "## Brainstack Graph Truth" in changed_block
        finally:
            provider.shutdown()
