from __future__ import annotations

import importlib.util
import json
import sys
import types
from datetime import timezone
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "run_brainstack_longmemeval_subset.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("brainstack_longmemeval_subset_script", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_extract_memory_context_returns_only_memory_block():
    module = _load_script_module()
    prompt = (
        "system header\n\n"
        "<memory-context>\n"
        "## Brainstack Aggregate Evidence\n"
        "1. [2024-04-11 | turn 1 | turn] User: I drove 120 miles.\n"
        "</memory-context>\n\n"
        "footer"
    )

    extracted = module._extract_memory_context(prompt)

    assert "system header" not in extracted
    assert "footer" not in extracted
    assert "120 miles" in extracted


def test_classify_failure_layer_separates_retrieval_and_answer_failures():
    module = _load_script_module()

    assert module._classify_failure_layer(answer_correct=True, retrieval_correct=True) == "none"
    assert module._classify_failure_layer(answer_correct=False, retrieval_correct=True) == "llm_answer"
    assert module._classify_failure_layer(answer_correct=False, retrieval_correct=False) == "retrieval"
    assert (
        module._classify_failure_layer(answer_correct=True, retrieval_correct=False)
        == "answer_recovered_despite_retrieval_gap"
    )


def test_provider_route_snapshot_extracts_existing_prefetch_fields():
    module = _load_script_module()

    class DummyProvider:
        _last_prefetch_routing = {
            "requested_mode": "aggregate",
            "applied_mode": "fact",
            "source": "fallback",
            "reason": "thin aggregate support",
            "fallback_used": True,
            "bounds": {"row_cap": 6},
        }
        _last_prefetch_channels = [
            {"name": "keyword", "status": "active", "candidate_count": 3, "reason": "ok"},
            {"name": "temporal", "status": "active", "candidate_count": 1},
        ]

    snapshot = module._provider_route_snapshot(DummyProvider())

    assert snapshot["requested_mode"] == "aggregate"
    assert snapshot["applied_mode"] == "fact"
    assert snapshot["fallback_used"] is True
    assert snapshot["bounds"] == {"row_cap": 6}
    assert snapshot["channels"][0]["candidate_count"] == 3
    assert snapshot["channels"][1]["name"] == "temporal"


def test_provider_candidate_debug_snapshot_extracts_fused_and_selected_rows():
    module = _load_script_module()

    class DummyProvider:
        _last_prefetch_debug = {
            "fused_candidates": [
                {
                    "key": "transcript:1",
                    "shelf": "transcript",
                    "rrf_score": 0.12,
                    "priority_bonus": 0.04,
                    "channel_ranks": {"keyword": 1, "semantic": 3},
                    "id": 17,
                    "turn_number": 9,
                    "created_at": "2023-04-03T08:30:00+00:00",
                    "overlap_count": 2,
                    "semantic_score": 0.91,
                    "same_session": False,
                    "content_excerpt": "I used to work as a marketing specialist at a small startup.",
                }
            ],
            "selected_rows": {
                "transcript_rows": [
                    {
                        "id": 17,
                        "session_id": "other-session",
                        "turn_number": 9,
                        "created_at": "2023-04-03T08:30:00+00:00",
                        "overlap_count": 2,
                        "semantic_score": 0.91,
                        "channels": ["keyword", "semantic"],
                        "channel_ranks": {"keyword": 1, "semantic": 3},
                        "rrf_score": 0.12,
                        "content_excerpt": "I used to work as a marketing specialist at a small startup.",
                    }
                ]
            },
        }

    snapshot = module._provider_candidate_debug_snapshot(DummyProvider())

    assert snapshot["fused_candidates"][0]["shelf"] == "transcript"
    assert snapshot["fused_candidates"][0]["channel_ranks"] == {"keyword": 1, "semantic": 3}
    assert snapshot["fused_candidates"][0]["turn_number"] == 9
    assert snapshot["fused_candidates"][0]["overlap_count"] == 2
    assert "marketing specialist" in snapshot["fused_candidates"][0]["content_excerpt"]
    assert snapshot["selected_rows"]["transcript_rows"][0]["session_id"] == "other-session"
    assert "marketing specialist" in snapshot["selected_rows"]["transcript_rows"][0]["content_excerpt"]


def test_parse_fixed_now_normalizes_zulu_and_sets_tz():
    module = _load_script_module()

    parsed = module._parse_fixed_now("2026-04-13T09:10:11Z")

    assert parsed is not None
    assert parsed.isoformat() == "2026-04-13T09:10:11+00:00"
    assert parsed.tzinfo == timezone.utc


