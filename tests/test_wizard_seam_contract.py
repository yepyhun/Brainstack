from __future__ import annotations

import asyncio
import importlib.util
import subprocess
from pathlib import Path

from brainstack.db import BrainstackStore
from brainstack.retrieval import build_system_prompt_projection, render_working_memory_block
from scripts import brainstack_doctor
from scripts import hermes_gateway_patch_support
from scripts import install_into_hermes


def test_continuation_engine_is_extension_not_brainstack_core() -> None:
    assert (install_into_hermes.SOURCE_HERMES_CONTINUATION_EXTENSION / "hermes_continuation" / "engine.py").exists()
    assert not (install_into_hermes.SOURCE_PLUGIN / "autonomy_continuation_engine.py").exists()
    assert not (install_into_hermes.SOURCE_PLUGIN / "continuation_control_contract.py").exists()
    assert not (install_into_hermes.SOURCE_PLUGIN / "work_state_contract.py").exists()


def test_token_audit_helpers_are_installer_visible() -> None:
    assert (install_into_hermes.REPO_ROOT / "scripts" / "brainstack_context_audit.py").exists()
    assert (install_into_hermes.REPO_ROOT / "scripts" / "brainstack_skill_audit.py").exists()


def test_patch_config_adds_inert_continuation_extension_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("model:\n  default: local\n", encoding="utf-8")

    result = install_into_hermes._patch_config(config_path, dry_run=False, embedding_runtime="none")
    config = install_into_hermes._load_yaml(config_path)
    continuation = config["extensions"]["hermes_continuation"]

    assert result["continuation_runtime"]["status"] == "configured"
    assert continuation["enabled"] is False
    assert continuation["mode"] == "dry_run"
    assert continuation["max_fanout"] == 4


def test_installer_removes_stale_continuation_core_files(tmp_path: Path) -> None:
    plugin_target = tmp_path / "plugins" / "memory" / "brainstack"
    plugin_target.mkdir(parents=True)
    for name in install_into_hermes.STALE_BRAINSTACK_PLUGIN_FILES:
        (plugin_target / name).write_text("stale", encoding="utf-8")

    removed = install_into_hermes._remove_stale_files(
        plugin_target,
        install_into_hermes.STALE_BRAINSTACK_PLUGIN_FILES,
        dry_run=False,
    )

    assert len(removed) == 3
    assert all(not (plugin_target / name).exists() for name in install_into_hermes.STALE_BRAINSTACK_PLUGIN_FILES)


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


def test_core_host_patch_mode_applies_skill_prompt_policy(tmp_path: Path) -> None:
    prompt_builder = tmp_path / "prompt_builder.py"
    prompt_builder.write_text(
        "def build_skills_system_prompt():\n"
        "    result = (\n"
        "        \"## Skills (mandatory)\\n\"\n"
        "        \"Before replying, scan the skills below. If a skill matches or is even partially relevant \"\n"
        "        \"to your task, you MUST load it with skill_view(name) and follow its instructions. \"\n"
        "        \"Err on the side of loading — it is always better to have context you don't need \"\n"
        "        \"than to miss critical steps, pitfalls, or established workflows. \"\n"
        "        \"Skills contain specialized knowledge — API endpoints, tool-specific commands, \"\n"
        "        \"and proven workflows that outperform general-purpose approaches. Load the skill \"\n"
        "        \"even if you think you could handle the task with basic tools like web_search or terminal. \"\n"
        "        \"Skills also encode the user's preferred approach, conventions, and quality standards \"\n"
        "        \"for tasks like code review, planning, and testing — load them even for tasks you \"\n"
        "        \"already know how to do, because the skill defines how it should be done here.\\n\"\n"
        "    )\n",
        encoding="utf-8",
    )

    actions = install_into_hermes._run_host_patch(
        "_patch_skill_prompt_policy",
        prompt_builder,
        dry_run=False,
        host_patch_mode="core",
    )
    text = prompt_builder.read_text(encoding="utf-8")

    assert actions == ["skill_prompt_policy:direct_relevance"]
    assert "even partially relevant" not in text
    assert "Err on the side of loading" not in text
    assert "directly relevant" in text
    assert "Do not reload the same skill in the same session" in text


def test_core_host_patch_mode_skips_skill_prompt_policy_when_upstream_present(tmp_path: Path) -> None:
    prompt_builder = tmp_path / "prompt_builder.py"
    original = (
        "def build_skills_system_prompt():\n"
        "    result = (\n"
        "        \"## Skills (mandatory)\\n\"\n"
        "        \"Before replying, scan the skills below. Load a skill only when it is directly relevant \"\n"
        "        \"to the user's current task, explicitly requested by the user, or needed for a risky operation. \"\n"
        "        \"Do not reload the same skill in the same session if it is already loaded and unchanged.\"\n"
        "    )\n"
    )
    prompt_builder.write_text(original, encoding="utf-8")

    actions = install_into_hermes._run_host_patch(
        "_patch_skill_prompt_policy",
        prompt_builder,
        dry_run=False,
        host_patch_mode="core",
    )

    assert actions == []
    assert prompt_builder.read_text(encoding="utf-8") == original


