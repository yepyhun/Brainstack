# ruff: noqa: E402
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_host_shims_path = REPO_ROOT / "tests" / "_host_import_shims.py"
_host_shims_spec = importlib.util.spec_from_file_location("phase24_host_import_shims", _host_shims_path)
assert _host_shims_spec and _host_shims_spec.loader
_host_shims = importlib.util.module_from_spec(_host_shims_spec)
_host_shims_spec.loader.exec_module(_host_shims)
install_host_import_shims = _host_shims.install_host_import_shims

install_host_import_shims(hermes_home=REPO_ROOT)

from brainstack.db import BrainstackStore
from brainstack.control_plane import analyze_query, build_working_memory_packet
from brainstack.retrieval import build_system_prompt_block
from brainstack.reconciler import reconcile_tier2_candidates


def _scope(platform: str, user_id: str) -> dict[str, object]:
    principal_scope = {
        "platform": platform,
        "user_id": user_id,
        "agent_identity": "assistant-main",
        "agent_workspace": "discord-main",
    }
    principal_scope_key = "|".join(f"{key}:{value}" for key, value in principal_scope.items())
    return {
        "principal_scope": principal_scope,
        "principal_scope_key": principal_scope_key,
    }


def test_scoped_personal_profile_rows_do_not_fallback_to_global_rows(tmp_path):
    store = BrainstackStore(str(tmp_path / "brainstack.db"))
    store.open()

    scope_a = _scope("discord", "user-a")

    store.upsert_profile_item(
        stable_key="preference:ai_name",
        category="preference",
        content="Call the assistant Hermes.",
        source="test",
        confidence=0.6,
    )
    store.upsert_profile_item(
        stable_key="preference:response_language",
        category="preference",
        content="Always respond in Hungarian.",
        source="test",
        confidence=0.95,
        metadata=scope_a,
    )

    scoped_language = store.get_profile_item(
        stable_key="preference:response_language",
        principal_scope_key=str(scope_a["principal_scope_key"]),
    )
    scoped_ai_name = store.get_profile_item(
        stable_key="preference:ai_name",
        principal_scope_key=str(scope_a["principal_scope_key"]),
    )

    assert scoped_language is not None
    assert scoped_language["content"] == "Always respond in Hungarian."
    assert scoped_language["stable_key"] == "preference:response_language"
    assert scoped_language["storage_key"] != scoped_language["stable_key"]
    assert scoped_language["principal_scope_key"] == scope_a["principal_scope_key"]
    assert scoped_ai_name is None


def test_tier2_profile_reconcile_isolates_personal_rows_by_principal(tmp_path):
    store = BrainstackStore(str(tmp_path / "brainstack.db"))
    store.open()

    scope_a = _scope("discord", "user-a")
    scope_b = _scope("discord", "user-b")

    reconcile_tier2_candidates(
        store,
        session_id="session-a",
        turn_number=1,
        source="tier2:test",
        metadata=scope_a,
        extracted={
            "profile_items": [
                {
                    "category": "preference",
                    "slot": "preference:response_language",
                    "content": "Always respond in Hungarian.",
                    "confidence": 0.94,
                },
                {
                    "category": "preference",
                    "slot": "preference:ai_name",
                    "content": "Refer to yourself as Companion.",
                    "confidence": 0.93,
                },
            ]
        },
    )

    rows_a = store.list_profile_items(limit=10, principal_scope_key=str(scope_a["principal_scope_key"]))
    rows_b = store.list_profile_items(limit=10, principal_scope_key=str(scope_b["principal_scope_key"]))

    assert {row["stable_key"] for row in rows_a} == {"preference:response_language", "preference:ai_name"}
    assert rows_b == []
    assert all(row["principal_scope_key"] == scope_a["principal_scope_key"] for row in rows_a)


