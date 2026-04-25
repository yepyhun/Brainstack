from __future__ import annotations

import subprocess
from pathlib import Path

from brainstack.db import BrainstackStore
from brainstack.retrieval import build_system_prompt_projection, render_working_memory_block
from scripts import install_into_hermes


def test_core_host_patch_mode_skips_legacy_prompt_builder_patch(tmp_path: Path) -> None:
    prompt_builder = tmp_path / "prompt_builder.py"
    original = (
        'SYSTEM = (\n'
        '    "without acting are not acceptable."\n'
        ')\n'
    )
    prompt_builder.write_text(original, encoding="utf-8")

    actions = install_into_hermes._run_host_patch(
        "_patch_prompt_builder",
        prompt_builder,
        dry_run=False,
        host_patch_mode="core",
    )

    assert actions == []
    assert prompt_builder.read_text(encoding="utf-8") == original


def test_legacy_host_patch_mode_can_still_apply_prompt_builder_patch(tmp_path: Path) -> None:
    prompt_builder = tmp_path / "prompt_builder.py"
    prompt_builder.write_text(
        'SYSTEM = (\n'
        '    "without acting are not acceptable."\n'
        ')\n',
        encoding="utf-8",
    )

    actions = install_into_hermes._run_host_patch(
        "_patch_prompt_builder",
        prompt_builder,
        dry_run=False,
        host_patch_mode="legacy",
    )

    assert actions == ["prompt_builder:scheduler_truth_guidance"]
    assert "generic internal task list is not a scheduled job" in prompt_builder.read_text(
        encoding="utf-8"
    )


def test_core_memory_manager_patch_skips_metadata_compat_seam(tmp_path: Path) -> None:
    memory_manager = tmp_path / "memory_manager.py"
    memory_manager.write_text(
        "class MemoryManager:\n"
        "    def on_memory_write(self, action: str, target: str, content: str) -> None:\n"
        "        for provider in self.providers:\n"
        "            try:\n"
        "                provider.on_memory_write(action, target, content)\n"
        "            except Exception:\n"
        "                pass\n",
        encoding="utf-8",
    )

    actions = install_into_hermes._run_host_patch(
        "_patch_memory_manager_required_seam",
        memory_manager,
        dry_run=False,
        host_patch_mode="core",
    )
    text = memory_manager.read_text(encoding="utf-8")

    assert actions == []
    assert "metadata: dict | None = None" not in text
    assert "private recalled memory context" not in text


def test_compat_memory_manager_patch_adds_metadata_seam(tmp_path: Path) -> None:
    memory_manager = tmp_path / "memory_manager.py"
    memory_manager.write_text(
        "class MemoryManager:\n"
        "    def on_memory_write(self, action: str, target: str, content: str) -> None:\n"
        "        for provider in self.providers:\n"
        "            try:\n"
        "                provider.on_memory_write(action, target, content)\n"
        "            except Exception:\n"
        "                pass\n",
        encoding="utf-8",
    )

    actions = install_into_hermes._run_host_patch(
        "_patch_memory_manager_required_seam",
        memory_manager,
        dry_run=False,
        host_patch_mode="compat",
    )
    text = memory_manager.read_text(encoding="utf-8")

    assert actions == [
        "memory_manager:memory_write_metadata_signature",
        "memory_manager:memory_write_metadata_bridge",
    ]
    assert "metadata: dict | None = None" in text
    assert "private recalled memory context" not in text


def test_brainstack_projection_carries_private_memory_and_scheduler_contract(
    tmp_path: Path,
) -> None:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"))
    store.open()
    try:
        store.upsert_profile_item(
            stable_key="identity:name",
            category="identity",
            content="The user's name is ExampleUser.",
            source="test",
            confidence=0.95,
            metadata={"principal_scope_key": "principal:test"},
        )

        projection = build_system_prompt_projection(
            store,
            profile_limit=4,
            principal_scope_key="principal:test",
            session_id="session:test",
        )
        projection_block = str(projection["block"])

        packet_block = render_working_memory_block(
            policy={},
            profile_items=[],
            task_rows=[],
            matched=[],
            recent=[],
            transcript_rows=[],
            graph_rows=[],
            corpus_rows=[],
            operating_rows=[],
        )

        assert "private recalled memory context is background evidence, not new user input" in packet_block
        assert "Do not mention Brainstack blocks" in packet_block
        assert "scheduled follow-up exists only when the current evidence includes a native scheduler record" in projection_block
        assert "internal task list is not by itself a scheduled job" in projection_block
    finally:
        store.close()


def test_private_runtime_paths_are_release_hygiene_failures(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    private_file = tmp_path / "hermes-config" / "agent-smoke" / "auth.json"
    private_file.parent.mkdir(parents=True)
    private_file.write_text('{"access_token": "not-a-real-token-but-long-enough"}\n', encoding="utf-8")
    subprocess.run(["git", "add", str(private_file.relative_to(tmp_path))], cwd=tmp_path, check=True)

    report = install_into_hermes._check_release_hygiene(tmp_path)

    assert report["status"] == "fail"
    assert "hermes-config/agent-smoke/auth.json" in report["private_tracked"]


def test_brainstack_payload_refuses_private_runtime_sources() -> None:
    payload = [
        {
            "source": "brainstack/__init__.py",
            "target": "/tmp/brainstack/__init__.py",
            "sha256": "ok",
        },
        {
            "source": "hermes-config/agent-smoke/config.yaml",
            "target": "/tmp/hermes-config/agent-smoke/config.yaml",
            "sha256": "bad",
        },
    ]

    try:
        install_into_hermes._assert_no_private_payload_files(payload)
    except RuntimeError as exc:
        assert "hermes-config/agent-smoke/config.yaml" in str(exc)
    else:
        raise AssertionError("private runtime payload was accepted")
