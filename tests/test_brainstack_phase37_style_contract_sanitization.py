# ruff: noqa: E402
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_host_shims_path = REPO_ROOT / "tests" / "_host_import_shims.py"
_host_shims_spec = importlib.util.spec_from_file_location(
    "phase37_host_import_shims",
    _host_shims_path,
)
assert _host_shims_spec and _host_shims_spec.loader
_host_shims = importlib.util.module_from_spec(_host_shims_spec)
_host_shims_spec.loader.exec_module(_host_shims)
install_host_import_shims = _host_shims.install_host_import_shims

install_host_import_shims(hermes_home=REPO_ROOT)

from brainstack import BrainstackMemoryProvider
from brainstack.behavior_policy import compile_behavior_policy
from brainstack.db import BrainstackStore, utc_now_iso
from brainstack.output_contract import build_output_contract, validate_output_against_contract
from brainstack.style_contract import STYLE_CONTRACT_SLOT, build_style_contract_from_text


def _make_provider(tmp_path: Path, session_id: str) -> BrainstackMemoryProvider:
    provider = BrainstackMemoryProvider(config={"db_path": str(tmp_path / "brainstack.db")})
    provider.initialize(
        session_id,
        hermes_home=str(tmp_path),
        user_id="user-1",
        platform="discord",
        agent_identity="assistant-main",
        agent_workspace="workspace-a",
    )
    return provider


def _seed_style_contract(provider: BrainstackMemoryProvider) -> None:
    provider.prefetch(
        (
            "User style contract\n\n"
            "rules:\n"
            "1. Always respond in Hungarian.\n"
            "2. Do not use emojis.\n"
            "3. Do not use em dash punctuation.\n"
            "4. Capitalize Én, Te, and Ő only when explicitly requested.\n"
        ),
        session_id="seed-style-contract",
    )


def test_conversational_fragment_cannot_pollute_multiline_contract_title(tmp_path: Path) -> None:
    provider = _make_provider(tmp_path, "phase37-pollution")
    try:
        provider.prefetch("ird le pontosan mit kapsz meg mast ne", session_id="phase37-pollution")
        provider.prefetch(
            (
                "content:\n"
                "1. konkret tenyeket irj.\n"
                "2. emoji tilos.\n\n"
                "formatting:\n"
                "3. semmi dash, semmi kotojel.\n"
            ),
            session_id="phase37-pollution",
        )

        store = provider._store
        assert store is not None
        row = store.get_behavior_contract(principal_scope_key=provider._principal_scope_key)
        assert row is not None
        assert row["metadata"]["style_contract_title"] == "User style contract"
        assert "ird le pontosan" not in row["content"].casefold()

        trace = provider.memory_operation_trace()
        assert trace is not None
        receipt = trace["last_write_receipt"]
        assert receipt["fragment_count"] == 1
        assert receipt["write_mode"] == "create"
    finally:
        provider.shutdown()


def test_patch_lane_ignores_prior_chat_fragments(tmp_path: Path) -> None:
    provider = _make_provider(tmp_path, "phase37-patch")
    try:
        _seed_style_contract(provider)
        provider.prefetch("mondd el pontosan mit latsz", session_id="phase37-patch")
        provider.prefetch(
            "Capitalize Én, Te, and Ő every time you use them.",
            session_id="phase37-patch",
        )

        store = provider._store
        assert store is not None
        row = store.get_behavior_contract(principal_scope_key=provider._principal_scope_key)
        assert row is not None
        assert "mondd el pontosan" not in row["content"].casefold()

        trace = provider.memory_operation_trace()
        assert trace is not None
        receipt = trace["last_write_receipt"]
        assert receipt["write_mode"] == "patch"
        assert receipt["fragment_count"] == 1
        assert receipt["patch_rule_count"] == 1
    finally:
        provider.shutdown()


def test_full_contract_commit_marks_replace_after_existing_contract(tmp_path: Path) -> None:
    provider = _make_provider(tmp_path, "phase37-replace")
    try:
        _seed_style_contract(provider)

        store = provider._store
        assert store is not None
        first = store.get_behavior_contract(principal_scope_key=provider._principal_scope_key)
        assert first is not None

        provider.prefetch(
            (
                "content:\n"
                "1. konkret tenyeket irj.\n"
                "2. emoji tilos.\n\n"
                "formatting:\n"
                "3. semmi dash, semmi kotojel.\n"
            ),
            session_id="phase37-replace",
        )

        second = store.get_behavior_contract(principal_scope_key=provider._principal_scope_key)
        assert second is not None
        assert int(second["revision_number"]) == int(first["revision_number"]) + 1
        assert "semmi dash, semmi kotojel" in second["content"].casefold()

        trace = provider.memory_operation_trace()
        assert trace is not None
        receipt = trace["last_write_receipt"]
        assert receipt["write_mode"] == "replace"
    finally:
        provider.shutdown()