def test_extract_route_hint_payload_text_falls_back_to_plain_mode_word():
    module = _load_script_module()

    payload = module._extract_route_hint_payload_text("Temporal. The question asks which happened first.")

    assert payload["mode"] == "temporal"
    assert "happened first" in payload["reason"]


def test_extract_route_hint_payload_text_rejects_ambiguous_explanatory_response():
    module = _load_script_module()

    payload = module._extract_route_hint_payload_text(
        "The question is not temporal or aggregate. This should use fact."
    )

    assert payload == {}


def test_extract_memory_context_returns_empty_without_memory_tags():
    module = _load_script_module()

    assert module._extract_memory_context("System prompt only without memory tags") == ""


def test_extract_route_hint_response_text_uses_reasoning_content_when_content_empty():
    module = _load_script_module()

    class Message:
        content = ""
        reasoning_content = "aggregate"

    class Choice:
        message = Message()

    class Response:
        choices = [Choice()]

    assert module._extract_route_hint_response_text(Response()) == "aggregate"


def test_judge_retrieval_support_accepts_time_format_equivalence(monkeypatch):
    module = _load_script_module()
    monkeypatch.setattr(module, "_judge_yes_no", lambda **_: "no")

    result = module._judge_retrieval_support(
        base_url="unused",
        api_key="unused",
        model="unused",
        question="What was my personal best time in the charity 5K run?",
        answer="25 minutes and 50 seconds (or 25:50)",
        captured_prompt="<memory-context>I'm hoping to beat my personal best time of 25:50 this time around.</memory-context>",
    )

    assert result == "yes_answer_found_time_equivalent"


def test_judge_retrieval_support_accepts_named_entity_token_coverage(monkeypatch):
    module = _load_script_module()
    monkeypatch.setattr(module, "_judge_yes_no", lambda **_: "no")

    result = module._judge_retrieval_support(
        base_url="unused",
        api_key="unused",
        model="unused",
        question="Remind me of that unique dessert shop with the giant milkshakes.",
        answer="The Sugar Factory at Icon Park.",
        captured_prompt=(
            "<memory-context>"
            "The Sugar Factory - A sweet shop located at Icon Park that is famous for giant milkshakes."
            "</memory-context>"
        ),
    )

    assert result == "yes_answer_supported_by_named_tokens"


def test_judge_retrieval_support_does_not_promote_derived_numeric_case(monkeypatch):
    module = _load_script_module()
    monkeypatch.setattr(module, "_judge_yes_no", lambda **_: "no")

    result = module._judge_retrieval_support(
        base_url="unused",
        api_key="unused",
        model="unused",
        question="How many points do I need to earn to redeem a free skincare product at Sephora?",
        answer="100",
        captured_prompt=(
            "<memory-context>"
            "You can earn 1 point for every dollar at Sephora and redeem those points for rewards."
            "</memory-context>"
        ),
    )

    assert result == "no"