def _skill_view_legacy_fixture() -> str:
    return (
        "import json\n"
        "import logging\n"
        "from typing import Any, Dict, List, Tuple\n\n"
        "MAX_NAME_LENGTH = 64\n"
        "MAX_DESCRIPTION_LENGTH = 1024\n\n"
        "_INJECTION_PATTERNS: list = [\n"
        "    \"ignore previous instructions\",\n"
        "    \"]]>\",\n"
        "]\n\n\n"
        "def set_secret_capture_callback(callback) -> None:\n"
        "    pass\n\n\n"
        "def skills_list(category: str = None, task_id: str = None) -> str:\n"
        "    return json.dumps({\"hint\": \"Use skill_view(name) to see full content, tags, and linked files\"})\n\n\n"
        "def _serve_plugin_skill(namespace, bare, *, preprocess: bool = True, session_id: str | None = None) -> str:\n"
        "    parsed_frontmatter = {}\n"
        "    rendered_content = \"# Plugin skill\\nBody\"\n"
        "    banner = \"\"\n"
        "    description = \"plugin\"\n"
        "    return json.dumps(\n"
        "        {\n"
        "            \"success\": True,\n"
        "            \"name\": f\"{namespace}:{bare}\",\n"
        "            \"content\": f\"{banner}{rendered_content}\" if banner else rendered_content,\n"
        "            \"description\": description,\n"
        "            \"linked_files\": None,\n"
        "            \"readiness_status\": \"available\",\n"
        "        },\n"
        "        ensure_ascii=False,\n"
        "    )\n\n\n"
        "def skill_view(skill_name: str, file_path: str = None, task_id: str = None, preprocess: bool = True) -> str:\n"
        "    if \":\" in skill_name:\n"
        "        namespace, bare = skill_name.split(\":\", 1)\n"
        "        return _serve_plugin_skill(\n"
        "            namespace,\n"
        "            bare,\n"
        "            preprocess=preprocess,\n"
        "            session_id=task_id,\n"
        "        )\n"
        "    frontmatter = {\"description\": \"demo\"}\n"
        "    tags = []\n"
        "    related_skills = []\n"
        "    rendered_content = \"# Demo\\nBody\"\n"
        "    rel_path = \"demo/SKILL.md\"\n"
        "    skill_dir = None\n"
        "    linked_files = None\n"
        "    required_env_vars = []\n"
        "    setup_needed = False\n"
        "    result = {\n"
        "        \"success\": True,\n"
        "        \"name\": skill_name,\n"
        "        \"description\": frontmatter.get(\"description\", \"\"),\n"
        "        \"tags\": tags,\n"
        "        \"related_skills\": related_skills,\n"
        "        \"content\": rendered_content,\n"
        "        \"path\": rel_path,\n"
        "        \"skill_dir\": str(skill_dir) if skill_dir else None,\n"
        "        \"linked_files\": linked_files if linked_files else None,\n"
        "        \"readiness_status\": \"setup_needed\" if setup_needed else \"available\",\n"
        "    }\n"
        "    setup_help = next((e[\"help\"] for e in required_env_vars if e.get(\"help\")), None)\n"
        "    return json.dumps(result, ensure_ascii=False)\n\n\n"
        "SKILLS_LIST_SCHEMA = {\n"
        "    \"name\": \"skills_list\",\n"
        "    \"description\": \"List available skills (name + description). Use skill_view(name) to load full content.\",\n"
        "}\n\n"
        "SKILL_VIEW_SCHEMA = {\n"
        "    \"name\": \"skill_view\",\n"
        "    \"description\": \"Skills allow for loading information about specific tasks and workflows, as well as scripts and templates. Load a skill's full content or access its linked files (references, templates, scripts). First call returns SKILL.md content plus a 'linked_files' dict showing available references/templates/scripts. To access those, call again with file_path parameter.\",\n"
        "    \"parameters\": {\n"
        "        \"type\": \"object\",\n"
        "        \"properties\": {\n"
        "            \"name\": {\"type\": \"string\"},\n"
        "            \"file_path\": {\"type\": \"string\", \"description\": \"OPTIONAL: Path to a linked file within the skill.\"},\n"
        "        },\n"
        "        \"required\": [\"name\"],\n"
        "    },\n"
        "}\n\n"
        "def _skill_view_with_bump(args, **kw):\n"
        "    name = args.get(\"name\", \"\")\n"
        "    result = skill_view(\n"
        "        name, file_path=args.get(\"file_path\"), task_id=kw.get(\"task_id\")\n"
        "    )\n"
        "    return result\n"
    )


def test_core_host_patch_mode_applies_skill_view_progressive_disclosure(tmp_path: Path) -> None:
    skills_tool = tmp_path / "skills_tool.py"
    skills_tool.write_text(_skill_view_legacy_fixture(), encoding="utf-8")

    actions = install_into_hermes._run_host_patch(
        "_patch_skill_view_progressive_disclosure",
        skills_tool,
        dry_run=False,
        host_patch_mode="core",
    )
    text = skills_tool.read_text(encoding="utf-8")

    assert "skill_view:policy_helpers" in actions
    assert "skill_view:plugin_mode" in actions
    assert "skill_view:local_content_fields" in actions
    assert "skill_view:tool_handler_auto_mode" in actions
    assert "DEFAULT_SKILL_VIEW_AUTO_FULL_CHAR_LIMIT" in text
    assert "content_mode" in text
    assert "content_hash" in text
    assert "already_loaded_in_session" in text
    assert "mode=args.get(\"mode\") or (\"full\" if args.get(\"file_path\") else \"auto\")" in text
    assert '"enum": ["auto", "summary", "full"]' in text