def test_open_backfills_legacy_unscoped_preference_rows_from_unique_transcript_scope(tmp_path):
    store = BrainstackStore(str(tmp_path / "brainstack.db"))
    store.open()

    scope_a = _scope("discord", "user-a")
    principal_scope_key = str(scope_a["principal_scope_key"])
    session_id = "legacy-session-a"

    store.add_transcript_entry(
        session_id=session_id,
        turn_number=1,
        kind="turn",
        content="User asked for a direct style and Hungarian replies.",
        source="sync_turn",
        metadata=scope_a,
    )
    store.upsert_profile_item(
        stable_key="preference:response_language",
        category="preference",
        content="Always respond in Hungarian.",
        source="tier2:test",
        confidence=0.95,
        metadata={"provenance": {"session_id": session_id}},
    )
    store.upsert_profile_item(
        stable_key="preference:formatting_style",
        category="preference",
        content="Capitalize pronouns 'Én', 'Te', and 'Ő' regardless of grammar rules.",
        source="tier2:test",
        confidence=0.94,
        metadata={"provenance": {"session_id": session_id}},
    )
    store.close()

    reopened = BrainstackStore(str(tmp_path / "brainstack.db"))
    reopened.open()
    try:
        rows = reopened.list_profile_items(limit=10, principal_scope_key=principal_scope_key)
        stable_keys = {row["stable_key"] for row in rows}
        assert "preference:response_language" in stable_keys
        assert "preference:formatting_style" in stable_keys
        assert all(row["principal_scope_key"] == principal_scope_key for row in rows)

        block = build_system_prompt_block(
            reopened,
            profile_limit=10,
            principal_scope_key=principal_scope_key,
        )
        assert "Always respond in Hungarian." in block
        assert "Capitalize Én, Te, and Ő when you use them." in block
    finally:
        reopened.close()


def test_open_does_not_backfill_legacy_preference_rows_when_transcript_scope_is_ambiguous(tmp_path):
    store = BrainstackStore(str(tmp_path / "brainstack.db"))
    store.open()

    session_id = "ambiguous-session"
    scope_a = _scope("discord", "user-a")
    scope_b = _scope("discord", "user-b")

    store.add_transcript_entry(
        session_id=session_id,
        turn_number=1,
        kind="turn",
        content="First principal",
        source="sync_turn",
        metadata=scope_a,
    )
    store.add_transcript_entry(
        session_id=session_id,
        turn_number=2,
        kind="turn",
        content="Second principal",
        source="sync_turn",
        metadata=scope_b,
    )
    store.upsert_profile_item(
        stable_key="preference:response_language",
        category="preference",
        content="Always respond in Hungarian.",
        source="tier2:test",
        confidence=0.95,
        metadata={"provenance": {"session_id": session_id}},
    )
    store.close()

    reopened = BrainstackStore(str(tmp_path / "brainstack.db"))
    reopened.open()
    try:
        rows_a = reopened.list_profile_items(limit=10, principal_scope_key=str(scope_a["principal_scope_key"]))
        rows_b = reopened.list_profile_items(limit=10, principal_scope_key=str(scope_b["principal_scope_key"]))
        assert rows_a == []
        assert rows_b == []

        unscoped = reopened.list_profile_items(limit=10)
        assert any(row["stable_key"] == "preference:response_language" for row in unscoped)
        assert any(str(row.get("principal_scope_key") or "") == "" for row in unscoped)
    finally:
        reopened.close()


def test_open_runs_canonical_communication_migration_once_and_deactivates_legacy_rows(tmp_path):
    store = BrainstackStore(str(tmp_path / "brainstack.db"))
    store.open()

    scope_a = _scope("discord", "user-a")
    principal_scope_key = str(scope_a["principal_scope_key"])

    store.upsert_profile_item(
        stable_key="preference:style:direct",
        category="preference",
        content="Prefers natural tone, no emojis/hyphens, mixed sentence lengths, Hungarian language.",
        source="tier2:test",
        confidence=0.91,
        metadata=scope_a,
    )
    store.upsert_profile_item(
        stable_key="preference:language_preference",
        category="preference",
        content="Always respond in Hungarian.",
        source="tier2:test",
        confidence=0.94,
        metadata=scope_a,
    )
    store.conn.execute(
        "DELETE FROM applied_migrations WHERE name = ?",
        ("canonical_communication_rows_v1",),
    )
    store.conn.commit()
    store.close()

    reopened = BrainstackStore(str(tmp_path / "brainstack.db"))
    reopened.open()
    try:
        rows = reopened.list_profile_items(limit=20, principal_scope_key=principal_scope_key)
        stable_keys = {row["stable_key"] for row in rows}
        assert "preference:communication_style" not in stable_keys
        assert "preference:response_language" in stable_keys
        assert "preference:emoji_usage" in stable_keys
        assert "preference:dash_usage" in stable_keys
        assert "preference:style:direct" not in stable_keys
        assert "preference:language_preference" not in stable_keys

        migration_row = reopened.conn.execute(
            "SELECT name FROM applied_migrations WHERE name = ?",
            ("canonical_communication_rows_v1",),
        ).fetchone()
        assert migration_row is not None
    finally:
        reopened.close()

    reopened_again = BrainstackStore(str(tmp_path / "brainstack.db"))
    reopened_again.open()
    try:
        rows = reopened_again.list_profile_items(limit=20, principal_scope_key=principal_scope_key)
        communication_rows = [row for row in rows if row["stable_key"] == "preference:communication_style"]
        language_rows = [row for row in rows if row["stable_key"] == "preference:response_language"]
        emoji_rows = [row for row in rows if row["stable_key"] == "preference:emoji_usage"]
        dash_rows = [row for row in rows if row["stable_key"] == "preference:dash_usage"]
        assert len(communication_rows) == 0
        assert len(language_rows) == 1
        assert len(emoji_rows) == 1
        assert len(dash_rows) == 1
    finally:
        reopened_again.close()