def test_backend_population_snapshot_reads_graph_and_corpus_counts():
    module = _load_script_module()

    class FakeRows:
        def __init__(self, value):
            self._value = value
            self._used = False

        def has_next(self):
            return not self._used

        def get_next(self):
            self._used = True
            return [self._value]

    class FakeConn:
        def __init__(self, values):
            self._values = values

        def execute(self, query):
            if "count(e)" in query:
                return FakeRows(self._values["entity_count"])
            if "count(s)" in query:
                return FakeRows(self._values["state_count"])
            if "count(c)" in query:
                return FakeRows(self._values["conflict_count"])
            if "INFERRED_RELATES_TO" in query:
                return FakeRows(self._values["inferred_relation_count"])
            if "RELATES_TO" in query:
                return FakeRows(self._values["relation_count"])
            raise AssertionError(f"unexpected query: {query}")

    class FakeGraphBackend:
        def __init__(self):
            self.conn = FakeConn(
                {
                    "entity_count": 4,
                    "state_count": 5,
                    "conflict_count": 1,
                    "relation_count": 3,
                    "inferred_relation_count": 2,
                }
            )

    class FakeSQLiteCursor:
        def __init__(self, value):
            self._value = value

        def fetchone(self):
            return [self._value]

    class FakeSQLiteConn:
        def execute(self, query):
            if "graph_entities" in query:
                return FakeSQLiteCursor(7)
            if "graph_states" in query:
                return FakeSQLiteCursor(5)
            if "graph_conflicts" in query:
                return FakeSQLiteCursor(1)
            if "graph_inferred_relations" in query:
                return FakeSQLiteCursor(2)
            if "graph_relations" in query:
                return FakeSQLiteCursor(4)
            raise AssertionError(f"unexpected sqlite query: {query}")

    class FakeCollection:
        def count(self):
            return 6

        def get(self, include=None):
            del include
            return {
                "metadatas": [
                    {"stable_key": "doc:a"},
                    {"stable_key": "doc:a"},
                    {"stable_key": "doc:b"},
                ]
            }

    class FakeCorpusBackend:
        @property
        def collection(self):
            return FakeCollection()

    class FakeStore:
        _graph_backend_name = "kuzu"
        _graph_backend_error = ""
        _graph_backend = FakeGraphBackend()
        conn = FakeSQLiteConn()
        _corpus_backend_name = "chroma"
        _corpus_backend_error = ""
        _corpus_backend = FakeCorpusBackend()

    class FakeProvider:
        _store = FakeStore()

    snapshot = module._backend_population_snapshot(FakeProvider())

    assert snapshot["graph_backend"] == "kuzu"
    assert snapshot["sqlite_graph_counts"]["entity_count"] == 7
    assert snapshot["sqlite_graph_counts"]["relation_count"] == 4
    assert snapshot["graph_counts"]["entity_count"] == 4
    assert snapshot["graph_counts"]["inferred_relation_count"] == 2
    assert snapshot["corpus_backend"] == "chroma"
    assert snapshot["corpus_counts"]["section_count"] == 6
    assert snapshot["corpus_counts"]["stable_key_count"] == 2


def test_memory_manager_route_snapshot_reads_brainstack_provider_state():
    module = _load_script_module()

    class DummyProvider:
        name = "brainstack"
        _last_prefetch_routing = {
            "requested_mode": "temporal",
            "applied_mode": "fact",
            "source": "fallback",
            "reason": "thin temporal support",
            "fallback_used": True,
            "bounds": {"recent_cap": 3},
        }
        _last_prefetch_channels = [{"name": "temporal", "status": "active", "candidate_count": 1}]

    class DummyManager:
        _providers = [DummyProvider()]

    snapshot = module._memory_manager_route_snapshot(DummyManager())

    assert snapshot["requested_mode"] == "temporal"
    assert snapshot["applied_mode"] == "fact"
    assert snapshot["fallback_used"] is True
    assert snapshot["channels"][0]["name"] == "temporal"


def test_install_brainstack_route_resolver_updates_matching_provider_only():
    module = _load_script_module()

    class BrainstackProvider:
        name = "brainstack"
        _config = {}
        _route_resolver_override = None

    class OtherProvider:
        name = "other"
        _config = {}
        _route_resolver_override = None

    class DummyManager:
        _providers = [OtherProvider(), BrainstackProvider()]

    resolver = lambda query: {"mode": "fact", "reason": query}
    installed = module._install_brainstack_route_resolver(DummyManager(), resolver)

    assert installed is True
    assert DummyManager._providers[0]._config == {}
    assert DummyManager._providers[0]._route_resolver_override is None
    assert DummyManager._providers[1]._config["_route_resolver"] is resolver
    assert DummyManager._providers[1]._route_resolver_override is resolver


def test_write_report_writes_partial_payload(tmp_path):
    module = _load_script_module()
    report_path = tmp_path / "report.json"

    module._write_report(
        report_path,
        {"partial": True, "completed": 1},
        [{"question_id": "q1", "passed": True}],
    )

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["summary"]["partial"] is True
    assert payload["summary"]["completed"] == 1
    assert payload["results"][0]["question_id"] == "q1"


def test_verify_runtime_sync_accepts_matching_payloads(tmp_path, monkeypatch):
    module = _load_script_module()
    source_root = tmp_path / "src"
    hermes_root = tmp_path / "hermes"

    (source_root / "brainstack").mkdir(parents=True)
    (source_root / "brainstack" / "executive_retrieval.py").write_text("alpha", encoding="utf-8")
    (source_root / "host_payload" / "gateway").mkdir(parents=True)
    (source_root / "host_payload" / "gateway" / "shim.py").write_text("beta", encoding="utf-8")
    (source_root / "rtk_sidecar.py").write_text("gamma", encoding="utf-8")

    (hermes_root / "plugins" / "memory" / "brainstack").mkdir(parents=True)
    (hermes_root / "plugins" / "memory" / "brainstack" / "executive_retrieval.py").write_text("alpha", encoding="utf-8")
    (hermes_root / "gateway").mkdir(parents=True)
    (hermes_root / "gateway" / "shim.py").write_text("beta", encoding="utf-8")
    (hermes_root / "agent").mkdir(parents=True)
    (hermes_root / "agent" / "rtk_sidecar.py").write_text("gamma", encoding="utf-8")

    monkeypatch.setattr(module, "REPO_ROOT", source_root)

    snapshot = module._verify_runtime_sync(hermes_root)

    assert snapshot["ok"] is True
    assert snapshot["mismatch_count"] == 0
    assert snapshot["compared_files"] == 3