def test_core_host_patch_mode_skips_skill_view_progressive_disclosure_when_upstream_present(
    tmp_path: Path,
) -> None:
    skills_tool = tmp_path / "skills_tool.py"
    original = (
        "DEFAULT_SKILL_VIEW_AUTO_FULL_CHAR_LIMIT = 8000\n"
        "def _skill_view_content_fields():\n"
        "    return {\"content_mode\": \"summary\", \"already_loaded_in_session\": False}\n"
        "def _skill_view_with_bump(args, **kw):\n"
        "    return skill_view(mode=args.get(\"mode\") or (\"full\" if args.get(\"file_path\") else \"auto\"))\n"
    )
    skills_tool.write_text(original, encoding="utf-8")

    actions = install_into_hermes._run_host_patch(
        "_patch_skill_view_progressive_disclosure",
        skills_tool,
        dry_run=False,
        host_patch_mode="core",
    )

    assert actions == []
    assert skills_tool.read_text(encoding="utf-8") == original


def test_skill_policy_patches_are_temporary_upstream_hotfix_inventory() -> None:
    inventory = {
        item["patcher"]: item
        for item in install_into_hermes._selected_host_patch_inventory(
            "docker",
            host_patch_mode="core",
        )
    }

    for patcher in {
        "_patch_skill_prompt_policy",
        "_patch_skill_view_progressive_disclosure",
    }:
        seam = inventory[patcher]
        assert seam["selected"] is True
        assert seam["category"] == "temporary_upstream_hotfix"
        assert seam["owner"] == "upstream-hermes-skill-policy"
        assert "skill" in seam["removal_condition"].lower()


def test_doctor_warns_about_aggressive_skill_policy_and_large_skill(tmp_path: Path) -> None:
    target = tmp_path / "hermes"
    (target / "agent").mkdir(parents=True)
    (target / "tools").mkdir()
    (target / "skills" / "wide").mkdir(parents=True)
    (target / "agent" / "memory_provider.py").write_text("", encoding="utf-8")
    (target / "agent" / "memory_manager.py").write_text("", encoding="utf-8")
    (target / "agent" / "prompt_builder.py").write_text(
        "If a skill matches or is even partially relevant, you MUST load it with skill_view(name). "
        "Err on the side of loading.",
        encoding="utf-8",
    )
    (target / "tools" / "skills_tool.py").write_text(
        "def skill_view(name):\n    return {'content': 'full'}\n",
        encoding="utf-8",
    )
    (target / "skills" / "wide" / "SKILL.md").write_text("# Wide\n" + ("x" * 17000), encoding="utf-8")

    checks = brainstack_doctor._check_skill_policy_surfaces(target, planned_install=False)
    by_name = {check.name: check for check in checks}

    assert by_name["hermes_skill_prompt_policy"].status == "warn"
    assert by_name["hermes_skill_view_progressive_disclosure"].status == "warn"
    assert by_name["hermes_skill_file_size_advisory"].status == "warn"
    assert "wide/SKILL.md" in by_name["hermes_skill_file_size_advisory"].message


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


def test_core_host_patch_mode_skips_discord_typing_backoff_when_upstream_changed(tmp_path: Path) -> None:
    discord_py = tmp_path / "discord.py"
    original = (
        "class DiscordAdapter:\n"
        "    async def send_typing(self, chat_id: str, metadata=None) -> None:\n"
        "        await self._client.trigger_typing(chat_id)\n"
    )
    discord_py.write_text(original, encoding="utf-8")

    actions = install_into_hermes._run_host_patch(
        "_patch_discord_typing_backoff",
        discord_py,
        dry_run=False,
        host_patch_mode="core",
    )

    assert actions == []
    assert discord_py.read_text(encoding="utf-8") == original


