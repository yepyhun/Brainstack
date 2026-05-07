from __future__ import annotations

import subprocess
from pathlib import Path

from brainstack.db import BrainstackStore
from brainstack.retrieval import build_system_prompt_projection, render_working_memory_block
from scripts import hermes_gateway_patch_support
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


def test_core_host_patch_mode_applies_auxiliary_main_model_inheritance(tmp_path: Path) -> None:
    auxiliary_client = tmp_path / "auxiliary_client.py"
    auxiliary_client.write_text(
        "def resolve_provider_client(provider=None, model=None):\n"
        "    cfg_provider = provider\n"
        "    cfg_model = None\n"
        "    resolved_model = model or cfg_model\n"
        "    return provider, resolved_model\n",
        encoding="utf-8",
    )

    actions = install_into_hermes._run_host_patch(
        "_patch_auxiliary_client",
        auxiliary_client,
        dry_run=False,
        host_patch_mode="core",
    )
    text = auxiliary_client.read_text(encoding="utf-8")

    assert actions == ["auxiliary_client:inherit_main_model"]
    assert 'explicit_provider == "main"' in text
    assert "_read_main_model() or None" in text


def test_core_run_agent_patch_closes_memory_provider_on_soft_cache_eviction(tmp_path: Path) -> None:
    run_agent = tmp_path / "run_agent.py"
    run_agent.write_text(
        "class AIAgent:\n"
        "    def release_clients(self) -> None:\n"
        "        \"\"\"Release cached agent resources.\n\n"
        "        Do not kill:\n"
        "          - process_registry entries for task_id\n"
        "          - memory provider (has its own lifecycle; keeps running)\n"
        "        \"\"\"\n"
        "        if self._memory_manager and final_response and original_user_message and not interrupted:\n"
        "            pass\n"
        "        # Close the OpenAI/httpx client to release sockets immediately.\n"
        "        try:\n"
        "            client = getattr(self, \"client\", None)\n"
        "            if client is not None:\n"
        "                self._close_openai_client(client, reason=\"cache_evict\", shared=True)\n"
        "                self.client = None\n"
        "        except Exception:\n"
        "            pass\n",
        encoding="utf-8",
    )

    actions = install_into_hermes._run_host_patch(
        "_patch_run_agent_cache_evict_memory_provider_shutdown",
        run_agent,
        dry_run=False,
        host_patch_mode="core",
    )
    text = run_agent.read_text(encoding="utf-8")

    assert "run_agent:cache_evict_memory_provider_shutdown" in actions
    assert "self._memory_manager.shutdown_all()" in text
    assert "self._memory_manager = None" in text
    assert "do not call on_session_end() here" in text
    assert "memory provider session-end flush" in text
    assert "keeps running" not in text


def test_core_host_patch_mode_bounds_session_search_before_gateway_timeout(
    tmp_path: Path,
) -> None:
    session_search_tool = tmp_path / "session_search_tool.py"
    session_search_tool.write_text(
        "import asyncio\n"
        "import concurrent.futures\n"
        "import json\n\n"
        "def _get_session_search_max_concurrency(default=3):\n"
        "    return default\n\n"
        "def _format_timestamp(ts):\n"
        "    return str(ts)\n\n"
        "def session_search(query):\n"
        "    try:\n"
        "        seen_sessions = {}\n"
        "        tasks = []\n"
        "        async def _summarize_all():\n"
        "            coros = []\n"
        "            return await asyncio.gather(*coros, return_exceptions=True)\n"
        "        try:\n"
        "            results = _run_async(_summarize_all())\n"
        "        except concurrent.futures.TimeoutError:\n"
        "            logging.warning(\n"
        "                \"Session summarization timed out after 60 seconds\",\n"
        "                exc_info=True,\n"
        "            )\n"
        "            return json.dumps({\n"
        "                \"success\": False,\n"
        "                \"error\": \"Session summarization timed out. Try a more specific query or reduce the limit.\",\n"
        "            }, ensure_ascii=False)\n",
        encoding="utf-8",
    )

    actions = install_into_hermes._run_host_patch(
        "_patch_session_search_total_deadline",
        session_search_tool,
        dry_run=False,
        host_patch_mode="core",
    )
    text = session_search_tool.read_text(encoding="utf-8")

    assert actions == [
        "session_search:total_deadline_helper",
        "session_search:bounded_gather",
        "session_search:timeout_degraded_preview",
    ]
    assert "def _get_session_search_total_deadline" in text
    assert "timeout=_get_session_search_total_deadline()" in text
    assert "SESSION_SEARCH_SUMMARIZATION_TIMEOUT" in text
    assert '"success": True' in text


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