def test_open_backfills_explicit_age_from_principal_scoped_transcript_history(tmp_path):
    store = BrainstackStore(str(tmp_path / "brainstack.db"))
    store.open()

    scope_a = _scope("discord", "user-a")
    principal_scope_key = str(scope_a["principal_scope_key"])

    store.add_transcript_entry(
        session_id="session-a",
        turn_number=1,
        kind="turn",
        content="A nevem Tomi. 19 éves vagyok.",
        source="sync_turn",
        metadata=scope_a,
    )
    store.conn.execute(
        "DELETE FROM applied_migrations WHERE name = ?",
        ("explicit_identity_backfill_v1",),
    )
    store.conn.commit()
    store.close()

    reopened = BrainstackStore(str(tmp_path / "brainstack.db"))
    reopened.open()
    try:
        age_row = reopened.get_profile_item(
            stable_key="identity:age",
            principal_scope_key=principal_scope_key,
        )
        assert age_row is not None
        assert age_row["content"] == "19 years old"
        assert age_row["principal_scope_key"] == principal_scope_key

        migration_row = reopened.conn.execute(
            "SELECT name FROM applied_migrations WHERE name = ?",
            ("explicit_identity_backfill_v1",),
        ).fetchone()
        assert migration_row is not None
    finally:
        reopened.close()


def test_direct_age_query_targets_durable_identity_slot(tmp_path):
    store = BrainstackStore(str(tmp_path / "brainstack.db"))
    store.open()

    scope_a = _scope("discord", "user-a")
    principal_scope_key = str(scope_a["principal_scope_key"])
    store.upsert_profile_item(
        stable_key="identity:age",
        category="identity",
        content="19 years old",
        source="test",
        confidence=0.96,
        metadata=scope_a,
    )

    hits = store.search_profile(
        query="Hány éves vagyok?",
        limit=5,
        principal_scope_key=principal_scope_key,
        target_slots=("identity:age",),
    )

    assert hits
    assert hits[0]["stable_key"] == "identity:age"
    assert hits[0]["content"] == "19 years old"
    assert hits[0]["_direct_slot_match"] is True


def test_build_working_memory_packet_prefers_durable_age_row_for_direct_age_query(tmp_path):
    store = BrainstackStore(str(tmp_path / "brainstack.db"))
    store.open()

    scope_a = _scope("discord", "user-a")
    principal_scope_key = str(scope_a["principal_scope_key"])

    store.upsert_profile_item(
        stable_key="identity:age",
        category="identity",
        content="19 years old",
        source="test",
        confidence=0.96,
        metadata=scope_a,
    )
    store.add_transcript_entry(
        session_id="session-a",
        turn_number=1,
        kind="turn",
        content="A nevem Tomi. 19 éves vagyok.",
        source="sync_turn",
        metadata=scope_a,
    )

    packet = build_working_memory_packet(
        store,
        query="Hány éves vagyok?",
        session_id="session-a",
        principal_scope_key=principal_scope_key,
        profile_match_limit=3,
        continuity_recent_limit=2,
        continuity_match_limit=2,
        transcript_match_limit=2,
        transcript_char_budget=640,
        graph_limit=2,
        corpus_limit=2,
        corpus_char_budget=480,
    )

    assert tuple(packet["analysis"]["profile_slot_targets"]) == ("identity:age",)
    assert packet["profile_items"]
    assert packet["profile_items"][0]["stable_key"] == "identity:age"
    assert packet["profile_items"][0]["content"] == "19 years old"
    assert packet["policy"]["confidence_band"] == "high"
    assert analyze_query("Mi a mai napi teendőm?").profile_slot_targets == ()