def test_verify_runtime_sync_reports_hash_mismatch(tmp_path, monkeypatch):
    module = _load_script_module()
    source_root = tmp_path / "src"
    hermes_root = tmp_path / "hermes"

    (source_root / "brainstack").mkdir(parents=True)
    (source_root / "brainstack" / "executive_retrieval.py").write_text("alpha", encoding="utf-8")
    (hermes_root / "plugins" / "memory" / "brainstack").mkdir(parents=True)
    (hermes_root / "plugins" / "memory" / "brainstack" / "executive_retrieval.py").write_text("omega", encoding="utf-8")

    monkeypatch.setattr(module, "REPO_ROOT", source_root)

    snapshot = module._verify_runtime_sync(hermes_root)

    assert snapshot["ok"] is False
    assert snapshot["mismatch_count"] == 1
    assert snapshot["mismatches"][0]["reason"] == "hash_mismatch"
    assert snapshot["mismatches"][0]["source"].endswith("brainstack/executive_retrieval.py")


def test_select_entries_canary_preserves_fixed_order(monkeypatch):
    module = _load_script_module()
    monkeypatch.setattr(module, "FIXED_CANARY_QUESTION_IDS", ["q3", "q1", "q2"])
    entries = [
        {"question_id": "q1"},
        {"question_id": "q2"},
        {"question_id": "q3"},
    ]

    chosen = module._select_entries(
        entries,
        donor_module=types.SimpleNamespace(),
        sample_size=2,
        seed=7,
        question_ids=[],
        canary=True,
    )

    assert [entry["question_id"] for entry in chosen] == ["q3", "q1", "q2"]


def test_build_memory_context_prompt_wraps_prefetch_block():
    module = _load_script_module()

    prompt = module._build_memory_context_prompt(
        system_prompt_block="# Brainstack Profile\n- likes tea",
        prefetch_block="## Brainstack Transcript Evidence\n- User: example",
    )

    assert prompt.startswith("# Brainstack Profile")
    assert "<memory-context>" in prompt
    assert "## Brainstack Transcript Evidence" in prompt
    assert prompt.rstrip().endswith("</memory-context>")


def test_direct_tier2_extractor_falls_back_on_non_json(monkeypatch, capsys):
    module = _load_script_module()
    fake_module = types.ModuleType("plugins.memory.brainstack.tier2_extractor")

    def _fake_extract_tier2_candidates(transcript_entries, *, llm_caller):
        del transcript_entries
        llm_caller(task="flush_memories", messages=[], timeout=1.0, max_tokens=32)
        raise ValueError("non-json payload")

    fake_module.extract_tier2_candidates = _fake_extract_tier2_candidates
    monkeypatch.setitem(sys.modules, "plugins.memory.brainstack.tier2_extractor", fake_module)

    class DummyCompletions:
        def create(self, **kwargs):
            del kwargs
            return {"choices": [{"message": {"content": "not json"}}]}

    class DummyClient:
        def __init__(self, *args, **kwargs):
            del args, kwargs
            self.chat = type("Chat", (), {"completions": DummyCompletions()})()

        def close(self):
            return None

    monkeypatch.setattr(module.openai, "OpenAI", DummyClient)
    extractor, client = module._build_direct_tier2_extractor(
        model="judge-model",
        base_url="https://example.invalid/v1",
        api_key="test-key",
    )

    payload = extractor(
        [{"role": "user", "content": "hello"}],
        session_id="s1",
        turn_number=7,
        trigger_reason="unit-test",
    )

    assert payload["profile_items"] == []
    assert payload["states"] == []
    assert payload["relations"] == []
    assert payload["inferred_relations"] == []
    assert payload["typed_entities"] == []
    assert payload["temporal_events"] == []
    assert payload["continuity_summary"] == ""
    assert payload["decisions"] == []
    assert payload["_meta"]["json_parse_status"] == "exception"
    assert payload["_meta"]["trigger_reason"] == "unit-test"
    out = capsys.readouterr().out
    assert "\"event\": \"tier2_fallback\"" in out
    assert "\"session_id\": \"s1\"" in out
    client.close()