def test_core_host_patch_mode_applies_discord_outbound_final_dedupe(tmp_path: Path) -> None:
    discord_py = tmp_path / "discord.py"
    discord_py.write_text(
        "import asyncio\n"
        "import os\n"
        "import time\n"
        "from typing import Dict\n\n"
        "class SendResult:\n"
        "    def __init__(self, success=True, message_id=None, raw_response=None):\n"
        "        self.success = success\n"
        "        self.message_id = message_id\n"
        "        self.raw_response = raw_response or {}\n\n"
        "class DiscordAdapter:\n"
        "    MAX_MESSAGE_LENGTH = 2000\n\n"
        "    def __init__(self):\n"
        "        self._typing_tasks: Dict[str, asyncio.Task] = {}\n"
        "        self._reply_to_mode = \"first\"\n"
        "        self.name = \"discord\"\n"
        "        self._client = None\n\n"
        "    def format_message(self, content):\n"
        "        return content\n\n"
        "    def truncate_message(self, formatted, limit):\n"
        "        return [formatted]\n\n"
        "    async def send_message(self, chat_id: str, content: str, thread_id=None, reply_to=None, metadata=None):\n"
        "        channel = await self._client.fetch_channel(thread_id or chat_id)\n"
        "        try:\n"
        "            # Format and split message if needed\n"
        "            formatted = self.format_message(content)\n"
        "            chunks = self.truncate_message(formatted, self.MAX_MESSAGE_LENGTH)\n"
        "\n"
        "            message_ids = []\n"
        "            reference = None\n"
        "            if reply_to and self._reply_to_mode != \"off\":\n"
        "                reference = reply_to\n"
        "            for i, chunk in enumerate(chunks):\n"
        "                if self._reply_to_mode == \"all\":\n"
        "                    chunk_reference = reference\n"
        "                else:  # \"first\" (default) or \"off\"\n"
        "                    chunk_reference = reference if i == 0 else None\n"
        "                try:\n"
        "                    msg = await channel.send(\n"
        "                        content=chunk,\n"
        "                        reference=chunk_reference,\n"
        "                    )\n"
        "                except Exception:\n"
        "                    raise\n"
        "                message_ids.append(str(msg.id))\n"
        "            return SendResult(\n"
        "                success=True,\n"
        "                message_id=message_ids[0] if message_ids else None,\n"
        "                raw_response={\"message_ids\": message_ids},\n"
        "            )\n"
        "        except Exception:\n"
        "            raise\n",
        encoding="utf-8",
    )

    actions = install_into_hermes._run_host_patch(
        "_patch_discord_outbound_final_dedupe",
        discord_py,
        dry_run=False,
        host_patch_mode="core",
    )
    text = discord_py.read_text(encoding="utf-8")

    assert actions == [
        "discord_outbound_dedupe:import",
        "discord_outbound_dedupe:state",
        "discord_outbound_dedupe:setup",
        "discord_outbound_dedupe:final_check",
        "discord_outbound_dedupe:check",
        "discord_outbound_dedupe:record",
        "discord_outbound_dedupe:final_record",
    ]
    assert "import hashlib" in text
    assert "Temporary upstream Hermes bugfix (#25349)" in text
    assert "self._recent_outbound_final_dedupe" in text
    assert "HERMES_DISCORD_OUTBOUND_FINAL_DEDUPE_SECONDS" in text
    assert "HERMES_DISCORD_OUTBOUND_DEDUPE_SECONDS" in text
    assert "hermes_delivery_id" in text
    assert "content_hash = hashlib.sha256" in text
    assert ":{i}:{content_hash}" in text
    assert "Suppressed duplicate Discord final response" in text
    assert "Suppressed duplicate Discord outbound chunk" in text
    assert "self._recent_outbound_chunk_dedupe[dedupe_key]" in text
    assert "self._recent_outbound_final_dedupe[final_dedupe_key]" in text


def test_discord_final_response_dedupe_suppresses_second_logical_send(tmp_path: Path) -> None:
    discord_py = tmp_path / "discord_runtime.py"
    discord_py.write_text(
        "import asyncio\n"
        "import os\n"
        "import time\n"
        "from typing import Dict\n\n"
        "class Logger:\n"
        "    def info(self, *args, **kwargs):\n"
        "        pass\n"
        "logger = Logger()\n\n"
        "class SendResult:\n"
        "    def __init__(self, success=True, message_id=None, raw_response=None):\n"
        "        self.success = success\n"
        "        self.message_id = message_id\n"
        "        self.raw_response = raw_response or {}\n\n"
        "class FakeMessage:\n"
        "    def __init__(self, mid):\n"
        "        self.id = mid\n\n"
        "class FakeChannel:\n"
        "    id = \"channel-1\"\n"
        "    def __init__(self):\n"
        "        self.sent = []\n"
        "    async def send(self, content, reference=None):\n"
        "        self.sent.append(content)\n"
        "        return FakeMessage(f\"m{len(self.sent)}\")\n\n"
        "class FakeClient:\n"
        "    def __init__(self, channel):\n"
        "        self.channel = channel\n"
        "    async def fetch_channel(self, channel_id):\n"
        "        return self.channel\n\n"
        "class DiscordAdapter:\n"
        "    MAX_MESSAGE_LENGTH = 2000\n\n"
        "    def __init__(self, channel):\n"
        "        self._typing_tasks: Dict[str, asyncio.Task] = {}\n"
        "        self._reply_to_mode = \"first\"\n"
        "        self.name = \"discord\"\n"
        "        self._client = FakeClient(channel)\n\n"
        "    def format_message(self, content):\n"
        "        return content\n\n"
        "    def truncate_message(self, formatted, limit):\n"
        "        return [formatted[i:i + limit] for i in range(0, len(formatted), limit)] or [\"\"]\n\n"
        "    async def send_message(self, chat_id: str, content: str, thread_id=None, reply_to=None, metadata=None):\n"
        "        channel = await self._client.fetch_channel(thread_id or chat_id)\n"
        "        try:\n"
        "            # Format and split message if needed\n"
        "            formatted = self.format_message(content)\n"
        "            chunks = self.truncate_message(formatted, self.MAX_MESSAGE_LENGTH)\n"
        "\n"
        "            message_ids = []\n"
        "            reference = None\n"
        "            if reply_to and self._reply_to_mode != \"off\":\n"
        "                reference = reply_to\n"
        "            for i, chunk in enumerate(chunks):\n"
        "                if self._reply_to_mode == \"all\":\n"
        "                    chunk_reference = reference\n"
        "                else:  # \"first\" (default) or \"off\"\n"
        "                    chunk_reference = reference if i == 0 else None\n"
        "                try:\n"
        "                    msg = await channel.send(\n"
        "                        content=chunk,\n"
        "                        reference=chunk_reference,\n"
        "                    )\n"
        "                except Exception:\n"
        "                    raise\n"
        "                message_ids.append(str(msg.id))\n"
        "            return SendResult(\n"
        "                success=True,\n"
        "                message_id=message_ids[0] if message_ids else None,\n"
        "                raw_response={\"message_ids\": message_ids},\n"
        "            )\n"
        "        except Exception:\n"
        "            raise\n",
        encoding="utf-8",
    )
    install_into_hermes._run_host_patch(
        "_patch_discord_outbound_final_dedupe",
        discord_py,
        dry_run=False,
        host_patch_mode="core",
    )
    spec = importlib.util.spec_from_file_location("discord_runtime", discord_py)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    channel = module.FakeChannel()
    adapter = module.DiscordAdapter(channel)
    metadata = {"hermes_delivery_scope": "final_response", "hermes_delivery_id": "turn-1-final"}

    first = asyncio.run(adapter.send_message("c", "x" * 4442, metadata=metadata))
    second = asyncio.run(adapter.send_message("c", "x" * 4442, metadata=metadata))

    assert first.success is True
    assert second.success is True
    assert second.raw_response["duplicate_suppressed"] is True
    assert second.raw_response["dedupe_scope"] == "final_response"
    assert len(channel.sent) == 3