def test_scoped_identity_lookup_drives_user_alias_canonicalization(tmp_path):
    store = BrainstackStore(str(tmp_path / "brainstack.db"))
    store.open()

    scope_a = _scope("discord", "user-a")
    scope_b = _scope("discord", "user-b")

    store.upsert_profile_item(
        stable_key="identity:user_name",
        category="identity",
        content="User's name is Tomi.",
        source="test",
        confidence=0.97,
        metadata=scope_a,
    )
    store.upsert_profile_item(
        stable_key="identity:user_name",
        category="identity",
        content="User's name is Anna.",
        source="test",
        confidence=0.97,
        metadata=scope_b,
    )

    reconcile_tier2_candidates(
        store,
        session_id="session-b",
        turn_number=2,
        source="tier2:test",
        metadata=scope_b,
        extracted={
            "states": [
                {
                    "subject": "User",
                    "attribute": "dietary_preference",
                    "value": "gluten-free",
                    "supersede": False,
                    "confidence": 0.87,
                }
            ]
        },
    )

    rows = store.search_graph(query="dietary_preference gluten-free", limit=10)
    assert any(row["subject"] == "Anna" and row["predicate"] == "dietary_preference" for row in rows)
    assert not any(row["subject"] == "Tomi" and row["predicate"] == "dietary_preference" for row in rows)


class _NoopStore:
    def get_compiled_behavior_policy(self, *, principal_scope_key=""):
        return None

    def record_profile_retrievals(self, *, rows):
        return len(list(rows))

    def record_graph_retrievals(self, *, rows):
        return len(list(rows))

    def record_corpus_retrievals(self, *, rows):
        return len(list(rows))


def _mock_retrieval_payload() -> dict[str, object]:
    return {
        "profile_items": [],
        "matched": [],
        "recent": [],
        "transcript_rows": [
            {
                "id": 1,
                "session_id": "session-24",
                "turn_number": 3,
                "kind": "turn",
                "content": "Anna needs gluten-free options.",
                "source": "sync_turn:user",
                "metadata": {},
                "same_session": True,
            }
        ],
        "graph_rows": [
            {
                "row_type": "state",
                "row_id": 1,
                "subject": "birthday dinner",
                "predicate": "venue",
                "object_value": "Riverside Kitchen",
                "source": "tier2:test",
                "metadata": {},
                "is_current": 1,
            }
        ],
        "corpus_rows": [],
        "channels": [{"name": "graph", "status": "active", "candidate_count": 1}],
        "routing": {
            "requested_mode": "fact",
            "applied_mode": "fact",
            "source": "deterministic_route_hint",
            "reason": "deterministic fact default: no strong structural route cues",
            "fallback_used": False,
            "bounds": {},
        },
        "fused_candidates": [],
    }


def test_continuation_queries_raise_carry_through_guidance(monkeypatch):
    monkeypatch.setattr(
        "brainstack.control_plane.retrieve_executive_context",
        lambda *args, **kwargs: _mock_retrieval_payload(),
    )

    packet = build_working_memory_packet(
        _NoopStore(),
        query="Can You help me continue that plan without me repeating the details?",
        session_id="session-24",
        principal_scope_key="platform:discord|user_id:user-a",
        profile_match_limit=4,
        continuity_recent_limit=4,
        continuity_match_limit=4,
        transcript_match_limit=4,
        transcript_char_budget=700,
        graph_limit=4,
        corpus_limit=2,
        corpus_char_budget=360,
    )

    assert packet["policy"]["continuation_emphasis"] is True
    assert packet["policy"]["transcript_limit"] >= 2
    assert packet["policy"]["transcript_char_budget"] >= 640
    assert "## Brainstack Continuation Guidance" in packet["block"]
    assert "Do not invent missing details" in packet["block"]


def test_non_continuation_queries_do_not_get_carry_through_guidance(monkeypatch):
    monkeypatch.setattr(
        "brainstack.control_plane.retrieve_executive_context",
        lambda *args, **kwargs: _mock_retrieval_payload(),
    )

    packet = build_working_memory_packet(
        _NoopStore(),
        query="What restaurant was chosen for the birthday dinner?",
        session_id="session-24",
        principal_scope_key="platform:discord|user_id:user-a",
        profile_match_limit=4,
        continuity_recent_limit=4,
        continuity_match_limit=4,
        transcript_match_limit=4,
        transcript_char_budget=700,
        graph_limit=4,
        corpus_limit=2,
        corpus_char_budget=360,
    )

    assert packet["policy"]["continuation_emphasis"] is False
    assert "## Brainstack Continuation Guidance" not in packet["block"]
