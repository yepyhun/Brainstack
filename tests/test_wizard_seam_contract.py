from __future__ import annotations

import importlib.util
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


def test_core_host_patch_mode_evicts_closed_auxiliary_sync_client(tmp_path: Path) -> None:
    auxiliary_client = tmp_path / "auxiliary_client.py"
    auxiliary_client.write_text(
        "from typing import Any, Dict, Optional, Tuple\n\n"
        "created = []\n"
        "_client_cache = {}\n\n"
        "class _Lock:\n"
        "    def __enter__(self):\n"
        "        return self\n"
        "    def __exit__(self, *args):\n"
        "        return False\n\n"
        "_client_cache_lock = _Lock()\n\n"
        "class _RealClient:\n"
        "    def __init__(self):\n"
        "        self.closed = False\n"
        "    def is_closed(self):\n"
        "        return self.closed\n"
        "    def close(self):\n"
        "        self.closed = True\n\n"
        "class _WrappedClient:\n"
        "    def __init__(self):\n"
        "        self._real_client = _RealClient()\n"
        "    def close(self):\n"
        "        self._real_client.close()\n\n"
        "def _read_main_model():\n"
        "    return 'gpt-main'\n\n"
        "def _normalize_main_runtime(main_runtime):\n"
        "    return main_runtime\n\n"
        "def _client_cache_key(provider, *, async_mode=False, base_url=None, api_key=None, api_mode=None, main_runtime=None, is_vision=False):\n"
        "    return (provider, async_mode, base_url or '', api_key or '', api_mode or '', is_vision)\n\n"
        "def _force_close_async_httpx(client):\n"
        "    client.force_closed = True\n\n"
        "def resolve_provider_client(provider, model=None, async_mode=False, explicit_base_url=None, explicit_api_key=None, api_mode=None, main_runtime=None, is_vision=False):\n"
        "    cfg_provider = provider\n"
        "    cfg_model = None\n"
        "    resolved_model = model or cfg_model\n"
        "    client = _WrappedClient()\n"
        "    created.append(client)\n"
        "    return client, resolved_model or 'gpt-main'\n\n"
        "def _cached_client_accepts_slash_models(client: Any, cached_default: Optional[str]) -> bool:\n"
        "    return True\n\n"
        "def _compat_model(client: Any, model: Optional[str], cached_default: Optional[str]) -> Optional[str]:\n"
        "    if model and '/' in model and not _cached_client_accepts_slash_models(client, cached_default):\n"
        "        return cached_default\n"
        "    return model or cached_default\n\n"
        "def _get_cached_client(\n"
        "    provider: str,\n"
        "    model: str = None,\n"
        "    async_mode: bool = False,\n"
        "    base_url: str = None,\n"
        "    api_key: str = None,\n"
        "    api_mode: str = None,\n"
        "    main_runtime: Optional[Dict[str, Any]] = None,\n"
        "    is_vision: bool = False,\n"
        ") -> Tuple[Optional[Any], Optional[str]]:\n"
        "    current_loop = None\n"
        "    runtime = _normalize_main_runtime(main_runtime)\n"
        "    cache_key = _client_cache_key(\n"
        "        provider,\n"
        "        async_mode=async_mode,\n"
        "        base_url=base_url,\n"
        "        api_key=api_key,\n"
        "        api_mode=api_mode,\n"
        "        main_runtime=main_runtime,\n"
        "        is_vision=is_vision,\n"
        "    )\n"
        "    with _client_cache_lock:\n"
        "        if cache_key in _client_cache:\n"
        "            cached_client, cached_default, cached_loop = _client_cache[cache_key]\n"
        "            if async_mode:\n"
        "                loop_ok = (\n"
        "                    cached_loop is not None\n"
        "                    and cached_loop is current_loop\n"
        "                    and not cached_loop.is_closed()\n"
        "                )\n"
        "                if loop_ok:\n"
        "                    effective = _compat_model(cached_client, model, cached_default)\n"
        "                    return cached_client, effective\n"
        "                _force_close_async_httpx(cached_client)\n"
        "                del _client_cache[cache_key]\n"
        "            else:\n"
        "                effective = _compat_model(cached_client, model, cached_default)\n"
        "                return cached_client, effective\n"
        "    client, default_model = resolve_provider_client(\n"
        "        provider,\n"
        "        model,\n"
        "        async_mode,\n"
        "        explicit_base_url=base_url,\n"
        "        explicit_api_key=api_key,\n"
        "        api_mode=api_mode,\n"
        "        main_runtime=runtime,\n"
        "        is_vision=is_vision,\n"
        "    )\n"
        "    with _client_cache_lock:\n"
        "        _client_cache[cache_key] = (client, default_model, current_loop)\n"
        "    return client, default_model\n",
        encoding="utf-8",
    )

    actions = install_into_hermes._run_host_patch(
        "_patch_auxiliary_client",
        auxiliary_client,
        dry_run=False,
        host_patch_mode="core",
    )
    text = auxiliary_client.read_text(encoding="utf-8")

    assert actions == [
        "auxiliary_client:inherit_main_model",
        "auxiliary_client:closed_sync_cache_helper",
        "auxiliary_client:evict_closed_sync_cache",
    ]
    assert "def _brainstack_auxiliary_client_is_closed" in text
    assert "_brainstack_auxiliary_client_is_closed(cached_client)" in text

    spec = importlib.util.spec_from_file_location("patched_auxiliary_client", auxiliary_client)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    first_client, _ = module._get_cached_client("openai-codex", model="gpt-5.5", base_url="https://example.test")
    first_client.close()
    second_client, _ = module._get_cached_client("openai-codex", model="gpt-5.5", base_url="https://example.test")

    assert first_client is not second_client
    assert len(module.created) == 2

    repeated_actions = install_into_hermes._run_host_patch(
        "_patch_auxiliary_client",
        auxiliary_client,
        dry_run=False,
        host_patch_mode="core",
    )
    assert repeated_actions == []