def test_core_host_patch_mode_adds_final_dedupe_when_chunk_dedupe_already_exists(tmp_path: Path) -> None:
    discord_py = tmp_path / "discord.py"
    discord_py.write_text(
        "import asyncio\n"
        "import hashlib\n"
        "import os\n"
        "import time\n"
        "from typing import Dict\n\n"
        "class SendResult:\n"
        "    def __init__(self, success=True, message_id=None, raw_response=None):\n"
        "        self.success = success\n"
        "        self.message_id = message_id\n"
        "        self.raw_response = raw_response or {}\n\n"
        "class DiscordAdapter:\n"
        "    MAX_MESSAGE_LENGTH = 2000\n"
        "    def __init__(self):\n"
        "        self._typing_tasks: Dict[str, asyncio.Task] = {}\n"
        "        self._recent_outbound_chunk_dedupe: Dict[str, tuple[float, str]] = {}\n"
        "        self._outbound_chunk_dedupe_seconds = max(\n"
        "            0.0,\n"
        "            float(os.getenv(\"HERMES_DISCORD_OUTBOUND_DEDUPE_SECONDS\", \"120\")),\n"
        "        )\n"
        "        self._outbound_chunk_dedupe_min_chars = max(\n"
        "            0,\n"
        "            int(os.getenv(\"HERMES_DISCORD_OUTBOUND_DEDUPE_MIN_CHARS\", \"200\")),\n"
        "        )\n"
        "        self._reply_to_mode = \"first\"\n"
        "        self.name = \"discord\"\n"
        "    def format_message(self, content):\n"
        "        return content\n"
        "    def truncate_message(self, formatted, limit):\n"
        "        return [formatted]\n"
        "    async def send(self, chat_id, content, reply_to=None, metadata=None):\n"
        "        channel = object()\n"
        "        thread_id = None\n"
        "        try:\n"
        "            formatted = self.format_message(content)\n"
        "            chunks = self.truncate_message(formatted, self.MAX_MESSAGE_LENGTH)\n"
        "            message_ids = []\n"
        "            dedupe_enabled = self._outbound_chunk_dedupe_seconds > 0\n"
        "            dedupe_now = time.monotonic()\n"
        "            dedupe_target_id = str(getattr(channel, \"id\", thread_id or chat_id))\n"
        "            if dedupe_enabled and len(self._recent_outbound_chunk_dedupe) > 512:\n"
        "                dedupe_cutoff = dedupe_now - self._outbound_chunk_dedupe_seconds\n"
        "                for dedupe_key, (seen_at, _msg_id) in list(self._recent_outbound_chunk_dedupe.items()):\n"
        "                    if seen_at < dedupe_cutoff:\n"
        "                        self._recent_outbound_chunk_dedupe.pop(dedupe_key, None)\n"
        "            reference = None\n"
        "            for i, chunk in enumerate(chunks):\n"
        "                reference_id = \"\"\n"
        "                content_hash = hashlib.sha256(chunk.encode(\"utf-8\")).hexdigest()\n"
        "                if True:\n"
        "                    dedupe_key = f\"{dedupe_target_id}:{reference_id}:{content_hash}\"\n"
        "                msg = type(\"Msg\", (), {\"id\": \"m1\"})()\n"
        "                message_ids.append(str(msg.id))\n"
        "            return SendResult(\n"
        "                success=True,\n"
        "                message_id=message_ids[0] if message_ids else None,\n"
        "                raw_response={\"message_ids\": message_ids}\n"
        "            )\n"
        "        except Exception:\n"
        "            raise\n",
        encoding="utf-8",
    )

    actions = install_into_hermes._run_host_patch(
        "_patch_discord_outbound_final_dedupe",
        discord_py,
        dry_run=False,
        host_patch_mode="core",
    )
    text = discord_py.read_text(encoding="utf-8")

    assert actions == [
        "discord_outbound_dedupe:final_state",
        "discord_outbound_dedupe:final_setup",
        "discord_outbound_dedupe:final_check",
        "discord_outbound_dedupe:chunk_index_key",
        "discord_outbound_dedupe:final_record",
    ]
    assert "self._recent_outbound_final_dedupe" in text
    assert "Suppressed duplicate Discord final response" in text


def test_core_host_patch_mode_skips_discord_outbound_dedupe_when_upstream_changed(tmp_path: Path) -> None:
    discord_py = tmp_path / "discord.py"
    original = (
        "class DiscordAdapter:\n"
        "    async def send_message(self, channel, content):\n"
        "        content_hash = \"abc\"\n"
        "        duplicate_suppressed = True\n"
        "        return await channel.send(content=content)\n"
    )
    discord_py.write_text(original, encoding="utf-8")

    actions = install_into_hermes._run_host_patch(
        "_patch_discord_outbound_final_dedupe",
        discord_py,
        dry_run=False,
        host_patch_mode="core",
    )

    assert actions == []
    assert discord_py.read_text(encoding="utf-8") == original


