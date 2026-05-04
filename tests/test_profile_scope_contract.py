from __future__ import annotations

from pathlib import Path

from brainstack.db import BrainstackStore


def _open_store(tmp_path: Path) -> BrainstackStore:
    store = BrainstackStore(
        str(tmp_path / "brainstack.sqlite3"),
        graph_backend="sqlite",
        corpus_backend="sqlite",
    )
    store.open()
    return store


def test_user_specific_profile_categories_are_storage_key_scoped(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.upsert_profile_item(
            stable_key="style.reply_tone",
            category="style_preference",
            content="Use terse Hungarian.",
            source="user_explicit",
            confidence=0.97,
            metadata={"principal_scope_key": "principal:laura"},
        )
        store.upsert_profile_item(
            stable_key="style.reply_tone",
            category="style_preference",
            content="Use formal English.",
            source="user_explicit",
            confidence=0.97,
            metadata={"principal_scope_key": "principal:other"},
        )

        laura_item = store.get_profile_item(stable_key="style.reply_tone", principal_scope_key="principal:laura")
        other_item = store.get_profile_item(stable_key="style.reply_tone", principal_scope_key="principal:other")

        assert laura_item is not None
        assert other_item is not None
        assert laura_item["content"] == "Use terse Hungarian."
        assert other_item["content"] == "Use formal English."
        assert laura_item["storage_key"] != other_item["storage_key"]
    finally:
        store.close()


def test_operating_profile_categories_remain_list_scoped(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.upsert_profile_item(
            stable_key="workspace.current_focus",
            category="work_context",
            content="Brainstack live follow-up.",
            source="user_explicit",
            confidence=0.95,
            metadata={"principal_scope_key": "principal:laura"},
        )
        store.upsert_profile_item(
            stable_key="workspace.current_focus",
            category="work_context",
            content="Other project.",
            source="user_explicit",
            confidence=0.95,
            metadata={"principal_scope_key": "principal:other"},
        )

        laura_items = store.list_profile_items(
            limit=4,
            categories=["work_context"],
            principal_scope_key="principal:laura",
        )

        assert [item["content"] for item in laura_items] == ["Brainstack live follow-up."]
    finally:
        store.close()