def test_flush_benchmark_tier2_returns_batch_result_and_clears_pending():
    module = _load_script_module()

    class DummyProvider:
        def __init__(self):
            self._pending_tier2_turns = 3
            self._turn_counter = 9

        def _run_tier2_batch(self, *, session_id, turn_number, trigger_reason):
            assert session_id == "seed-session"
            assert turn_number == 9
            assert trigger_reason == "unit-flush"
            return {"status": "ok", "json_parse_status": "json_object", "writes_performed": 2}

    provider = DummyProvider()
    result = module._flush_benchmark_tier2(
        provider,
        session_id="seed-session",
        trigger_reason="unit-flush",
    )

    assert result["status"] == "ok"
    assert result["json_parse_status"] == "json_object"
    assert provider._pending_tier2_turns == 0


def test_flush_benchmark_tier2_can_temporarily_override_transcript_limit():
    module = _load_script_module()

    class DummyProvider:
        def __init__(self):
            self._pending_tier2_turns = 2
            self._turn_counter = 11
            self._tier2_transcript_limit = 192

        def _run_tier2_batch(self, *, session_id, turn_number, trigger_reason):
            assert session_id == "seed-session"
            assert turn_number == 11
            assert trigger_reason == "session-boundary"
            assert self._tier2_transcript_limit == 6
            return {"status": "ok", "json_parse_status": "json_object", "writes_performed": 1}

    provider = DummyProvider()
    result = module._flush_benchmark_tier2(
        provider,
        session_id="seed-session",
        trigger_reason="session-boundary",
        transcript_limit_override=6,
    )

    assert result["status"] == "ok"
    assert provider._pending_tier2_turns == 0
    assert provider._tier2_transcript_limit == 192


def test_summarize_tier2_batch_results_counts_failures_and_writes():
    module = _load_script_module()

    summary = module._summarize_tier2_batch_results(
        [
            {
                "status": "ok",
                "json_parse_status": "json_repaired",
                "writes_performed": 3,
                "trigger_reason": "flush-1",
                "transcript_turn_numbers": [1, 2, 3],
                "extracted_counts": {"temporal_events": 1, "typed_entities": 0},
                "temporal_event_samples": [{"turn_number": 3, "content": "Family trip to Muir Woods National Monument"}],
                "typed_entity_samples": [],
                "raw_payload_preview": "{\"profile_items\": []}",
                "raw_payload_tail": "{\"profile_items\": []}",
                "raw_payload_length": 21,
            },
            {
                "status": "ok",
                "json_parse_status": "non_json",
                "writes_performed": 0,
                "trigger_reason": "flush-2",
                "transcript_turn_numbers": [4, 5, 6],
                "extracted_counts": {"temporal_events": 0, "typed_entities": 0},
                "temporal_event_samples": [],
                "typed_entity_samples": [],
                "raw_payload_preview": "I found these items...",
                "raw_payload_tail": "I found these items...",
                "raw_payload_length": 22,
            },
        ]
    )

    assert summary["batch_count"] == 2
    assert summary["parse_status_counts"] == {"json_repaired": 1, "non_json": 1}
    assert summary["status_counts"] == {"ok": 2}
    assert summary["batches_with_writes"] == 1
    assert summary["total_writes"] == 3
    assert summary["success_batches"][0]["trigger_reason"] == "flush-1"
    assert summary["success_batches"][0]["raw_payload_preview"] == "{\"profile_items\": []}"
    assert summary["success_batches"][0]["raw_payload_tail"] == "{\"profile_items\": []}"
    assert summary["success_batches"][0]["temporal_event_samples"] == [
        {"turn_number": 3, "content": "Family trip to Muir Woods National Monument"}
    ]
    assert summary["success_batches"][0]["typed_entity_samples"] == []
    assert summary["failure_batches"][0]["trigger_reason"] == "flush-2"
    assert summary["failure_batches"][0]["raw_payload_preview"] == "I found these items..."
    assert summary["failure_batches"][0]["raw_payload_tail"] == "I found these items..."
    assert summary["failure_batches"][0]["temporal_event_samples"] == []
    assert summary["failure_batches"][0]["typed_entity_samples"] == []