def test_core_host_patch_mode_marks_platform_final_response_delivery_metadata(tmp_path: Path) -> None:
    base_py = tmp_path / "base.py"
    base_py.write_text(
        "async def process(self, event, text_content, session_key, _thread_metadata, _reply_anchor):\n"
        "    if text_content:\n"
        "                    if _thread_metadata is not None:\n"
        "                        _thread_metadata = dict(_thread_metadata)\n"
        "                        _thread_metadata[\"notify\"] = True\n"
        "                    else:\n"
        "                        _thread_metadata = {\"notify\": True}\n"
        "                    result = await self._send_with_retry(\n"
        "                        chat_id=event.source.chat_id,\n"
        "                        content=text_content,\n"
        "                        reply_to=_reply_anchor,\n"
        "                        metadata=_thread_metadata,\n"
        "                    )\n",
        encoding="utf-8",
    )

    actions = install_into_hermes._run_host_patch(
        "_patch_platform_final_response_delivery_metadata",
        base_py,
        dry_run=False,
        host_patch_mode="core",
    )
    text = base_py.read_text(encoding="utf-8")

    assert actions == ["platform_final_delivery_metadata:final_response"]
    assert "hermes_delivery_scope" in text
    assert "hermes_delivery_id" in text
    assert "session_key}:final:" in text


def test_discord_outbound_dedupe_is_temporary_upstream_hotfix_inventory() -> None:
    inventory = {
        item["patcher"]: item
        for item in install_into_hermes._selected_host_patch_inventory(
            "docker",
            host_patch_mode="core",
        )
    }

    seam = inventory["_patch_discord_outbound_final_dedupe"]
    assert seam["selected"] is True
    assert seam["category"] == "temporary_upstream_hotfix"
    assert seam["owner"] == "upstream-hermes-discord-bugfix"
    assert "25349" in seam["removal_condition"]
    metadata = inventory["_patch_platform_final_response_delivery_metadata"]
    assert metadata["selected"] is True
    assert metadata["category"] == "temporary_upstream_hotfix"
    assert metadata["owner"] == "upstream-hermes-discord-bugfix"
    assert "25349" in metadata["removal_condition"]


def test_core_host_patch_mode_applies_cron_authority_jobs_without_forcing_shared_default(
    tmp_path: Path,
) -> None:
    jobs_py = tmp_path / "jobs.py"
    jobs_py.write_text(
        "import json\n"
        "from pathlib import Path\n"
        "from hermes_constants import get_hermes_home\n\n"
        "HERMES_DIR = get_hermes_home().resolve()\n"
        "CRON_DIR = HERMES_DIR / \"cron\"\n"
        "JOBS_FILE = CRON_DIR / \"jobs.json\"\n"
        "OUTPUT_DIR = CRON_DIR / \"output\"\n",
        encoding="utf-8",
    )

    actions = install_into_hermes._run_host_patch(
        "_patch_cron_authority_jobs",
        jobs_py,
        dry_run=False,
        host_patch_mode="core",
    )
    text = jobs_py.read_text(encoding="utf-8")

    assert actions == ["cron_authority_jobs:import_os", "cron_authority_jobs:resolver"]
    assert "def get_cron_home() -> Path:" in text
    assert 'os.environ.get("HERMES_CRON_HOME", "")' in text
    assert "return get_hermes_home()" in text
    assert "get_default_hermes_root" not in text
    assert "HERMES_DIR = get_cron_home().resolve()" in text
    assert "OUTPUT_DIR = CRON_DIR / \"output\"" in text


def test_core_host_patch_mode_applies_cron_authority_jobs_with_existing_lock_block(
    tmp_path: Path,
) -> None:
    jobs_py = tmp_path / "jobs.py"
    jobs_py.write_text(
        "import copy\n"
        "import json\n"
        "import threading\n"
        "import os\n"
        "from pathlib import Path\n"
        "from hermes_constants import get_hermes_home\n\n"
        "HERMES_DIR = get_hermes_home().resolve()\n"
        "CRON_DIR = HERMES_DIR / \"cron\"\n"
        "JOBS_FILE = CRON_DIR / \"jobs.json\"\n"
        "\n"
        "# In-process lock protecting load_jobs\u2192modify\u2192save_jobs cycles.\n"
        "# Required when tick() runs jobs in parallel threads \u2014 without this,\n"
        "# concurrent mark_job_run / advance_next_run calls can clobber each other.\n"
        "_jobs_file_lock = threading.Lock()\n"
        "OUTPUT_DIR = CRON_DIR / \"output\"\n",
        encoding="utf-8",
    )

    actions = install_into_hermes._run_host_patch(
        "_patch_cron_authority_jobs",
        jobs_py,
        dry_run=False,
        host_patch_mode="core",
    )
    text = jobs_py.read_text(encoding="utf-8")

    assert actions == ["cron_authority_jobs:resolver"]
    assert "def get_cron_home() -> Path:" in text
    assert "HERMES_DIR = get_cron_home().resolve()" in text
    assert "_jobs_file_lock = threading.Lock()" in text
    assert "OUTPUT_DIR = CRON_DIR / \"output\"" in text