def test_core_host_patch_mode_applies_discord_typing_backoff(tmp_path: Path) -> None:
    discord_py = tmp_path / "discord.py"
    discord_py.write_text(
        "import asyncio\n"
        "import os\n"
        "import time\n"
        "from typing import Dict\n\n"
        "class DiscordAdapter:\n"
        "    def __init__(self):\n"
        "        # Persistent typing indicator loops per channel (DMs don't reliably\n"
        "        # show the standard typing gateway event for bots)\n"
        "        self._typing_tasks: Dict[str, asyncio.Task] = {}\n\n"
        "    async def send_typing(self, chat_id: str, metadata=None) -> None:\n"
        "        \"\"\"Start a persistent typing indicator for a channel.\n\n"
        "        Discord's TYPING_START gateway event is unreliable in DMs for bots.\n"
        "        Instead, start a background loop that hits the typing endpoint every\n"
        "        8 seconds (typing indicator lasts ~10s).  The loop is cancelled when\n"
        "        stop_typing() is called (after the response is sent).\n"
        "        \"\"\"\n"
        "        if not self._client:\n"
        "            return\n"
        "        # Don't start a duplicate loop\n"
        "        if chat_id in self._typing_tasks:\n"
        "            return\n\n"
        "        async def _typing_loop() -> None:\n"
        "            try:\n"
        "                while True:\n"
        "                    try:\n"
        "                        route = discord.http.Route(\n"
        "                            \"POST\", \"/channels/{channel_id}/typing\",\n"
        "                            channel_id=chat_id,\n"
        "                        )\n"
        "                        await self._client.http.request(route)\n"
        "                    except asyncio.CancelledError:\n"
        "                        return\n"
        "                    except Exception as e:\n"
        "                        logger.debug(\"Discord typing indicator failed for %s: %s\", chat_id, e)\n"
        "                        return\n"
        "                    await asyncio.sleep(8)\n"
        "            except asyncio.CancelledError:\n"
        "                pass\n\n"
        "        self._typing_tasks[chat_id] = asyncio.create_task(_typing_loop())\n\n"
        "    async def stop_typing(self, chat_id: str) -> None:\n"
        "        \"\"\"Stop the persistent typing indicator for a channel.\"\"\"\n"
        "        task = self._typing_tasks.pop(chat_id, None)\n"
        "        if task:\n"
        "            task.cancel()\n"
        "            try:\n"
        "                await task\n"
        "            except (asyncio.CancelledError, Exception):\n"
        "                pass\n",
        encoding="utf-8",
    )

    actions = install_into_hermes._run_host_patch(
        "_patch_discord_typing_backoff",
        discord_py,
        dry_run=False,
        host_patch_mode="core",
    )
    text = discord_py.read_text(encoding="utf-8")

    assert actions == [
        "discord_typing:rate_limit_state",
        "discord_typing:opt_in_loop",
    ]
    assert "self._typing_endpoint_enabled" in text
    assert "self._typing_backoff_until" in text
    assert "Discord edit-streaming is the primary liveness channel" in text
    assert "HERMES_DISCORD_TYPING_ENDPOINT_ENABLED" in text
    assert "if not self._typing_endpoint_enabled or not self._client" in text
    assert "if not existing.done()" in text
    assert "asyncio.shield(task)" in text


def test_core_host_patch_mode_applies_ebadf_provider_transport_recovery(tmp_path: Path) -> None:
    run_agent = tmp_path / "run_agent.py"
    run_agent.write_text(
        "class AIAgent:\n"
        "    _TRANSIENT_TRANSPORT_ERRORS = frozenset({'ReadTimeout'})\n\n"
        "    def _try_recover_primary_transport(self, api_error, *, retry_count, max_retries):\n"
        "        # Only for transient transport errors\n"
        "        error_type = type(api_error).__name__\n"
        "        if error_type not in self._TRANSIENT_TRANSPORT_ERRORS:\n"
        "            return False\n"
        "        return True\n",
        encoding="utf-8",
    )

    actions = install_into_hermes._run_host_patch(
        "_patch_run_agent_ebadf_transport_recovery",
        run_agent,
        dry_run=False,
        host_patch_mode="core",
    )
    text = run_agent.read_text(encoding="utf-8")

    assert actions == ["run_agent:ebadf_transport_recovery"]
    assert "is_ebadf_transport_error" in text
    assert "_errno.EBADF" in text
    assert "and not is_ebadf_transport_error" in text


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
    assert "def _get_session_search_total_deadline(default: float = 20.0)" in text
    assert "timeout=_get_session_search_total_deadline()" in text
    assert "SESSION_SEARCH_SUMMARIZATION_TIMEOUT" in text
    assert '"success": True' in text


def test_core_host_patch_lowers_existing_session_search_90s_default(tmp_path: Path) -> None:
    session_search_tool = tmp_path / "session_search_tool.py"
    session_search_tool.write_text(
        "def _get_session_search_total_deadline(default: float = 90.0) -> float:\n"
        "    return default\n\n"
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

    assert "session_search:lower_default_total_deadline" in actions
    assert "default: float = 20.0" in text
    assert "default: float = 90.0" not in text


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
