from plugins.memory.brainstack.db import BrainstackStore
from plugins.memory.brainstack.retrieval import build_system_prompt_block, render_working_memory_block


def test_system_prompt_projects_active_communication_contract(tmp_path):
    store = BrainstackStore(str(tmp_path / "brainstack.db"))
    store.upsert_profile_item(
        stable_key="identity:name",
        category="identity",
        content="Tomi",
        source="test",
        confidence=0.95,
    )
    store.upsert_profile_item(
        stable_key="preference:emoji_usage",
        category="preference",
        content="Minimize emoji usage; only use them if truly fitting or funny.",
        source="test",
        confidence=0.9,
    )
    store.upsert_profile_item(
        stable_key="preference:formatting",
        category="preference",
        content="Do not use dashes. Prefer commas or periods.",
        source="test",
        confidence=0.9,
    )
    store.upsert_graph_state(
        subject_name="Assistant",
        attribute="writing_style",
        value_text="Write directly, rarely use emoji, avoid dashes, and keep paragraph breaks readable.",
        source="test",
        supersede=True,
    )

    block = build_system_prompt_block(store, profile_limit=6)

    assert "# Brainstack Active Communication Contract" in block
    assert "Apply these rules silently in every reply." in block
    assert "rarely use emoji" in block
    assert "[identity] Tomi" in block
    assert "[preference] Minimize emoji usage" not in block
    assert "[preference] Do not use dashes" not in block


def test_working_memory_block_hides_contract_rows_from_profile_match(tmp_path):
    store = BrainstackStore(str(tmp_path / "brainstack.db"))
    store.upsert_profile_item(
        stable_key="preference:communication_style",
        category="preference",
        content="Avoid technical jargon and explain logic in an easy-to-understand way.",
        source="test",
        confidence=0.92,
    )
    store.upsert_profile_item(
        stable_key="preference:emoji_usage",
        category="preference",
        content="Minimize emoji usage; only use them if truly fitting or funny.",
        source="test",
        confidence=0.9,
    )
    store.upsert_profile_item(
        stable_key="shared_work:project",
        category="shared_work",
        content="Tomi is leading the BrainStack project.",
        source="test",
        confidence=0.88,
    )
    store.upsert_graph_state(
        subject_name="Assistant",
        attribute="writing_style",
        value_text="No dashes, rare emoji, and readable paragraph breaks.",
        source="test",
        supersede=True,
    )

    block = render_working_memory_block(
        policy={
            "mode": "balanced",
            "provenance_mode": "compact",
            "confidence_band": "high",
            "tool_avoidance_allowed": True,
            "tool_avoidance_reason": "test",
            "show_policy": False,
            "show_graph_history": False,
            "transcript_char_budget": 0,
            "corpus_char_budget": 0,
        },
        profile_items=store.list_profile_items(limit=10),
        matched=[],
        recent=[],
        transcript_rows=[],
        graph_rows=store.search_graph(query="Assistant", limit=10),
        corpus_rows=[],
    )

    assert "## Brainstack Active Communication Contract" in block
    assert "No dashes, rare emoji, and readable paragraph breaks." in block
    assert "[shared work] Tomi is leading the BrainStack project." in block
    assert "[preference] Avoid technical jargon and explain logic in an easy-to-understand way." not in block
    assert "[preference] Minimize emoji usage; only use them if truly fitting or funny." not in block