def test_core_host_patch_mode_skips_cron_authority_jobs_when_upstream_present(
    tmp_path: Path,
) -> None:
    jobs_py = tmp_path / "jobs.py"
    original = (
        "import os\n"
        "from pathlib import Path\n"
        "from hermes_constants import get_hermes_home\n\n"
        "def get_cron_home() -> Path:\n"
        "    override = os.environ.get(\"HERMES_CRON_HOME\", \"\").strip()\n"
        "    if override:\n"
        "        return Path(override).expanduser()\n"
        "    return get_hermes_home()\n\n"
        "HERMES_DIR = get_cron_home().resolve()\n"
        "CRON_DIR = HERMES_DIR / \"cron\"\n"
    )
    jobs_py.write_text(original, encoding="utf-8")

    actions = install_into_hermes._run_host_patch(
        "_patch_cron_authority_jobs",
        jobs_py,
        dry_run=False,
        host_patch_mode="core",
    )

    assert actions == []
    assert jobs_py.read_text(encoding="utf-8") == original


def test_core_host_patch_mode_skips_cron_authority_jobs_with_direct_cron_dir_resolver(
    tmp_path: Path,
) -> None:
    jobs_py = tmp_path / "jobs.py"
    original = (
        "import os\n"
        "from pathlib import Path\n"
        "from hermes_constants import get_hermes_home\n\n"
        "def get_cron_home() -> Path:\n"
        "    override = os.environ.get(\"HERMES_CRON_HOME\", \"\").strip()\n"
        "    if override:\n"
        "        return Path(override).expanduser()\n"
        "    return get_hermes_home()\n\n"
        "CRON_DIR = get_cron_home().resolve() / \"cron\"\n"
        "JOBS_FILE = CRON_DIR / \"jobs.json\"\n"
        "OUTPUT_DIR = CRON_DIR / \"output\"\n"
    )
    jobs_py.write_text(original, encoding="utf-8")

    actions = install_into_hermes._run_host_patch(
        "_patch_cron_authority_jobs",
        jobs_py,
        dry_run=False,
        host_patch_mode="core",
    )

    assert actions == []
    assert jobs_py.read_text(encoding="utf-8") == original


def test_core_host_patch_mode_applies_cron_scheduler_authority_lock(
    tmp_path: Path,
) -> None:
    scheduler_py = tmp_path / "scheduler.py"
    scheduler_py.write_text(
        "import logging\n"
        "from pathlib import Path\n"
        "from hermes_constants import get_hermes_home\n\n"
        "_hermes_home: Path | None = None\n\n"
        "def _get_hermes_home() -> Path:\n"
        "    return _hermes_home or get_hermes_home()\n\n\n"
        "def _get_lock_paths() -> tuple[Path, Path]:\n"
        "    hermes_home = _get_hermes_home()\n"
        "    lock_dir = hermes_home / \"cron\"\n"
        "    return lock_dir, lock_dir / \".tick.lock\"\n",
        encoding="utf-8",
    )

    actions = install_into_hermes._run_host_patch(
        "_patch_cron_authority_scheduler",
        scheduler_py,
        dry_run=False,
        host_patch_mode="core",
    )
    text = scheduler_py.read_text(encoding="utf-8")

    assert actions == [
        "cron_authority_scheduler:import_os",
        "cron_authority_scheduler:resolver",
        "cron_authority_scheduler:lock_resolver",
    ]
    assert "def _get_cron_home() -> Path:" in text
    assert 'os.environ.get("HERMES_CRON_HOME", "")' in text
    assert "cron_home = _get_cron_home()" in text
    assert "lock_dir = cron_home / \"cron\"" in text


def test_core_host_patch_mode_applies_cron_scheduler_authority_with_docstrings(
    tmp_path: Path,
) -> None:
    scheduler_py = tmp_path / "scheduler.py"
    scheduler_py.write_text(
        "import logging\n"
        "import os\n"
        "from pathlib import Path\n"
        "from hermes_constants import get_hermes_home\n\n"
        "_hermes_home: Path | None = None\n\n"
        "def _get_hermes_home() -> Path:\n"
        "    \"\"\"Resolve Hermes home dynamically while preserving test monkeypatch hooks.\"\"\"\n"
        "    return _hermes_home or get_hermes_home()\n\n\n"
        "def _get_lock_paths() -> tuple[Path, Path]:\n"
        "    \"\"\"Resolve cron lock paths at call time so profile/env changes are honored.\"\"\"\n"
        "    hermes_home = _get_hermes_home()\n"
        "    lock_dir = hermes_home / \"cron\"\n"
        "    return lock_dir, lock_dir / \".tick.lock\"\n",
        encoding="utf-8",
    )

    actions = install_into_hermes._run_host_patch(
        "_patch_cron_authority_scheduler",
        scheduler_py,
        dry_run=False,
        host_patch_mode="core",
    )
    text = scheduler_py.read_text(encoding="utf-8")

    assert actions == [
        "cron_authority_scheduler:resolver",
        "cron_authority_scheduler:lock_resolver",
    ]
    assert "def _get_cron_home() -> Path:" in text
    assert "cron_home = _get_cron_home()" in text
    assert "lock_dir = cron_home / \"cron\"" in text