def test_polluted_canonical_contract_quarantines_compiled_policy(tmp_path: Path) -> None:
    store = BrainstackStore(str(tmp_path / "brainstack.db"))
    store.open()
    try:
        principal_scope_key = "platform:discord|user_id:user-1|agent_identity:assistant-main|agent_workspace:workspace-a"
        metadata = {
            "memory_class": "style_contract",
            "principal_scope_key": principal_scope_key,
            "principal_scope": {
                "platform": "discord",
                "user_id": "user-1",
                "agent_identity": "assistant-main",
                "agent_workspace": "workspace-a",
            },
            "style_contract_title": "[LauraTom] ird le pontosan mit kapsz meg mast ne!",
            "style_contract_sections": [{"heading": "Rules", "lines": ["emoji tilos", "semmi dash, semmi kotojel"]}],
        }
        now = utc_now_iso()
        content = (
            "[LauraTom] ird le pontosan mit kapsz meg mast ne!\n\n"
            "Rules:\n"
            "- emoji tilos\n"
            "- semmi dash, semmi kotojel"
        )
        store.conn.execute(
            """
            INSERT INTO behavior_contracts (
                storage_key,
                principal_scope_key,
                stable_key,
                category,
                content,
                source,
                confidence,
                metadata_json,
                source_contract_hash,
                revision_number,
                parent_revision_id,
                status,
                committed_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "behavior_contract::preference:style_contract::test::r1",
                principal_scope_key,
                STYLE_CONTRACT_SLOT,
                "preference",
                content,
                "prefetch:style_contract",
                0.9,
                json.dumps(metadata, ensure_ascii=True, sort_keys=True),
                hashlib.sha256(content.encode("utf-8")).hexdigest(),
                1,
                0,
                "active",
                now,
                now,
            ),
        )
        store.conn.execute(
            """
            INSERT INTO compiled_behavior_policies (
                principal_scope_key,
                source_storage_key,
                source_contract_hash,
                source_contract_updated_at,
                schema_version,
                compiler_version,
                title,
                policy_json,
                projection_text,
                status,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                principal_scope_key,
                "behavior_contract::preference:style_contract::test::r1",
                hashlib.sha256(content.encode("utf-8")).hexdigest(),
                now,
                2,
                "behavior_policy_v2",
                "[LauraTom] polluted",
                json.dumps({"active": True}, ensure_ascii=True, sort_keys=True),
                "polluted projection",
                "active",
                now,
            ),
        )
        store.conn.commit()

        compiled = store.get_compiled_behavior_policy(principal_scope_key=principal_scope_key)
        assert compiled is None
        remaining = store.conn.execute(
            "SELECT COUNT(*) AS count FROM compiled_behavior_policies WHERE principal_scope_key = ?",
            (principal_scope_key,),
        ).fetchone()
        assert remaining is not None
        assert int(remaining["count"]) == 0
    finally:
        store.close()


def test_dash_policy_preserves_forbid_all_dash_like_semantics(tmp_path: Path) -> None:
    payload = build_style_contract_from_text(
        raw_text=(
            "User style contract\n\n"
            "rules:\n"
            "1. Do not use dashes. Prefer commas or periods.\n"
        ),
        source="test",
    )
    assert payload is not None
    compiled = compile_behavior_policy(
        raw_content=str(payload["content"]),
        metadata=payload["metadata"],
        source_storage_key="behavior_contract::test",
        source_updated_at=utc_now_iso(),
    )
    assert compiled is not None

    contract = build_output_contract(compiled)
    result = validate_output_against_contract(
        content="alpha-beta and gamma—delta",
        compiled_policy=compiled,
    )

    assert contract["dash_policy"] == "forbid_all_dash_like"
    assert result["repairs"] == []
    assert any(item["violation"] == "dash_like_punctuation" for item in result["remaining_violations"])


def test_dash_policy_keeps_em_dash_only_repair(tmp_path: Path) -> None:
    payload = build_style_contract_from_text(
        raw_text=(
            "User style contract\n\n"
            "rules:\n"
            "1. Do not use em dash punctuation.\n"
        ),
        source="test",
    )
    assert payload is not None
    compiled = compile_behavior_policy(
        raw_content=str(payload["content"]),
        metadata=payload["metadata"],
        source_storage_key="behavior_contract::test",
        source_updated_at=utc_now_iso(),
    )
    assert compiled is not None

    contract = build_output_contract(compiled)
    result = validate_output_against_contract(
        content="alpha—beta",
        compiled_policy=compiled,
    )

    assert contract["dash_policy"] == "forbid_em_dash_only"
    assert result["content"] == "alpha-beta"
    assert any(item["repair"] == "replace_with_hyphen_minus" for item in result["repairs"])