def test_profile_projection_uses_typed_slot_labels(tmp_path: Path) -> None:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"))
    store.open()
    try:
        store.upsert_profile_item(
            stable_key="identity:age",
            category="identity",
            content="19",
            source="test",
            confidence=0.95,
            metadata={"principal_scope_key": "principal:test", "target_slot": "identity.age"},
        )
        projection = build_system_prompt_projection(
            store,
            profile_limit=4,
            principal_scope_key="principal:test",
            session_id="session:test",
        )

        assert "[identity.age] 19" in str(projection["block"])
    finally:
        store.close()


def test_system_projection_includes_truth_eligible_project_metadata(tmp_path: Path) -> None:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    try:
        scope = "principal:project-metadata"
        store.upsert_graph_state(
            subject_name="Brainstack",
            attribute="created_by",
            value_text="Canary Alex",
            source="test",
            metadata={
                "principal_scope_key": scope,
                "truth_eligible": True,
                "support_visibility": "answer_evidence",
                "admission": {
                    "target_slot": "project.created_by",
                    "truth_eligible": True,
                    "support_visibility": "answer_evidence",
                },
            },
        )
        store.upsert_graph_state(
            subject_name="Brainstack graph layer",
            attribute="component_inspired_by",
            value_text="Graphiti",
            source="test",
            metadata={
                "principal_scope_key": scope,
                "truth_eligible": True,
                "support_visibility": "answer_evidence",
                "admission": {
                    "target_slot": "project.component_inspired_by",
                    "truth_eligible": True,
                    "support_visibility": "answer_evidence",
                },
            },
        )
        projection = build_system_prompt_projection(
            store,
            profile_limit=4,
            principal_scope_key=scope,
            session_id="session:test",
        )

        assert "[project.created.by] Brainstack: Canary Alex" in str(projection["block"])
        assert "[project.component.inspired.by] Brainstack graph layer: Graphiti" in str(projection["block"])
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


def test_gateway_patch_bundle_contains_capability_preserving_toolloader_patch() -> None:
    manifest = hermes_gateway_patch_support.patch_bundle_manifest()
    patch_names = {entry["name"] for entry in manifest["patches"]}
    payload_paths = {entry["path"] for entry in manifest["payloads"]}

    assert "002-capability-preserving-deferred-tool-schema.patch" in patch_names
    assert "003-tool-runtime-spawn-hardening.patch" in patch_names
    assert "gateway/turn_profiles.py" in payload_paths
    assert "gateway/memory_answer_renderer.py" in payload_paths

    patch_text = (
        Path(__file__).resolve().parents[1]
        / "patches"
        / "hermes_gateway"
        / "002-capability-preserving-deferred-tool-schema.patch"
    ).read_text(encoding="utf-8")
    assert "hermes_deferred_tools.py" in patch_text
    assert "deferred_tool_schema_mode" in patch_text
    assert "DISCORD_DEFAULT_CAPABILITY_PRESERVED" in patch_text
    assert "TOOL_NOT_LOADED_OR_NOT_CONFIGURED" in patch_text


def test_gateway_patch_bundle_installs_tool_runtime_spawn_hardening() -> None:
    source_patch_names = {path.name for path in hermes_gateway_patch_support.source_patch_files()}
    assert source_patch_names == {"003-tool-runtime-spawn-hardening.patch"}

    patch_text = (
        Path(__file__).resolve().parents[1]
        / "patches"
        / "hermes_gateway"
        / "003-tool-runtime-spawn-hardening.patch"
    ).read_text(encoding="utf-8")

    assert "tools/environments/base.py" in patch_text
    assert "tools/environments/local.py" in patch_text
    assert "tools/code_execution_tool.py" in patch_text
    assert "tools/process_registry.py" in patch_text
    assert "gateway/platforms/whatsapp.py" in patch_text
    assert "_execute_lock = threading.RLock()" in patch_text
    assert "with self._execute_lock" in patch_text
    assert "start_new_session=False if _IS_WINDOWS else True" in patch_text


def test_gateway_patch_probes_enforce_boost_only_toolloader_contract() -> None:
    probes = hermes_gateway_patch_support.REQUIRED_GATEWAY_PROBES

    assert "hermes_deferred_tools.py" not in probes
    assert "validate_assistant_output_all" in probes["run_agent.py"]
    assert "validate_assistant_output_all" in probes["agent/memory_manager.py"]
    assert "capability_preserving_default" in probes["gateway/turn_profiles.py"]
    assert "render_memory_answer" in probes["gateway/memory_answer_renderer.py"]
    assert "_execute_lock" in probes["tools/environments/base.py"]
    assert "start_new_session=False if _IS_WINDOWS else True" in probes["tools/environments/local.py"]
    assert "start_new_session=False if _IS_WINDOWS else True" in probes["tools/code_execution_tool.py"]
    assert "start_new_session=False if _IS_WINDOWS else True" in probes["tools/process_registry.py"]
    assert "start_new_session=False if _IS_WINDOWS else True" in probes["gateway/platforms/whatsapp.py"]