def test_core_host_patch_mode_applies_kanban_spawn_cron_authority_env(
    tmp_path: Path,
) -> None:
    kanban_db_py = tmp_path / "kanban_db.py"
    kanban_db_py.write_text(
        "import json\n\n"
        "def _default_spawn(task, profile_arg):\n"
        "    env = dict(os.environ)\n"
        "    try:\n"
        "        env[\"HERMES_HOME\"] = resolve_profile_env(profile_arg)\n"
        "    except FileNotFoundError:\n"
        "        pass\n"
        "    return env\n",
        encoding="utf-8",
    )

    actions = install_into_hermes._run_host_patch(
        "_patch_kanban_spawn_cron_authority",
        kanban_db_py,
        dry_run=False,
        host_patch_mode="core",
    )
    text = kanban_db_py.read_text(encoding="utf-8")

    assert actions == [
        "kanban_spawn_cron_authority:import_os",
        "kanban_spawn_cron_authority:env",
    ]
    assert "import os" in text
    assert 'cron_home = os.environ.get("HERMES_CRON_HOME", "").strip()' in text
    assert 'env["HERMES_CRON_HOME"] = cron_home' in text


def test_cron_authority_patches_are_temporary_upstream_hotfix_inventory() -> None:
    inventory = {
        item["patcher"]: item
        for item in install_into_hermes._selected_host_patch_inventory(
            "docker",
            host_patch_mode="core",
        )
    }

    for patcher in {
        "_patch_cron_authority_jobs",
        "_patch_cron_authority_scheduler",
        "_patch_kanban_spawn_cron_authority",
        "_patch_cron_authority_tests",
        "_patch_cron_scheduler_authority_tests",
    }:
        seam = inventory[patcher]
        assert seam["selected"] is True
        assert seam["category"] == "temporary_upstream_hotfix"
        assert seam["owner"].startswith("upstream-hermes-cron-authority")
        assert "HERMES_CRON_HOME" in seam["removal_condition"]


def test_core_host_patch_mode_applies_openai_codex_runtime_pool_fallback(
    tmp_path: Path,
) -> None:
    auth_py = tmp_path / "auth.py"
    auth_py.write_text(
        "from __future__ import annotations\n\n"
        "from typing import Any, Dict\n\n"
        "class AuthError(RuntimeError):\n"
        "    pass\n\n"
        "CODEX_ACCESS_TOKEN_REFRESH_SKEW_SECONDS = 60\n\n"
        "def _read_codex_tokens(*, _lock: bool = True) -> Dict[str, Any]:\n"
        "    raise AuthError('missing')\n\n"
        "def resolve_codex_runtime_credentials(\n"
        "    *,\n"
        "    force_refresh: bool = False,\n"
        "    refresh_if_expiring: bool = True,\n"
        "    refresh_skew_seconds: int = CODEX_ACCESS_TOKEN_REFRESH_SKEW_SECONDS,\n"
        ") -> Dict[str, Any]:\n"
        "    data = _read_codex_tokens()\n"
        "    tokens = dict(data[\"tokens\"])\n"
        "    should_refresh = bool(force_refresh)\n"
        "    if should_refresh:\n"
        "        with _auth_store_lock():\n"
        "            data = _read_codex_tokens(_lock=False)\n"
        "            tokens = dict(data[\"tokens\"])\n"
        "    return {\"api_key\": tokens.get(\"access_token\")}\n",
        encoding="utf-8",
    )

    actions = install_into_hermes._run_host_patch(
        "_patch_openai_codex_runtime_pool_fallback",
        auth_py,
        dry_run=False,
        host_patch_mode="core",
    )
    text = auth_py.read_text(encoding="utf-8")

    assert actions == [
        "openai_codex_auth:pool_fallback_helper",
        "openai_codex_auth:initial_pool_fallback",
        "openai_codex_auth:refresh_pool_fallback",
    ]
    assert "def _read_codex_pool_tokens" in text
    assert 'load_pool("openai-codex")' in text
    assert "initial_codex_pool_data" in text


def test_openai_codex_runtime_pool_fallback_is_temporary_upstream_hotfix_inventory() -> None:
    inventory = {
        item["patcher"]: item
        for item in install_into_hermes._selected_host_patch_inventory(
            "docker",
            host_patch_mode="core",
        )
    }

    seam = inventory["_patch_openai_codex_runtime_pool_fallback"]
    assert seam["selected"] is True
    assert seam["category"] == "temporary_upstream_hotfix"
    assert seam["owner"] == "upstream-hermes-auth-pool-runtime"
    assert "credential pool" in seam["removal_condition"]


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


def test_core_host_patch_skips_zero_llm_session_search_shape(tmp_path: Path) -> None:
    session_search_tool = tmp_path / "session_search_tool.py"
    session_search_tool.write_text(
        '"""Session search without summarization LLM calls."""\n'
        "def _format_timestamp(ts):\n"
        "    return str(ts)\n"
        "def session_search(query=None):\n"
        "    return {'success': True, 'mode': 'discovery'}\n",
        encoding="utf-8",
    )

    actions = install_into_hermes._patch_session_search_total_deadline(
        session_search_tool,
        dry_run=False,
    )

    assert actions == []
    assert "def _get_session_search_total_deadline" not in session_search_tool.read_text(encoding="utf-8")


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


def test_gateway_patch_dry_run_copy_ignores_runtime_state() -> None:
    ignored = set(hermes_gateway_patch_support.GATEWAY_PATCH_DRY_RUN_COPY_IGNORE_PATTERNS)

    assert "hermes-config" in ignored
    assert "runtime" in ignored
    assert "state.db*" in ignored
    assert "auth.json*" in ignored
