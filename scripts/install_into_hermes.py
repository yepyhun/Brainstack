#!/usr/bin/env python3
"""Install Brainstack into a target Hermes checkout.

This installer copies the Brainstack provider payload and applies recognized
config changes. It avoids blind host-code patching; compatibility is verified
by ``brainstack_doctor.py``. Hermes-native explicit truth capture, addressing
precedence, explicit rule-pack fidelity, and ordinary-turn compliance remain
upstream Hermes seams rather than Brainstack installer responsibilities.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from brainstack.background_task_binding import (  # noqa: E402
    REASON_UNSUPPORTED_MODEL_FOR_PROVIDER,
    install_default_background_task_bindings,
    resolve_auxiliary_route_readiness,
)
from brainstack.capability_enablement import (  # noqa: E402
    build_enablement_plan,
    summarize_enablement_plan,
)
from brainstack.tier2_runtime_spine import (  # noqa: E402
    TIER2_HINDSIGHT_PUBLIC_API_BRIDGE,
    TIER2_INTERNAL_EXTRACTOR,
    build_tier2_runtime_spine,
)

try:
    from hermes_gateway_patch_support import (
        apply_gateway_patch_bundle,
        inspect_gateway_patch_support,
    )
except ModuleNotFoundError:
    from scripts.hermes_gateway_patch_support import (
        apply_gateway_patch_bundle,
        inspect_gateway_patch_support,
    )


SOURCE_PLUGIN = REPO_ROOT / "brainstack"
SOURCE_HOST_PAYLOAD = REPO_ROOT / "host_payload"
SOURCE_HERMES_PROACTIVE_EXTENSION = REPO_ROOT / "extensions" / "hermes_proactive"
BACKEND_DEPENDENCIES = {
    "kuzu": "kuzu",
    "chromadb": "chromadb",
    "hindsight_client": "hindsight-all-slim",
    "pg0": "hindsight-api-slim[embedded-db]",
    "openai": "openai",
    "croniter": "croniter",
}

LOCAL_TIER2_PROVIDER = "ollama"
LOCAL_TIER2_LOOPBACK_MODEL_URL_MARKERS = ("127.0.0.1:11434", "localhost:11434")
PROACTIVE_RUNTIME_MODES = {"disabled", "dry_run", "live"}
DEFAULT_PROACTIVE_RUNTIME_MODE = "dry_run"
PROACTIVE_CRON_JOB_NAME = "Brainstack Proactive Pulse"
PROACTIVE_CRON_GATE_SCRIPT_NAME = "brainstack_proactive_pulse_gate.py"
SESSION_SEARCH_TOTAL_TIMEOUT_SECONDS = 20
SESSION_SEARCH_MAX_CONCURRENCY = 1
DISCORD_STREAMING_EDIT_INTERVAL_SECONDS = 3.0
DISCORD_STREAMING_BUFFER_THRESHOLD = 200

HOST_PATCH_MODE_CATEGORIES: dict[str, set[str]] = {
    "core": {"required_seam", "core_hygiene"},
    "compat": {"required_seam", "core_hygiene", "compat_hotfix"},
    "legacy": {"required_seam", "core_hygiene", "compat_hotfix", "legacy_host_patch"},
}

HOST_PATCH_POLICIES: dict[str, dict[str, str]] = {
    "_patch_run_agent": {
        "category": "compat_hotfix",
        "owner": "host-seam",
        "removal_condition": "Hermes exposes structured write-origin metadata and interrupted-turn sync suppression natively.",
    },
    "_patch_run_agent_cache_evict_memory_provider_shutdown": {
        "category": "required_seam",
        "owner": "host-lifecycle-seam",
        "removal_condition": "Hermes soft cache eviction closes external memory provider runtime handles natively.",
    },
    "_patch_run_agent_tool_call_interim_boundary": {
        "category": "required_seam",
        "owner": "host-output-seam",
        "removal_condition": "Hermes natively treats assistant content on tool-call turns as transcript/API state and keeps public progress on explicit status/tool channels.",
    },
    "_patch_gateway_background_process_output_boundary": {
        "category": "required_seam",
        "owner": "host-output-seam",
        "removal_condition": "Hermes natively stores large background-process output as artifacts and injects only bounded summaries into chat/model context.",
    },
    "_patch_memory_provider": {
        "category": "compat_hotfix",
        "owner": "host-seam",
        "removal_condition": "Hermes MemoryProvider.on_memory_write accepts optional metadata natively.",
    },
    "_patch_memory_manager_required_seam": {
        "category": "compat_hotfix",
        "owner": "host-seam",
        "removal_condition": "Hermes MemoryManager forwards optional write metadata natively.",
    },
    "_patch_dockerfile_backend_dependencies": {
        "category": "required_seam",
        "owner": "build-seam",
        "removal_condition": "Hermes supports plugin-declared runtime dependency installation.",
    },
    "_patch_dockerfile_workstation_python_alias": {
        "category": "required_seam",
        "owner": "build-seam",
        "removal_condition": "Hermes Docker images expose `python` as a stable workstation command natively.",
    },
    "_patch_dockerignore": {
        "category": "core_hygiene",
        "owner": "source-hygiene",
        "removal_condition": "Upstream Docker build context already excludes private runtime state.",
    },
    "_patch_config": {
        "category": "core_hygiene",
        "owner": "runtime-config",
        "removal_condition": "Hermes provides a first-class provider activation config writer.",
    },
    "_patch_auxiliary_client": {
        "category": "required_seam",
        "owner": "host-provider-hotfix",
        "removal_condition": "Hermes auxiliary task resolver natively supports provider=main model inheritance and evicts closed cached sync clients.",
    },
    "_patch_session_search_total_deadline": {
        "category": "required_seam",
        "owner": "host-tool-hotfix",
        "removal_condition": "Hermes session_search natively enforces a tool-level total deadline below gateway idle timeout.",
    },
    "_patch_discord_typing_backoff": {
        "category": "required_seam",
        "owner": "host-discord-runtime",
        "removal_condition": "Hermes Discord adapter natively keeps typing indicators rate-limit aware and prevents overlapping stale typing loops.",
    },
    "_patch_run_agent_ebadf_transport_recovery": {
        "category": "required_seam",
        "owner": "host-provider-runtime",
        "removal_condition": "Hermes provider transport recovery natively handles EBADF closed-file-descriptor failures by rebuilding the request client once.",
    },
    "_patch_credential_pool": {
        "category": "compat_hotfix",
        "owner": "host-provider-hotfix",
        "removal_condition": "Hermes credential pool natively rejects stale Nous agent keys at selection time.",
    },
    "_patch_credential_pool_tests": {
        "category": "compat_hotfix",
        "owner": "host-provider-hotfix-test",
        "removal_condition": "Upstream Hermes tests cover stale Nous agent-key rejection.",
    },
    "_patch_compose_healthcheck": {
        "category": "required_seam",
        "owner": "private-runtime",
        "removal_condition": "Runtime deployment provides an explicit readiness healthcheck outside source patching.",
    },
    "_patch_compose_runtime_identity": {
        "category": "required_seam",
        "owner": "private-runtime",
        "removal_condition": "Runtime deployment provides UID/GID mapping outside source patching.",
    },
    "_patch_compose_plugin_pythonpath": {
        "category": "required_seam",
        "owner": "docker-runtime-seam",
        "removal_condition": "Hermes Docker runtime adds project plugin roots before mutable runtime state paths.",
    },
    "_patch_compose_discord_bot_mentions": {
        "category": "required_seam",
        "owner": "docker-runtime-seam",
        "removal_condition": "Hermes Discord adapter provides first-class trusted bot canary sender support.",
    },
    "_patch_compose_terminal_workspace_cwd": {
        "category": "required_seam",
        "owner": "docker-runtime-seam",
        "removal_condition": "Hermes Docker runtime explicitly sets terminal working directory to mounted workspace.",
    },
    "_patch_compose_local_tei_jina_runtime": {
        "category": "required_seam",
        "owner": "embedding-runtime",
        "removal_condition": "Hermes Docker runtime provides an explicit healthy embedding runtime for Chroma.",
    },
    "_patch_compose_hindsight_local_tier2_runtime": {
        "category": "required_seam",
        "owner": "tier2-donor-runtime",
        "removal_condition": "Hermes Docker runtime provides a first-class local Hindsight memory runtime binding.",
    },
    "_patch_compose_remove_discord_forced_heavy_profile": {
        "category": "required_seam",
        "owner": "docker-runtime-seam",
        "removal_condition": "All supported installs are already free of the old forced-heavy Discord fallback.",
    },
    "_patch_gateway_turn_profiles_capability_preserving_default": {
        "category": "required_seam",
        "owner": "gateway-runtime-seam",
        "removal_condition": "Hermes Discord turn profiles preserve native platform toolsets by default while deferred ToolLoader support is incomplete.",
    },
    "_patch_gateway_run_turn_profile_resolution": {
        "category": "required_seam",
        "owner": "gateway-runtime-seam",
        "removal_condition": "Hermes Gateway natively resolves turn profiles while preserving configured platform toolsets.",
    },
    "_patch_deferred_tool_loader_contract": {
        "category": "compat_hotfix",
        "owner": "hermes-tool-loader-seam",
        "removal_condition": "Hermes ToolLoader natively treats bundle/capability ids as schema aliases and returns continuation guidance.",
    },
    "_patch_run_agent_deferred_tool_continuation": {
        "category": "compat_hotfix",
        "owner": "hermes-tool-loader-seam",
        "removal_condition": "Hermes provider loop natively prevents final answers after schema loading until the loaded tool is used.",
    },
    "_patch_memory_manager_output_validation_seam": {
        "category": "required_seam",
        "owner": "hermes-memory-commitment-seam",
        "removal_condition": "Hermes MemoryManager natively exposes final-output validation and delivery receipt hooks for external memory providers.",
    },
    "_patch_run_agent_memory_output_validation_seam": {
        "category": "required_seam",
        "owner": "hermes-memory-commitment-seam",
        "removal_condition": "Hermes run loop natively validates memory acknowledgements before final response persistence and delivery.",
    },
    "_patch_run_agent_terminal_final_guard_seam": {
        "category": "compat_hotfix",
        "owner": "hermes-tool-safety-seam",
        "removal_condition": "Hermes provider loop natively prevents terminal execution success claims without terminal tool results.",
    },
    "_patch_memory_answer_renderer_language": {
        "category": "compat_hotfix",
        "owner": "hermes-presentation-seam",
        "removal_condition": "Hermes deterministic memory renderer natively localizes fixed templates from runtime language preference.",
    },
    "_patch_terminal_tool_result_hygiene": {
        "category": "required_seam",
        "owner": "hermes-tool-safety-seam",
        "removal_condition": "Hermes terminal tool natively mirrors blocked/approval status into model-facing output, not only error fields.",
    },
    "_patch_prompt_builder": {
        "category": "legacy_host_patch",
        "owner": "host-prompt-legacy",
        "removal_condition": "Brainstack provider projection renders the evidence-use contract.",
    },
    "_patch_memory_manager": {
        "category": "legacy_host_patch",
        "owner": "host-memory-legacy",
        "removal_condition": "Brainstack provider projection renders private memory-context guidance.",
    },
    "_patch_cron_jobs": {
        "category": "legacy_host_patch",
        "owner": "host-scheduler",
        "removal_condition": "Scheduler correctness is handled by upstream Hermes or explicit private runtime tooling.",
    },
    "_patch_cron_scheduler": {
        "category": "legacy_host_patch",
        "owner": "host-scheduler",
        "removal_condition": "Scheduler delivery/fail-closed behavior is handled by upstream Hermes.",
    },
    "_patch_cron_scheduler_tests": {
        "category": "legacy_host_patch",
        "owner": "host-scheduler-test",
        "removal_condition": "Scheduler compatibility patches are no longer applied by Brainstack installer.",
    },
    "_patch_cron_tests": {
        "category": "legacy_host_patch",
        "owner": "host-scheduler-test",
        "removal_condition": "Scheduler compatibility patches are no longer applied by Brainstack installer.",
    },
    "_patch_gateway_run": {
        "category": "legacy_host_patch",
        "owner": "host-gateway",
        "removal_condition": "Gateway lifecycle/status behavior is handled by upstream Hermes.",
    },
    "_patch_docker_entrypoint": {
        "category": "legacy_host_patch",
        "owner": "host-docker-runtime",
        "removal_condition": "Upstream Docker entrypoint owns UID/GID and runtime ownership normalization.",
    },
}

PRIVATE_RUNTIME_DENYLIST: tuple[str, ...] = (
    ".planning",
    ".planning/**",
    "hermes-config",
    "hermes-config/**",
    "runtime",
    "runtime/**",
    "docker-compose.*.yml",
    "scripts/desktop",
    "scripts/desktop/**",
    "*.desktop",
    "sessions",
    "sessions/**",
    "memories",
    "memories/**",
    "cron",
    "cron/**",
    "auth.json",
    "**/auth.json",
    "auth.lock",
    "**/auth.lock",
    ".env",
    "**/.env",
    "gateway_state.json",
    "**/gateway_state.json",
    "gateway.pid",
    "**/gateway.pid",
    "state.db",
    "state.db-*",
    "**/state.db",
    "**/state.db-*",
    "brainstack/*.db",
    "brainstack/*.db-*",
    "**/brainstack/*.db",
    "**/brainstack/*.db-*",
)

SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|"
    r"oauth[_-]?token|agent[_-]?key)\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{20,}"
)

HOST_PATCH_INVENTORY: tuple[dict[str, Any], ...] = (
    {
        "patcher": "_patch_run_agent",
        "target": "run_agent.py",
        "scope": "host-runtime-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Brainstack session-finalize wiring, transcript hygiene, and deterministic memory sync hooks.",
        "why": "Needed until Hermes exposes a stable memory-finalization seam for Brainstack.",
    },
    {
        "patcher": "_patch_run_agent_cache_evict_memory_provider_shutdown",
        "target": "run_agent.py",
        "scope": "host-lifecycle-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Close external memory provider DB/backend handles when Hermes softly evicts a cached agent.",
        "why": "Soft cache eviction rebuilds AIAgent later; open Brainstack graph/vector/sqlite handles can block the next init before the first model call.",
    },
    {
        "patcher": "_patch_run_agent_tool_call_interim_boundary",
        "target": "run_agent.py",
        "scope": "host-output-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Prevent assistant content attached to tool-call turns from being emitted as user-facing interim commentary.",
        "why": "Models may put planning text in assistant content before tool calls; public progress must use explicit status/tool callbacks, not protocol content.",
    },
    {
        "patcher": "_patch_prompt_builder",
        "target": "agent/prompt_builder.py",
        "scope": "prompt-projection-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Inject Brainstack-owned truth and memory guidance into the host prompt assembly path.",
        "why": "Brainstack still needs a thin prompt projection seam instead of a parallel prompt stack.",
    },
    {
        "patcher": "_patch_cron_jobs",
        "target": "cron/jobs.py",
        "scope": "cron-correctness-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Fail-closed job state and one-shot scheduling correctness for Brainstack-integrated reminder truth.",
        "why": "Prevents scheduler-state illusions that would contaminate Brainstack recall and user-facing truth.",
    },
    {
        "patcher": "_patch_cron_scheduler",
        "target": "cron/scheduler.py",
        "scope": "cron-delivery-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Delivery fail-closed behavior, bounded cron execution, and Brainstack-safe reminder semantics.",
        "why": "Keeps reminder truth aligned with actual scheduler delivery instead of memory-only claims.",
    },
    {
        "patcher": "_patch_cron_scheduler_tests",
        "target": "tests/cron/test_scheduler.py",
        "scope": "verification-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Align cron scheduler regression tests with the narrowed discord tool disable set and resolved runtime credential-pool contract.",
        "why": "Installer-applied cron scheduler behavior must ship with explicit regression coverage to prevent drift across Hermes updates.",
    },
    {
        "patcher": "_patch_cron_tests",
        "target": "tests/cron/test_jobs.py",
        "scope": "verification-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Extends host cron tests to cover the Brainstack-owned delivery/truth contract.",
        "why": "Installer-applied host behavior must ship with explicit regression coverage.",
    },
    {
        "patcher": "_patch_auxiliary_client",
        "target": "agent/auxiliary_client.py",
        "scope": "auxiliary-routing-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Expose Brainstack auxiliary task routing and provider control without forking the host client stack.",
        "why": "Brainstack structured-understanding and flush paths need stable auxiliary task plumbing.",
    },
    {
        "patcher": "_patch_session_search_total_deadline",
        "target": "tools/session_search_tool.py",
        "scope": "host-tool-timeout-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Keep Hermes session_search bounded so long summarization cannot outlive the gateway turn timeout.",
        "why": "Session search can otherwise spend several per-session retry windows inside the tool and leave the agent stuck until the gateway kills the turn.",
    },
    {
        "patcher": "_patch_discord_typing_backoff",
        "target": "gateway/platforms/discord.py",
        "scope": "discord-visibility-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Keep Discord typing visibility useful without letting stale overlapping typing loops hammer the channel typing endpoint.",
        "why": "Long Hermes turns should show safe liveness, but Discord typing is optional and must back off instead of producing repeated 429 retries.",
    },
    {
        "patcher": "_patch_run_agent_ebadf_transport_recovery",
        "target": "run_agent.py",
        "scope": "provider-transport-recovery-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Recover once from closed-file-descriptor provider transport failures by rebuilding the active OpenAI-wire client.",
        "why": "Long-lived gateway and cron jobs can hit stale closed descriptors; one transport rebuild is safer than failing a large background run immediately.",
    },
    {
        "patcher": "_patch_credential_pool",
        "target": "agent/credential_pool.py",
        "scope": "provider-auth-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Prevent stale Nous agent-key entries from being selected by the host credential pool during live runtime execution.",
        "why": "Without this, cron and other runtime paths can randomly fall onto expired Nous entries and appear logged out despite valid credentials.",
    },
    {
        "patcher": "_patch_credential_pool_tests",
        "target": "tests/agent/test_credential_pool.py",
        "scope": "verification-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Add regression coverage for skipping stale Nous credential-pool entries and keep time-sensitive fixtures valid.",
        "why": "The credential-pool seam is host-owned runtime behavior and must keep an explicit, reproducible test contract.",
    },
    {
        "patcher": "_patch_memory_provider",
        "target": "agent/memory_provider.py",
        "scope": "memory-provider-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Add Brainstack-specific write-origin and provider bridge wiring.",
        "why": "Preserves provenance/trust boundaries between host memory events and Brainstack durable state.",
    },
    {
        "patcher": "_patch_memory_manager_required_seam",
        "target": "agent/memory_manager.py",
        "scope": "memory-write-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Forward optional write-origin metadata from Hermes memory manager to external memory providers.",
        "why": "Brainstack must distinguish reflection/background writes from user-established truth without heuristic inference.",
    },
    {
        "patcher": "_patch_memory_manager",
        "target": "agent/memory_manager.py",
        "scope": "legacy-memory-projection-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Legacy host-side private recalled-memory wording mutation.",
        "why": "Superseded by Brainstack-owned evidence-use projection; retained only for legacy emergency installs.",
    },
    {
        "patcher": "_patch_gateway_run",
        "target": "gateway/run.py",
        "scope": "gateway-lifecycle-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Brainstack lifecycle hooks that must execute at gateway runtime boundaries.",
        "why": "Avoids a parallel runtime while keeping Brainstack synchronized with the single Hermes gateway.",
    },
    {
        "patcher": "_patch_gateway_background_process_output_boundary",
        "target": "gateway/run.py",
        "scope": "gateway-output-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Keep large background-process/watch output out of user-facing and model-facing chat context while preserving full output as an artifact.",
        "why": "Raw process output injected through watch/queue messages can force repeated compression and make queued work look frozen.",
    },
    {
        "patcher": "_patch_gateway_turn_profiles_capability_preserving_default",
        "target": "gateway/turn_profiles.py",
        "scope": "gateway-capability-preservation-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Prevent Discord conversation mode from replacing Hermes' native platform toolset with an empty compact profile.",
        "why": "Brainstack integration must not make native file, terminal, web, or workflow tools disappear behind hidden mode selection.",
    },
    {
        "patcher": "_patch_gateway_run_turn_profile_resolution",
        "target": "gateway/run.py",
        "scope": "gateway-capability-preservation-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Wire Gateway turns through the capability-preserving turn profile resolver.",
        "why": "The profile module is inert unless Gateway uses it before constructing the per-turn agent.",
    },
    {
        "patcher": "_patch_config",
        "target": "hermes-config/<agent>/config.yaml",
        "scope": "runtime-config-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Enable Brainstack provider and task-specific auxiliary/runtime configuration.",
        "why": "The live runtime needs explicit config ownership separate from copied plugin payload files.",
    },
    {
        "patcher": "_patch_compose_healthcheck",
        "target": "docker-compose*.yml",
        "scope": "docker-runtime-seam",
        "runtime_modes": ("docker",),
        "purpose": "Install Brainstack-aware gateway healthcheck behavior for Docker runtime verification.",
        "why": "Docker installs need explicit health semantics to validate the integrated runtime, not just the container process.",
    },
    {
        "patcher": "_patch_compose_runtime_identity",
        "target": "docker-compose*.yml",
        "scope": "docker-runtime-seam",
        "runtime_modes": ("docker",),
        "purpose": "Align runtime UID/GID and mounted state paths with the generated Brainstack Docker flow.",
        "why": "Prevents permission drift and runtime ownership breakage in containerized installs.",
    },
    {
        "patcher": "_patch_compose_plugin_pythonpath",
        "target": "docker-compose*.yml",
        "scope": "docker-runtime-seam",
        "runtime_modes": ("docker",),
        "purpose": "Put the Hermes project plugin root ahead of mutable runtime state for Python imports.",
        "why": "Prevents /opt/data/brainstack runtime storage from shadowing the installed Brainstack plugin package.",
    },
    {
        "patcher": "_patch_compose_discord_bot_mentions",
        "target": "docker-compose*.yml",
        "scope": "docker-runtime-seam",
        "runtime_modes": ("docker",),
        "purpose": "Allow trusted canary bot messages only when they mention the Hermes Discord bot.",
        "why": "Live Discord smoke uses a separate bot sender; without this env the adapter ignores bot-origin messages by default.",
    },
    {
        "patcher": "_patch_compose_terminal_workspace_cwd",
        "target": "docker-compose*.yml",
        "scope": "docker-runtime-seam",
        "runtime_modes": ("docker",),
        "purpose": "Make terminal commands execute from the mounted workspace by default.",
        "why": "Docker file/terminal canaries need an explicit workspace contract instead of inherited image cwd.",
    },
    {
        "patcher": "_patch_compose_hindsight_local_tier2_runtime",
        "target": "docker-compose*.yml",
        "scope": "tier2-donor-runtime-seam",
        "runtime_modes": ("docker",),
        "purpose": "Bind Tier2 shadow runtime to local Hindsight over local Ollama with no cloud route or secret.",
        "why": "Tier2 cannot claim runtime readiness until the donor spine is explicitly local, inspectable, and reproducible by the installer.",
    },
    {
        "patcher": "_patch_compose_remove_discord_forced_heavy_profile",
        "target": "docker-compose*.yml",
        "scope": "docker-runtime-seam",
        "runtime_modes": ("docker",),
        "purpose": "Remove the obsolete forced-heavy Discord profile fallback from existing Docker installs.",
        "why": "Capability preservation now belongs to the turn profile seam, not a permanent heavy-mode runtime override.",
    },
    {
        "patcher": "_patch_deferred_tool_loader_contract",
        "target": "hermes_deferred_tools.py",
        "scope": "tool-loader-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Keep deferred tool loading capability-preserving when the model asks for bundle/capability aliases.",
        "why": "A schema alias such as terminal_execute must load the concrete configured tool instead of becoming a false no-access path.",
    },
    {
        "patcher": "_patch_run_agent_deferred_tool_continuation",
        "target": "run_agent.py",
        "scope": "provider-loop-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Prevent a final answer after tool schema loading until the loaded concrete tool is used.",
        "why": "Deferred schema loading is only product-safe if the provider loop cannot answer from memory after declaring a tool need.",
    },
    {
        "patcher": "_patch_memory_manager_output_validation_seam",
        "target": "agent/memory_manager.py",
        "scope": "memory-commitment-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Expose final-output validation and delivery hooks from Hermes MemoryManager to external memory providers.",
        "why": "A model's remembered/saved wording is not proof; Brainstack receipts must be checked before Hermes ships the final response.",
    },
    {
        "patcher": "_patch_run_agent_memory_output_validation_seam",
        "target": "run_agent.py",
        "scope": "memory-commitment-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Validate final memory acknowledgements before session persistence, plugin hooks, external sync, and user delivery.",
        "why": "Prevents false durable-memory acknowledgement when the provider failed to produce complete receipt coverage.",
    },
    {
        "patcher": "_patch_run_agent_terminal_final_guard_seam",
        "target": "run_agent.py",
        "scope": "tool-safety-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Prevent terminal command results from being claimed without a terminal tool result in the same turn.",
        "why": "Cheap or unstable providers can answer from memory; Hermes must enforce no-final-before-terminal-result at the runtime boundary.",
    },
    {
        "patcher": "_patch_memory_answer_renderer_language",
        "target": "gateway/memory_answer_renderer.py",
        "scope": "presentation-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Localize deterministic memory renderer templates from runtime language preference.",
        "why": "Direct renderer speed must not bypass user-visible language/style contract on typed memory answers.",
    },
    {
        "patcher": "_patch_terminal_tool_result_hygiene",
        "target": "tools/terminal_tool.py",
        "scope": "tool-safety-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Make blocked terminal results impossible to summarize as successful blank-output commands.",
        "why": "A blocked/approval-required side-effect tool result must carry its denial in model-facing output to avoid unsafe success hallucinations.",
    },
    {
        "patcher": "_patch_dockerignore",
        "target": ".dockerignore",
        "scope": "docker-build-seam",
        "runtime_modes": ("docker",),
        "purpose": "Ensure required Brainstack payload and runtime assets are available in Docker builds.",
        "why": "Without this, Docker rebuilds can silently omit install-critical files.",
    },
    {
        "patcher": "_patch_dockerfile_backend_dependencies",
        "target": "Dockerfile",
        "scope": "docker-build-seam",
        "runtime_modes": ("docker",),
        "purpose": "Install Brainstack backend dependencies inside the runtime image.",
        "why": "The plugin payload alone is insufficient; the container image must contain its runtime deps.",
    },
    {
        "patcher": "_patch_dockerfile_workstation_python_alias",
        "target": "Dockerfile",
        "scope": "docker-workstation-seam",
        "runtime_modes": ("docker",),
        "purpose": "Expose `python` for agent terminal/tool sessions even when login shells reset PATH.",
        "why": "The container process PATH can be correct while login shells still fall back to /usr/local/bin:/usr/bin without a `python` command.",
    },
    {
        "patcher": "_patch_docker_entrypoint",
        "target": "docker/entrypoint.sh",
        "scope": "docker-runtime-seam",
        "runtime_modes": ("docker",),
        "purpose": "Preserve Brainstack runtime startup invariants in Docker mode.",
        "why": "Keeps the container startup path aligned with the installed Brainstack-integrated runtime.",
    },
)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iter_payload_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and not path.name.endswith(".pyc"):
            files.append(path)
    return files


def _normalize_rel_path(value: str | Path) -> str:
    rendered = str(value).replace("\\", "/").strip()
    while rendered.startswith("./"):
        rendered = rendered[2:]
    return rendered.strip("/")


def _is_private_runtime_path(value: str | Path) -> bool:
    normalized = _normalize_rel_path(value)
    if not normalized:
        return False
    return any(
        normalized == pattern.rstrip("/").replace("/**", "")
        or fnmatch.fnmatch(normalized, pattern)
        for pattern in PRIVATE_RUNTIME_DENYLIST
    )


def _assert_no_private_payload_files(files: list[dict[str, str]]) -> None:
    private_sources = [
        item["source"]
        for item in files
        if _is_private_runtime_path(item.get("source", ""))
    ]
    if private_sources:
        raise RuntimeError(
            "Refusing to include private runtime files in Brainstack payload: "
            + ", ".join(sorted(private_sources)[:12])
        )


def _path_may_contain_text(path: Path) -> bool:
    return path.suffix.lower() in {
        "",
        ".cfg",
        ".conf",
        ".json",
        ".md",
        ".py",
        ".sh",
        ".toml",
        ".txt",
        ".yaml",
        ".yml",
    }


def _scan_tracked_secret_like_assignments(repo_root: Path) -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=repo_root,
            text=False,
            capture_output=True,
            check=True,
        )
    except Exception:
        return []
    findings: list[str] = []
    for raw in proc.stdout.split(b"\0"):
        if not raw:
            continue
        rel = raw.decode("utf-8", errors="replace")
        path = repo_root / rel
        if not path.is_file() or not _path_may_contain_text(path):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if SECRET_ASSIGNMENT_RE.search(text):
            findings.append(rel)
    return findings


def _check_release_hygiene(repo_root: Path) -> dict[str, Any]:
    tracked: list[str] = []
    staged: list[str] = []
    for cmd, output in (
        (["git", "ls-files", "-z"], tracked),
        (["git", "diff", "--cached", "--name-only", "-z"], staged),
    ):
        proc = subprocess.run(cmd, cwd=repo_root, text=False, capture_output=True, check=True)
        output.extend(
            raw.decode("utf-8", errors="replace")
            for raw in proc.stdout.split(b"\0")
            if raw
        )
    private_tracked = [path for path in tracked if _is_private_runtime_path(path)]
    private_staged = [path for path in staged if _is_private_runtime_path(path)]
    secret_like = _scan_tracked_secret_like_assignments(repo_root)
    status = "pass" if not private_tracked and not private_staged and not secret_like else "fail"
    return {
        "schema": "brainstack.release_hygiene.v1",
        "status": status,
        "private_tracked": private_tracked,
        "private_staged": private_staged,
        "secret_like_tracked": secret_like,
    }


def _default_target_python(target: Path) -> Path | None:
    candidates = [
        target / ".venv" / "bin" / "python",
        target / "venv" / "bin" / "python",
        target / ".venv" / "Scripts" / "python.exe",
        target / "venv" / "Scripts" / "python.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _python_can_import(python_bin: Path, module_name: str) -> bool:
    try:
        proc = subprocess.run(
            [
                str(python_bin),
                "-c",
                (
                    "import importlib.util, sys; "
                    f"sys.exit(0 if importlib.util.find_spec({module_name!r}) else 1)"
                ),
            ],
            capture_output=True,
            text=True,
        )
        return proc.returncode == 0
    except Exception:
        return False


def _ensure_backend_dependencies(
    python_bin: Path | None,
    *,
    dry_run: bool,
    skip_deps: bool,
) -> dict[str, Any]:
    if skip_deps:
        return {"status": "skipped", "reason": "skip_deps"}
    if python_bin is None:
        return {"status": "skipped", "reason": "no_target_python"}

    missing = [dist for module, dist in BACKEND_DEPENDENCIES.items() if not _python_can_import(python_bin, module)]
    if not missing:
        return {"status": "already_satisfied", "python": str(python_bin), "packages": []}
    if dry_run:
        return {"status": "planned", "python": str(python_bin), "packages": missing}

    attempts: list[tuple[str, list[str]]] = [
        ("pip", [str(python_bin), "-m", "pip", "install", *missing]),
    ]
    uv_bin = shutil.which("uv")
    if uv_bin:
        attempts.append(("uv", [uv_bin, "pip", "install", "--python", str(python_bin), *missing]))

    failures: list[str] = []
    for label, cmd in attempts:
        proc = subprocess.run(cmd, text=True, capture_output=True)
        if proc.returncode == 0:
            return {"status": "installed", "python": str(python_bin), "packages": missing, "installer": label}
        stderr = (proc.stderr or "").strip()
        stdout = (proc.stdout or "").strip()
        failures.append(f"{label}: {stderr or stdout or 'unknown error'}")

    raise RuntimeError(
        f"Dependency install failed for {' '.join(missing)} using {python_bin}; "
        + " | ".join(failures)
    )


def _copy_tree(src: Path, dst: Path, dry_run: bool) -> list[dict[str, str]]:
    copied: list[dict[str, str]] = []
    for src_file in _iter_payload_files(src):
        rel = src_file.relative_to(src)
        dst_file = dst / rel
        copied.append({"source": str(src_file.relative_to(REPO_ROOT)), "target": str(dst_file), "sha256": _hash_file(src_file)})
        if not dry_run:
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
    return copied


def _copy_file(src: Path, dst: Path, dry_run: bool) -> dict[str, str]:
    copied = {
        "source": str(src.relative_to(REPO_ROOT)),
        "target": str(dst),
        "sha256": _hash_file(src),
    }
    if not dry_run:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return copied


def _host_patch_policy(patcher: str) -> dict[str, str]:
    return dict(
        HOST_PATCH_POLICIES.get(
            patcher,
            {
                "category": "legacy_host_patch",
                "owner": "unclassified",
                "removal_condition": "Classify this host patch before enabling it by default.",
            },
        )
    )


def _host_patch_selected(patcher: str, host_patch_mode: str) -> bool:
    policy = _host_patch_policy(patcher)
    allowed = HOST_PATCH_MODE_CATEGORIES[host_patch_mode]
    return policy["category"] in allowed


def _selected_host_patch_inventory(runtime_mode: str, host_patch_mode: str = "core") -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    normalized = "docker" if runtime_mode == "docker" else "source"
    for item in HOST_PATCH_INVENTORY:
        runtime_modes = tuple(item.get("runtime_modes") or ())
        if normalized in runtime_modes:
            patcher = str(item["patcher"])
            policy = _host_patch_policy(patcher)
            selected.append(
                {
                    "patcher": patcher,
                    "target": item["target"],
                    "scope": item["scope"],
                    "runtime_modes": list(runtime_modes),
                    "purpose": item["purpose"],
                    "why": item["why"],
                    "category": policy["category"],
                    "owner": policy["owner"],
                    "removal_condition": policy["removal_condition"],
                    "selected": _host_patch_selected(patcher, host_patch_mode),
                    "host_patch_mode": host_patch_mode,
                }
            )
    return selected


def _run_host_patch(
    patcher: str,
    target_path: Path,
    dry_run: bool,
    *,
    host_patch_mode: str,
) -> list[str]:
    if not _host_patch_selected(patcher, host_patch_mode):
        return []
    patch_func = globals().get(patcher)
    if not callable(patch_func):
        raise RuntimeError(f"Unknown host patcher: {patcher}")
    return list(patch_func(target_path, dry_run))


def _replace_once(text: str, old: str, new: str, *, label: str, path: Path) -> str:
    if old not in text:
        raise RuntimeError(f"Installer patch anchor missing for {label} in {path}")
    return text.replace(old, new, 1)


def _replace_once_any(
    text: str,
    replacements: list[tuple[str, str]],
    *,
    label: str,
    path: Path,
) -> str:
    for old, new in replacements:
        if old in text:
            return text.replace(old, new, 1)
    raise RuntimeError(f"Installer patch anchor missing for {label} in {path}")


def _memory_write_signature_accepts_metadata(text: str) -> bool:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "on_memory_write":
            arg_names = {arg.arg for arg in [*node.args.args, *node.args.kwonlyargs]}
            return "metadata" in arg_names
    return False


def _memory_manager_forwards_write_metadata(text: str) -> bool:
    if not _memory_write_signature_accepts_metadata(text):
        return False
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "on_memory_write":
            continue
        if any(keyword.arg == "metadata" for keyword in node.keywords):
            return True
        if len(node.args) >= 4:
            return True
    return False


def _patch_memory_manager_required_seam(path: Path, dry_run: bool) -> list[str]:
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []

    if _memory_manager_forwards_write_metadata(text):
        return []

    metadata_signature = "def on_memory_write(self, action: str, target: str, content: str, metadata: dict | None = None) -> None:"
    if metadata_signature not in text:
        old_signature = "def on_memory_write(self, action: str, target: str, content: str) -> None:"
        new_signature = "def on_memory_write(self, action: str, target: str, content: str, metadata: dict | None = None) -> None:"
        text = _replace_once(
            text,
            old_signature,
            new_signature,
            label="memory_manager memory-write metadata signature",
            path=path,
        )
        applied.append("memory_manager:memory_write_metadata_signature")

    metadata_bridge = (
        "                if metadata:\n"
        "                    try:\n"
        "                        provider.on_memory_write(action, target, content, metadata=metadata)\n"
        "                    except TypeError:\n"
        "                        provider.on_memory_write(action, target, content)\n"
        "                else:\n"
        "                    provider.on_memory_write(action, target, content)\n"
    )
    if metadata_bridge not in text:
        old_call = "                provider.on_memory_write(action, target, content)\n"
        text = _replace_once(
            text,
            old_call,
            metadata_bridge,
            label="memory_manager memory-write metadata bridge",
            path=path,
        )
        applied.append("memory_manager:memory_write_metadata_bridge")

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _patch_memory_manager_output_validation_seam(path: Path, dry_run: bool) -> list[str]:
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []

    typing_import = "from typing import Any, Dict, List, Optional"
    if typing_import in text:
        text = text.replace(typing_import, "from typing import Any, Dict, List, Mapping, Optional", 1)
        applied.append("memory_manager:typing_mapping_import")

    if "def validate_assistant_output_all(" not in text:
        old_block = (
            "    def sync_all(self, user_content: str, assistant_content: str, *, session_id: str = \"\") -> None:\n"
            "        \"\"\"Sync a completed turn to all providers.\"\"\"\n"
            "        for provider in self._providers:\n"
            "            try:\n"
            "                provider.sync_turn(user_content, assistant_content, session_id=session_id)\n"
            "            except Exception as e:\n"
            "                logger.warning(\n"
            "                    \"Memory provider '%s' sync_turn failed: %s\",\n"
            "                    provider.name, e,\n"
            "                )\n"
        )
        new_block = old_block + (
            "\n"
            "    def validate_assistant_output_all(\n"
            "        self,\n"
            "        content: str,\n"
            "        *,\n"
            "        user_content: str = \"\",\n"
            "        session_id: str = \"\",\n"
            "    ) -> Dict[str, Any] | None:\n"
            "        \"\"\"Validate a final assistant response through external memory providers.\n"
            "\n"
            "        Providers only return validation/receipt state. Hermes owns whether to\n"
            "        ship, retry, or render an honest failure message.\n"
            "        \"\"\"\n"
            "        current_content = str(content or \"\")\n"
            "        provider_results: List[Dict[str, Any]] = []\n"
            "        changed = False\n"
            "        blocked = False\n"
            "        for provider in self._providers:\n"
            "            validator = getattr(provider, \"validate_assistant_output\", None)\n"
            "            if not callable(validator):\n"
            "                continue\n"
            "            try:\n"
            "                try:\n"
            "                    result = validator(current_content, user_content=user_content, session_id=session_id)\n"
            "                except TypeError:\n"
            "                    result = validator(current_content)\n"
            "            except Exception as e:\n"
            "                logger.warning(\"Memory provider '%s' validate_assistant_output failed: %s\", provider.name, e)\n"
            "                continue\n"
            "            if not isinstance(result, Mapping):\n"
            "                continue\n"
            "            payload = dict(result)\n"
            "            payload[\"provider\"] = provider.name\n"
            "            provider_results.append(payload)\n"
            "            next_content = payload.get(\"content\")\n"
            "            if isinstance(next_content, str) and next_content and next_content != current_content:\n"
            "                current_content = next_content\n"
            "                changed = True\n"
            "            if payload.get(\"blocked\") or payload.get(\"can_ship\") is False:\n"
            "                blocked = True\n"
            "        if not provider_results:\n"
            "            return None\n"
            "        if blocked:\n"
            "            current_content = _render_memory_commitment_blocked(provider_results)\n"
            "            changed = True\n"
            "        return {\n"
            "            \"schema\": \"hermes.memory_output_validation.v1\",\n"
            "            \"content\": current_content,\n"
            "            \"changed\": changed,\n"
            "            \"blocked\": blocked,\n"
            "            \"provider_results\": provider_results,\n"
            "        }\n"
            "\n"
            "    def record_output_validation_delivery_all(\n"
            "        self,\n"
            "        validation_result: Mapping[str, Any] | None,\n"
            "        *,\n"
            "        delivered_content: str,\n"
            "    ) -> None:\n"
            "        if not isinstance(validation_result, Mapping):\n"
            "            return\n"
            "        results = validation_result.get(\"provider_results\")\n"
            "        if not isinstance(results, list):\n"
            "            return\n"
            "        by_name = {str(item.get(\"provider\") or \"\"): item for item in results if isinstance(item, Mapping)}\n"
            "        for provider in self._providers:\n"
            "            recorder = getattr(provider, \"record_output_validation_delivery\", None)\n"
            "            if not callable(recorder):\n"
            "                continue\n"
            "            try:\n"
            "                recorder(by_name.get(provider.name), delivered_content=delivered_content)\n"
            "            except Exception as e:\n"
            "                logger.debug(\"Memory provider '%s' output validation delivery record failed: %s\", provider.name, e)\n"
        )
        text = _replace_once(
            text,
            old_block,
            new_block,
            label="memory_manager output validation seam",
            path=path,
        )
        applied.append("memory_manager:output_validation_seam")

    if "def _render_memory_commitment_blocked(" not in text:
        helper_anchor = "\n\nclass MemoryManager:\n"
        helper_block = (
            "\n\n"
            "def _render_memory_commitment_blocked(provider_results: List[Mapping[str, Any]]) -> str:\n"
            "    missing: List[str] = []\n"
            "    covered: List[str] = []\n"
            "    for result in provider_results:\n"
            "        validation = result.get(\"memory_commitment_validation\") if isinstance(result, Mapping) else None\n"
            "        if not isinstance(validation, Mapping):\n"
            "            continue\n"
            "        ack = validation.get(\"ack_plan\")\n"
            "        if not isinstance(ack, Mapping):\n"
            "            continue\n"
            "        covered.extend(str(slot) for slot in ack.get(\"covered_slots\") or [] if slot)\n"
            "        missing.extend(str(slot) for slot in ack.get(\"missing_slots\") or [] if slot)\n"
            "    if covered or missing:\n"
            "        covered_text = \", \".join(covered) if covered else \"no verified fields\"\n"
            "        missing_text = \", \".join(missing) if missing else \"no missing fields\"\n"
            "        return (\n"
            "            \"I cannot claim everything was saved because full write receipt coverage is missing. \"\n"
            "            f\"Verified: {covered_text}. Missing: {missing_text}.\"\n"
            "        )\n"
            "    return \"I cannot claim this was saved because there is no successful durable memory write receipt.\"\n"
            "\n\n"
            "class MemoryManager:\n"
        )
        text = _replace_once(
            text,
            helper_anchor,
            helper_block,
            label="memory_manager memory commitment blocked renderer",
            path=path,
        )
        applied.append("memory_manager:memory_commitment_blocked_renderer")

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _patch_memory_manager(path: Path, dry_run: bool) -> list[str]:
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []

    old_note = (
        '        "[System note: The following is recalled memory context, "\n'
        '        "NOT new user input. Treat as informational background data.]\\n\\n"\n'
    )
    new_note = (
        '        "[System note: The following is private recalled memory context, NOT new user input. "\n'
        '        "Apply it silently in your reply. Do not mention memory blocks, recalled-memory headings, "\n'
        '        "or internal memory state unless the user explicitly asks about memory behavior or debugging. "\n'
        '        "Use recalled details as supporting memory context, and when recalled items disagree, prefer the strongest committed or non-conflicted recalled record instead of blending them.]\\n\\n"\n'
    )
    current_private_note = (
        '        "[System note: The following is private recalled memory context, NOT new user input. "\n'
        '        "Apply it silently in your reply. Do not mention memory blocks, recalled-memory headings, "\n'
        '        "or internal memory state unless the user explicitly asks about memory behavior or debugging.]\\n\\n"\n'
    )
    authoritative_private_note = (
        '        "[System note: The following is private recalled memory context, NOT new user input. "\n'
        '        "Apply it silently in your reply. Do not mention memory blocks, recalled-memory headings, "\n'
        '        "or internal memory state unless the user explicitly asks about memory behavior or debugging. "\n'
        '        "When recalled memory provides a specific, non-conflicted factual user detail or committed owner-backed record such as a name, number, date, or task record, treat it as authoritative over assistant suggestions or generic prior knowledge unless another recalled fact in this memory block conflicts with it.]\\n\\n"\n'
    )
    if new_note not in text:
        text = _replace_once_any(
            text,
            [
                (old_note, new_note),
                (current_private_note, new_note),
                (authoritative_private_note, new_note),
            ],
            label="memory_manager private recall note",
            path=path,
        )
        applied.append("memory_manager:private_recall_note")

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")

    applied.extend(_patch_memory_manager_required_seam(path, dry_run))
    return applied


def _patch_memory_provider(path: Path, dry_run: bool) -> list[str]:
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []

    if _memory_write_signature_accepts_metadata(text):
        return []

    metadata_doc = "    def on_memory_write(self, action: str, target: str, content: str, metadata: dict[str, Any] | None = None) -> None:\n"
    if metadata_doc not in text:
        old_signature = "    def on_memory_write(self, action: str, target: str, content: str) -> None:\n"
        new_signature = "    def on_memory_write(self, action: str, target: str, content: str, metadata: dict[str, Any] | None = None) -> None:\n"
        text = _replace_once(
            text,
            old_signature,
            new_signature,
            label="memory_provider memory-write metadata signature",
            path=path,
        )
        applied.append("memory_provider:memory_write_metadata_signature")

    if "metadata: optional write-origin or trust metadata" not in text:
        old_doc = (
            "        action: 'add', 'replace', or 'remove'\n"
            "        target: 'memory' or 'user'\n"
            "        content: the entry content\n"
            "\n"
            "        Use to mirror built-in memory writes to your backend.\n"
        )
        new_doc = (
            "        action: 'add', 'replace', or 'remove'\n"
            "        target: 'memory' or 'user'\n"
            "        content: the entry content\n"
            "        metadata: optional write-origin or trust metadata\n"
            "\n"
            "        Use to mirror built-in memory writes to your backend.\n"
        )
        text = _replace_once(
            text,
            old_doc,
            new_doc,
            label="memory_provider memory-write metadata doc",
            path=path,
        )
        applied.append("memory_provider:memory_write_metadata_doc")

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _patch_prompt_builder(path: Path, dry_run: bool) -> list[str]:
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []

    scheduler_guidance = (
        '    "without acting are not acceptable.\\n"\n'
        '    "If you claim that a reminder, cron job, or scheduled follow-up exists, that claim must be grounded in a real native scheduler record or a successful cronjob tool result from this run. A memory entry, todo note, or generic internal task list is not a scheduled job. Do not inspect OS-level cron or systemd timers as a substitute for Hermes scheduler state. If the cronjob tool is unavailable or the scheduler call fails, say that scheduling is unavailable or failed."\n'
        ")\n"
    )
    old_tail = (
        '    "without acting are not acceptable."\n'
        ")\n"
    )
    weaker_tail = (
        '    "without acting are not acceptable.\\n"\n'
        '    "If you claim that a reminder, cron job, or scheduled follow-up exists, that claim must be grounded in a real native scheduler record or a successful cronjob tool result from this run. Memory alone is not a scheduled job. If scheduling fails or you did not verify the job exists, say so plainly."\n'
        ")\n"
    )
    if "generic internal task list is not a scheduled job" not in text and weaker_tail in text:
        text = _replace_once(
            text,
            weaker_tail,
            scheduler_guidance,
            label="prompt_builder stronger scheduler truth guidance",
            path=path,
        )
        applied.append("prompt_builder:stronger_scheduler_truth_guidance")
    elif "generic internal task list is not a scheduled job" not in text and old_tail in text:
        text = _replace_once(
            text,
            old_tail,
            scheduler_guidance,
            label="prompt_builder scheduler truth guidance",
            path=path,
        )
        applied.append("prompt_builder:scheduler_truth_guidance")

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _patch_cron_jobs(path: Path, dry_run: bool) -> list[str]:
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []

    helper_anchor = "ONESHOT_GRACE_SECONDS = 120\n\n\n"
    helper_block = (
        "ONESHOT_GRACE_SECONDS = 120\n\n\n"
        "def _request_active_job_cancel(job_id: str, reason: str) -> None:\n"
        "    \"\"\"Best-effort interrupt for an in-flight cron job running in this process.\"\"\"\n"
        "    try:\n"
        "        from cron.scheduler import request_cancel  # Lazy import avoids module cycle at import time\n"
        "        request_cancel(job_id, reason)\n"
        "    except Exception:\n"
        "        pass\n\n\n"
        "def _request_scheduler_wake(reason: str) -> None:\n"
        "    \"\"\"Best-effort wake-up hint for the in-process cron ticker.\"\"\"\n"
        "    try:\n"
        "        from cron.scheduler import request_tick_wake  # Lazy import avoids module cycle at import time\n"
        "        request_tick_wake(reason)\n"
        "    except Exception:\n"
        "        pass\n\n\n"
    )
    if "def _request_scheduler_wake(reason: str) -> None:" not in text and helper_anchor in text:
        text = _replace_once(
            text,
            helper_anchor,
            helper_block,
            label="cron.jobs wake/cancel helpers",
            path=path,
        )
        applied.append("cron_jobs:wake_cancel_helpers")

    old_block = (
        "    # Default delivery to origin if available, otherwise local\n"
        "    if deliver is None:\n"
        "        deliver = \"origin\" if origin else \"local\"\n"
        "\n"
        "    job_id = uuid.uuid4().hex[:12]\n"
        "    now = _hermes_now().isoformat()\n"
    )
    new_block = (
        "    # Default delivery to origin if available, otherwise local\n"
        "    if deliver is None:\n"
        "        deliver = \"origin\" if origin else \"local\"\n"
        "\n"
        "    next_run_at = compute_next_run(parsed_schedule)\n"
        "    if parsed_schedule[\"kind\"] == \"once\" and next_run_at is None:\n"
        "        raise ValueError(\"Requested one-shot schedule is already in the past.\")\n"
        "\n"
        "    job_id = uuid.uuid4().hex[:12]\n"
        "    now = _hermes_now().isoformat()\n"
    )
    if "Requested one-shot schedule is already in the past." not in text and old_block in text:
        text = _replace_once(text, old_block, new_block, label="cron.jobs past one-shot rejection", path=path)
        applied.append("cron_jobs:reject_past_oneshot")

    old_next_run = '        "next_run_at": compute_next_run(parsed_schedule),\n'
    new_next_run = '        "next_run_at": next_run_at,\n'
    if old_next_run in text and new_next_run not in text:
        text = _replace_once(text, old_next_run, new_next_run, label="cron.jobs cached next_run_at", path=path)
        applied.append("cron_jobs:reuse_next_run_at")

    old_create_save = (
        "    jobs = load_jobs()\n"
        "    jobs.append(job)\n"
        "    save_jobs(jobs)\n"
        "\n"
        "    return job\n"
    )
    new_create_save = (
        "    jobs = load_jobs()\n"
        "    jobs.append(job)\n"
        "    save_jobs(jobs)\n"
        "    _request_scheduler_wake(f\"cron job created: {job_id}\")\n"
        "\n"
        "    return job\n"
    )
    if "_request_scheduler_wake(f\"cron job created: {job_id}\")" not in text and old_create_save in text:
        text = _replace_once(text, old_create_save, new_create_save, label="cron.jobs wake after create", path=path)
        applied.append("cron_jobs:wake_after_create")

    old_update_intro = (
        "        updated = _apply_skill_fields({**job, **updates})\n"
        "        schedule_changed = \"schedule\" in updates\n"
        "\n"
        "        if \"skills\" in updates or \"skill\" in updates:\n"
    )
    new_update_intro = (
        "        updated = _apply_skill_fields({**job, **updates})\n"
        "        schedule_changed = \"schedule\" in updates\n"
        "        update_keys = set(updates)\n"
        "        should_cancel_active = bool(\n"
        "            update_keys.intersection(\n"
        "                {\n"
        "                    \"schedule\",\n"
        "                    \"enabled\",\n"
        "                    \"state\",\n"
        "                    \"next_run_at\",\n"
        "                    \"prompt\",\n"
        "                    \"skill\",\n"
        "                    \"skills\",\n"
        "                    \"script\",\n"
        "                    \"model\",\n"
        "                    \"provider\",\n"
        "                    \"base_url\",\n"
        "                    \"deliver\",\n"
        "                    \"origin\",\n"
        "                }\n"
        "            )\n"
        "        )\n"
        "        should_wake_scheduler = bool(\n"
        "            update_keys.intersection({\"schedule\", \"enabled\", \"state\", \"next_run_at\"})\n"
        "        )\n"
        "\n"
        "        if \"skills\" in updates or \"skill\" in updates:\n"
    )
    if "should_wake_scheduler = bool(" not in text and old_update_intro in text:
        text = _replace_once(text, old_update_intro, new_update_intro, label="cron.jobs update control flags", path=path)
        applied.append("cron_jobs:update_control_flags")

    old_update_save = (
        "        jobs[i] = updated\n"
        "        save_jobs(jobs)\n"
        "        return _apply_skill_fields(jobs[i])\n"
    )
    new_update_save = (
        "        jobs[i] = updated\n"
        "        save_jobs(jobs)\n"
        "        if should_cancel_active:\n"
        "            _request_active_job_cancel(job_id, \"Cron job updated while running\")\n"
        "        if should_wake_scheduler:\n"
        "            _request_scheduler_wake(f\"cron job updated: {job_id}\")\n"
        "        return _apply_skill_fields(jobs[i])\n"
    )
    if "Cron job updated while running" not in text and old_update_save in text:
        text = _replace_once(text, old_update_save, new_update_save, label="cron.jobs update wake/cancel", path=path)
        applied.append("cron_jobs:update_wake_cancel")

    old_remove = (
        "    if len(jobs) < original_len:\n"
        "        save_jobs(jobs)\n"
        "        return True\n"
    )
    new_remove = (
        "    if len(jobs) < original_len:\n"
        "        save_jobs(jobs)\n"
        "        _request_active_job_cancel(job_id, \"Cron job removed\")\n"
        "        _request_scheduler_wake(f\"cron job removed: {job_id}\")\n"
        "        return True\n"
    )
    if "_request_scheduler_wake(f\"cron job removed: {job_id}\")" not in text and old_remove in text:
        text = _replace_once(text, old_remove, new_remove, label="cron.jobs remove wake/cancel", path=path)
        applied.append("cron_jobs:remove_wake_cancel")

    old_delivery_status = (
        '            job["last_status"] = "ok" if success else "error"\n'
        '            job["last_error"] = error if not success else None\n'
        '            # Track delivery failures separately — cleared on successful delivery\n'
        '            job["last_delivery_error"] = delivery_error\n'
    )
    new_delivery_status = (
        '            delivery_failed = bool(delivery_error)\n'
        '            job["last_status"] = "error" if (not success or delivery_failed) else "ok"\n'
        '            job["last_error"] = error if error else (delivery_error if delivery_failed else None)\n'
        '            job["last_delivery_error"] = delivery_error\n'
    )
    if 'job["last_status"] = "error" if (not success or delivery_failed) else "ok"' not in text and old_delivery_status in text:
        text = _replace_once(text, old_delivery_status, new_delivery_status, label="cron.jobs fail_closed_delivery_status", path=path)
        applied.append("cron_jobs:fail_closed_delivery_status")

    seconds_helper_anchor = "def save_job_output(job_id: str, output: str):\n"
    seconds_helper_block = (
        "def seconds_until_next_run(max_wait: float = 60.0) -> float:\n"
        "    \"\"\"Return seconds until the next due job, bounded by ``max_wait``.\"\"\"\n"
        "    now = _hermes_now()\n"
        "    soonest = max_wait\n"
        "\n"
        "    for job in [_apply_skill_fields(j) for j in copy.deepcopy(load_jobs())]:\n"
        "        if not job.get(\"enabled\", True):\n"
        "            continue\n"
        "\n"
        "        next_run = job.get(\"next_run_at\")\n"
        "        if not next_run:\n"
        "            next_run = _recoverable_oneshot_run_at(\n"
        "                job.get(\"schedule\", {}),\n"
        "                now,\n"
        "                last_run_at=job.get(\"last_run_at\"),\n"
        "            )\n"
        "        if not next_run:\n"
        "            continue\n"
        "\n"
        "        try:\n"
        "            next_dt = _ensure_aware(datetime.fromisoformat(next_run))\n"
        "        except Exception:\n"
        "            continue\n"
        "\n"
        "        delay = (next_dt - now).total_seconds()\n"
        "        if delay <= 0:\n"
        "            return 0.0\n"
        "        if delay < soonest:\n"
        "            soonest = delay\n"
        "\n"
        "    return max(0.0, min(max_wait, soonest))\n\n\n"
        "def save_job_output(job_id: str, output: str):\n"
    )
    if "def seconds_until_next_run(max_wait: float = 60.0) -> float:" not in text and seconds_helper_anchor in text:
        text = _replace_once(text, seconds_helper_anchor, seconds_helper_block, label="cron.jobs next-run delay helper", path=path)
        applied.append("cron_jobs:seconds_until_next_run")

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _patch_cron_scheduler(path: Path, dry_run: bool) -> list[str]:
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []

    import_anchor = "from cron.jobs import get_due_jobs, mark_job_run, save_job_output, advance_next_run\n"
    import_block = (
        "from cron.jobs import get_due_jobs, mark_job_run, save_job_output, advance_next_run\n\n"
        "_ACTIVE_JOBS_LOCK = threading.Lock()\n"
        "_ACTIVE_JOBS: dict[str, dict] = {}\n"
        "_TICK_WAKE_EVENT = threading.Event()\n\n\n"
        "def _set_active_job_field(job_id: str, **updates) -> None:\n"
        "    with _ACTIVE_JOBS_LOCK:\n"
        "        entry = _ACTIVE_JOBS.setdefault(\n"
        "            job_id,\n"
        "            {\n"
        "                \"agent\": None,\n"
        "                \"future\": None,\n"
        "                \"cancel_requested\": False,\n"
        "                \"cancel_reason\": None,\n"
        "            },\n"
        "        )\n"
        "        entry.update(updates)\n\n\n"
        "def _clear_active_job(job_id: str) -> None:\n"
        "    with _ACTIVE_JOBS_LOCK:\n"
        "        _ACTIVE_JOBS.pop(job_id, None)\n\n\n"
        "def _is_cancel_requested(job_id: str) -> tuple[bool, Optional[str]]:\n"
        "    with _ACTIVE_JOBS_LOCK:\n"
        "        entry = _ACTIVE_JOBS.get(job_id) or {}\n"
        "        return bool(entry.get(\"cancel_requested\")), entry.get(\"cancel_reason\")\n\n\n"
        "def request_cancel(job_id: str, reason: str = \"Cron job cancelled\") -> bool:\n"
        "    with _ACTIVE_JOBS_LOCK:\n"
        "        entry = _ACTIVE_JOBS.get(job_id)\n"
        "        if not entry:\n"
        "            return False\n"
        "        entry[\"cancel_requested\"] = True\n"
        "        entry[\"cancel_reason\"] = reason\n"
        "        agent = entry.get(\"agent\")\n"
        "        future = entry.get(\"future\")\n\n"
        "    if agent is not None and hasattr(agent, \"interrupt\"):\n"
        "        try:\n"
        "            agent.interrupt(reason)\n"
        "        except Exception:\n"
        "            pass\n"
        "    if future is not None:\n"
        "        try:\n"
        "            future.cancel()\n"
        "        except Exception:\n"
        "            pass\n"
        "    return True\n\n\n"
        "def request_tick_wake(reason: Optional[str] = None) -> None:\n"
        "    if reason:\n"
        "        logger.debug(\"Cron scheduler wake requested: %s\", reason)\n"
        "    _TICK_WAKE_EVENT.set()\n\n\n"
        "def wait_for_tick_wake(stop_event: threading.Event, timeout: float) -> None:\n"
        "    if timeout <= 0:\n"
        "        return\n"
        "    if stop_event.is_set():\n"
        "        return\n"
        "    _TICK_WAKE_EVENT.wait(timeout=timeout)\n"
        "    _TICK_WAKE_EVENT.clear()\n"
    )
    if "def request_tick_wake(reason: Optional[str] = None) -> None:" not in text and import_anchor in text:
        text = _replace_once(text, import_anchor, import_block, label="cron.scheduler active job registry", path=path)
        applied.append("cron_scheduler:active_job_registry")

    old_live_adapter = (
        "        runtime_adapter = (adapters or {}).get(platform)\n"
        "        delivered = False\n"
        "        if runtime_adapter is not None and loop is not None and getattr(loop, \"is_running\", lambda: False)():\n"
    )
    new_live_adapter = (
        "        runtime_adapter = (adapters or {}).get(platform)\n"
        "        gateway_delivery_mode = adapters is not None and loop is not None\n"
        "        delivered = False\n"
        "        live_adapter_error = None\n"
        "        if runtime_adapter is not None and loop is not None and getattr(loop, \"is_running\", lambda: False)():\n"
    )
    if "live_adapter_error = None" not in text and old_live_adapter in text:
        text = _replace_once(text, old_live_adapter, new_live_adapter, label="cron.scheduler gateway delivery mode", path=path)
        applied.append("cron_scheduler:gateway_delivery_mode")

    old_disabled = '            disabled_toolsets=["cronjob", "messaging", "clarify"],\n'
    new_disabled = '            disabled_toolsets=["cronjob", "messaging", "clarify", "discord"],\n'
    if old_disabled in text and new_disabled not in text:
        text = _replace_once(text, old_disabled, new_disabled, label="cron.scheduler disable discord admin tool", path=path)
    legacy_disabled = '            disabled_toolsets=["cronjob", "messaging", "clarify", "hermes-discord"],\n'
    if legacy_disabled in text:
        text = _replace_once(text, legacy_disabled, new_disabled, label="cron.scheduler replace over-broad hermes-discord disable", path=path)
        applied.append("cron_scheduler:disable_hermes_discord")

    old_pool_block = (
        "        fallback_model = _cfg.get(\"fallback_providers\") or _cfg.get(\"fallback_model\") or None\n"
        "        credential_pool = None\n"
        "        runtime_provider = str(runtime.get(\"provider\") or \"\").strip().lower()\n"
        "        if runtime_provider:\n"
        "            try:\n"
        "                from agent.credential_pool import load_pool\n"
        "                pool = load_pool(runtime_provider)\n"
        "                if pool.has_credentials():\n"
        "                    credential_pool = pool\n"
        "                    logger.info(\n"
        "                        \"Job '%s': loaded credential pool for provider %s with %d entries\",\n"
        "                        job_id,\n"
        "                        runtime_provider,\n"
        "                        len(pool.entries()),\n"
        "                    )\n"
        "            except Exception as e:\n"
        "                logger.debug(\"Job '%s': failed to load credential pool for %s: %s\", job_id, runtime_provider, e)\n"
    )
    new_pool_block = (
        "        fallback_model = _cfg.get(\"fallback_providers\") or _cfg.get(\"fallback_model\") or None\n"
        "        credential_pool = runtime.get(\"credential_pool\")\n"
        "        runtime_provider = str(runtime.get(\"provider\") or \"\").strip().lower()\n"
        "        if credential_pool is not None:\n"
        "            try:\n"
        "                if credential_pool.has_credentials():\n"
        "                    logger.info(\n"
        "                        \"Job '%s': using resolved credential pool for provider %s with %d entries\",\n"
        "                        job_id,\n"
        "                        runtime_provider,\n"
        "                        len(credential_pool.entries()),\n"
        "                    )\n"
        "                else:\n"
        "                    credential_pool = None\n"
        "            except Exception as e:\n"
        "                logger.debug(\n"
        "                    \"Job '%s': resolved credential pool unusable for %s: %s\",\n"
        "                    job_id,\n"
        "                    runtime_provider,\n"
        "                    e,\n"
        "                )\n"
        "                credential_pool = None\n"
    )
    if old_pool_block in text and new_pool_block not in text:
        text = _replace_once(text, old_pool_block, new_pool_block, label="cron.scheduler resolved credential pool", path=path)
        applied.append("cron_scheduler:resolved_credential_pool")

    old_ctx = (
        "    _ctx_tokens = set_session_vars(\n"
        "        platform=origin[\"platform\"] if origin else \"\",\n"
        "        chat_id=str(origin[\"chat_id\"]) if origin else \"\",\n"
        "        chat_name=origin.get(\"chat_name\", \"\") if origin else \"\",\n"
        "    )\n"
    )
    new_ctx = old_ctx + "    _set_active_job_field(job_id)\n"
    if "_set_active_job_field(job_id)" not in text and old_ctx in text:
        text = _replace_once(text, old_ctx, new_ctx, label="cron.scheduler mark active job", path=path)
        applied.append("cron_scheduler:mark_active_job")

    old_future = "        _cron_future = _cron_pool.submit(_cron_context.run, agent.run_conversation, prompt)\n"
    new_future = (
        "        _cron_future = _cron_pool.submit(_cron_context.run, agent.run_conversation, prompt)\n"
        "        _set_active_job_field(job_id, agent=agent, future=_cron_future)\n"
    )
    if "_set_active_job_field(job_id, agent=agent, future=_cron_future)" not in text and old_future in text:
        text = _replace_once(text, old_future, new_future, label="cron.scheduler track cron future", path=path)
        applied.append("cron_scheduler:track_future")

    old_wait_loop = (
        "                while True:\n"
        "                    done, _ = concurrent.futures.wait(\n"
        "                        {_cron_future}, timeout=_POLL_INTERVAL,\n"
        "                    )\n"
    )
    new_wait_loop = (
        "                while True:\n"
        "                    _cancelled, _cancel_reason = _is_cancel_requested(job_id)\n"
        "                    if _cancelled:\n"
        "                        if hasattr(agent, \"interrupt\"):\n"
        "                            try:\n"
        "                                agent.interrupt(_cancel_reason or \"Cron job cancelled\")\n"
        "                            except Exception:\n"
        "                                pass\n"
        "                        raise RuntimeError(_cancel_reason or \"Cron job cancelled\")\n"
        "                    done, _ = concurrent.futures.wait(\n"
        "                        {_cron_future}, timeout=_POLL_INTERVAL,\n"
        "                    )\n"
    )
    if "_cancelled, _cancel_reason = _is_cancel_requested(job_id)" not in text and old_wait_loop in text:
        text = _replace_once(text, old_wait_loop, new_wait_loop, label="cron.scheduler cancel while waiting", path=path)
        applied.append("cron_scheduler:cancel_while_waiting")

    old_final_response = '        final_response = result.get("final_response", "") or ""\n'
    new_final_response = (
        "        _cancelled, _cancel_reason = _is_cancel_requested(job_id)\n"
        "        if _cancelled:\n"
        "            raise RuntimeError(_cancel_reason or \"Cron job cancelled\")\n\n"
        '        final_response = result.get("final_response", "") or ""\n'
    )
    if "_cancelled, _cancel_reason = _is_cancel_requested(job_id)" in text:
        pass
    elif old_final_response in text:
        text = _replace_once(text, old_final_response, new_final_response, label="cron.scheduler cancel before final response", path=path)
        applied.append("cron_scheduler:cancel_before_final_response")

    old_run_finally = (
        "    finally:\n"
        "        # Clean up ContextVar session/delivery state for this job.\n"
        "        clear_session_vars(_ctx_tokens)\n"
    )
    new_run_finally = (
        "    finally:\n"
        "        _clear_active_job(job_id)\n"
        "        # Clean up ContextVar session/delivery state for this job.\n"
        "        clear_session_vars(_ctx_tokens)\n"
    )
    if "_clear_active_job(job_id)" not in text and old_run_finally in text:
        text = _replace_once(text, old_run_finally, new_run_finally, label="cron.scheduler clear active job", path=path)
        applied.append("cron_scheduler:clear_active_job")

    old_live_send_fail = (
        "                        msg = f\"live adapter send to {platform_name}:{chat_id} failed: {err}\"\n"
        "                        logger.warning(\"Job '%s': %s\", job[\"id\"], msg)\n"
        "                        delivery_errors.append(msg)\n"
        "                        adapter_ok = False\n"
    )
    new_live_send_fail = (
        "                        msg = f\"live adapter send to {platform_name}:{chat_id} failed: {err}\"\n"
        "                        logger.warning(\"Job '%s': %s\", job[\"id\"], msg)\n"
        "                        live_adapter_error = msg\n"
        "                        adapter_ok = False\n"
    )
    if old_live_send_fail in text and new_live_send_fail not in text:
        text = _replace_once(text, old_live_send_fail, new_live_send_fail, label="cron.scheduler retain live send error for fallback", path=path)
        applied.append("cron_scheduler:live_send_error_buffer")

    old_live_send_success = (
        "                # Send extracted media files as native attachments via the live adapter\n"
        "                if adapter_ok and media_files:\n"
        "                    _send_media_via_adapter(runtime_adapter, chat_id, media_files, send_metadata, loop, job)\n"
        "\n"
        "                if adapter_ok:\n"
        "                    logger.info(\"Job '%s': delivered to %s:%s via live adapter\", job[\"id\"], platform_name, chat_id)\n"
        "                    delivered = True\n"
        "                else:\n"
        "                    continue\n"
        "            except Exception as e:\n"
        "                msg = f\"live adapter delivery to {platform_name}:{chat_id} failed: {e}\"\n"
        "                logger.warning(\"Job '%s': %s\", job[\"id\"], msg)\n"
        "                delivery_errors.append(msg)\n"
        "                continue\n"
    )
    new_live_send_success = (
        "                # Send extracted media files as native attachments via the live adapter\n"
        "                if adapter_ok and media_files:\n"
        "                    _send_media_via_adapter(runtime_adapter, chat_id, media_files, send_metadata, loop, job)\n"
        "\n"
        "                if adapter_ok:\n"
        "                    logger.info(\"Job '%s': delivered to %s:%s via live adapter\", job[\"id\"], platform_name, chat_id)\n"
        "                    delivered = True\n"
        "            except Exception as e:\n"
        "                msg = f\"live adapter delivery to {platform_name}:{chat_id} failed: {e}\"\n"
        "                logger.warning(\"Job '%s': %s\", job[\"id\"], msg)\n"
        "                live_adapter_error = msg\n"
    )
    if old_live_send_success in text and new_live_send_success not in text:
        text = _replace_once(text, old_live_send_success, new_live_send_success, label="cron.scheduler fallback after live adapter failure", path=path)
        applied.append("cron_scheduler:live_delivery_fallback")

    old_platform_disabled = (
        "            if not pconfig or not pconfig.enabled:\n"
        "                msg = f\"platform '{platform_name}' not configured/enabled\"\n"
        "                logger.warning(\"Job '%s': %s\", job[\"id\"], msg)\n"
        "                delivery_errors.append(msg)\n"
        "                continue\n"
    )
    new_platform_disabled = (
        "            if not pconfig or not pconfig.enabled:\n"
        "                if live_adapter_error:\n"
        "                    delivery_errors.append(live_adapter_error)\n"
        "                msg = f\"platform '{platform_name}' not configured/enabled\"\n"
        "                logger.warning(\"Job '%s': %s\", job[\"id\"], msg)\n"
        "                delivery_errors.append(msg)\n"
        "                continue\n"
    )
    if "if live_adapter_error:\n                    delivery_errors.append(live_adapter_error)" not in text and old_platform_disabled in text:
        text = _replace_once(text, old_platform_disabled, new_platform_disabled, label="cron.scheduler preserve live adapter error when fallback unavailable", path=path)
        applied.append("cron_scheduler:preserve_live_error_on_disabled_platform")

    old_standalone = (
        "            # Standalone path: run the async send in a fresh event loop (safe from any thread)\n"
        "            coro = _send_to_platform(platform, pconfig, chat_id, cleaned_delivery_content, thread_id=thread_id, media_files=media_files)\n"
        "            try:\n"
        "                result = asyncio.run(coro)\n"
        "            except RuntimeError:\n"
        "                # asyncio.run() checks for a running loop before awaiting the coroutine;\n"
        "                # when it raises, the original coro was never started — close it to\n"
        "                # prevent \"coroutine was never awaited\" RuntimeWarning, then retry in a\n"
        "                # fresh thread that has no running loop.\n"
        "                coro.close()\n"
        "                import concurrent.futures\n"
        "                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:\n"
        "                    future = pool.submit(asyncio.run, _send_to_platform(platform, pconfig, chat_id, cleaned_delivery_content, thread_id=thread_id, media_files=media_files))\n"
        "                    result = future.result(timeout=30)\n"
        "            except Exception as e:\n"
        "                msg = f\"delivery to {platform_name}:{chat_id} failed: {e}\"\n"
        "                logger.error(\"Job '%s': %s\", job[\"id\"], msg)\n"
        "                delivery_errors.append(msg)\n"
        "                continue\n"
    )
    new_standalone = (
        "            # Standalone path: always run in a bounded worker thread so a hung\n"
        "            # network send cannot wedge the scheduler tick.\n"
        "            import concurrent.futures\n"
        "            _standalone_timeout = int(float(os.getenv(\"HERMES_CRON_DELIVERY_TIMEOUT\", \"30\")))\n"
        "            _pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)\n"
        "            try:\n"
        "                future = _pool.submit(\n"
        "                    asyncio.run,\n"
        "                    _send_to_platform(\n"
        "                        platform,\n"
        "                        pconfig,\n"
        "                        chat_id,\n"
        "                        cleaned_delivery_content,\n"
        "                        thread_id=thread_id,\n"
        "                        media_files=media_files,\n"
        "                    ),\n"
        "                )\n"
        "                result = future.result(timeout=_standalone_timeout)\n"
        "            except concurrent.futures.TimeoutError:\n"
        "                if live_adapter_error:\n"
        "                    delivery_errors.append(live_adapter_error)\n"
        "                msg = f\"delivery to {platform_name}:{chat_id} timed out after {_standalone_timeout}s\"\n"
        "                logger.error(\"Job '%s': %s\", job[\"id\"], msg)\n"
        "                delivery_errors.append(msg)\n"
        "                _pool.shutdown(wait=False, cancel_futures=True)\n"
        "                continue\n"
        "            except Exception as e:\n"
        "                if live_adapter_error:\n"
        "                    delivery_errors.append(live_adapter_error)\n"
        "                msg = f\"delivery to {platform_name}:{chat_id} failed: {e}\"\n"
        "                logger.error(\"Job '%s': %s\", job[\"id\"], msg)\n"
        "                delivery_errors.append(msg)\n"
        "                _pool.shutdown(wait=False, cancel_futures=True)\n"
        "                continue\n"
        "            finally:\n"
        "                _pool.shutdown(wait=False, cancel_futures=True)\n"
    )
    if "HERMES_CRON_DELIVERY_TIMEOUT" not in text and old_standalone in text:
        text = _replace_once(text, old_standalone, new_standalone, label="cron.scheduler bounded standalone delivery", path=path)
        applied.append("cron_scheduler:bounded_standalone_delivery")

    old_result_error = (
        "            if result and result.get(\"error\"):\n"
        "                msg = f\"delivery error: {result['error']}\"\n"
        "                logger.error(\"Job '%s': %s\", job[\"id\"], msg)\n"
        "                delivery_errors.append(msg)\n"
        "                continue\n"
    )
    new_result_error = (
        "            if result and result.get(\"error\"):\n"
        "                if live_adapter_error:\n"
        "                    delivery_errors.append(live_adapter_error)\n"
        "                msg = f\"delivery error: {result['error']}\"\n"
        "                logger.error(\"Job '%s': %s\", job[\"id\"], msg)\n"
        "                delivery_errors.append(msg)\n"
        "                continue\n"
    )
    if "if live_adapter_error:\n                    delivery_errors.append(live_adapter_error)" not in text[text.find("if result and result.get(\"error\")") - 120:text.find("if result and result.get(\"error\")") + 240] and old_result_error in text:
        text = _replace_once(text, old_result_error, new_result_error, label="cron.scheduler retain live adapter error on fallback error", path=path)
        applied.append("cron_scheduler:retain_live_error_on_fallback_error")

    old_mark = '                mark_job_run(job["id"], success, error, delivery_error=delivery_error)\n'
    new_mark = (
        '                mark_job_run(job["id"], success, error, delivery_error=delivery_error)\n'
        '                logger.info(\n'
        '                    "Job \'%s\': finalized success=%s delivery_error=%s",\n'
        '                    job["id"],\n'
        '                    success,\n'
        '                    delivery_error,\n'
        '                )\n'
    )
    if 'logger.info(\n                    "Job \'%s\': finalized success=%s delivery_error=%s"' not in text and old_mark in text:
        text = _replace_once(text, old_mark, new_mark, label="cron.scheduler finalized logging", path=path)
        applied.append("cron_scheduler:finalized_logging")

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _patch_cron_tests(path: Path, dry_run: bool) -> list[str]:
    if not path.exists():
        return []

    text = path.read_text(encoding="utf-8")
    applied: list[str] = []

    old_expectation = (
        '        assert updated["last_status"] == "ok"\n'
        '        assert updated["last_error"] is None\n'
        "        assert updated[\"last_delivery_error\"] == \"platform 'telegram' not configured\"\n"
    )
    new_expectation = (
        '        assert updated["last_status"] == "error"\n'
        "        assert updated[\"last_error\"] == \"platform 'telegram' not configured\"\n"
        "        assert updated[\"last_delivery_error\"] == \"platform 'telegram' not configured\"\n"
    )
    if old_expectation in text and new_expectation not in text:
        text = _replace_once(
            text,
            old_expectation,
            new_expectation,
            label="cron tests fail_closed_delivery_expectation",
            path=path,
        )
        applied.append("cron_tests:fail_closed_delivery_expectation")

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _patch_cron_scheduler_tests(path: Path, dry_run: bool) -> list[str]:
    if not path.exists():
        return []

    text = path.read_text(encoding="utf-8")
    applied: list[str] = []

    old_disabled_expectation = '        assert "hermes-discord" in (kwargs["disabled_toolsets"] or [])\n'
    new_disabled_expectation = '        assert "discord" in (kwargs["disabled_toolsets"] or [])\n'
    if old_disabled_expectation in text and new_disabled_expectation not in text:
        text = _replace_once(
            text,
            old_disabled_expectation,
            new_disabled_expectation,
            label="cron scheduler tests narrow discord disabled toolset expectation",
            path=path,
        )
        applied.append("cron_scheduler_tests:disable_discord_expectation")

    old_pool_test = (
        "        assert kwargs[\"credential_pool\"] is pool\n"
        "        mock_load_pool.assert_called_once_with(\"nous\")\n"
    )
    new_pool_test = (
        "        assert kwargs[\"credential_pool\"] is pool\n"
        "        mock_load_pool.assert_not_called()\n"
    )
    if old_pool_test in text and new_pool_test not in text:
        text = _replace_once(
            text,
            old_pool_test,
            new_pool_test,
            label="cron scheduler tests resolved credential pool expectation",
            path=path,
        )
        applied.append("cron_scheduler_tests:resolved_credential_pool")

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _patch_credential_pool(path: Path, dry_run: bool) -> list[str]:
    if not path.exists():
        return []

    text = path.read_text(encoding="utf-8")
    applied: list[str] = []

    old_available_block = (
        "            if refresh and self._entry_needs_refresh(entry):\n"
        "                refreshed = self._refresh_entry(entry, force=False)\n"
        "                if refreshed is None:\n"
        "                    continue\n"
        "                entry = refreshed\n"
        "            available.append(entry)\n"
    )
    new_available_block = (
        "            if refresh and self._entry_needs_refresh(entry):\n"
        "                refreshed = self._refresh_entry(entry, force=False)\n"
        "                if refreshed is None:\n"
        "                    continue\n"
        "                entry = refreshed\n"
        "            if self.provider == \"nous\":\n"
        "                nous_state = {\n"
        "                    \"agent_key\": entry.agent_key,\n"
        "                    \"agent_key_expires_at\": entry.agent_key_expires_at,\n"
        "                }\n"
        "                if not auth_mod._agent_key_is_usable(\n"
        "                    nous_state,\n"
        "                    DEFAULT_AGENT_KEY_MIN_TTL_SECONDS,\n"
        "                ):\n"
        "                    continue\n"
        "            available.append(entry)\n"
    )
    if old_available_block in text and new_available_block not in text:
        text = _replace_once(
            text,
            old_available_block,
            new_available_block,
            label="credential pool skip stale nous agent keys",
            path=path,
        )
        applied.append("credential_pool:skip_stale_nous_entries")

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _patch_credential_pool_tests(path: Path, dry_run: bool) -> list[str]:
    if not path.exists():
        return []

    text = path.read_text(encoding="utf-8")
    applied: list[str] = []

    old_fixture_dates = [
        ("                    \"expires_at\": \"2026-03-24T12:00:00+00:00\",\n", "                    \"expires_at\": \"2027-03-24T12:00:00+00:00\",\n"),
        ("                    \"agent_key_expires_at\": \"2026-03-24T13:30:00+00:00\",\n", "                    \"agent_key_expires_at\": \"2027-03-24T13:30:00+00:00\",\n"),
    ]
    fixture_patched = False
    for old_line, new_line in old_fixture_dates:
        if old_line in text:
            text = text.replace(old_line, new_line)
            fixture_patched = True
    if fixture_patched:
        applied.append("credential_pool_tests:refresh_nous_fixture_dates")

    marker = "def test_singleton_seed_does_not_clobber_manual_oauth_entry"
    new_test = (
        "\n\ndef test_select_skips_stale_nous_agent_keys(tmp_path, monkeypatch):\n"
        "    monkeypatch.setenv(\"HERMES_HOME\", str(tmp_path / \"hermes\"))\n"
        "    _write_auth_store(\n"
        "        tmp_path,\n"
        "        {\n"
        "            \"version\": 1,\n"
        "            \"credential_pool\": {\n"
        "                \"nous\": [\n"
        "                    {\n"
        "                        \"id\": \"stale\",\n"
        "                        \"label\": \"stale-manual\",\n"
        "                        \"auth_type\": \"oauth\",\n"
        "                        \"priority\": 0,\n"
        "                        \"source\": \"manual:device_code\",\n"
        "                        \"access_token\": \"portal-token-stale\",\n"
        "                        \"refresh_token\": \"refresh-stale\",\n"
        "                        \"agent_key\": \"agent-key-stale\",\n"
        "                        \"agent_key_expires_at\": \"2026-04-11T19:06:29.675Z\",\n"
        "                        \"inference_base_url\": \"https://inference-api.nousresearch.com/v1\",\n"
        "                    },\n"
        "                    {\n"
        "                        \"id\": \"fresh\",\n"
        "                        \"label\": \"fresh-device\",\n"
        "                        \"auth_type\": \"oauth\",\n"
        "                        \"priority\": 1,\n"
        "                        \"source\": \"device_code\",\n"
        "                        \"access_token\": \"portal-token-fresh\",\n"
        "                        \"refresh_token\": \"refresh-fresh\",\n"
        "                        \"agent_key\": \"agent-key-fresh\",\n"
        "                        \"agent_key_expires_at\": \"2026-04-24T00:04:33.001Z\",\n"
        "                        \"inference_base_url\": \"https://inference-api.nousresearch.com/v1\",\n"
        "                    },\n"
        "                ]\n"
        "            },\n"
        "        },\n"
        "    )\n"
        "\n"
        "    from agent.credential_pool import load_pool\n"
        "\n"
        "    pool = load_pool(\"nous\")\n"
        "    entry = pool.select()\n"
        "\n"
        "    assert entry is not None\n"
        "    assert entry.id == \"fresh\"\n"
    )
    if "def test_select_skips_stale_nous_agent_keys" not in text and marker in text:
        text = text.replace(marker, new_test + "\n\n" + marker)
        applied.append("credential_pool_tests:skip_stale_nous_entries")

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _patch_run_agent_cache_evict_memory_provider_shutdown(path: Path, dry_run: bool) -> list[str]:
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []

    if "          - memory provider (has its own lifecycle; keeps running)\n" in text:
        text = text.replace(
            "          - memory provider (has its own lifecycle; keeps running)\n",
            "          - memory provider session-end flush (soft eviction only closes runtime handles)\n",
            1,
        )
        applied.append("run_agent:cache_evict_memory_provider_docstring")

    cache_evict_memory_shutdown = (
        "        # Close external memory provider runtime handles. Soft cache eviction\n"
        "        # is not a session boundary, so do not call on_session_end() here.\n"
        "        # Closing provider handles prevents graph/vector/sqlite locks from\n"
        "        # leaking into the freshly rebuilt agent for the same session.\n"
        "        try:\n"
        "            if self._memory_manager:\n"
        "                self._memory_manager.shutdown_all()\n"
        "                self._memory_manager = None\n"
        "        except Exception:\n"
        "            pass\n\n"
    )
    if "Soft cache eviction\n        # is not a session boundary" not in text:
        text = _replace_once(
            text,
            "        # Close the OpenAI/httpx client to release sockets immediately.\n",
            cache_evict_memory_shutdown
            + "        # Close the OpenAI/httpx client to release sockets immediately.\n",
            label="run_agent cache-evict memory provider shutdown",
            path=path,
        )
        applied.append("run_agent:cache_evict_memory_provider_shutdown")

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _patch_run_agent_tool_call_interim_boundary(path: Path, dry_run: bool) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []

    anchor = (
        "        if cb is None or not isinstance(assistant_msg, dict):\n"
        "            return\n"
        "        content = assistant_msg.get(\"content\")\n"
    )
    replacement = (
        "        if cb is None or not isinstance(assistant_msg, dict):\n"
        "            return\n"
        "        if assistant_msg.get(\"tool_calls\"):\n"
        "            # Tool-call turns are transcript/API state; public progress uses explicit callbacks.\n"
        "            return\n"
        "        content = assistant_msg.get(\"content\")\n"
    )
    if "Tool-call turns are transcript/API state" not in text and anchor in text:
        text = _replace_once(
            text,
            anchor,
            replacement,
            label="run_agent tool-call interim user-facing boundary",
            path=path,
        )
        applied.append("run_agent:tool_call_interim_user_facing_boundary")

    codex_state_anchor = (
        "        max_stream_retries = 1\n"
        "        has_tool_calls = False\n"
        "        first_delta_fired = False\n"
    )
    codex_state_replacement = (
        "        max_stream_retries = 1\n"
        "        has_tool_calls = False\n"
        "        first_delta_fired = False\n"
        "        tool_boundary_text_buffer: list[str] = []\n"
        "\n"
        "        def _flush_tool_boundary_text_buffer() -> None:\n"
        "            nonlocal first_delta_fired\n"
        "            if has_tool_calls or not tool_boundary_text_buffer:\n"
        "                tool_boundary_text_buffer.clear()\n"
        "                return\n"
        "            for _delta_text in list(tool_boundary_text_buffer):\n"
        "                if not first_delta_fired:\n"
        "                    first_delta_fired = True\n"
        "                    if on_first_delta:\n"
        "                        try:\n"
        "                            on_first_delta()\n"
        "                        except Exception:\n"
        "                            pass\n"
        "                self._fire_stream_delta(_delta_text)\n"
        "            tool_boundary_text_buffer.clear()\n"
    )
    if "def _flush_tool_boundary_text_buffer() -> None:" not in text and codex_state_anchor in text:
        text = _replace_once(
            text,
            codex_state_anchor,
            codex_state_replacement,
            label="run_agent codex stream tool-boundary buffer",
            path=path,
        )
        applied.append("run_agent:codex_stream_tool_boundary_buffer")

    codex_delta_anchor = (
        "                            if delta_text and not has_tool_calls:\n"
        "                                if not first_delta_fired:\n"
        "                                    first_delta_fired = True\n"
        "                                    if on_first_delta:\n"
        "                                        try:\n"
        "                                            on_first_delta()\n"
        "                                        except Exception:\n"
        "                                            pass\n"
        "                                self._fire_stream_delta(delta_text)\n"
    )
    codex_delta_replacement = (
        "                            if delta_text:\n"
        "                                # Buffer until the completed response proves this is not a tool-call turn.\n"
        "                                tool_boundary_text_buffer.append(delta_text)\n"
    )
    if "tool_boundary_text_buffer.append(delta_text)" not in text and codex_delta_anchor in text:
        text = _replace_once(
            text,
            codex_delta_anchor,
            codex_delta_replacement,
            label="run_agent codex stream buffer deltas before tool boundary",
            path=path,
        )
        applied.append("run_agent:codex_stream_buffer_preface")

    codex_flush_anchor = "                    final_response = stream.get_final_response()\n"
    codex_flush_replacement = "                    _flush_tool_boundary_text_buffer()\n                    final_response = stream.get_final_response()\n"
    if "_flush_tool_boundary_text_buffer()\n                    final_response = stream.get_final_response()" not in text and codex_flush_anchor in text:
        text = _replace_once(
            text,
            codex_flush_anchor,
            codex_flush_replacement,
            label="run_agent codex stream flush non-tool final text",
            path=path,
        )
        applied.append("run_agent:codex_stream_flush_safe_final")

    chat_state_anchor = (
        "            content_parts: list = []\n"
        "            tool_calls_acc: dict = {}\n"
    )
    chat_state_replacement = (
        "            content_parts: list = []\n"
        "            tool_boundary_text_buffer: list[str] = []\n"
        "            tool_calls_acc: dict = {}\n"
    )
    if "tool_boundary_text_buffer: list[str] = []\n            tool_calls_acc: dict = {}" not in text and chat_state_anchor in text:
        text = _replace_once(
            text,
            chat_state_anchor,
            chat_state_replacement,
            label="run_agent chat stream tool-boundary buffer",
            path=path,
        )
        applied.append("run_agent:chat_stream_tool_boundary_buffer")

    chat_delta_anchor = (
        "                if delta and delta.content:\n"
        "                    content_parts.append(delta.content)\n"
        "                    if not tool_calls_acc:\n"
        "                        _fire_first_delta()\n"
        "                        self._fire_stream_delta(delta.content)\n"
        "                        deltas_were_sent[\"yes\"] = True\n"
        "                    else:\n"
        "                        # Tool calls suppress regular content streaming (avoids\n"
        "                        # displaying chatty \"I'll use the tool...\" text alongside\n"
        "                        # tool calls).  But reasoning tags embedded in suppressed\n"
        "                        # content should still reach the display — otherwise the\n"
        "                        # reasoning box only appears as a post-response fallback,\n"
        "                        # rendering it confusingly after the already-streamed\n"
        "                        # response.  Route suppressed content through the stream\n"
        "                        # delta callback so its tag extraction can fire the\n"
        "                        # reasoning display.  Non-reasoning text is harmlessly\n"
        "                        # suppressed by the CLI's _stream_delta when the stream\n"
        "                        # box is already closed (tool boundary flush).\n"
        "                        if self.stream_delta_callback:\n"
        "                            try:\n"
        "                                self.stream_delta_callback(delta.content)\n"
        "                                self._record_streamed_assistant_text(delta.content)\n"
        "                            except Exception:\n"
        "                                pass\n"
    )
    chat_delta_replacement = (
        "                if delta and delta.content:\n"
        "                    content_parts.append(delta.content)\n"
        "                    if not tool_calls_acc:\n"
        "                        # Buffer until the completed response proves this is not a tool-call turn.\n"
        "                        tool_boundary_text_buffer.append(delta.content)\n"
    )
    if "tool_boundary_text_buffer.append(delta.content)" not in text and chat_delta_anchor in text:
        text = _replace_once(
            text,
            chat_delta_anchor,
            chat_delta_replacement,
            label="run_agent chat stream buffer preface",
            path=path,
        )
        applied.append("run_agent:chat_stream_buffer_preface")

    chat_flush_anchor = "            # Build mock response matching non-streaming shape\n"
    chat_flush_replacement = (
        "            if not tool_calls_acc and tool_boundary_text_buffer:\n"
        "                for _delta_text in list(tool_boundary_text_buffer):\n"
        "                    _fire_first_delta()\n"
        "                    self._fire_stream_delta(_delta_text)\n"
        "                    deltas_were_sent[\"yes\"] = True\n"
        "                tool_boundary_text_buffer.clear()\n"
        "\n"
        "            # Build mock response matching non-streaming shape\n"
    )
    if "if not tool_calls_acc and tool_boundary_text_buffer:" not in text and chat_flush_anchor in text:
        text = _replace_once(
            text,
            chat_flush_anchor,
            chat_flush_replacement,
            label="run_agent chat stream flush safe final text",
            path=path,
        )
        applied.append("run_agent:chat_stream_flush_safe_final")

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _patch_run_agent(path: Path, dry_run: bool) -> list[str]:
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []

    deterministic_index_impl = (
        "    def _compile_user_profile_index(self) -> None:\n"
        "        if not self._memory_store or not self._user_profile_enabled:\n"
        "            return\n"
        "        entries = [str(entry).strip() for entry in getattr(self._memory_store, \"user_entries\", []) if str(entry).strip()]\n"
        "        if not entries:\n"
        "            try:\n"
        "                self._memory_store.save_user_profile_index({})\n"
        "            except Exception:\n"
        "                pass\n"
        "            return\n"
        "        normalized = self._memory_store._derive_user_profile_index_from_entries(entries)\n"
        "        try:\n"
        "            self._memory_store.save_user_profile_index(\n"
        "                {\n"
        "                    \"preferred_user_name\": str(normalized.get(\"preferred_user_name\") or \"\").strip(),\n"
        "                    \"assistant_name\": str(normalized.get(\"assistant_name\") or \"\").strip(),\n"
        "                }\n"
        "            )\n"
        "        except Exception:\n"
        "            pass\n"
    )
    old_compile = (
        "    def _compile_user_profile_index(self) -> None:\n"
        "        if not self._memory_store or not self._user_profile_enabled:\n"
        "            return\n"
        "        entries = [str(entry).strip() for entry in getattr(self._memory_store, \"user_entries\", []) if str(entry).strip()]\n"
        "        if not entries:\n"
        "            try:\n"
        "                self._memory_store.save_user_profile_index({})\n"
        "            except Exception:\n"
        "                pass\n"
        "            return\n"
        "        messages = [\n"
        "            {\n"
        "                \"role\": \"system\",\n"
        "                \"content\": (\n"
        "                    \"You compile a tiny reusable index from explicit user-taught profile truth. \"\n"
        "                    \"Return JSON only with keys preferred_user_name and assistant_name. \"\n"
        "                    \"Fill a key only when the explicit entries make it clearly usable later. \"\n"
        "                    \"For preferred_user_name, return the direct reusable address form that should be used to address \"\n"
        "                    \"the user in later replies, not an inflected sentence fragment. If a stored entry already uses a \"\n"
        "                    \"canonical naming label but its value is still a sentence fragment or grammatically inflected \"\n"
        "                    \"variant, repair it to the shortest reusable standalone name or address form. Do not return \"\n"
        "                    \"surrounding teaching words, quoted clauses, or case-marked variants when a direct reusable form \"\n"
        "                    \"is recoverable from the explicit entry. \"\n"
        "                    \"For assistant_name, return the assistant's own name only if explicit user-taught truth makes it clear. \"\n"
        "                    \"Do not infer age, language, style, or any other fields. \"\n"
        "                    \"If unclear, return empty strings.\"\n"
        "                ),\n"
        "            },\n"
        "            {\"role\": \"user\", \"content\": json.dumps({\"entries\": entries}, ensure_ascii=False)},\n"
        "        ]\n"
        "        try:\n"
        "            from agent.auxiliary_client import get_text_auxiliary_client, _get_task_timeout\n"
        "\n"
        "            aux_client, aux_model = get_text_auxiliary_client(\"user_profile_index\")\n"
        "            request_client = aux_client or self._ensure_primary_openai_client(reason=\"user_profile_index\")\n"
        "            request_model = aux_model or self.model\n"
        "            response = self._side_chat_completion(\n"
        "                reason=\"user_profile_index\",\n"
        "                client=request_client,\n"
        "                timeout=_get_task_timeout(\"user_profile_index\"),\n"
        "                model=request_model,\n"
        "                messages=messages,\n"
        "                temperature=0,\n"
        "                **self._max_tokens_param(512),\n"
        "            )\n"
        "            content = \"\"\n"
        "            if hasattr(response, \"choices\") and response.choices:\n"
        "                content = str(getattr(response.choices[0].message, \"content\", \"\") or \"\")\n"
        "            payload = self._extract_json_object(content)\n"
        "            normalized = {\n"
        "                \"preferred_user_name\": str(payload.get(\"preferred_user_name\") or \"\").strip(),\n"
        "                \"assistant_name\": str(payload.get(\"assistant_name\") or \"\").strip(),\n"
        "            }\n"
        "            # Fail closed: do not erase an existing compiled index when the\n"
        "            # model returns nothing usable for an otherwise populated profile.\n"
        "            if not any(normalized.values()):\n"
        "                return\n"
        "            self._memory_store.save_user_profile_index(normalized)\n"
        "        except Exception:\n"
        "            pass\n"
    )
    if (
        "self._memory_store._derive_user_profile_index_from_entries(entries)" not in text
        and old_compile in text
    ):
        text = _replace_once(text, old_compile, deterministic_index_impl, label="run_agent deterministic user-profile index", path=path)
        applied.append("run_agent:deterministic_user_profile_index")

    upstream_interrupted_sync_guard = (
        "def _sync_external_memory_for_turn(" in text
        and "Interrupted turns are skipped entirely (#15218)" in text
        and "if interrupted:\n            return" in text
    )
    sync_guard = "if self._memory_manager and final_response and original_user_message and not interrupted:"
    if not upstream_interrupted_sync_guard and sync_guard not in text:
        old_sync = (
            "        if self._memory_manager and final_response and original_user_message:\n"
            "            try:\n"
            "                self._memory_manager.sync_all(original_user_message, final_response)\n"
            "                self._memory_manager.queue_prefetch_all(original_user_message)\n"
            "            except Exception:\n"
            "                pass\n"
        )
        new_sync = (
            "        if self._memory_manager and final_response and original_user_message and not interrupted:\n"
            "            try:\n"
            "                self._memory_manager.sync_all(original_user_message, final_response)\n"
            "                self._memory_manager.queue_prefetch_all(original_user_message)\n"
            "            except Exception:\n"
            "                pass\n"
        )
        text = _replace_once(text, old_sync, new_sync, label="run_agent interrupted transcript hygiene", path=path)
        applied.append("run_agent:skip_interrupted_transcript_sync")

    background_origin = '                    review_agent._brainstack_memory_write_origin = "background_review"\n'
    native_background_origin = 'review_agent._memory_write_origin = "background_review"'
    if background_origin not in text and native_background_origin not in text:
        old_review_setup = (
            "                    review_agent._memory_store = self._memory_store\n"
            "                    review_agent._memory_enabled = self._memory_enabled\n"
            "                    review_agent._user_profile_enabled = self._user_profile_enabled\n"
            "                    review_agent._memory_nudge_interval = 0\n"
            "                    review_agent._skill_nudge_interval = 0\n"
        )
        new_review_setup = (
            "                    review_agent._memory_store = self._memory_store\n"
            "                    review_agent._memory_enabled = self._memory_enabled\n"
            "                    review_agent._user_profile_enabled = self._user_profile_enabled\n"
            "                    review_agent._brainstack_memory_write_origin = \"background_review\"\n"
            "                    review_agent._memory_nudge_interval = 0\n"
            "                    review_agent._skill_nudge_interval = 0\n"
        )
        text = _replace_once(
            text,
            old_review_setup,
            new_review_setup,
            label="run_agent background-review write origin tag",
            path=path,
        )
        applied.append("run_agent:background_review_write_origin")

    metadata_bridge_impl = (
        "                    memory_write_metadata = None\n"
        "                    write_origin = str(getattr(self, \"_brainstack_memory_write_origin\", \"\") or \"\").strip()\n"
        "                    if write_origin:\n"
        "                        memory_write_metadata = {\"write_origin\": write_origin}\n"
        "                    self._memory_manager.on_memory_write(\n"
        "                        function_args.get(\"action\", \"\"),\n"
        "                        target,\n"
        "                        function_args.get(\"content\", \"\"),\n"
        "                        metadata=memory_write_metadata,\n"
        "                    )\n"
    )
    if metadata_bridge_impl not in text:
        old_bridge = (
            "                    self._memory_manager.on_memory_write(\n"
            "                        function_args.get(\"action\", \"\"),\n"
            "                        target,\n"
            "                        function_args.get(\"content\", \"\"),\n"
            "                    )\n"
        )
        text = text.replace(old_bridge, metadata_bridge_impl, 2)
        if metadata_bridge_impl in text:
            applied.append("run_agent:memory_write_metadata_bridge")

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _patch_deferred_tool_loader_contract(path: Path, dry_run: bool) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []

    if '"brainstack_remember"' not in text:
        text = _replace_once(
            text,
            '    "memory": ("memory",),\n',
            '    "memory": ("memory", "brainstack_recall", "brainstack_inspect", "brainstack_remember", "brainstack_supersede"),\n',
            label="deferred memory bundle explicit Brainstack tools",
            path=path,
        )
        applied.append("deferred_tools:memory_bundle_explicit_brainstack_tools")

    if '"memory.write": ("memory",),' not in text:
        text = _replace_once(
            text,
            '    "memory.recall": ("memory",),\n',
            '    "memory.recall": ("memory",),\n'
            '    "memory.write": ("memory",),\n',
            label="deferred memory write capability catalog",
            path=path,
        )
        applied.append("deferred_tools:memory_write_capability")

    if "load memory.write before saying it was remembered" not in text:
        text = _replace_once(
            text,
            "            \"is unavailable unless CapabilityManifest marks it unavailable.\"\n"
            "        ),\n",
            "            \"is unavailable unless CapabilityManifest marks it unavailable. \"\n"
            "            \"For any user request to remember, save, store, or update memory in any language, \"\n"
            "            \"load memory.write before saying it was remembered.\"\n"
            "        ),\n",
            label="deferred catalog memory-write instruction",
            path=path,
        )
        applied.append("deferred_tools:memory_write_instruction")

    if '"memory.write": "Write explicit Brainstack/Hermes memory",' not in text:
        text = _replace_once(
            text,
            '        "memory.recall": "Recall Brainstack/Hermes memory",\n',
            '        "memory.recall": "Recall Brainstack/Hermes memory",\n'
            '        "memory.write": "Write explicit Brainstack/Hermes memory",\n',
            label="deferred catalog memory-write label",
            path=path,
        )
        applied.append("deferred_tools:memory_write_label")

    if "Commit explicit user-provided facts, preferences, references, or corrections" not in text:
        text = _replace_once(
            text,
            "    return {\n"
            '        "filesystem.search_read": "List, find, open, and inspect local/project files available to Hermes.",\n',
            "    return {\n"
            '        "memory.write": "Commit explicit user-provided facts, preferences, references, or corrections through the configured memory write contract.",\n'
            '        "filesystem.search_read": "List, find, open, and inspect local/project files available to Hermes.",\n',
            label="deferred catalog memory-write summary",
            path=path,
        )
        applied.append("deferred_tools:memory_write_summary")

    old_selection = (
        "    selected_names = set(requested_tools)\n"
        "    for bundle_id in requested_bundles:\n"
        "        selected_names.update(BUNDLE_TO_TOOLS.get(bundle_id, ()))\n"
    )
    new_selection = (
        "    selected_names: set[str] = set()\n"
        "    for requested_tool in requested_tools:\n"
        "        # Models sometimes put bundle/capability ids in tool_names after reading\n"
        "        # the compact catalog. Treat those as schema aliases, not missing tools.\n"
        "        if requested_tool in BUNDLE_TO_TOOLS:\n"
        "            selected_names.update(BUNDLE_TO_TOOLS.get(requested_tool, ()))\n"
        "            requested_bundles += (requested_tool,)\n"
        "            continue\n"
        "        if requested_tool in CAPABILITY_TO_BUNDLES:\n"
        "            bundles = CAPABILITY_TO_BUNDLES.get(requested_tool, ())\n"
        "            requested_bundles += tuple(bundles)\n"
        "            for bundle_id in bundles:\n"
        "                selected_names.update(BUNDLE_TO_TOOLS.get(bundle_id, ()))\n"
        "            continue\n"
        "        selected_names.add(requested_tool)\n"
        "    for bundle_id in requested_bundles:\n"
        "        selected_names.update(BUNDLE_TO_TOOLS.get(bundle_id, ()))\n"
    )
    if "Treat those as schema aliases, not missing tools." not in text:
        text = _replace_once(
            text,
            old_selection,
            new_selection,
            label="deferred tool bundle/capability alias expansion",
            path=path,
        )
        applied.append("deferred_tools:alias_tool_names")

    continuation_anchor = (
        '            "must_not_answer_from_memory_only": True,\n'
        '            "capability_preservation": {"capability_shrunk": False},\n'
    )
    continuation_replacement = (
        '            "must_not_answer_from_memory_only": True,\n'
        '            "next_step_instruction": (\n'
        '                "Continue the original task using one of loaded_tools exactly. "\n'
        '                "Do not answer that a requested bundle/capability alias is unavailable "\n'
        '                "when a concrete loaded tool is present."\n'
        "            ),\n"
        '            "capability_preservation": {"capability_shrunk": False},\n'
    )
    if '"next_step_instruction":' not in text:
        text = _replace_once(
            text,
            continuation_anchor,
            continuation_replacement,
            label="deferred tool continuation instruction",
            path=path,
        )
        applied.append("deferred_tools:continuation_instruction")

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _patch_run_agent_deferred_tool_continuation(path: Path, dry_run: bool) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []
    if "hermes_deferred_tools" not in text and "LOAD_TOOLS_NAME" not in text:
        return []

    if "    BUNDLE_TO_TOOLS,\n" not in text:
        text = _replace_once(
            text,
            "from hermes_deferred_tools import (\n    LOAD_TOOLS_NAME,\n",
            "from hermes_deferred_tools import (\n    BUNDLE_TO_TOOLS,\n    LOAD_TOOLS_NAME,\n",
            label="run_agent deferred tool alias import",
            path=path,
        )
        applied.append("run_agent:deferred_tool_alias_import")

    if "self._deferred_tool_continuation" not in text:
        text = _replace_once(
            text,
            "        self._deferred_loaded_tool_names: set[str] = set()\n"
            "        self._tool_loader_trace: Dict[str, Any] = {\n",
            "        self._deferred_loaded_tool_names: set[str] = set()\n"
            "        self._deferred_tool_continuation: Optional[Dict[str, Any]] = None\n"
            "        self._deferred_tool_continuation_retry_count = 0\n"
            "        self._tool_loader_trace: Dict[str, Any] = {\n",
            label="run_agent deferred tool continuation state",
            path=path,
        )
        applied.append("run_agent:deferred_tool_continuation_state")

    if "valid_alias_targets = [name for name in alias_tools if name in self.valid_tool_names]" not in text:
        text = _replace_once(
            text,
            "        if matches:\n"
            "            return matches[0]\n"
            "\n"
            "        return None\n",
            "        if matches:\n"
            "            return matches[0]\n"
            "\n"
            "        if self.deferred_tool_schema_mode:\n"
            "            alias_tools = BUNDLE_TO_TOOLS.get(normalized) or BUNDLE_TO_TOOLS.get(tool_name)\n"
            "            if alias_tools:\n"
            "                valid_alias_targets = [name for name in alias_tools if name in self.valid_tool_names]\n"
            "                if len(valid_alias_targets) == 1:\n"
            "                    return valid_alias_targets[0]\n"
            "\n"
            "        return None\n",
            label="run_agent deferred tool alias repair",
            path=path,
        )
        applied.append("run_agent:deferred_tool_alias_repair")

    if 'self._deferred_tool_continuation = dict(result.get("continuation") or {})' not in text:
        text = _replace_once(
            text,
            '        if loaded_names:\n'
            '            self._tool_loader_trace["tool_load_recall_pass"] = True\n'
            "        return json.dumps(result, ensure_ascii=False)\n",
            '        if loaded_names:\n'
            '            self._tool_loader_trace["tool_load_recall_pass"] = True\n'
            '            self._deferred_tool_continuation = dict(result.get("continuation") or {})\n'
            "            self._deferred_tool_continuation_retry_count = 0\n"
            "        return json.dumps(result, ensure_ascii=False)\n",
            label="run_agent deferred tool continuation capture",
            path=path,
        )
        applied.append("run_agent:deferred_tool_continuation_capture")

    helper_block = (
        "    def _mark_deferred_loaded_tool_used(self, function_name: str) -> None:\n"
        "        if function_name and function_name in self._deferred_loaded_tool_names:\n"
        "            self._deferred_tool_continuation = None\n"
        "            self._deferred_tool_continuation_retry_count = 0\n"
        "\n"
        "    def _deferred_tool_final_guard_nudge(self, final_response: str) -> str | None:\n"
        "        if not self.deferred_tool_schema_mode or not self._deferred_tool_continuation:\n"
        "            return None\n"
        "        if not self._has_content_after_think_block(final_response):\n"
        "            return None\n"
        "        loaded_tools = [\n"
        "            str(name)\n"
        "            for name in (self._deferred_tool_continuation.get(\"loaded_tools\") or ())\n"
        "            if str(name)\n"
        "        ]\n"
        "        if not loaded_tools:\n"
        "            return None\n"
        "        if self._deferred_tool_continuation_retry_count >= 2:\n"
        "            return None\n"
        "        task = str(self._deferred_tool_continuation.get(\"original_task_summary\") or \"the original task\")\n"
        "        return (\n"
        "            \"Runtime guard: you loaded tool schemas for this task but attempted a final answer \"\n"
        "            \"before using the loaded tool. Continue the original task now. \"\n"
        "            f\"Original task: {task}. \"\n"
        "            f\"Loaded tool names available now: {', '.join(sorted(loaded_tools))}. \"\n"
        "            \"Call one of those tool names exactly. If the tool requires approval, call it so the \"\n"
        "            \"runtime approval service can request approval. Do not claim the capability is \"\n"
        "            \"unavailable merely because a bundle/capability alias was not itself a tool name.\"\n"
        "        )\n"
        "\n"
    )
    if "def _mark_deferred_loaded_tool_used" not in text:
        text = _replace_once(
            text,
            "        return json.dumps(result, ensure_ascii=False)\n"
            "\n"
            "    def _invoke_tool(",
            "        return json.dumps(result, ensure_ascii=False)\n"
            "\n"
            + helper_block
            + "    def _invoke_tool(",
            label="run_agent deferred tool final guard helpers",
            path=path,
        )
        applied.append("run_agent:deferred_tool_final_guard_helpers")

    if "self._mark_deferred_loaded_tool_used(function_name)\n        if function_name == \"todo\":" not in text:
        text = _replace_once(
            text,
            "        if function_name == LOAD_TOOLS_NAME:\n"
            "            return self._handle_deferred_tool_load(function_args)\n"
            "        if function_name == \"todo\":\n",
            "        if function_name == LOAD_TOOLS_NAME:\n"
            "            return self._handle_deferred_tool_load(function_args)\n"
            "        self._mark_deferred_loaded_tool_used(function_name)\n"
            "        if function_name == \"todo\":\n",
            label="run_agent deferred loaded tool used marker",
            path=path,
        )
        applied.append("run_agent:deferred_loaded_tool_used_marker")

    if "_deferred_tool_guard_nudge = self._deferred_tool_final_guard_nudge(final_response)" not in text:
        text = _replace_once(
            text,
            "                    final_response = assistant_message.content or \"\"\n"
            "\n"
            "                    # Fix: unmute output when entering the no-tool-call branch\n",
            "                    final_response = assistant_message.content or \"\"\n"
            "\n"
            "                    _deferred_tool_guard_nudge = self._deferred_tool_final_guard_nudge(final_response)\n"
            "                    if _deferred_tool_guard_nudge:\n"
            "                        self._deferred_tool_continuation_retry_count += 1\n"
            "                        guard_msg = self._build_assistant_message(assistant_message, finish_reason)\n"
            "                        messages.append(guard_msg)\n"
            "                        messages.append({\"role\": \"user\", \"content\": _deferred_tool_guard_nudge})\n"
            "                        self._tool_loader_trace[\"final_answer_blocked_before_tool\"] = True\n"
            "                        self._tool_loader_trace[\n"
            "                            \"final_answer_block_reason\"\n"
            "                        ] = \"DECLARED_EXTERNAL_CAPABILITY_NOT_USED\"\n"
            "                        continue\n"
            "\n"
            "                    # Fix: unmute output when entering the no-tool-call branch\n",
            label="run_agent deferred final answer guard",
            path=path,
        )
        applied.append("run_agent:deferred_final_answer_guard")

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _patch_run_agent_memory_output_validation_seam(path: Path, dry_run: bool) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []

    if "def _validate_external_memory_final_response(" not in text:
        old_block = (
            "    def _sync_external_memory_for_turn(\n"
            "        self,\n"
            "        *,\n"
            "        original_user_message: Any,\n"
            "        final_response: Any,\n"
            "        interrupted: bool,\n"
            "    ) -> None:\n"
        )
        helper_block = (
            "    def _validate_external_memory_final_response(\n"
            "        self,\n"
            "        *,\n"
            "        original_user_message: Any,\n"
            "        final_response: Any,\n"
            "        interrupted: bool,\n"
            "    ) -> Any:\n"
            "        if interrupted or not (self._memory_manager and final_response and original_user_message):\n"
            "            return final_response\n"
            "        try:\n"
            "            validator = getattr(self._memory_manager, \"validate_assistant_output_all\", None)\n"
            "            if not callable(validator):\n"
            "                return final_response\n"
            "            result = validator(\n"
            "                final_response,\n"
            "                user_content=original_user_message,\n"
            "                session_id=self.session_id or \"\",\n"
            "            )\n"
            "            self._last_memory_output_validation = result if isinstance(result, dict) else None\n"
            "            if isinstance(result, dict) and isinstance(result.get(\"content\"), str):\n"
            "                return result[\"content\"]\n"
            "        except Exception:\n"
            "            logger.warning(\"external memory final output validation failed\", exc_info=True)\n"
            "        return final_response\n"
            "\n"
            "    def _replace_last_assistant_response_content(\n"
            "        self,\n"
            "        messages: Any,\n"
            "        conversation_history: Any,\n"
            "        final_response: Any,\n"
            "    ) -> None:\n"
            "        for collection in (messages, conversation_history):\n"
            "            if not isinstance(collection, list):\n"
            "                continue\n"
            "            for msg in reversed(collection):\n"
            "                if isinstance(msg, dict) and msg.get(\"role\") == \"assistant\" and \"content\" in msg:\n"
            "                    msg[\"content\"] = final_response\n"
            "                    break\n"
            "\n"
            "    def _record_external_memory_validation_delivery(self, delivered_content: Any) -> None:\n"
            "        result = getattr(self, \"_last_memory_output_validation\", None)\n"
            "        if not isinstance(result, dict) or not self._memory_manager:\n"
            "            return\n"
            "        try:\n"
            "            recorder = getattr(self._memory_manager, \"record_output_validation_delivery_all\", None)\n"
            "            if callable(recorder):\n"
            "                recorder(result, delivered_content=str(delivered_content or \"\"))\n"
            "        except Exception:\n"
            "            logger.debug(\"external memory validation delivery record failed\", exc_info=True)\n"
            "\n"
        )
        text = _replace_once(
            text,
            old_block,
            helper_block + old_block,
            label="run_agent memory output validation helpers",
            path=path,
        )
        applied.append("run_agent:memory_output_validation_helpers")

    direct_anchor = (
        "                final_response = _rendered_answer.text\n"
        "                messages.append({\"role\": \"assistant\", \"content\": final_response})\n"
    )
    direct_replacement = (
        "                final_response = _rendered_answer.text\n"
        "                messages.append({\"role\": \"assistant\", \"content\": final_response})\n"
        "                final_response = self._validate_external_memory_final_response(\n"
        "                    original_user_message=original_user_message,\n"
        "                    final_response=final_response,\n"
        "                    interrupted=False,\n"
        "                )\n"
        "                self._replace_last_assistant_response_content(messages, conversation_history, final_response)\n"
    )
    if "original_user_message=original_user_message,\n                    final_response=final_response,\n                    interrupted=False,\n                )\n                self._replace_last_assistant_response_content(messages, conversation_history, final_response)" not in text:
        if direct_anchor in text:
            text = text.replace(direct_anchor, direct_replacement, 1)
            applied.append("run_agent:direct_renderer_memory_output_validation")
        else:
            applied.append("run_agent:direct_renderer_memory_output_validation_absent")

    normal_anchor = (
        "        # Persist session to both JSON log and SQLite\n"
        "        self._persist_session(messages, conversation_history)\n"
    )
    normal_replacement = (
        "        if final_response and not interrupted:\n"
        "            final_response = self._validate_external_memory_final_response(\n"
        "                original_user_message=original_user_message,\n"
        "                final_response=final_response,\n"
        "                interrupted=interrupted,\n"
        "            )\n"
        "            self._replace_last_assistant_response_content(messages, conversation_history, final_response)\n"
        "\n"
        "        # Persist session to both JSON log and SQLite\n"
        "        self._persist_session(messages, conversation_history)\n"
    )
    normal_cleanup_anchor = (
        "        # Persist session to both JSON log and SQLite only after private retry\n"
        "        # scaffolding has been removed. Otherwise a later user \"continue\" turn\n"
        "        # can replay assistant(\"(empty)\") / recovery nudges and fall into the\n"
        "        # same empty-response loop again.\n"
        "        self._drop_trailing_empty_response_scaffolding(messages)\n"
        "        self._persist_session(messages, conversation_history)\n"
    )
    normal_cleanup_replacement = (
        "        if final_response and not interrupted:\n"
        "            final_response = self._validate_external_memory_final_response(\n"
        "                original_user_message=original_user_message,\n"
        "                final_response=final_response,\n"
        "                interrupted=interrupted,\n"
        "            )\n"
        "            self._replace_last_assistant_response_content(messages, conversation_history, final_response)\n"
        "\n"
        "        # Persist session to both JSON log and SQLite only after private retry\n"
        "        # scaffolding has been removed. Otherwise a later user \"continue\" turn\n"
        "        # can replay assistant(\"(empty)\") / recovery nudges and fall into the\n"
        "        # same empty-response loop again.\n"
        "        self._drop_trailing_empty_response_scaffolding(messages)\n"
        "        self._persist_session(messages, conversation_history)\n"
    )
    if "        if final_response and not interrupted:\n            final_response = self._validate_external_memory_final_response(\n                original_user_message=original_user_message,\n                final_response=final_response,\n                interrupted=interrupted,\n            )" not in text:
        if normal_anchor in text:
            text = text.replace(normal_anchor, normal_replacement, 1)
        else:
            text = _replace_once(
                text,
                normal_cleanup_anchor,
                normal_cleanup_replacement,
                label="run_agent normal memory output validation",
                path=path,
            )
        applied.append("run_agent:normal_memory_output_validation")

    delivery_anchor = (
        "        if final_response and not interrupted:\n"
        "            try:\n"
        "                from hermes_cli.plugins import invoke_hook as _invoke_hook\n"
    )
    delivery_replacement = (
        "        if final_response and not interrupted:\n"
        "            self._record_external_memory_validation_delivery(final_response)\n"
        "            try:\n"
        "                from hermes_cli.plugins import invoke_hook as _invoke_hook\n"
    )
    if "self._record_external_memory_validation_delivery(final_response)" not in text:
        text = _replace_once(
            text,
            delivery_anchor,
            delivery_replacement,
            label="run_agent memory output validation delivery record",
            path=path,
        )
        applied.append("run_agent:memory_output_validation_delivery_record")

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _patch_run_agent_terminal_final_guard_seam(path: Path, dry_run: bool) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []

    if "def _terminal_tool_final_guard_nudge(" not in text:
        helper_anchor = "    def _replace_last_assistant_response_content(\n"
        if helper_anchor not in text:
            helper_anchor = (
                "    def _sync_external_memory_for_turn(\n"
                "        self,\n"
                "        *,\n"
                "        original_user_message: Any,\n"
                "        final_response: Any,\n"
                "        interrupted: bool,\n"
                "    ) -> None:\n"
            )
        helper_block = (
            "    @staticmethod\n"
            "    def _terminal_guard_text(value: Any) -> str:\n"
            "        if isinstance(value, str):\n"
            "            return value\n"
            "        try:\n"
            "            return _summarize_user_message_for_log(value)\n"
            "        except Exception:\n"
            "            return str(value or \"\")\n"
            "\n"
            "    @staticmethod\n"
            "    def _terminal_guard_url_literals(text: str) -> set[str]:\n"
            "        if not text:\n"
            "            return set()\n"
            "        return {\n"
            "            match.rstrip(\".,);]\\\"'\")\n"
            "            for match in re.findall(r\"https?://[^\\s<>()\\\"']+\", text)\n"
            "            if match\n"
            "        }\n"
            "\n"
            "    def _terminal_guard_latest_user_text(self, messages: Any) -> str:\n"
            "        if not isinstance(messages, list):\n"
            "            return \"\"\n"
            "        for msg in reversed(messages):\n"
            "            if not isinstance(msg, dict) or msg.get(\"role\") != \"user\":\n"
            "                continue\n"
            "            text = self._terminal_guard_text(msg.get(\"content\") or \"\")\n"
            "            if text.startswith(\"Runtime guard:\"):\n"
            "                continue\n"
            "            return text\n"
            "        return \"\"\n"
            "\n"
            "    @staticmethod\n"
            "    def _terminal_guard_tool_name(tool_call: Any) -> str:\n"
            "        if isinstance(tool_call, dict):\n"
            "            fn = tool_call.get(\"function\")\n"
            "            if isinstance(fn, dict):\n"
            "                return str(fn.get(\"name\") or \"\")\n"
            "            return str(tool_call.get(\"name\") or \"\")\n"
            "        fn = getattr(tool_call, \"function\", None)\n"
            "        return str(getattr(fn, \"name\", \"\") or getattr(tool_call, \"name\", \"\") or \"\")\n"
            "\n"
            "    @staticmethod\n"
            "    def _terminal_guard_tool_call_id(tool_call: Any) -> str:\n"
            "        if isinstance(tool_call, dict):\n"
            "            return str(tool_call.get(\"id\") or \"\")\n"
            "        return str(getattr(tool_call, \"id\", \"\") or \"\")\n"
            "\n"
            "    def _terminal_tool_result_payloads(self, messages: Any) -> list[dict[str, Any]]:\n"
            "        if not isinstance(messages, list):\n"
            "            return []\n"
            "        terminal_call_ids: set[str] = set()\n"
            "        for msg in messages:\n"
            "            if not isinstance(msg, dict) or msg.get(\"role\") != \"assistant\":\n"
            "                continue\n"
            "            for tool_call in msg.get(\"tool_calls\") or []:\n"
            "                if self._terminal_guard_tool_name(tool_call) == \"terminal\":\n"
            "                    call_id = self._terminal_guard_tool_call_id(tool_call)\n"
            "                    if call_id:\n"
            "                        terminal_call_ids.add(call_id)\n"
            "        if not terminal_call_ids:\n"
            "            return []\n"
            "        payloads: list[dict[str, Any]] = []\n"
            "        for msg in messages:\n"
            "            if not isinstance(msg, dict) or msg.get(\"role\") != \"tool\":\n"
            "                continue\n"
            "            if str(msg.get(\"tool_call_id\") or \"\") not in terminal_call_ids:\n"
            "                continue\n"
            "            content = msg.get(\"content\") or \"\"\n"
            "            parsed: Any = None\n"
            "            if isinstance(content, str):\n"
            "                try:\n"
            "                    parsed = json.loads(content)\n"
            "                except Exception:\n"
            "                    parsed = {\"output\": content}\n"
            "            elif isinstance(content, dict):\n"
            "                parsed = content\n"
            "            if isinstance(parsed, dict):\n"
            "                payloads.append(parsed)\n"
            "        return payloads\n"
            "\n"
            "    @staticmethod\n"
            "    def _extract_terminal_command_request(user_text: str) -> str:\n"
            "        if not user_text:\n"
            "            return \"\"\n"
            "        fenced = re.search(r\"```(?:bash|sh|shell)?\\\\s*\\\\n(?P<cmd>[^`]+?)\\\\n?```\", user_text, flags=re.IGNORECASE)\n"
            "        if fenced:\n"
            "            return fenced.group(\"cmd\").strip()\n"
            "        command_names = (\n"
            "            \"pwd\", \"ls\", \"cat\", \"grep\", \"rg\", \"find\", \"python\", \"python3\", \"node\",\n"
            "            \"npm\", \"pnpm\", \"yarn\", \"git\", \"rm\", \"mkdir\", \"touch\", \"cp\", \"mv\",\n"
            "            \"sed\", \"awk\", \"curl\", \"wget\", \"docker\", \"pytest\", \"uv\", \"pip\",\n"
            "            \"bash\", \"sh\",\n"
            "        )\n"
            "        command_re = re.compile(\n"
            "            r\"(?:^|[:\\\\n])\\\\s*(?P<cmd>(?:\" + \"|\".join(re.escape(name) for name in command_names) + r\")\\\\b[^\\\\n]*)\",\n"
            "            flags=re.IGNORECASE,\n"
            "        )\n"
            "        match = command_re.search(user_text)\n"
            "        if not match:\n"
            "            return \"\"\n"
            "        return match.group(\"cmd\").strip()\n"
            "\n"
            "    def _terminal_url_fetch_block_message(self, function_name: str, function_args: dict[str, Any], messages: Any) -> str | None:\n"
            "        if function_name != \"terminal\" or not isinstance(function_args, dict):\n"
            "            return None\n"
            "        command = str(function_args.get(\"command\") or \"\")\n"
            "        command_urls = self._terminal_guard_url_literals(command)\n"
            "        if not command_urls:\n"
            "            return None\n"
            "        user_text = self._terminal_guard_latest_user_text(messages)\n"
            "        if not user_text or self._extract_terminal_command_request(user_text):\n"
            "            return None\n"
            "        user_urls = self._terminal_guard_url_literals(user_text)\n"
            "        if not (command_urls & user_urls):\n"
            "            return None\n"
            "        return (\n"
            "            \"Implicit terminal URL fetch blocked: the user asked to inspect a URL but did not request shell command execution. \"\n"
            "            \"Use configured web/browser tools for URL inspection. If web/browser capability is unavailable, report that diagnostic without guessing. \"\n"
            "            \"Terminal remains available when the user explicitly asks to run a shell command.\"\n"
            "        )\n"
            "\n"
            "    @staticmethod\n"
            "    def _terminal_success_claim_present(response_text: str, command: str) -> bool:\n"
            "        lower = response_text.lower()\n"
            "        if any(marker in lower for marker in (\"executed successfully\", \"deleted\")):\n"
            "            return True\n"
            "        if command.strip().split(\" \", 1)[0] == \"pwd\":\n"
            "            return bool(re.search(r\"(?m)^\\\\s*/[^\\\\s]+\", response_text.strip()))\n"
            "        return False\n"
            "\n"
            "    def _terminal_tool_final_guard_nudge(\n"
            "        self,\n"
            "        *,\n"
            "        original_user_message: Any,\n"
            "        final_response: Any,\n"
            "        messages: Any,\n"
            "    ) -> str | None:\n"
            "        user_text = self._terminal_guard_text(original_user_message)\n"
            "        command = self._extract_terminal_command_request(user_text)\n"
            "        if not command:\n"
            "            return None\n"
            "        if self._terminal_tool_result_payloads(messages):\n"
            "            return None\n"
            "        response_text = self._terminal_guard_text(final_response)\n"
            "        guard_key = hashlib.sha256(f\"{self.session_id or ''}:{user_text}\".encode(\"utf-8\", \"ignore\")).hexdigest()\n"
            "        if getattr(self, \"_terminal_tool_guard_key\", \"\") != guard_key:\n"
            "            self._terminal_tool_guard_key = guard_key\n"
            "            self._terminal_tool_guard_retry_count = 0\n"
            "        if getattr(self, \"_terminal_tool_guard_retry_count\", 0) >= 2:\n"
            "            return None\n"
            "        return (\n"
            "            \"Runtime guard: the user requested shell/terminal command execution, \"\n"
            "            \"but the final answer arrived without a terminal tool result in this turn. \"\n"
            "            f\"Continue the original task by calling the terminal tool for this command: {command!r}. \"\n"
            "            \"If approval is required or the terminal is unavailable, report that exact runtime result. \"\n"
            "            \"Do not answer from memory.\"\n"
            "        )\n"
            "\n"
            "    def _validate_terminal_final_response(\n"
            "        self,\n"
            "        *,\n"
            "        original_user_message: Any,\n"
            "        final_response: Any,\n"
            "        messages: Any,\n"
            "        interrupted: bool,\n"
            "    ) -> Any:\n"
            "        if interrupted or not (final_response and original_user_message):\n"
            "            return final_response\n"
            "        user_text = self._terminal_guard_text(original_user_message)\n"
            "        command = self._extract_terminal_command_request(user_text)\n"
            "        if not command:\n"
            "            return final_response\n"
            "        terminal_payloads = self._terminal_tool_result_payloads(messages)\n"
            "        response_text = self._terminal_guard_text(final_response)\n"
            "        if terminal_payloads:\n"
            "            blocked = [\n"
            "                payload for payload in terminal_payloads\n"
            "                if str(payload.get(\"status\") or \"\").lower() in {\"approval_required\", \"blocked\"}\n"
            "                or str(payload.get(\"exit_code\") or \"\") == \"-1\"\n"
            "            ]\n"
            "            if blocked and self._terminal_success_claim_present(response_text, command):\n"
            "                output = str(blocked[-1].get(\"output\") or blocked[-1].get(\"error\") or \"Terminal command did not execute.\")\n"
            "                return output.strip()\n"
            "            return final_response\n"
            "        return (\n"
            "            \"I cannot verify that the command ran: this turn has no terminal tool result. \"\n"
            "            \"I will not claim successful execution.\"\n"
            "        )\n"
            "\n"
        )
        text = _replace_once(
            text,
            helper_anchor,
            helper_block + helper_anchor,
            label="run_agent terminal final guard helpers",
            path=path,
        )
        applied.append("run_agent:terminal_final_guard_helpers")

    if "def _terminal_url_fetch_block_message(" not in text:
        helper_anchor = "    @staticmethod\n    def _terminal_success_claim_present(response_text: str, command: str) -> bool:\n"
        helper_block = (
            "    @staticmethod\n"
            "    def _terminal_guard_url_literals(text: str) -> set[str]:\n"
            "        if not text:\n"
            "            return set()\n"
            "        return {\n"
            "            match.rstrip(\".,);]\\\"'\")\n"
            "            for match in re.findall(r\"https?://[^\\s<>()\\\"']+\", text)\n"
            "            if match\n"
            "        }\n"
            "\n"
            "    def _terminal_guard_latest_user_text(self, messages: Any) -> str:\n"
            "        if not isinstance(messages, list):\n"
            "            return \"\"\n"
            "        for msg in reversed(messages):\n"
            "            if not isinstance(msg, dict) or msg.get(\"role\") != \"user\":\n"
            "                continue\n"
            "            text = self._terminal_guard_text(msg.get(\"content\") or \"\")\n"
            "            if text.startswith(\"Runtime guard:\"):\n"
            "                continue\n"
            "            return text\n"
            "        return \"\"\n"
            "\n"
            "    def _terminal_url_fetch_block_message(self, function_name: str, function_args: dict[str, Any], messages: Any) -> str | None:\n"
            "        if function_name != \"terminal\" or not isinstance(function_args, dict):\n"
            "            return None\n"
            "        command = str(function_args.get(\"command\") or \"\")\n"
            "        command_urls = self._terminal_guard_url_literals(command)\n"
            "        if not command_urls:\n"
            "            return None\n"
            "        user_text = self._terminal_guard_latest_user_text(messages)\n"
            "        if not user_text or self._extract_terminal_command_request(user_text):\n"
            "            return None\n"
            "        user_urls = self._terminal_guard_url_literals(user_text)\n"
            "        if not (command_urls & user_urls):\n"
            "            return None\n"
            "        return (\n"
            "            \"Implicit terminal URL fetch blocked: the user asked to inspect a URL but did not request shell command execution. \"\n"
            "            \"Use configured web/browser tools for URL inspection. If web/browser capability is unavailable, report that diagnostic without guessing. \"\n"
            "            \"Terminal remains available when the user explicitly asks to run a shell command.\"\n"
            "        )\n"
            "\n"
        )
        text = _replace_once(
            text,
            helper_anchor,
            helper_block + helper_anchor,
            label="run_agent terminal implicit URL fetch guard helpers",
            path=path,
        )
        applied.append("run_agent:terminal_url_fetch_guard_helpers")

    if (
        "but the final answer claimed a command result without a terminal tool result in this turn." in text
        or "if not self._terminal_success_claim_present(response_text, command):\n            return None" in text
    ):
        text = text.replace(
            "        response_text = self._terminal_guard_text(final_response)\n"
            "        if not self._terminal_success_claim_present(response_text, command):\n"
            "            return None\n"
            "        guard_key = hashlib.sha256(f\"{self.session_id or ''}:{user_text}\".encode(\"utf-8\", \"ignore\")).hexdigest()\n",
            "        response_text = self._terminal_guard_text(final_response)\n"
            "        guard_key = hashlib.sha256(f\"{self.session_id or ''}:{user_text}\".encode(\"utf-8\", \"ignore\")).hexdigest()\n",
        )
        text = text.replace(
            "            \"but the final answer claimed a command result without a terminal tool result in this turn. \"\n",
            "            \"but the final answer arrived without a terminal tool result in this turn. \"\n",
        )
        text = text.replace(
            "        if self._terminal_success_claim_present(response_text, command):\n"
            "            return (\n"
            "                \"I cannot verify that the command ran: this turn has no terminal tool result. \"\n"
            "                \"I will not claim successful execution.\"\n"
            "            )\n"
            "        return final_response\n",
            "        return (\n"
            "            \"I cannot verify that the command ran: this turn has no terminal tool result. \"\n"
            "            \"I will not claim successful execution.\"\n"
            "        )\n",
        )
        applied.append("run_agent:terminal_command_requires_tool_result")

    if "_terminal_url_fetch_block_message(function_name, function_args, messages)" not in text:
        concurrent_anchor = (
            "        if block_message is not None:\n"
            "            return json.dumps({\"error\": block_message}, ensure_ascii=False)\n"
        )
        concurrent_replacement = (
            "        if block_message is None:\n"
            "            try:\n"
            "                block_message = self._terminal_url_fetch_block_message(function_name, function_args, messages)\n"
            "            except Exception:\n"
            "                pass\n"
            "        if block_message is not None:\n"
            "            return json.dumps({\"error\": block_message}, ensure_ascii=False)\n"
        )
        text = _replace_once(
            text,
            concurrent_anchor,
            concurrent_replacement,
            label="run_agent concurrent terminal implicit URL fetch block",
            path=path,
        )
        applied.append("run_agent:terminal_url_fetch_guard_concurrent")

    if "_terminal_url_fetch_block_message(function_name, function_args, messages)" not in text.split("def _execute_tool_calls_sequential", 1)[-1]:
        sequential_anchor = (
            "            if _block_msg is not None:\n"
            "                # Tool blocked by plugin policy — skip counter resets.\n"
            "                # Execution is handled below in the tool dispatch chain.\n"
            "                pass\n"
            "            else:\n"
        )
        sequential_replacement = (
            "            if _block_msg is None:\n"
            "                try:\n"
            "                    _block_msg = self._terminal_url_fetch_block_message(function_name, function_args, messages)\n"
            "                except Exception:\n"
            "                    pass\n"
            "\n"
            "            if _block_msg is not None:\n"
            "                # Tool blocked by plugin policy or runtime boundary guard — skip counter resets.\n"
            "                # Execution is handled below in the tool dispatch chain.\n"
            "                pass\n"
            "            else:\n"
        )
        sequential_guardrail_anchor = (
            "            _guardrail_block_decision: ToolGuardrailDecision | None = None\n"
            "            if _block_msg is None:\n"
            "                guardrail_decision = self._tool_guardrails.before_call(function_name, function_args)\n"
        )
        sequential_guardrail_replacement = (
            "            if _block_msg is None:\n"
            "                try:\n"
            "                    _block_msg = self._terminal_url_fetch_block_message(function_name, function_args, messages)\n"
            "                except Exception:\n"
            "                    pass\n"
            "\n"
            "            _guardrail_block_decision: ToolGuardrailDecision | None = None\n"
            "            if _block_msg is None:\n"
            "                guardrail_decision = self._tool_guardrails.before_call(function_name, function_args)\n"
        )
        if sequential_anchor in text:
            text = text.replace(sequential_anchor, sequential_replacement, 1)
        else:
            text = _replace_once(
                text,
                sequential_guardrail_anchor,
                sequential_guardrail_replacement,
                label="run_agent sequential terminal implicit URL fetch block",
                path=path,
            )
        applied.append("run_agent:terminal_url_fetch_guard_sequential")

    if "_terminal_tool_guard_nudge = self._terminal_tool_final_guard_nudge(" not in text:
        nudge_anchor = (
            "                    # Fix: unmute output when entering the no-tool-call branch\n"
            "                    # so the user can see empty-response warnings and recovery\n"
        )
        nudge_block = (
            "                    _terminal_tool_guard_nudge = self._terminal_tool_final_guard_nudge(\n"
            "                        original_user_message=original_user_message,\n"
            "                        final_response=final_response,\n"
            "                        messages=messages,\n"
            "                    )\n"
            "                    if _terminal_tool_guard_nudge:\n"
            "                        self._terminal_tool_guard_retry_count = getattr(\n"
            "                            self, \"_terminal_tool_guard_retry_count\", 0\n"
            "                        ) + 1\n"
            "                        guard_msg = self._build_assistant_message(assistant_message, finish_reason)\n"
            "                        messages.append(guard_msg)\n"
            "                        messages.append({\"role\": \"user\", \"content\": _terminal_tool_guard_nudge})\n"
            "                        continue\n"
            "                    \n"
        )
        text = _replace_once(
            text,
            nudge_anchor,
            nudge_block + nudge_anchor,
            label="run_agent terminal no-final-before-tool nudge",
            path=path,
        )
        applied.append("run_agent:terminal_final_guard_nudge")

    if "final_response = self._validate_terminal_final_response(" not in text:
        validation_anchor = (
            "            final_response = self._validate_external_memory_final_response(\n"
            "                original_user_message=original_user_message,\n"
            "                final_response=final_response,\n"
            "                interrupted=interrupted,\n"
            "            )\n"
            "            self._replace_last_assistant_response_content(messages, conversation_history, final_response)\n"
        )
        validation_cleanup_anchor = (
            "        # Persist session to both JSON log and SQLite only after private retry\n"
            "        # scaffolding has been removed. Otherwise a later user \"continue\" turn\n"
            "        # can replay assistant(\"(empty)\") / recovery nudges and fall into the\n"
            "        # same empty-response loop again.\n"
            "        self._drop_trailing_empty_response_scaffolding(messages)\n"
            "        self._persist_session(messages, conversation_history)\n"
        )
        validation_replacement = (
            "            final_response = self._validate_external_memory_final_response(\n"
            "                original_user_message=original_user_message,\n"
            "                final_response=final_response,\n"
            "                interrupted=interrupted,\n"
            "            )\n"
            "            final_response = self._validate_terminal_final_response(\n"
            "                original_user_message=original_user_message,\n"
            "                final_response=final_response,\n"
            "                messages=messages,\n"
            "                interrupted=interrupted,\n"
            "            )\n"
            "            self._replace_last_assistant_response_content(messages, conversation_history, final_response)\n"
        )
        validation_cleanup_replacement = (
            "        if final_response and not interrupted:\n"
            "            final_response = self._validate_terminal_final_response(\n"
            "                original_user_message=original_user_message,\n"
            "                final_response=final_response,\n"
            "                messages=messages,\n"
            "                interrupted=interrupted,\n"
            "            )\n"
            "            self._replace_last_assistant_response_content(messages, conversation_history, final_response)\n"
            "\n"
            "        # Persist session to both JSON log and SQLite only after private retry\n"
            "        # scaffolding has been removed. Otherwise a later user \"continue\" turn\n"
            "        # can replay assistant(\"(empty)\") / recovery nudges and fall into the\n"
            "        # same empty-response loop again.\n"
            "        self._drop_trailing_empty_response_scaffolding(messages)\n"
            "        self._persist_session(messages, conversation_history)\n"
        )
        if validation_anchor in text:
            text = text.replace(validation_anchor, validation_replacement, 1)
        else:
            text = _replace_once(
                text,
                validation_cleanup_anchor,
                validation_cleanup_replacement,
                label="run_agent terminal final response validation",
                path=path,
            )
        applied.append("run_agent:terminal_final_response_validation")

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _patch_memory_answer_renderer_language(path: Path, dry_run: bool) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []
    old_render_signature = "def _render_text(answer_type: str, claim_style: str, answer_value: str) -> str:"
    if old_render_signature not in text and "def _render_text(answer_type: str, claim_style: str, answer_evidence" in text:
        return []

    if "import os\n" not in text:
        text = _replace_once(
            text,
            "from dataclasses import asdict, dataclass\n",
            "from dataclasses import asdict, dataclass\nimport os\n",
            label="memory renderer os import",
            path=path,
        )
        applied.append("memory_renderer:language_import")

    text, removed_language_helper = re.subn(
        r"\n\ndef _response_language\(\) -> str:\n(?:    .*\n)+?\n(?=def _render_text\(answer_type: str, claim_style: str, answer_value: str\) -> str:\n)",
        "\n\n",
        text,
        count=1,
    )
    if removed_language_helper:
        applied.append("memory_renderer:remove_response_language_helper")

    text, removed_localized_branch = re.subn(
        r"(def _render_text\(answer_type: str, claim_style: str, answer_value: str\) -> str:\n)"
        r"    if _response_language\(\) == \"hu\":\n"
        r"(?:        .*\n)+?\n"
        r"(?=    if claim_style == \"unsupported\":\n)",
        r"\1",
        text,
        count=1,
    )
    if removed_localized_branch:
        applied.append("memory_renderer:remove_localized_templates")

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _patch_terminal_tool_result_hygiene(path: Path, dry_run: bool) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []

    if '"output": message,' not in text:
        text = _replace_once(
            text,
            '                if approval.get("status") == "approval_required":\n'
            "                    return json.dumps({\n"
            '                        "output": "",\n'
            '                        "exit_code": -1,\n'
            '                        "error": approval.get("message", "Waiting for user approval"),\n',
            '                if approval.get("status") == "approval_required":\n'
            '                    message = approval.get("message", "Waiting for user approval")\n'
            "                    return json.dumps({\n"
            '                        "output": message,\n'
            '                        "exit_code": -1,\n'
            '                        "error": message,\n',
            label="terminal approval-required output hygiene",
            path=path,
        )
        applied.append("terminal_tool:approval_required_output_hygiene")

    if '"output": approval.get("message", fallback_msg),' not in text:
        text = _replace_once(
            text,
            "                return json.dumps({\n"
            '                    "output": "",\n'
            '                    "exit_code": -1,\n'
            '                    "error": approval.get("message", fallback_msg),\n'
            '                    "status": "blocked"\n'
            "                }, ensure_ascii=False)\n",
            "                return json.dumps({\n"
            '                    "output": approval.get("message", fallback_msg),\n'
            '                    "exit_code": -1,\n'
            '                    "error": approval.get("message", fallback_msg),\n'
            '                    "status": "blocked"\n'
            "                }, ensure_ascii=False)\n",
            label="terminal blocked output hygiene",
            path=path,
        )
        applied.append("terminal_tool:blocked_output_hygiene")

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _canonicalize_runtime_user_profile(config_path: Path, dry_run: bool) -> dict[str, Any]:
    runtime_root = config_path.parent
    user_path = runtime_root / "memories" / "USER.md"
    index_path = runtime_root / "memories" / "USER_PROFILE_INDEX.json"
    if not user_path.exists():
        return {"status": "skipped", "reason": "user_profile_missing", "path": str(user_path)}

    raw = user_path.read_text(encoding="utf-8")
    delimiter = "\n§\n"
    entries = [entry.strip() for entry in raw.split(delimiter) if entry.strip()]
    if not entries:
        return {"status": "no_entries", "path": str(user_path)}

    legacy_name_re = re.compile(r"^User's Discord name is (?P<handle>.+?) but should be addressed as (?P<name>.+)$")
    legacy_address_re = re.compile(r"^Address user as (?P<name>.+), not (?P<handle>.+)$")

    def _rehydrate_rule_pack(text: str) -> str:
        prefix = "Communication rules:"
        if not text.startswith(prefix):
            return text
        body = text[len(prefix):].strip()
        normalized_body = body.replace("\\n", "\n").strip()
        if not normalized_body:
            return text
        if "\n" in normalized_body:
            return prefix + "\n" + normalized_body
        body = normalized_body
        matches = list(re.finditer(r"(?<!\S)\d+\.\s", body))
        if len(matches) < 2:
            return text
        parts: list[str] = []
        for index, match in enumerate(matches):
            start = match.start()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
            part = body[start:end].strip()
            if part:
                parts.append(part)
        if len(parts) < 2:
            return text
        return prefix + "\n" + "\n".join(parts)

    rewritten: list[str] = []
    preferred_user_name = ""
    assistant_name = ""
    discord_handle = ""
    changed = False

    for entry in entries:
        text = str(entry).strip()
        if not text:
            continue
        if text.startswith("Preferred user name:"):
            preferred_user_name = text.partition(":")[2].strip()
            continue
        if text.startswith("Assistant name:"):
            assistant_name = text.partition(":")[2].strip()
            continue
        if text.startswith("Discord handle:"):
            discord_handle = text.partition(":")[2].strip()
            continue

        match = legacy_name_re.match(text)
        if match:
            preferred_user_name = preferred_user_name or match.group("name").strip()
            discord_handle = discord_handle or match.group("handle").strip()
            changed = True
            continue

        match = legacy_address_re.match(text)
        if match:
            preferred_user_name = preferred_user_name or match.group("name").strip()
            discord_handle = discord_handle or match.group("handle").strip()
            changed = True
            continue

        canonical = _rehydrate_rule_pack(text)
        if canonical != text:
            changed = True
        rewritten.append(canonical)

    canonical_entries: list[str] = []
    seen: set[str] = set()

    def _append(entry: str) -> None:
        normalized = str(entry).strip()
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        canonical_entries.append(normalized)

    if preferred_user_name:
        _append(f"Preferred user name: {preferred_user_name}")
    if assistant_name:
        _append(f"Assistant name: {assistant_name}")
    if discord_handle:
        _append(f"Discord handle: {discord_handle}")
    for entry in rewritten:
        _append(entry)

    serialized = delimiter.join(canonical_entries)
    current_index = {}
    if index_path.exists():
        try:
            current_index = json.loads(index_path.read_text(encoding="utf-8").strip() or "{}")
            if not isinstance(current_index, dict):
                current_index = {}
        except (OSError, json.JSONDecodeError):
            current_index = {}
    new_index = {
        "preferred_user_name": preferred_user_name,
        "assistant_name": assistant_name,
    }
    if canonical_entries != entries:
        changed = True
    if current_index != new_index:
        changed = True

    if changed and not dry_run:
        user_path.write_text(serialized, encoding="utf-8")
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(json.dumps(new_index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    return {
        "status": "updated" if changed else "already_canonical",
        "path": str(user_path),
        "index_path": str(index_path),
        "entry_count": len(canonical_entries),
        "preferred_user_name": preferred_user_name,
        "assistant_name": assistant_name,
        "discord_handle": discord_handle,
    }


def _canonicalize_runtime_brainstack_db(
    target: Path,
    config_path: Path,
    *,
    python_bin: Path | None,
    dry_run: bool,
) -> dict[str, Any]:
    runtime_root = config_path.parent
    db_path = runtime_root / "brainstack" / "brainstack.db"
    if not db_path.exists():
        return {"status": "skipped", "reason": "brainstack_db_missing", "path": str(db_path)}
    if dry_run:
        return {"status": "planned", "path": str(db_path)}

    python_exec = str(python_bin or sys.executable)
    script = f"""
import json
import sys
sys.path.insert(0, {str(target)!r})
from plugins.memory.brainstack.db import BrainstackStore

store = BrainstackStore({str(db_path)!r})
store.open()
conn = store.conn
before = {{
    "style_contract_behavior_rows": conn.execute(
        "select count(*) from behavior_contracts where stable_key = ?",
        ("preference:style_contract",),
    ).fetchone()[0],
    "compiled_behavior_policies": conn.execute(
        "select count(*) from compiled_behavior_policies"
    ).fetchone()[0],
    "interrupt_transcript_hits": conn.execute(
        "select count(*) from transcript_entries where content like '%Assistant: Operation interrupted:%' or content like '%Assistant: Session reset.%'"
    ).fetchone()[0],
}}
transcript_scrub = store.scrub_transcript_hygiene_residue()
behavior_residue = store.purge_style_contract_behavior_residue()
result = {{
    "before": before,
    "transcript_scrub": transcript_scrub,
    "behavior_residue": behavior_residue,
    "style_contract_behavior_rows": conn.execute(
        "select count(*) from behavior_contracts where stable_key = ?",
        ("preference:style_contract",),
    ).fetchone()[0],
    "active_behavior_contracts": conn.execute(
        "select count(*) from behavior_contracts where stable_key = ? and status = ?",
        ("preference:style_contract", "active"),
    ).fetchone()[0],
    "superseded_behavior_contracts": conn.execute(
        "select count(*) from behavior_contracts where stable_key = ? and status = ?",
        ("preference:style_contract", "superseded"),
    ).fetchone()[0],
    "quarantined_behavior_contracts": conn.execute(
        "select count(*) from behavior_contracts where stable_key = ? and status = ?",
        ("preference:style_contract", "quarantined"),
    ).fetchone()[0],
    "compiled_behavior_policies": conn.execute(
        "select count(*) from compiled_behavior_policies"
    ).fetchone()[0],
    "interrupt_transcript_hits": conn.execute(
        "select count(*) from transcript_entries where content like '%Assistant: Operation interrupted:%' or content like '%Assistant: Session reset.%'"
    ).fetchone()[0],
    "style_contract_profile_items": conn.execute(
        "select count(*) from profile_items where stable_key like 'preference:style_contract%'"
    ).fetchone()[0],
    "applied_migrations": [
        row[0]
        for row in conn.execute(
            "select name from applied_migrations where name like 'style_contract%' or name like 'behavior%' order by name"
        ).fetchall()
    ],
}}
store.close()
print(json.dumps(result, ensure_ascii=False))
"""
    proc = subprocess.run([python_exec, "-c", script], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            "Brainstack DB canonicalization failed for "
            f"{db_path}: {proc.stderr.strip() or proc.stdout.strip() or 'unknown error'}"
        )
    payload = json.loads(proc.stdout.strip() or "{}")
    payload["status"] = "updated"
    payload["path"] = str(db_path)
    return payload


def _patch_gateway_background_process_output_boundary(path: Path, dry_run: bool) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []

    helper_anchor = "def _format_gateway_process_notification(evt: dict) -> \"str | None\":\n"
    helper_block = (
        "PROCESS_OUTPUT_CONTEXT_PREVIEW_CHARS = 600\n"
        "PROCESS_OUTPUT_ARTIFACT_THRESHOLD_CHARS = 900\n"
        "\n"
        "\n"
        "def _write_gateway_process_output_artifact(session_id: str, kind: str, output: str) -> str | None:\n"
        "    if not output:\n"
        "        return None\n"
        "    try:\n"
        "        safe_session = re.sub(r\"[^A-Za-z0-9_.-]+\", \"_\", str(session_id or \"process\"))[:80]\n"
        "        safe_kind = re.sub(r\"[^A-Za-z0-9_.-]+\", \"_\", str(kind or \"output\"))[:40]\n"
        "        base = Path(os.environ.get(\"HERMES_HOME\") or \"~/.hermes\").expanduser()\n"
        "        out_dir = base / \"process_artifacts\"\n"
        "        out_dir.mkdir(parents=True, exist_ok=True)\n"
        "        path = out_dir / f\"{safe_session}_{safe_kind}_{int(time.time())}.txt\"\n"
        "        path.write_text(output, encoding=\"utf-8\", errors=\"replace\")\n"
        "        return str(path)\n"
        "    except Exception:\n"
        "        return None\n"
        "\n"
        "\n"
        "def _compact_gateway_process_output(session_id: str, kind: str, output: str) -> tuple[str, str | None]:\n"
        "    rendered = str(output or \"\")\n"
        "    if len(rendered) <= PROCESS_OUTPUT_ARTIFACT_THRESHOLD_CHARS:\n"
        "        return rendered, None\n"
        "    artifact_ref = _write_gateway_process_output_artifact(session_id, kind, rendered)\n"
        "    half = max(PROCESS_OUTPUT_CONTEXT_PREVIEW_CHARS // 2, 1)\n"
        "    preview = rendered[:half].rstrip()\n"
        "    tail = rendered[-half:].lstrip()\n"
        "    if tail and tail != preview:\n"
        "        preview = f\"{preview}\\n...\\n{tail}\"\n"
        "    omitted = max(len(rendered) - len(preview), 0)\n"
        "    if artifact_ref:\n"
        "        prefix = f\"[large output: {len(rendered)} chars, {omitted} chars omitted; full output artifact: {artifact_ref}]\"\n"
        "    else:\n"
        "        prefix = f\"[large output: {len(rendered)} chars, {omitted} chars omitted; artifact write unavailable]\"\n"
        "    return f\"{prefix}\\n{preview}\", artifact_ref\n"
        "\n"
        "\n"
        + helper_anchor
    )
    if "PROCESS_OUTPUT_CONTEXT_PREVIEW_CHARS = 600" not in text and helper_anchor in text:
        text = _replace_once(
            text,
            helper_anchor,
            helper_block,
            label="gateway background process output boundary helpers",
            path=path,
        )
        applied.append("gateway:background_output_boundary_helpers")

    replacements = [
        (
            (
                "        _out = evt.get(\"output\", \"\")\n"
                "        _sup = evt.get(\"suppressed\", 0)\n"
                "        text = (\n"
                "            f\"[IMPORTANT: Background process {_sid} matched \"\n"
                "            f\"watch pattern \\\"{_pat}\\\".\\n\"\n"
                "            f\"Command: {_cmd}\\n\"\n"
                "            f\"Matched output:\\n{_out}\"\n"
                "        )\n"
            ),
            (
                "        _out, _artifact_ref = _compact_gateway_process_output(_sid, \"watch_match\", evt.get(\"output\", \"\"))\n"
                "        _sup = evt.get(\"suppressed\", 0)\n"
                "        _artifact_line = f\"Full output artifact: {_artifact_ref}\\n\" if _artifact_ref else \"\"\n"
                "        text = (\n"
                "            f\"[IMPORTANT: Background process {_sid} matched \"\n"
                "            f\"watch pattern \\\"{_pat}\\\".\\n\"\n"
                "            f\"Command: {_cmd}\\n\"\n"
                "            f\"{_artifact_line}\"\n"
                "            f\"Matched output:\\n{_out}\"\n"
                "        )\n"
            ),
            "gateway:watch_output_compact_artifact",
            "_compact_gateway_process_output(_sid, \"watch_match\"",
        ),
        (
            (
                "                    _out = strip_ansi(session.output_buffer[-2000:]) if session.output_buffer else \"\"\n"
                "                    synth_text = (\n"
                "                        f\"[IMPORTANT: Background process {session_id} completed \"\n"
                "                        f\"(exit code {session.exit_code}).\\n\"\n"
                "                        f\"Command: {session.command}\\n\"\n"
                "                        f\"Output:\\n{_out}]\"\n"
                "                    )\n"
            ),
            (
                "                    _raw_output = strip_ansi(session.output_buffer) if session.output_buffer else \"\"\n"
                "                    _out, _artifact_ref = _compact_gateway_process_output(session_id, \"agent_completion\", _raw_output)\n"
                "                    _artifact_line = f\"Full output artifact: {_artifact_ref}\\n\" if _artifact_ref else \"\"\n"
                "                    synth_text = (\n"
                "                        f\"[IMPORTANT: Background process {session_id} completed \"\n"
                "                        f\"(exit code {session.exit_code}).\\n\"\n"
                "                        f\"Command: {session.command}\\n\"\n"
                "                        f\"{_artifact_line}\"\n"
                "                        f\"Output:\\n{_out}]\"\n"
                "                    )\n"
            ),
            "gateway:agent_completion_output_compact_artifact",
            "_compact_gateway_process_output(session_id, \"agent_completion\"",
        ),
        (
            (
                "                    new_output = session.output_buffer[-1000:] if session.output_buffer else \"\"\n"
                "                    message_text = (\n"
                "                        f\"[Background process {session_id} finished with exit code {session.exit_code}~ \"\n"
                "                        f\"Here's the final output:\\n{new_output}]\"\n"
                "                    )\n"
            ),
            (
                "                    new_output, artifact_ref = _compact_gateway_process_output(\n"
                "                        session_id,\n"
                "                        \"user_completion\",\n"
                "                        session.output_buffer if session.output_buffer else \"\",\n"
                "                    )\n"
                "                    artifact_line = f\"Full output artifact: {artifact_ref}\\n\" if artifact_ref else \"\"\n"
                "                    message_text = (\n"
                "                        f\"[Background process {session_id} finished with exit code {session.exit_code}~ \"\n"
                "                        f\"{artifact_line}\"\n"
                "                        f\"Final output preview:\\n{new_output}]\"\n"
                "                    )\n"
            ),
            "gateway:user_completion_output_compact_artifact",
            "_compact_gateway_process_output(\n                        session_id,\n                        \"user_completion\"",
        ),
        (
            (
                "                new_output = session.output_buffer[-500:] if session.output_buffer else \"\"\n"
                "                message_text = (\n"
                "                    f\"[Background process {session_id} is still running~ \"\n"
                "                    f\"New output:\\n{new_output}]\"\n"
                "                )\n"
            ),
            (
                "                new_output, artifact_ref = _compact_gateway_process_output(\n"
                "                    session_id,\n"
                "                    \"running_update\",\n"
                "                    session.output_buffer if session.output_buffer else \"\",\n"
                "                )\n"
                "                artifact_line = f\"Full output artifact: {artifact_ref}\\n\" if artifact_ref else \"\"\n"
                "                message_text = (\n"
                "                    f\"[Background process {session_id} is still running~ \"\n"
                "                    f\"{artifact_line}\"\n"
                "                    f\"New output preview:\\n{new_output}]\"\n"
                "                )\n"
            ),
            "gateway:running_output_compact_artifact",
            "_compact_gateway_process_output(\n                    session_id,\n                    \"running_update\"",
        ),
    ]
    for old, new, label, marker in replacements:
        if marker not in text and old in text:
            text = _replace_once(text, old, new, label=label, path=path)
            applied.append(label)

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _patch_gateway_run(path: Path, dry_run: bool) -> list[str]:
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []

    hooks_anchor = "    # -- Setup skill availability ----------------------------------------\n\n    def _has_setup_skill(self) -> bool:\n"
    hooks_inject = (
        "    def _maintenance_agent_toolsets(self) -> list[str]:\n"
        "        return [\"memory\"]\n"
        "\n"
        "    def _derive_gateway_runtime_state(self) -> str:\n"
        "        if self.adapters:\n"
        "            return \"degraded\" if self._failed_platforms else \"running\"\n"
        "        if self._failed_platforms:\n"
        "            return \"reconnecting\"\n"
        "        if self._running:\n"
        "            return \"idle\"\n"
        "        return \"starting\"\n"
        "\n"
        "    def _write_gateway_runtime_status(\n"
        "        self,\n"
        "        *,\n"
        "        gateway_state: str | None = None,\n"
        "        exit_reason: str | None = None,\n"
        "        platform: str | None = None,\n"
        "        platform_state: str | None = None,\n"
        "        error_code: str | None = None,\n"
        "        error_message: str | None = None,\n"
        "    ) -> None:\n"
        "        try:\n"
        "            from gateway.status import write_runtime_status\n"
        "\n"
        "            write_runtime_status(\n"
        "                gateway_state=gateway_state if gateway_state is not None else self._derive_gateway_runtime_state(),\n"
        "                exit_reason=exit_reason,\n"
        "                platform=platform,\n"
        "                platform_state=platform_state,\n"
        "                error_code=error_code,\n"
        "                error_message=error_message,\n"
        "            )\n"
        "        except Exception:\n"
        "            pass\n"
        "\n"
        "    def _finalize_session_memory_sync(\n"
        "        self,\n"
        "        session_key: str,\n"
        "        session_id: str,\n"
        "    ) -> None:\n"
        "        del session_key\n"
        "        self._flush_memories_for_session(session_id)\n"
        "\n"
        "    async def _async_finalize_session_memory(\n"
        "        self,\n"
        "        session_key: str,\n"
        "        session_id: str,\n"
        "    ) -> None:\n"
        "        loop = asyncio.get_event_loop()\n"
        "        await loop.run_in_executor(\n"
        "            None,\n"
        "            self._finalize_session_memory_sync,\n"
        "            session_key,\n"
        "            session_id,\n"
        "        )\n"
        "\n"
        + hooks_anchor
    )
    if "def _maintenance_agent_toolsets(self) -> list[str]:" not in text:
        text = _replace_once(text, hooks_anchor, hooks_inject, label="gateway helper block", path=path)
        applied.append("gateway:add_boundary_helpers")

    replacements = [
        (
            "        try:\n            from gateway.status import write_runtime_status\n            write_runtime_status(gateway_state=\"starting\", exit_reason=None)\n        except Exception:\n            pass\n",
            "        self._write_gateway_runtime_status(gateway_state=\"starting\", exit_reason=None)\n",
            "gateway:startup_status",
        ),
        (
            "                                    enabled_toolsets=[\"memory\"],\n",
            "                                    enabled_toolsets=self._maintenance_agent_toolsets(),\n",
            "gateway:hygiene_toolsets",
        ),
        (
            "                enabled_toolsets=[\"memory\"],\n",
            "                enabled_toolsets=self._maintenance_agent_toolsets(),\n",
            "gateway:compress_toolsets",
        ),
        (
            "                        await self._async_flush_memories(entry.session_id)\n",
            "                        await self._async_finalize_session_memory(key, entry.session_id)\n",
            "gateway:expiry_finalize",
        ),
        (
            "                _flush_task = asyncio.create_task(\n                    self._async_flush_memories(old_entry.session_id)\n                )\n",
            "                _flush_task = asyncio.create_task(\n                    self._async_finalize_session_memory(session_key, old_entry.session_id)\n                )\n",
            "gateway:reset_finalize",
        ),
        (
            "            _flush_task = asyncio.create_task(\n                self._async_flush_memories(current_entry.session_id)\n            )\n",
            "            _flush_task = asyncio.create_task(\n                self._async_finalize_session_memory(session_key, current_entry.session_id)\n            )\n",
            "gateway:resume_finalize",
        ),
        (
            "                        logger.debug(\n                            \"Memory flush completed for session %s\",\n",
            "                        self._evict_cached_agent(key)\n                        logger.debug(\n                            \"Memory flush completed for session %s\",\n",
            "gateway:evict_cached_expiry",
        ),
        (
            "            logger.info(\"Connecting to %s...\", platform.value)\n            try:\n",
            "            logger.info(\"Connecting to %s...\", platform.value)\n            self._write_gateway_runtime_status(\n                gateway_state=\"starting\",\n                exit_reason=None,\n                platform=platform.value,\n                platform_state=\"connecting\",\n                error_code=None,\n                error_message=None,\n            )\n            try:\n",
            "gateway:connect_starting_status",
        ),
        (
            "                    connected_count += 1\n                    logger.info(\"✓ %s connected\", platform.value)\n",
            "                    connected_count += 1\n                    self._write_gateway_runtime_status(\n                        gateway_state=\"starting\",\n                        exit_reason=None,\n                        platform=platform.value,\n                        platform_state=\"connected\",\n                        error_code=None,\n                        error_message=None,\n                    )\n                    logger.info(\"✓ %s connected\", platform.value)\n",
            "gateway:connect_success_status",
        ),
        (
            "                    if adapter.has_fatal_error:\n                        target = (\n",
            "                    if adapter.has_fatal_error:\n                        self._write_gateway_runtime_status(\n                            gateway_state=\"starting\",\n                            exit_reason=None,\n                            platform=platform.value,\n                            platform_state=\"retrying\" if adapter.fatal_error_retryable else \"failed\",\n                            error_code=adapter.fatal_error_code,\n                            error_message=adapter.fatal_error_message,\n                        )\n                        target = (\n",
            "gateway:connect_fatal_status",
        ),
        (
            "                    else:\n                        startup_retryable_errors.append(\n",
            "                    else:\n                        self._write_gateway_runtime_status(\n                            gateway_state=\"starting\",\n                            exit_reason=None,\n                            platform=platform.value,\n                            platform_state=\"retrying\",\n                            error_code=\"connect_failed\",\n                            error_message=\"failed to connect\",\n                        )\n                        startup_retryable_errors.append(\n",
            "gateway:connect_retry_status",
        ),
        (
            "            except Exception as e:\n                logger.error(\"✗ %s error: %s\", platform.value, e)\n                startup_retryable_errors.append(f\"{platform.value}: {e}\")\n",
            "            except Exception as e:\n                logger.error(\"✗ %s error: %s\", platform.value, e)\n                self._write_gateway_runtime_status(\n                    gateway_state=\"starting\",\n                    exit_reason=None,\n                    platform=platform.value,\n                    platform_state=\"retrying\",\n                    error_code=\"connect_exception\",\n                    error_message=str(e),\n                )\n                startup_retryable_errors.append(f\"{platform.value}: {e}\")\n",
            "gateway:connect_exception_status",
        ),
        (
            "        self._running = True\n        try:\n            from gateway.status import write_runtime_status\n            write_runtime_status(gateway_state=\"running\", exit_reason=None)\n        except Exception:\n            pass\n",
            "        self._running = True\n        self._write_gateway_runtime_status(\n            gateway_state=\"degraded\" if self._failed_platforms else \"running\",\n            exit_reason=None,\n        )\n",
            "gateway:running_status",
        ),
        (
            "                logger.info(\n                    \"%s queued for background reconnection\",\n                    adapter.platform.value,\n                )\n\n        if not self.adapters and not self._failed_platforms:\n",
            "                logger.info(\n                    \"%s queued for background reconnection\",\n                    adapter.platform.value,\n                )\n\n        self._write_gateway_runtime_status(\n            platform=adapter.platform.value,\n            platform_state=\"retrying\" if adapter.fatal_error_retryable else \"failed\",\n            error_code=adapter.fatal_error_code,\n            error_message=adapter.fatal_error_message,\n        )\n\n        if not self.adapters and not self._failed_platforms:\n",
            "gateway:fatal_status",
        ),
        (
            "        if not self.adapters and not self._failed_platforms:\n            self._exit_reason = adapter.fatal_error_message or \"All messaging adapters disconnected\"\n",
            "        if not self.adapters and not self._failed_platforms:\n            self._exit_reason = adapter.fatal_error_message or \"All messaging adapters disconnected\"\n            self._write_gateway_runtime_status(\n                gateway_state=\"startup_failed\",\n                exit_reason=self._exit_reason,\n                platform=adapter.platform.value,\n                platform_state=\"failed\",\n                error_code=adapter.fatal_error_code,\n                error_message=adapter.fatal_error_message,\n            )\n",
            "gateway:fatal_exit_status",
        ),
        (
            "                logger.info(\n                    \"Reconnecting %s (attempt %d/%d)...\",\n                    platform.value, attempt, _MAX_ATTEMPTS,\n                )\n\n                try:\n",
            "                logger.info(\n                    \"Reconnecting %s (attempt %d/%d)...\",\n                    platform.value, attempt, _MAX_ATTEMPTS,\n                )\n                self._write_gateway_runtime_status(\n                    gateway_state=\"reconnecting\" if not self.adapters else \"degraded\",\n                    exit_reason=None,\n                    platform=platform.value,\n                    platform_state=\"retrying\",\n                    error_code=None,\n                    error_message=None,\n                )\n\n                try:\n",
            "gateway:reconnect_attempt_status",
        ),
        (
            "                        self.delivery_router.adapters = self.adapters\n                        del self._failed_platforms[platform]\n                        logger.info(\"✓ %s reconnected successfully\", platform.value)\n",
            "                        self.delivery_router.adapters = self.adapters\n                        del self._failed_platforms[platform]\n                        self._write_gateway_runtime_status(\n                            gateway_state=\"degraded\" if self._failed_platforms else \"running\",\n                            exit_reason=None,\n                            platform=platform.value,\n                            platform_state=\"connected\",\n                            error_code=None,\n                            error_message=None,\n                        )\n                        logger.info(\"✓ %s reconnected successfully\", platform.value)\n",
            "gateway:reconnect_success_status",
        ),
        (
            "                            logger.warning(\n                                \"Reconnect %s: non-retryable error (%s), removing from retry queue\",\n                                platform.value, adapter.fatal_error_message,\n                            )\n                            del self._failed_platforms[platform]\n",
            "                            logger.warning(\n                                \"Reconnect %s: non-retryable error (%s), removing from retry queue\",\n                                platform.value, adapter.fatal_error_message,\n                            )\n                            del self._failed_platforms[platform]\n                            self._write_gateway_runtime_status(\n                                gateway_state=\"degraded\" if self.adapters else \"startup_failed\",\n                                exit_reason=None if self.adapters else adapter.fatal_error_message,\n                                platform=platform.value,\n                                platform_state=\"failed\",\n                                error_code=adapter.fatal_error_code,\n                                error_message=adapter.fatal_error_message,\n                            )\n",
            "gateway:reconnect_nonretryable_status",
        ),
        (
            "                            backoff = min(30 * (2 ** (attempt - 1)), _BACKOFF_CAP)\n                            info[\"attempts\"] = attempt\n                            info[\"next_retry\"] = time.monotonic() + backoff\n                            logger.info(\n                                \"Reconnect %s failed, next retry in %ds\",\n                                platform.value, backoff,\n                            )\n",
            "                            backoff = min(30 * (2 ** (attempt - 1)), _BACKOFF_CAP)\n                            info[\"attempts\"] = attempt\n                            info[\"next_retry\"] = time.monotonic() + backoff\n                            self._write_gateway_runtime_status(\n                                gateway_state=\"degraded\" if self.adapters else \"reconnecting\",\n                                exit_reason=None,\n                                platform=platform.value,\n                                platform_state=\"retrying\",\n                                error_code=adapter.fatal_error_code or \"reconnect_failed\",\n                                error_message=adapter.fatal_error_message or f\"next retry in {backoff}s\",\n                            )\n                            logger.info(\n                                \"Reconnect %s failed, next retry in %ds\",\n                                platform.value, backoff,\n                            )\n",
            "gateway:reconnect_retry_status",
        ),
        (
            "                    backoff = min(30 * (2 ** (attempt - 1)), _BACKOFF_CAP)\n                    info[\"attempts\"] = attempt\n                    info[\"next_retry\"] = time.monotonic() + backoff\n                    logger.warning(\n                        \"Reconnect %s error: %s, next retry in %ds\",\n                        platform.value, e, backoff,\n                    )\n",
            "                    backoff = min(30 * (2 ** (attempt - 1)), _BACKOFF_CAP)\n                    info[\"attempts\"] = attempt\n                    info[\"next_retry\"] = time.monotonic() + backoff\n                    self._write_gateway_runtime_status(\n                        gateway_state=\"degraded\" if self.adapters else \"reconnecting\",\n                        exit_reason=None,\n                        platform=platform.value,\n                        platform_state=\"retrying\",\n                        error_code=\"reconnect_exception\",\n                        error_message=str(e),\n                    )\n                    logger.warning(\n                        \"Reconnect %s error: %s, next retry in %ds\",\n                        platform.value, e, backoff,\n                    )\n",
            "gateway:reconnect_exception_status",
        ),
        (
            "                    logger.warning(\n                        \"Giving up reconnecting %s after %d attempts\",\n                        platform.value, info[\"attempts\"],\n                    )\n                    del self._failed_platforms[platform]\n                    continue\n",
            "                    logger.warning(\n                        \"Giving up reconnecting %s after %d attempts\",\n                        platform.value, info[\"attempts\"],\n                    )\n                    del self._failed_platforms[platform]\n                    self._write_gateway_runtime_status(\n                        gateway_state=\"degraded\" if self.adapters else \"startup_failed\",\n                        exit_reason=None if self.adapters else f\"{platform.value}: reconnect attempts exhausted\",\n                        platform=platform.value,\n                        platform_state=\"failed\",\n                        error_code=\"reconnect_exhausted\",\n                        error_message=f\"reconnect attempts exhausted after {info['attempts']} tries\",\n                    )\n                    continue\n",
            "gateway:reconnect_exhausted_status",
        ),
        (
            '            header = "Session reset."\n',
            '            header = "Fresh session started."\n',
            "gateway:clean_reset_header",
        ),
    ]
    for old, new, label in replacements:
        if new not in text and old in text:
            text = _replace_once(text, old, new, label=label, path=path)
            applied.append(label)

    old_cron_ticker = (
        "def _start_cron_ticker(stop_event: threading.Event, adapters=None, loop=None, interval: int = 60):\n"
        "    \"\"\"\n"
        "    Background thread that ticks the cron scheduler at a regular interval.\n"
        "    \n"
        "    Runs inside the gateway process so cronjobs fire automatically without\n"
        "    needing a separate `hermes cron daemon` or system cron entry.\n"
        "\n"
        "    When ``adapters`` and ``loop`` are provided, passes them through to the\n"
        "    cron delivery path so live adapters can be used for E2EE rooms.\n"
        "\n"
        "    Also refreshes the channel directory every 5 minutes and prunes the\n"
        "    image/audio/document cache once per hour.\n"
        "    \"\"\"\n"
        "    from cron.scheduler import tick as cron_tick\n"
        "    from gateway.platforms.base import cleanup_image_cache, cleanup_document_cache\n"
        "\n"
        "    IMAGE_CACHE_EVERY = 60   # ticks — once per hour at default 60s interval\n"
        "    CHANNEL_DIR_EVERY = 5    # ticks — every 5 minutes\n"
        "\n"
        "    logger.info(\"Cron ticker started (interval=%ds)\", interval)\n"
        "    tick_count = 0\n"
        "    while not stop_event.is_set():\n"
        "        try:\n"
        "            cron_tick(verbose=False, adapters=adapters, loop=loop)\n"
        "        except Exception as e:\n"
        "            logger.debug(\"Cron tick error: %s\", e)\n"
        "\n"
        "        tick_count += 1\n"
        "\n"
        "        if tick_count % CHANNEL_DIR_EVERY == 0 and adapters:\n"
        "            try:\n"
        "                from gateway.channel_directory import build_channel_directory\n"
        "                build_channel_directory(adapters)\n"
        "            except Exception as e:\n"
        "                logger.debug(\"Channel directory refresh error: %s\", e)\n"
        "\n"
        "        if tick_count % IMAGE_CACHE_EVERY == 0:\n"
        "            try:\n"
        "                removed = cleanup_image_cache(max_age_hours=24)\n"
        "                if removed:\n"
        "                    logger.info(\"Image cache cleanup: removed %d stale file(s)\", removed)\n"
        "            except Exception as e:\n"
        "                logger.debug(\"Image cache cleanup error: %s\", e)\n"
        "            try:\n"
        "                removed = cleanup_document_cache(max_age_hours=24)\n"
        "                if removed:\n"
        "                    logger.info(\"Document cache cleanup: removed %d stale file(s)\", removed)\n"
        "            except Exception as e:\n"
        "                logger.debug(\"Document cache cleanup error: %s\", e)\n"
        "\n"
        "        stop_event.wait(timeout=interval)\n"
        "    logger.info(\"Cron ticker stopped\")\n"
    )
    new_cron_ticker = (
        "def _start_cron_ticker(stop_event: threading.Event, adapters=None, loop=None, interval: int = 60):\n"
        "    \"\"\"\n"
        "    Background thread that ticks the cron scheduler at a regular interval.\n"
        "    \n"
        "    Runs inside the gateway process so cronjobs fire automatically without\n"
        "    needing a separate `hermes cron daemon` or system cron entry.\n"
        "\n"
        "    When ``adapters`` and ``loop`` are provided, passes them through to the\n"
        "    cron delivery path so live adapters can be used for E2EE rooms.\n"
        "\n"
        "    Also refreshes the channel directory every 5 minutes and prunes the\n"
        "    image/audio/document cache once per hour.\n"
        "    \"\"\"\n"
        "    from cron.jobs import seconds_until_next_run\n"
        "    from cron.scheduler import tick as cron_tick, wait_for_tick_wake\n"
        "    from gateway.platforms.base import cleanup_image_cache, cleanup_document_cache\n"
        "\n"
        "    IMAGE_CACHE_INTERVAL = 60 * 60\n"
        "    CHANNEL_DIR_INTERVAL = 5 * 60\n"
        "\n"
        "    logger.info(\"Cron ticker started (interval=%ds)\", interval)\n"
        "    last_channel_refresh = time.monotonic()\n"
        "    last_cache_cleanup = time.monotonic()\n"
        "    while not stop_event.is_set():\n"
        "        try:\n"
        "            cron_tick(verbose=False, adapters=adapters, loop=loop)\n"
        "        except Exception as e:\n"
        "            logger.debug(\"Cron tick error: %s\", e)\n"
        "\n"
        "        now_mono = time.monotonic()\n"
        "\n"
        "        if adapters and (now_mono - last_channel_refresh) >= CHANNEL_DIR_INTERVAL:\n"
        "            try:\n"
        "                from gateway.channel_directory import build_channel_directory\n"
        "                build_channel_directory(adapters)\n"
        "                last_channel_refresh = now_mono\n"
        "            except Exception as e:\n"
        "                logger.debug(\"Channel directory refresh error: %s\", e)\n"
        "\n"
        "        if (now_mono - last_cache_cleanup) >= IMAGE_CACHE_INTERVAL:\n"
        "            try:\n"
        "                removed = cleanup_image_cache(max_age_hours=24)\n"
        "                if removed:\n"
        "                    logger.info(\"Image cache cleanup: removed %d stale file(s)\", removed)\n"
        "            except Exception as e:\n"
        "                logger.debug(\"Image cache cleanup error: %s\", e)\n"
        "            try:\n"
        "                removed = cleanup_document_cache(max_age_hours=24)\n"
        "                if removed:\n"
        "                    logger.info(\"Document cache cleanup: removed %d stale file(s)\", removed)\n"
        "            except Exception as e:\n"
        "                logger.debug(\"Document cache cleanup error: %s\", e)\n"
        "            last_cache_cleanup = now_mono\n"
        "\n"
        "        wait_timeout = seconds_until_next_run(max_wait=float(interval))\n"
        "        wait_for_tick_wake(stop_event, timeout=wait_timeout)\n"
        "    logger.info(\"Cron ticker stopped\")\n"
    )
    if "from cron.jobs import seconds_until_next_run" not in text and old_cron_ticker in text:
        text = _replace_once(text, old_cron_ticker, new_cron_ticker, label="gateway:cron_wake_aware_ticker", path=path)
        applied.append("gateway:cron_wake_aware_ticker")

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _patch_gateway_turn_profiles_capability_preserving_default(path: Path, dry_run: bool) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    if "DISCORD_DEFAULT_CAPABILITY_PRESERVED" in text and "capability_preserving_default" in text:
        return []

    old = """    return ResolvedTurnProfile(
        schema=SCHEMA_VERSION,
        platform=platform,
        turn_profile="conversation_tools",
        tool_profile="conversation_tools",
        enabled_toolsets=CONVERSATION_TOOLSETS,
        reason_code="DISCORD_DEFAULT_CONVERSATION",
        explicit_heavy=False,
        heavy_bundle=None,
        url_attachment_candidate_only=_url_count(prompt) > 0,
        rollback_override_active=False,
        cli_local_unchanged=False,
    )
"""
    new = """    # capability_shrunk=false by construction: default Discord turns preserve
    # the configured Hermes platform toolsets. Compact/deferred schemas may
    # optimize prompt cost, but they must not hide native tools behind a mode.
    return ResolvedTurnProfile(
        schema=SCHEMA_VERSION,
        platform=platform,
        turn_profile="capability_preserving_default",
        tool_profile="existing_platform_default",
        enabled_toolsets=current,
        reason_code="DISCORD_DEFAULT_CAPABILITY_PRESERVED",
        explicit_heavy=False,
        heavy_bundle=None,
        url_attachment_candidate_only=_url_count(prompt) > 0,
        rollback_override_active=False,
        cli_local_unchanged=False,
    )
"""
    text = _replace_once(
        text,
        old,
        new,
        label="gateway turn profile capability-preserving Discord default",
        path=path,
    )
    if not dry_run:
        path.write_text(text, encoding="utf-8")
    return ["gateway_turn_profiles:capability_preserving_default"]


def _gateway_turn_profile_prompt_expr(text: str, position: int) -> str:
    local_context = text[max(0, position - 2500) : position]
    function_start = max(
        local_context.rfind("\n    async def "),
        local_context.rfind("\n    def "),
        local_context.rfind("\nasync def "),
        local_context.rfind("\ndef "),
    )
    function_context = local_context[function_start:] if function_start >= 0 else local_context
    return "prompt" if re.search(r"[(,]\s*prompt\s*:", function_context) else "message"


def _repair_gateway_run_turn_profile_prompt_expr(text: str) -> tuple[str, int]:
    marker = "        turn_profile_resolution = resolve_turn_profile(\n"
    rebuilt: list[str] = []
    last = 0
    repaired = 0
    for match in re.finditer(re.escape(marker), text):
        block_end = text.find("        )\n", match.end())
        if block_end < 0:
            continue
        block_end += len("        )\n")
        block = text[match.start() : block_end]
        prompt_line = re.search(r"(?m)^            prompt=(prompt|message),$", block)
        if not prompt_line:
            continue
        expected = _gateway_turn_profile_prompt_expr(text, match.start())
        current = prompt_line.group(1)
        if current == expected:
            continue
        rebuilt.append(text[last : match.start()])
        rebuilt.append(
            block[: prompt_line.start()]
            + f"            prompt={expected},"
            + block[prompt_line.end() :]
        )
        last = block_end
        repaired += 1
    if not repaired:
        return text, 0
    rebuilt.append(text[last:])
    return "".join(rebuilt), repaired


def _patch_gateway_run_turn_profile_resolution(path: Path, dry_run: bool) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    repaired_text, repaired = _repair_gateway_run_turn_profile_prompt_expr(text)
    if repaired:
        if not dry_run:
            path.write_text(repaired_text, encoding="utf-8")
        return [f"gateway_run:turn_profile_resolution_repair:{repaired}"]
    text = repaired_text
    if "from gateway.turn_profiles import resolve_turn_profile" in text and "_last_turn_profile_resolution" in text:
        return []

    anchor = (
        "        from hermes_cli.tools_config import _get_platform_tools\n"
        "        enabled_toolsets = sorted(_get_platform_tools(user_config, platform_key))\n"
    )
    matches = list(re.finditer(re.escape(anchor), text))
    if not matches:
        raise RuntimeError(f"Installer patch anchor missing for gateway turn profile resolution in {path}")

    rebuilt: list[str] = []
    last = 0
    applied = 0
    for index, match in enumerate(matches):
        rebuilt.append(text[last : match.end()])
        prompt_expr = _gateway_turn_profile_prompt_expr(text, match.start())
        rebuilt.append(
            "        from gateway.turn_profiles import resolve_turn_profile\n"
            "        turn_profile_resolution = resolve_turn_profile(\n"
            "            platform=platform_key,\n"
            f"            prompt={prompt_expr},\n"
            "            current_enabled_toolsets=enabled_toolsets,\n"
            "        )\n"
            "        enabled_toolsets = list(turn_profile_resolution.enabled_toolsets)\n"
            "        self._last_turn_profile_resolution = turn_profile_resolution.to_dict()\n"
        )
        last = match.end()
        applied += 1
    rebuilt.append(text[last:])
    if not dry_run:
        path.write_text("".join(rebuilt), encoding="utf-8")
    return [f"gateway_run:turn_profile_resolution:{applied}"]


def _patch_auxiliary_client(path: Path, dry_run: bool) -> list[str]:
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []

    old = "    resolved_model = model or cfg_model\n"
    new = (
        "    resolved_model = model or cfg_model\n"
        "    # Brainstack relies on auxiliary.flush_memories.provider: main meaning\n"
        "    # the task should inherit the agent's actual active model, not the\n"
        "    # provider default auxiliary model. Without this, a Nous-backed main\n"
        "    # provider can silently drift to a missing Gemini auxiliary default\n"
        "    # and durable Tier-2 writes fail at runtime.\n"
        "    if not resolved_model:\n"
        "        explicit_provider = str(provider or cfg_provider or \"\").strip().lower()\n"
        "        if explicit_provider == \"main\":\n"
        "            resolved_model = _read_main_model() or None\n"
    )
    if "explicit_provider == \"main\"" not in text:
        text = _replace_once(
            text,
            old,
            new,
            label="auxiliary_client main model inheritance",
            path=path,
        )
        applied.append("auxiliary_client:inherit_main_model")

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _patch_session_search_total_deadline(path: Path, dry_run: bool) -> list[str]:
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []

    helper = (
        "\n\n"
        "def _get_session_search_total_deadline(default: float = 20.0) -> float:\n"
        "    \"\"\"Return a tool-level deadline below the gateway idle timeout.\"\"\"\n"
        "    try:\n"
        "        from hermes_cli.config import load_config\n"
        "        config = load_config()\n"
        "    except ImportError:\n"
        "        return default\n"
        "    aux = config.get(\"auxiliary\", {}) if isinstance(config, dict) else {}\n"
        "    task_config = aux.get(\"session_search\", {}) if isinstance(aux, dict) else {}\n"
        "    if not isinstance(task_config, dict):\n"
        "        task_config = {}\n"
        "    configured = task_config.get(\"total_timeout\")\n"
        "    try:\n"
        "        value = float(configured) if configured is not None else default\n"
        "    except (TypeError, ValueError):\n"
        "        value = default\n"
        "    agent = config.get(\"agent\", {}) if isinstance(config, dict) else {}\n"
        "    gateway_timeout = agent.get(\"gateway_timeout\") if isinstance(agent, dict) else None\n"
        "    try:\n"
        "        gateway_limit = float(gateway_timeout) - 10.0\n"
        "    except (TypeError, ValueError):\n"
        "        gateway_limit = default\n"
        "    return max(5.0, min(value, gateway_limit))\n"
    )
    if "def _get_session_search_total_deadline" not in text:
        text = _replace_once(
            text,
            "\n\ndef _format_timestamp",
            helper + "\n\ndef _format_timestamp",
            label="session_search total deadline helper",
            path=path,
        )
        applied.append("session_search:total_deadline_helper")
    elif "def _get_session_search_total_deadline(default: float = 90.0)" in text:
        text = _replace_once(
            text,
            "def _get_session_search_total_deadline(default: float = 90.0)",
            "def _get_session_search_total_deadline(default: float = 20.0)",
            label="session_search lower default total deadline",
            path=path,
        )
        applied.append("session_search:lower_default_total_deadline")

    old_gather = "            return await asyncio.gather(*coros, return_exceptions=True)\n"
    new_gather = (
        "            return await asyncio.wait_for(\n"
        "                asyncio.gather(*coros, return_exceptions=True),\n"
        "                timeout=_get_session_search_total_deadline(),\n"
        "            )\n"
    )
    if "timeout=_get_session_search_total_deadline()" not in text:
        text = _replace_once(
            text,
            old_gather,
            new_gather,
            label="session_search bounded gather",
            path=path,
        )
        applied.append("session_search:bounded_gather")

    old_timeout = (
        "        except concurrent.futures.TimeoutError:\n"
        "            logging.warning(\n"
        "                \"Session summarization timed out after 60 seconds\",\n"
        "                exc_info=True,\n"
        "            )\n"
        "            return json.dumps({\n"
        "                \"success\": False,\n"
        "                \"error\": \"Session summarization timed out. Try a more specific query or reduce the limit.\",\n"
        "            }, ensure_ascii=False)\n"
    )
    new_timeout = (
        "        except (asyncio.TimeoutError, TimeoutError, concurrent.futures.TimeoutError):\n"
        "            deadline = _get_session_search_total_deadline()\n"
        "            logging.warning(\n"
        "                \"Session summarization timed out after %.1f seconds; returning raw previews\",\n"
        "                deadline,\n"
        "            )\n"
        "            summaries = []\n"
        "            for session_id, match_info, conversation_text, session_meta in tasks:\n"
        "                preview = (conversation_text[:500] + \"\\\\n...[truncated]\") if conversation_text else \"No preview available.\"\n"
        "                summaries.append({\n"
        "                    \"session_id\": session_id,\n"
        "                    \"when\": _format_timestamp(session_meta.get(\"started_at\") or match_info.get(\"session_started\")),\n"
        "                    \"source\": session_meta.get(\"source\") or match_info.get(\"source\", \"unknown\"),\n"
        "                    \"model\": session_meta.get(\"model\") or match_info.get(\"model\"),\n"
        "                    \"summary\": \"[Raw preview: summarization timed out]\\\\n\" + preview,\n"
        "                })\n"
        "            return json.dumps({\n"
        "                \"success\": True,\n"
        "                \"query\": query,\n"
        "                \"results\": summaries,\n"
        "                \"count\": len(summaries),\n"
        "                \"sessions_searched\": len(seen_sessions),\n"
        "                \"degraded\": True,\n"
        "                \"degraded_reason\": \"SESSION_SEARCH_SUMMARIZATION_TIMEOUT\",\n"
        "                \"tool_total_deadline_seconds\": deadline,\n"
        "            }, ensure_ascii=False)\n"
    )
    if "SESSION_SEARCH_SUMMARIZATION_TIMEOUT" not in text:
        text = _replace_once(
            text,
            old_timeout,
            new_timeout,
            label="session_search timeout degradation",
            path=path,
        )
        applied.append("session_search:timeout_degraded_preview")
    elif "Session summarization timed out after %.1f seconds\",\n                deadline,\n                exc_info=True" in text:
        text = _replace_once(
            text,
            "Session summarization timed out after %.1f seconds\",\n"
            "                deadline,\n"
            "                exc_info=True,\n",
            "Session summarization timed out after %.1f seconds; returning raw previews\",\n"
            "                deadline,\n",
            label="session_search expected timeout log hygiene",
            path=path,
        )
        applied.append("session_search:expected_timeout_log_hygiene")

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _patch_discord_typing_backoff(path: Path, dry_run: bool) -> list[str]:
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []

    typing_state_anchor = (
        "        # Persistent typing indicator loops per channel (DMs don't reliably\n"
        "        # show the standard typing gateway event for bots)\n"
        "        self._typing_tasks: Dict[str, asyncio.Task] = {}\n"
    )
    typing_state_replacement = (
        typing_state_anchor +
        "        self._typing_endpoint_enabled = os.getenv(\n"
        "            \"HERMES_DISCORD_TYPING_ENDPOINT_ENABLED\",\n"
        "            \"false\",\n"
        "        ).lower() in {\"1\", \"true\", \"yes\", \"on\"}\n"
        "        self._typing_backoff_until: Dict[str, float] = {}\n"
        "        self._typing_interval_seconds = max(\n"
        "            10.0,\n"
        "            float(os.getenv(\"HERMES_DISCORD_TYPING_INTERVAL_SECONDS\", \"12\")),\n"
        "        )\n"
        "        self._typing_rate_limit_backoff_seconds = max(\n"
        "            10.0,\n"
        "            float(os.getenv(\"HERMES_DISCORD_TYPING_RATE_LIMIT_BACKOFF_SECONDS\", \"30\")),\n"
        "        )\n"
    )
    if "self._typing_backoff_until" not in text:
        if typing_state_anchor not in text:
            return applied
        text = _replace_once(
            text,
            typing_state_anchor,
            typing_state_replacement,
            label="Discord typing rate-limit state",
            path=path,
        )
        applied.append("discord_typing:rate_limit_state")

    if "self._typing_endpoint_enabled" not in text:
        text = _replace_once(
            text,
            "        self._typing_backoff_until: Dict[str, float] = {}\n",
            "        self._typing_endpoint_enabled = os.getenv(\n"
            "            \"HERMES_DISCORD_TYPING_ENDPOINT_ENABLED\",\n"
            "            \"false\",\n"
            "        ).lower() in {\"1\", \"true\", \"yes\", \"on\"}\n"
            "        self._typing_backoff_until: Dict[str, float] = {}\n",
            label="Discord typing endpoint opt-in state",
            path=path,
        )
        applied.append("discord_typing:opt_in_state")

    old_send_typing = '''    async def send_typing(self, chat_id: str, metadata=None) -> None:
        """Start a persistent typing indicator for a channel.

        Discord's TYPING_START gateway event is unreliable in DMs for bots.
        Instead, start a background loop that hits the typing endpoint every
        8 seconds (typing indicator lasts ~10s).  The loop is cancelled when
        stop_typing() is called (after the response is sent).
        """
        if not self._client:
            return
        # Don't start a duplicate loop
        if chat_id in self._typing_tasks:
            return

        async def _typing_loop() -> None:
            try:
                while True:
                    try:
                        route = discord.http.Route(
                            "POST", "/channels/{channel_id}/typing",
                            channel_id=chat_id,
                        )
                        await self._client.http.request(route)
                    except asyncio.CancelledError:
                        return
                    except Exception as e:
                        logger.debug("Discord typing indicator failed for %s: %s", chat_id, e)
                        return
                    await asyncio.sleep(8)
            except asyncio.CancelledError:
                pass

        self._typing_tasks[chat_id] = asyncio.create_task(_typing_loop())

    async def stop_typing(self, chat_id: str) -> None:
        """Stop the persistent typing indicator for a channel."""
        task = self._typing_tasks.pop(chat_id, None)
        if task:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
'''
    rate_limit_send_typing = '''    async def send_typing(self, chat_id: str, metadata=None) -> None:
        """Start a rate-limit-aware persistent typing indicator for a channel."""
        if not self._client:
            return

        now = time.monotonic()
        if now < float(self._typing_backoff_until.get(chat_id, 0.0) or 0.0):
            return

        existing = self._typing_tasks.get(chat_id)
        if existing is not None:
            if not existing.done():
                return
            self._typing_tasks.pop(chat_id, None)

        async def _typing_loop() -> None:
            try:
                while True:
                    try:
                        route = discord.http.Route(
                            "POST", "/channels/{channel_id}/typing",
                            channel_id=chat_id,
                        )
                        await self._client.http.request(route)
                        self._typing_backoff_until.pop(chat_id, None)
                    except asyncio.CancelledError:
                        return
                    except Exception as e:
                        message = str(e).lower()
                        if "429" in message or "rate limit" in message or "too many requests" in message:
                            self._typing_backoff_until[chat_id] = (
                                time.monotonic() + self._typing_rate_limit_backoff_seconds
                            )
                            logger.debug("Discord typing indicator rate-limited for %s: %s", chat_id, e)
                        else:
                            logger.debug("Discord typing indicator failed for %s: %s", chat_id, e)
                        return
                    await asyncio.sleep(self._typing_interval_seconds)
            except asyncio.CancelledError:
                pass
            finally:
                current = self._typing_tasks.get(chat_id)
                if current is task:
                    self._typing_tasks.pop(chat_id, None)

        task = asyncio.create_task(_typing_loop())
        self._typing_tasks[chat_id] = task

    async def stop_typing(self, chat_id: str) -> None:
        """Stop the persistent typing indicator for a channel."""
        task = self._typing_tasks.get(chat_id)
        if task:
            task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=0.5)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception:
                pass
            if task.done():
                self._typing_tasks.pop(chat_id, None)
'''
    opt_in_send_typing = '''    async def send_typing(self, chat_id: str, metadata=None) -> None:
        """Start an optional rate-limit-aware typing indicator for a channel.

        Discord edit-streaming is the primary liveness channel. The typing
        endpoint is disabled by default because Discord can log and retry 429s
        inside the HTTP client before adapter-level backoff can react.
        """
        if not self._typing_endpoint_enabled or not self._client:
            return

        now = time.monotonic()
        if now < float(self._typing_backoff_until.get(chat_id, 0.0) or 0.0):
            return

        existing = self._typing_tasks.get(chat_id)
        if existing is not None:
            if not existing.done():
                return
            self._typing_tasks.pop(chat_id, None)

        async def _typing_loop() -> None:
            try:
                while True:
                    try:
                        route = discord.http.Route(
                            "POST", "/channels/{channel_id}/typing",
                            channel_id=chat_id,
                        )
                        await self._client.http.request(route)
                        self._typing_backoff_until.pop(chat_id, None)
                    except asyncio.CancelledError:
                        return
                    except Exception as e:
                        message = str(e).lower()
                        if "429" in message or "rate limit" in message or "too many requests" in message:
                            self._typing_backoff_until[chat_id] = (
                                time.monotonic() + self._typing_rate_limit_backoff_seconds
                            )
                            logger.debug("Discord typing indicator rate-limited for %s: %s", chat_id, e)
                        else:
                            logger.debug("Discord typing indicator failed for %s: %s", chat_id, e)
                        return
                    await asyncio.sleep(self._typing_interval_seconds)
            except asyncio.CancelledError:
                pass
            finally:
                current = self._typing_tasks.get(chat_id)
                if current is task:
                    self._typing_tasks.pop(chat_id, None)

        task = asyncio.create_task(_typing_loop())
        self._typing_tasks[chat_id] = task

    async def stop_typing(self, chat_id: str) -> None:
        """Stop the persistent typing indicator for a channel."""
        task = self._typing_tasks.get(chat_id)
        if task:
            task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=0.5)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception:
                pass
            if task.done():
                self._typing_tasks.pop(chat_id, None)
'''
    if "Discord edit-streaming is the primary liveness channel" not in text:
        replaced = False
        for candidate in (rate_limit_send_typing, old_send_typing):
            if candidate in text:
                text = text.replace(candidate, opt_in_send_typing, 1)
                replaced = True
                break
        if not replaced:
            return applied
        applied.append("discord_typing:opt_in_loop")

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _patch_run_agent_ebadf_transport_recovery(path: Path, dry_run: bool) -> list[str]:
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []

    old = (
        "        # Only for transient transport errors\n"
        "        error_type = type(api_error).__name__\n"
        "        if error_type not in self._TRANSIENT_TRANSPORT_ERRORS:\n"
        "            return False\n"
    )
    new = (
        "        # Only for transient transport errors. EBADF is the closed-file-\n"
        "        # descriptor variant seen when a long-lived provider transport is\n"
        "        # stale or was closed under a background cron run; recover once by\n"
        "        # rebuilding the client instead of failing a large job immediately.\n"
        "        error_type = type(api_error).__name__\n"
        "        is_ebadf_transport_error = False\n"
        "        if isinstance(api_error, OSError):\n"
        "            import errno as _errno\n"
        "            is_ebadf_transport_error = getattr(api_error, \"errno\", None) == _errno.EBADF\n"
        "        if error_type not in self._TRANSIENT_TRANSPORT_ERRORS and not is_ebadf_transport_error:\n"
        "            return False\n"
    )
    if "is_ebadf_transport_error" not in text:
        text = _replace_once(
            text,
            old,
            new,
            label="EBADF provider transport recovery",
            path=path,
        )
        applied.append("run_agent:ebadf_transport_recovery")

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        import yaml  # type: ignore[import-untyped]

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        raise RuntimeError(f"Cannot parse YAML config at {path}: {exc}") from exc


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    try:
        import yaml  # type: ignore[import-untyped]
    except Exception as exc:
        raise RuntimeError("PyYAML is required to patch Hermes config.yaml") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _discover_agent_configs(target: Path) -> list[Path]:
    candidates: list[Path] = []
    root_config = target / "config.yaml"
    if root_config.exists():
        candidates.append(root_config)
    hermes_config_root = target / "hermes-config"
    if hermes_config_root.exists():
        for config_path in sorted(hermes_config_root.glob("*/config.yaml")):
            if config_path.is_file():
                candidates.append(config_path)
    return candidates


def _default_config_path(target: Path) -> Path:
    candidates = _discover_agent_configs(target)
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise RuntimeError(
            "No Hermes agent config found. Create or select an agent first, then rerun the installer with "
            "--config <path/to/config.yaml> if needed."
        )
    rendered = ", ".join(str(path.relative_to(target)) for path in candidates)
    raise RuntimeError(
        "Multiple Hermes agent configs found. Pass --config explicitly so Brainstack installs into the right agent: "
        f"{rendered}"
    )


def _default_compose_path(target: Path, config_path: Path | None = None) -> Path:
    candidates: list[Path] = []
    root_compose = target / "docker-compose.yml"
    if root_compose.exists():
        candidates.append(root_compose)
    for compose_path in sorted(target.glob("docker-compose*.yml")):
        if compose_path.exists() and compose_path not in candidates:
            candidates.append(compose_path)

    if config_path:
        try:
            rel = config_path.relative_to(target / "hermes-config")
        except ValueError:
            rel = None
        if rel and len(rel.parts) >= 2:
            agent_name = rel.parts[0]
            agent_compose = target / f"docker-compose.{agent_name}.yml"
            if agent_compose.exists():
                return agent_compose
        if root_compose.exists():
            return root_compose

    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise RuntimeError(
            "No Docker compose file found for this Hermes checkout. Pass --compose-file explicitly if you use Docker."
        )
    rendered = ", ".join(str(path.relative_to(target)) for path in candidates)
    raise RuntimeError(
        "Multiple Docker compose files found. Pass --compose-file explicitly so Brainstack patches the right runtime: "
        f"{rendered}"
    )


def _docker_runtime_home_dir(target: Path, config_path: Path) -> Path:
    try:
        rel = config_path.relative_to(target / "hermes-config")
    except ValueError as exc:
        raise RuntimeError(
            "Docker runtime requires an agent home like hermes-config/<agent>/config.yaml. "
            "Root-level config.yaml is fine for local mode, but Docker needs a dedicated agent directory."
        ) from exc
    if len(rel.parts) < 2:
        raise RuntimeError(
            "Docker runtime requires an agent home like hermes-config/<agent>/config.yaml."
        )
    return target / "hermes-config" / rel.parts[0]


def _sanitize_compose_slug(name: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in name).strip("-")
    return cleaned or "brainstack"


def _generated_compose_path(target: Path, config_path: Path) -> Path:
    runtime_home = _docker_runtime_home_dir(target, config_path)
    return target / f"docker-compose.{_sanitize_compose_slug(runtime_home.name)}.yml"


def _normalize_proactive_runtime_config(config: dict[str, Any]) -> dict[str, Any]:
    raw_mode = str(config.get("proactive_mode") or "").strip().lower()
    if raw_mode in PROACTIVE_RUNTIME_MODES:
        mode = raw_mode
        reason = "preserved_valid_mode"
    else:
        mode = DEFAULT_PROACTIVE_RUNTIME_MODE
        reason = "defaulted" if not raw_mode else "normalized_invalid_mode"
    config["proactive_mode"] = mode
    config.setdefault("proactive_kill_switch", False)
    return {
        "mode": mode,
        "previous_mode": raw_mode,
        "reason": reason,
        "kill_switch": bool(config.get("proactive_kill_switch")),
        "delivery_default": "no_delivery_unless_mode_live_and_pulse_create_outbox_requested",
    }


def _looks_like_legacy_local_tier2_llm_config(brainstack: dict[str, Any]) -> bool:
    provider = str(brainstack.get("tier2_hindsight_llm_provider") or "").strip().lower()
    base_url = str(brainstack.get("tier2_hindsight_llm_base_url") or "").strip().lower()
    return provider == LOCAL_TIER2_PROVIDER and any(marker in base_url for marker in LOCAL_TIER2_LOOPBACK_MODEL_URL_MARKERS)


def _normalize_hermes_native_auxiliary_main_routes(config: dict[str, Any]) -> dict[str, Any]:
    """Clear stale provider=main model pins that the active main provider cannot run."""
    auxiliary = config.setdefault("auxiliary", {})
    if not isinstance(auxiliary, dict):
        raise RuntimeError("config.yaml has non-object `auxiliary` section")
    model_cfg = config.get("model", {})
    if isinstance(model_cfg, dict):
        main_provider = str(model_cfg.get("provider") or "").strip().lower()
        main_model = str(model_cfg.get("default") or "").strip()
    else:
        main_provider = ""
        main_model = str(model_cfg or "").strip()
    normalized: list[dict[str, Any]] = []
    for task_slot, raw_entry in list(auxiliary.items()):
        if not isinstance(raw_entry, dict):
            continue
        provider = str(raw_entry.get("provider") or "").strip().lower()
        model = str(raw_entry.get("model") or "").strip()
        if provider != "main" or not model:
            continue
        readiness = resolve_auxiliary_route_readiness(
            task_slot=str(task_slot),
            provider_label=provider,
            model_label=model,
            main_provider_label=main_provider,
            main_model_label=main_model,
        )
        if readiness.get("reason_code") != REASON_UNSUPPORTED_MODEL_FOR_PROVIDER:
            continue
        raw_entry["model"] = ""
        normalized.append(
            {
                "task_slot": str(task_slot),
                "previous_model": model,
                "provider": provider,
                "reason_code": readiness.get("reason_code"),
                "effective_provider_label": readiness.get("effective_provider_label"),
                "replacement": "inherit_main_model",
            }
        )
    return {
        "status": "normalized" if normalized else "unchanged",
        "normalized_count": len(normalized),
        "routes": normalized,
        "secret_redacted": True,
    }


def _normalize_session_search_runtime_config(config: dict[str, Any]) -> dict[str, Any]:
    """Keep native session_search useful without letting it monopolize a turn."""
    auxiliary = config.setdefault("auxiliary", {})
    if not isinstance(auxiliary, dict):
        raise RuntimeError("config.yaml has non-object `auxiliary` section")
    entry = auxiliary.setdefault("session_search", {})
    if not isinstance(entry, dict):
        entry = {}
        auxiliary["session_search"] = entry

    changed: dict[str, Any] = {}

    def _number(value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    total_timeout = _number(entry.get("total_timeout"))
    if total_timeout is None or total_timeout > SESSION_SEARCH_TOTAL_TIMEOUT_SECONDS:
        changed["previous_total_timeout"] = entry.get("total_timeout")
        entry["total_timeout"] = SESSION_SEARCH_TOTAL_TIMEOUT_SECONDS

    max_concurrency = _number(entry.get("max_concurrency"))
    if max_concurrency is None or max_concurrency > SESSION_SEARCH_MAX_CONCURRENCY:
        changed["previous_max_concurrency"] = entry.get("max_concurrency")
        entry["max_concurrency"] = SESSION_SEARCH_MAX_CONCURRENCY

    timeout = _number(entry.get("timeout"))
    if timeout is None or timeout > SESSION_SEARCH_TOTAL_TIMEOUT_SECONDS:
        changed["previous_timeout"] = entry.get("timeout")
        entry["timeout"] = min(15, SESSION_SEARCH_TOTAL_TIMEOUT_SECONDS)

    return {
        "status": "normalized" if changed else "unchanged",
        "total_timeout": entry.get("total_timeout"),
        "max_concurrency": entry.get("max_concurrency"),
        "timeout": entry.get("timeout"),
        "changes": changed,
        "secret_redacted": True,
    }


def _normalize_discord_visibility_runtime_config(config: dict[str, Any]) -> dict[str, Any]:
    """Enable bounded Discord response visibility without enabling noisy tool spam."""
    changed: dict[str, Any] = {}

    def _float(value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    streaming = config.setdefault("streaming", {})
    if not isinstance(streaming, dict):
        streaming = {}
        config["streaming"] = streaming

    if streaming.get("transport") not in (None, "edit"):
        changed["previous_transport"] = streaming.get("transport")
    streaming["transport"] = "edit"

    edit_interval = _float(streaming.get("edit_interval"))
    if edit_interval is None or edit_interval < DISCORD_STREAMING_EDIT_INTERVAL_SECONDS:
        changed["previous_edit_interval"] = streaming.get("edit_interval")
        streaming["edit_interval"] = DISCORD_STREAMING_EDIT_INTERVAL_SECONDS

    buffer_threshold = _int(streaming.get("buffer_threshold"))
    if buffer_threshold is None or buffer_threshold < DISCORD_STREAMING_BUFFER_THRESHOLD:
        changed["previous_buffer_threshold"] = streaming.get("buffer_threshold")
        streaming["buffer_threshold"] = DISCORD_STREAMING_BUFFER_THRESHOLD

    display = config.setdefault("display", {})
    if not isinstance(display, dict):
        display = {}
        config["display"] = display
    platforms = display.setdefault("platforms", {})
    if not isinstance(platforms, dict):
        platforms = {}
        display["platforms"] = platforms
    discord_cfg = platforms.setdefault("discord", {})
    if not isinstance(discord_cfg, dict):
        discord_cfg = {}
        platforms["discord"] = discord_cfg

    if discord_cfg.get("streaming") is not True:
        changed["previous_discord_streaming"] = discord_cfg.get("streaming")
        discord_cfg["streaming"] = True

    return {
        "status": "normalized" if changed else "unchanged",
        "discord_streaming": discord_cfg.get("streaming"),
        "transport": streaming.get("transport"),
        "edit_interval": streaming.get("edit_interval"),
        "buffer_threshold": streaming.get("buffer_threshold"),
        "changes": changed,
        "secret_redacted": True,
    }


def _normalize_unbound_tier2_runtime(brainstack: dict[str, Any]) -> dict[str, Any]:
    """Migrate unsupported Tier-2 runtime pins to the bound internal extractor."""
    before = str(brainstack.get("tier2_runtime") or "").strip()
    route = build_tier2_runtime_spine(brainstack)
    if before == TIER2_HINDSIGHT_PUBLIC_API_BRIDGE and route.binding_status == "configured_unbound":
        brainstack["tier2_runtime"] = TIER2_INTERNAL_EXTRACTOR
        return {
            "status": "normalized",
            "previous_runtime": before,
            "replacement": TIER2_INTERNAL_EXTRACTOR,
            "reason_code": route.binding_reason_code,
            "secret_redacted": True,
        }
    return {
        "status": "unchanged",
        "runtime": before or TIER2_INTERNAL_EXTRACTOR,
        "binding_status": route.binding_status,
        "reason_code": route.binding_reason_code,
        "secret_redacted": True,
    }


def _patch_config(config_path: Path, dry_run: bool, *, embedding_runtime: str = "external") -> dict[str, Any]:
    config = _load_yaml(config_path)
    config.setdefault("memory", {})
    if not isinstance(config["memory"], dict):
        raise RuntimeError("config.yaml has non-object `memory` section")
    config["memory"]["provider"] = "brainstack"
    config["memory"]["memory_enabled"] = True
    config["memory"]["user_profile_enabled"] = True
    config.setdefault("plugins", {})
    if not isinstance(config["plugins"], dict):
        raise RuntimeError("config.yaml has non-object `plugins` section")
    brainstack = config["plugins"].setdefault("brainstack", {})
    if not isinstance(brainstack, dict):
        brainstack = {}
        config["plugins"]["brainstack"] = brainstack
    brainstack.setdefault("db_path", "$HERMES_HOME/brainstack/brainstack.db")
    brainstack.setdefault("graph_backend", "kuzu")
    brainstack.setdefault("graph_db_path", "$HERMES_HOME/brainstack/brainstack.kuzu")
    if embedding_runtime == "none":
        brainstack["corpus_backend"] = "none"
        brainstack.pop("corpus_db_path", None)
    else:
        brainstack.setdefault("corpus_backend", "chroma")
        brainstack.setdefault("corpus_db_path", "$HERMES_HOME/brainstack/brainstack.chroma")
    brainstack.setdefault("profile_prompt_limit", 6)
    brainstack.setdefault("profile_match_limit", 4)
    brainstack.setdefault("continuity_recent_limit", 4)
    brainstack.setdefault("continuity_match_limit", 4)
    brainstack.setdefault("transcript_match_limit", 1)
    brainstack.setdefault("transcript_char_budget", 280)
    brainstack.setdefault("graph_match_limit", 6)
    brainstack.setdefault("corpus_match_limit", 4)
    brainstack.setdefault("corpus_char_budget", 700)
    brainstack.setdefault("tier2_mode", "shadow")
    brainstack.setdefault("tier2_runtime", "internal_extractor")
    brainstack.setdefault("tier2_hindsight_mode", "local_embedded")
    brainstack.setdefault("tier2_hindsight_bank_id", "brainstack-tier2")
    brainstack.setdefault("tier2_hindsight_llm_provider", "hermes_managed")
    brainstack.setdefault("tier2_hindsight_llm_model", "")
    brainstack.setdefault("tier2_hindsight_llm_base_url", "")
    if _looks_like_legacy_local_tier2_llm_config(brainstack):
        brainstack["tier2_hindsight_llm_provider"] = "hermes_managed"
        brainstack["tier2_hindsight_llm_model"] = ""
        brainstack["tier2_hindsight_llm_base_url"] = ""
    tier2_runtime_hygiene = _normalize_unbound_tier2_runtime(brainstack)
    session_search_runtime_hygiene = _normalize_session_search_runtime_config(config)
    discord_visibility_hygiene = _normalize_discord_visibility_runtime_config(config)
    brainstack.setdefault("tier2_hindsight_embeddings_provider", "tei")
    brainstack.setdefault("tier2_hindsight_embeddings_tei_url", "http://127.0.0.1:7997")
    brainstack.setdefault("tier2_hindsight_reranker_provider", "rrf")
    brainstack.setdefault("tier2_hindsight_retain_extraction_mode", "chunks")
    brainstack.setdefault("tier2_hindsight_retain_extract_causal_links", False)
    brainstack.setdefault("tier2_hindsight_api_command", "/opt/hermes/.venv/bin/hindsight-api")
    brainstack.setdefault("tier2_hindsight_budget", "low")
    brainstack.setdefault("tier2_session_end_flush_enabled", True)
    auxiliary_main_route_hygiene = _normalize_hermes_native_auxiliary_main_routes(config)
    background_task_status = install_default_background_task_bindings(config)
    config.setdefault("agent", {})
    if not isinstance(config["agent"], dict):
        raise RuntimeError("config.yaml has non-object `agent` section")
    agent = config["agent"]
    proactive_runtime = _normalize_proactive_runtime_config(config)
    if not dry_run:
        _write_yaml(config_path, config)
    return {
        "config_path": str(config_path),
        "memory_provider": "brainstack",
        "memory_enabled": True,
        "user_profile_enabled": True,
        "background_task_status": background_task_status,
        "auxiliary_main_route_hygiene": auxiliary_main_route_hygiene,
        "tier2_runtime_hygiene": tier2_runtime_hygiene,
        "session_search_runtime_hygiene": session_search_runtime_hygiene,
        "discord_visibility_hygiene": discord_visibility_hygiene,
        "gateway_timeout": agent.get("gateway_timeout"),
        "gateway_timeout_warning": agent.get("gateway_timeout_warning"),
        "proactive_runtime": proactive_runtime,
    }


def _write_hermes_proactive_cron_gate_script(runtime_home: Path, target: Path, dry_run: bool) -> dict[str, Any]:
    script_path = runtime_home / "scripts" / PROACTIVE_CRON_GATE_SCRIPT_NAME
    content = f'''#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _prepend(path: Path) -> None:
    text = str(path)
    if path.exists() and text not in sys.path:
        sys.path.insert(0, text)


HERMES_HOME = Path(os.environ.get("HERMES_HOME") or Path(__file__).resolve().parents[1])
for candidate in (
    Path("/opt/hermes/extensions/hermes_proactive"),
    Path("/opt/hermes/plugins/memory"),
    Path({str(target / "extensions" / "hermes_proactive")!r}),
    Path({str(target / "plugins" / "memory")!r}),
):
    _prepend(candidate)

from hermes_proactive.config import load_runtime_config  # noqa: E402
from hermes_proactive.pulse_producer import classify_pulse_wake, produce_pulse, project_pulse_output  # noqa: E402
from hermes_proactive.workrun import checkpoint_workrun, finish_workrun, prune_completed_workruns, start_workrun  # noqa: E402


def _runtime_config() -> dict[str, object]:
    return load_runtime_config(HERMES_HOME)


def main() -> int:
    workrun = start_workrun(
        hermes_home=HERMES_HOME,
        source_kind="proactive_pulse",
        source_id="brainstack_proactive_pulse_gate",
        objective="Inspect proactive runtime signals and surface safe recovery candidates.",
        recovery_policy="rerun pulse in dry-run and inspect recovery candidates before retrying delivery",
        side_effect_risk="none",
        next_safe_action="rerun proactive pulse gate or inspect listed recovery candidates",
        metadata={{"runtime": "cron_gate"}},
    )
    try:
        cfg = _runtime_config()
        output = produce_pulse(
            hermes_home=HERMES_HOME,
            principal_scope_key="runtime:brainstack",
            workspace_scope_key="workspace:default",
            stale_inbox_threshold=1,
        )
        checkpoint_workrun(
            hermes_home=HERMES_HOME,
            run_id=str(workrun["run_id"]),
            checkpoint_ref=str(output.get("run_id") or "pulse_output"),
            next_safe_action="project pulse output only if delivery policy allows it",
        )
        mode = str(cfg.get("mode") or "dry_run")
        live_delivery = mode == "live" and not bool(cfg.get("kill_switch"))
        projection = None
        wake = classify_pulse_wake(output, create_outbox=False)
        db_path = HERMES_HOME / "brainstack" / "brainstack.db"
        if live_delivery and db_path.exists():
            projection = project_pulse_output(db_path=db_path, output=output, create_outbox=True)
            wake = projection.get("wake") or wake
        finish_workrun(
            hermes_home=HERMES_HOME,
            run_id=str(workrun["run_id"]),
            status="completed",
            output_ref=str(output.get("run_id") or ""),
            next_safe_action="none",
        )
        prune_completed_workruns(hermes_home=HERMES_HOME, keep_completed=200)
        summary = {{
            "schema": "brainstack.proactive_cron_gate.v1",
            "mode": mode,
            "kill_switch": bool(cfg.get("kill_switch")),
            "config_status": cfg.get("status"),
            "config_reason_code": cfg.get("reason_code"),
            "pulse_status": output.get("status"),
            "task_count": len([item for item in output.get("tasks") or [] if isinstance(item, dict)]),
            "event_count": len([item for item in output.get("events") or [] if isinstance(item, dict)]),
            "delivery_requested": bool(wake.get("delivery_requested")),
            "wake_decision": wake.get("decision"),
            "wake_reason_code": wake.get("reason_code"),
            "projection_written_count": int((projection or {{}}).get("written_count") or 0),
            "projection_outbox_count": int((projection or {{}}).get("outbox_count") or 0),
            "workrun_id": workrun.get("run_id"),
            "provider_calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
        }}
        print(json.dumps(summary, ensure_ascii=True, sort_keys=True))
        print(json.dumps({{"wakeAgent": bool(wake.get("delivery_requested"))}}, ensure_ascii=True, sort_keys=True))
        return 0
    except BaseException as exc:
        finish_workrun(
            hermes_home=HERMES_HOME,
            run_id=str(workrun["run_id"]),
            status="interrupted",
            error_summary=str(exc),
            next_safe_action="inspect the last checkpoint and rerun pulse if safe",
        )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
'''
    if not dry_run:
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(content, encoding="utf-8")
        try:
            script_path.chmod(0o700)
        except OSError:
            pass
    return {
        "status": "planned" if dry_run else "installed",
        "target": str(script_path),
        "script": PROACTIVE_CRON_GATE_SCRIPT_NAME,
        "mode": DEFAULT_PROACTIVE_RUNTIME_MODE,
    }


def _upsert_hermes_proactive_cron_job(runtime_home: Path, dry_run: bool) -> dict[str, Any]:
    cron_dir = runtime_home / "cron"
    jobs_path = cron_dir / "jobs.json"
    if jobs_path.exists():
        try:
            data = json.loads(jobs_path.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError:
            data = {}
    else:
        data = {}
    jobs = data.get("jobs") if isinstance(data.get("jobs"), list) else []
    now = datetime.now(timezone.utc).isoformat()
    prompt = (
        "Review the Brainstack proactive pulse gate output. If wakeAgent is false, "
        "respond exactly [SILENT]. If wakeAgent is true, summarize the proactive item "
        "briefly; do not call tools and do not deliver manually."
    )
    selected: dict[str, Any] | None = None
    for job in jobs:
        if isinstance(job, dict) and str(job.get("name") or "") == PROACTIVE_CRON_JOB_NAME:
            selected = job
            break
    action = "updated" if selected is not None else "created"
    if selected is None:
        selected = {"id": hashlib.sha256(PROACTIVE_CRON_JOB_NAME.encode("utf-8")).hexdigest()[:12], "created_at": now}
        jobs.append(selected)
    previous = {
        "enabled": selected.get("enabled"),
        "state": selected.get("state"),
        "script": selected.get("script"),
        "prompt": selected.get("prompt"),
        "deliver": selected.get("deliver"),
    }
    selected.update(
        {
            "name": PROACTIVE_CRON_JOB_NAME,
            "prompt": prompt,
            "skills": [],
            "skill": None,
            "model": None,
            "provider": None,
            "base_url": None,
            "script": PROACTIVE_CRON_GATE_SCRIPT_NAME,
            "context_from": None,
            "schedule": {"kind": "cron", "expr": "*/10 * * * *", "display": "*/10 * * * *"},
            "schedule_display": "*/10 * * * *",
            "repeat": {"times": None, "completed": int((selected.get("repeat") or {}).get("completed") or 0) if isinstance(selected.get("repeat"), dict) else 0},
            "enabled": True,
            "state": "scheduled",
            "paused_at": None,
            "paused_reason": None,
            "next_run_at": selected.get("next_run_at") or now,
            "last_run_at": selected.get("last_run_at"),
            "last_status": selected.get("last_status"),
            "last_error": selected.get("last_error"),
            "last_delivery_error": selected.get("last_delivery_error"),
            "deliver": "local",
            "origin": None,
            "enabled_toolsets": None,
            "workdir": None,
            "updated_by": "brainstack_installer",
            "updated_at": now,
        }
    )
    data["jobs"] = jobs
    data["updated_at"] = now
    if not dry_run:
        cron_dir.mkdir(parents=True, exist_ok=True)
        jobs_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        try:
            jobs_path.chmod(0o600)
        except OSError:
            pass
    return {
        "status": "planned" if dry_run else "installed",
        "action": action,
        "jobs_path": str(jobs_path),
        "job_id": str(selected.get("id") or ""),
        "script": PROACTIVE_CRON_GATE_SCRIPT_NAME,
        "schedule": "*/10 * * * *",
        "enabled": True,
        "deliver": "local",
        "previous": previous,
    }


def _write_manifest(target: Path, manifest: dict[str, Any], dry_run: bool) -> None:
    if dry_run:
        return
    path = target / ".brainstack-install-manifest.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def _relative_to_target_or_absolute(target: Path, path: Path) -> str:
    try:
        return str(path.relative_to(target))
    except ValueError:
        return str(path)


def _write_docker_start_script(target: Path, config_path: Path, compose_path: Path, dry_run: bool) -> Path:
    script_path = target / "scripts" / "hermes-brainstack-start.sh"
    legacy_path = target / "scripts" / "brainstack-start.sh"
    config_ref = _relative_to_target_or_absolute(target, config_path)
    compose_ref = _relative_to_target_or_absolute(target, compose_path)
    runtime_home = _docker_runtime_home_dir(target, config_path)
    service_ref = f"hermes-{_sanitize_compose_slug(runtime_home.name)}"
    content = """#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

CONFIG_FILE="${HERMES_CONFIG_FILE:-$REPO_ROOT/__CONFIG_REF__}"
COMPOSE_FILE="${HERMES_COMPOSE_FILE:-$REPO_ROOT/__COMPOSE_REF__}"
HERMES_HOME_DEFAULT=$(dirname -- "$CONFIG_FILE")
HERMES_HOME_DIR="${HERMES_HOME_DIR:-$HERMES_HOME_DEFAULT}"
HERMES_UID="${HERMES_UID:-$(id -u)}"
HERMES_GID="${HERMES_GID:-$(id -g)}"
export HERMES_UID HERMES_GID

SERVICE="${HERMES_DOCKER_SERVICE:-}"
EXPECTED_SERVICE="__SERVICE_REF__"
if [ -z "$SERVICE" ] && [ -f "$COMPOSE_FILE" ]; then
  if awk -v svc="$EXPECTED_SERVICE" '$0 ~ "^[[:space:]]{2}" svc ":$" { found=1 } END { exit found ? 0 : 1 }' "$COMPOSE_FILE"; then
    SERVICE="$EXPECTED_SERVICE"
  else
    SERVICE=$(awk '
      /^[[:space:]]{2}[A-Za-z0-9_.-]+:$/ { svc=$1; gsub(":","",svc); next }
      /^[[:space:]]{4}container_name:[[:space:]]*hermes-.*-live[[:space:]]*$/ && svc { print svc; exit }
    ' "$COMPOSE_FILE")
  fi
fi

dc() {
  if [ -n "$SERVICE" ]; then
    docker compose -f "$COMPOSE_FILE" "$@" "$SERVICE"
  else
    docker compose -f "$COMPOSE_FILE" "$@"
  fi
}

ACTION="${1:-start}"
HEALTHCHECK="$REPO_ROOT/scripts/hermes-gateway-healthcheck.py"

wait_for_ready() {
  if [ ! -f "$HEALTHCHECK" ]; then
    return 0
  fi
  i=0
  while [ "$i" -lt 45 ]; do
    if HERMES_HOME="$HERMES_HOME_DIR" python3 "$HEALTHCHECK" --quiet; then
      HERMES_HOME="$HERMES_HOME_DIR" python3 "$HEALTHCHECK"
      return 0
    fi
    i=$((i + 1))
    sleep 2
  done
  HERMES_HOME="$HERMES_HOME_DIR" python3 "$HEALTHCHECK" || true
  return 1
}

show_status() {
  docker compose -f "$COMPOSE_FILE" ps
  if [ -f "$HEALTHCHECK" ]; then
    HERMES_HOME="$HERMES_HOME_DIR" python3 "$HEALTHCHECK" || true
  fi
}

confirm_destructive_reset() {
  echo "======================================"
  echo "WARNING: DELETE EVERY MEMORY"
  echo "======================================"
  echo "Ez torolni fogja:"
  echo "- Brainstack adatbazist"
  echo "- session replay fajlokat"
  echo "- state.db tartalmat"
  echo "- memories cache-t"
  echo "======================================"
  printf "Ird be pontosan hogy DELETE: "
  read -r CONFIRM
  if [ "$CONFIRM" != "DELETE" ]; then
    echo "Interrupted."
    exit 1
  fi
}

purge_runtime_state() {
  CLEANUP_SERVICE="$SERVICE"
  if [ -z "$CLEANUP_SERVICE" ]; then
    echo "No compose service was detected. Set HERMES_DOCKER_SERVICE."
    exit 1
  fi
  docker compose -f "$COMPOSE_FILE" run --rm --no-deps --entrypoint sh "$CLEANUP_SERVICE" -lc '
    rm -f \
      /opt/data/gateway_state.json \
      /opt/data/gateway.pid \
      /opt/data/channel_directory.json \
      /opt/data/discord_threads.json \
      /opt/data/.skills_prompt_snapshot.json \
      /opt/data/state.db \
      /opt/data/state.db-shm \
      /opt/data/state.db-wal \
      /opt/data/brainstack/brainstack.db \
      /opt/data/brainstack/brainstack.db-shm \
      /opt/data/brainstack/brainstack.db-wal
    rm -rf /opt/data/sessions /opt/data/memories
    mkdir -p /opt/data/sessions /opt/data/memories /opt/data/brainstack
  '
}

case "$ACTION" in
  start)
    dc up -d
    wait_for_ready
    ;;
  rebuild)
    dc up -d --build
    wait_for_ready
    ;;
  full|full-rebuild)
    if [ -n "$SERVICE" ]; then
      docker compose -f "$COMPOSE_FILE" build --no-cache --pull "$SERVICE"
      docker compose -f "$COMPOSE_FILE" up -d "$SERVICE"
    else
      docker compose -f "$COMPOSE_FILE" build --no-cache --pull
      docker compose -f "$COMPOSE_FILE" up -d
    fi
    wait_for_ready
    ;;
  stop)
    dc stop
    ;;
  purge|clear-memory|clear-state)
    confirm_destructive_reset
    dc stop || true
    purge_runtime_state
    ;;
  reset)
    confirm_destructive_reset
    dc stop || true
    purge_runtime_state
    dc up -d
    wait_for_ready
    ;;
  status)
    show_status
    ;;
  logs)
    if [ -n "$SERVICE" ]; then
      docker compose -f "$COMPOSE_FILE" logs --tail 200 -f "$SERVICE"
    else
      docker compose -f "$COMPOSE_FILE" logs --tail 200 -f
    fi
    ;;
  *)
    echo "Usage: $0 [start|rebuild|full|stop|purge|reset|status|logs]" >&2
    exit 1
    ;;
esac
"""
    content = (
        content.replace("__CONFIG_REF__", config_ref)
        .replace("__COMPOSE_REF__", compose_ref)
        .replace("__SERVICE_REF__", service_ref)
    )
    if not dry_run:
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(content, encoding="utf-8")
        script_path.chmod(0o755)
        if legacy_path.exists():
            legacy_path.unlink()
    return script_path


def _write_docker_compose_file(
    target: Path,
    config_path: Path,
    compose_path: Path,
    dry_run: bool,
    *,
    embedding_runtime: str = "local-tei-jina",
) -> Path:
    runtime_home = _docker_runtime_home_dir(target, config_path)
    runtime_ref = _relative_to_target_or_absolute(target, runtime_home)
    workspace_ref = "runtime/workspace"
    service_slug = _sanitize_compose_slug(runtime_home.name)
    tei_service = ""
    tei_depends_on = ""
    tei_environment = ""
    tei_volume = ""
    if embedding_runtime == "local-tei-jina":
        tei_service = """
  tei-jina:
    image: ghcr.io/huggingface/text-embeddings-inference:cpu-1.9
    container_name: tei-jina-v5
    restart: unless-stopped
    network_mode: host
    command:
      - --model-id
      - jinaai/jina-embeddings-v5-text-small-retrieval
      - --port
      - "7997"
      - --pooling
      - last-token
      - --max-batch-tokens
      - "4096"
    volumes:
      - tei-model-cache:/data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://127.0.0.1:7997/health"]
      interval: 15s
      timeout: 10s
      retries: 40
      start_period: 300s
"""
        tei_depends_on = """    depends_on:
      tei-jina:
        condition: service_healthy
"""
        tei_environment = """      BRAINSTACK_EMBEDDINGS_PROVIDER: tei
      BRAINSTACK_EMBEDDINGS_API: tei
      BRAINSTACK_EMBEDDINGS_URL: http://127.0.0.1:7997/embed
      BRAINSTACK_EMBEDDINGS_MODEL: jinaai/jina-embeddings-v5-text-small-retrieval
      BRAINSTACK_EMBEDDINGS_QUERY_PREFIX: "query: "
      BRAINSTACK_EMBEDDINGS_DOCUMENT_PREFIX: "document: "
      BRAINSTACK_EMBEDDINGS_TIMEOUT_SECONDS: "15"
      BRAINSTACK_DISABLE_CHROMA_DEFAULT_EMBEDDING: "true"
      BRAINSTACK_TEMPORAL_EMBEDDINGS_URL: http://127.0.0.1:7997/embed
      BRAINSTACK_TEMPORAL_EMBEDDINGS_MODEL: jinaai/jina-embeddings-v5-text-small-retrieval
      BRAINSTACK_TEMPORAL_EMBEDDINGS_QUERY_PREFIX: "query: "
      BRAINSTACK_TEMPORAL_EMBEDDINGS_DOCUMENT_PREFIX: "document: "
      BRAINSTACK_TEMPORAL_EMBEDDINGS_TIMEOUT_SECONDS: "15"
"""
        tei_volume = """
volumes:
  tei-model-cache:
"""
    tier2_hindsight_environment = """      BRAINSTACK_TIER2_MODE: shadow
      BRAINSTACK_TIER2_HINDSIGHT_MODE: local_embedded
      BRAINSTACK_TIER2_HINDSIGHT_PROFILE: brainstack-tier2
      BRAINSTACK_TIER2_HINDSIGHT_BANK_ID: brainstack-tier2
      BRAINSTACK_TIER2_HINDSIGHT_LLM_PROVIDER: hermes_managed
      BRAINSTACK_TIER2_HINDSIGHT_LLM_MODEL: ""
      BRAINSTACK_TIER2_HINDSIGHT_LLM_BASE_URL: ""
      BRAINSTACK_TIER2_HINDSIGHT_EMBEDDINGS_PROVIDER: tei
      BRAINSTACK_TIER2_HINDSIGHT_EMBEDDINGS_TEI_URL: http://127.0.0.1:7997
      BRAINSTACK_TIER2_HINDSIGHT_RERANKER_PROVIDER: rrf
      BRAINSTACK_TIER2_HINDSIGHT_RETAIN_EXTRACTION_MODE: chunks
      BRAINSTACK_TIER2_HINDSIGHT_RETAIN_EXTRACT_CAUSAL_LINKS: "false"
      BRAINSTACK_TIER2_HINDSIGHT_API_COMMAND: /opt/hermes/.venv/bin/hindsight-api
      BRAINSTACK_TIER2_HINDSIGHT_BUDGET: low
      BRAINSTACK_TIER2_HINDSIGHT_TIMEOUT_SECONDS: "180"
      BRAINSTACK_TIER2_HINDSIGHT_RETAIN_ASYNC: "false"
"""
    content = f"""name: hermes-{service_slug}

services:
{tei_service}
  hermes-{service_slug}:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: hermes-{service_slug}-live
    working_dir: /opt/data
    restart: unless-stopped
    network_mode: host
    command: ["gateway", "run", "--replace"]
{tei_depends_on}
    environment:
      HERMES_HOME: /opt/data
      HERMES_ENABLE_PROJECT_PLUGINS: "true"
      PYTHONPATH: /opt/hermes/plugins/memory
      HERMES_UID: "${{HERMES_UID:-1000}}"
      HERMES_GID: "${{HERMES_GID:-1000}}"
      DISCORD_ALLOW_BOTS: "mentions"
      TERMINAL_CWD: /workspace
      PATH: /opt/hermes/.venv/bin:/opt/data/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
{tier2_hindsight_environment}
{tei_environment}
    volumes:
      - ./{runtime_ref}:/opt/data
      - ./{workspace_ref}:/workspace
    healthcheck:
      test: ["CMD", "python3", "/opt/hermes/scripts/hermes-gateway-healthcheck.py", "--quiet"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
{tei_volume}
"""
    if not dry_run:
        compose_path.parent.mkdir(parents=True, exist_ok=True)
        compose_path.write_text(content, encoding="utf-8")
    return compose_path


def _patch_compose_runtime_identity(path: Path, dry_run: bool) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []
    old_text = text
    text, inserted_plugins = _compose_ensure_env(
        text,
        "HERMES_ENABLE_PROJECT_PLUGINS",
        '"true"',
        list_value="true",
    )
    if inserted_plugins:
        applied.append("compose:enable_project_plugins")
    text, inserted_home = _compose_ensure_env(
        text,
        "HERMES_HOME",
        "/opt/data",
        list_value="/opt/data",
    )
    if inserted_home:
        applied.append("compose:hermes_home")
    text, inserted_uid = _compose_ensure_env(
        text,
        "HERMES_UID",
        '"${HERMES_UID:-1000}"',
        list_value="${HERMES_UID:-1000}",
    )
    text, inserted_gid = _compose_ensure_env(
        text,
        "HERMES_GID",
        '"${HERMES_GID:-1000}"',
        list_value="${HERMES_GID:-1000}",
    )
    if inserted_uid or inserted_gid:
        applied.append("compose:runtime_identity_mapping")
    if text == old_text:
        return applied
    if not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _compose_env_present(text: str, key: str) -> bool:
    return re.search(rf"(?m)^\s*(?:-\s*)?{re.escape(key)}(?::|=)", text) is not None


def _compose_detect_environment_style(text: str) -> str:
    if re.search(r"(?m)^\s*-\s*[A-Z0-9_]+=", text):
        return "list"
    return "mapping"


def _compose_ensure_env(
    text: str,
    key: str,
    mapping_value: str,
    *,
    list_value: str | None = None,
    after_keys: tuple[str, ...] = (),
) -> tuple[str, bool]:
    if _compose_env_present(text, key):
        return text, False

    style = _compose_detect_environment_style(text)
    if style == "list":
        rendered_value = list_value if list_value is not None else mapping_value.strip("\"")
        entry = _compose_list_env_entry(key, rendered_value)
        anchors = [
            re.compile(rf"(?m)^      - {re.escape(anchor_key)}=.*\n")
            for anchor_key in after_keys
        ] + [
            re.compile(r"(?m)^      - HERMES_GID=.*\n"),
            re.compile(r"(?m)^      - HERMES_UID=.*\n"),
            re.compile(r"(?m)^    environment:\n"),
        ]
    else:
        entry = f"      {key}: {mapping_value}\n"
        anchors = [
            re.compile(rf"(?m)^      {re.escape(anchor_key)}: .*\n")
            for anchor_key in after_keys
        ] + [
            re.compile(r"(?m)^      HERMES_ENABLE_PROJECT_PLUGINS: .*\n"),
            re.compile(r"(?m)^      HERMES_GID: .*\n"),
            re.compile(r"(?m)^      HERMES_UID: .*\n"),
            re.compile(r"(?m)^      HERMES_HOME: .*\n"),
            re.compile(r"(?m)^    environment:\n"),
        ]

    for anchor in anchors:
        match = anchor.search(text)
        if match:
            return text[: match.end()] + entry + text[match.end() :], True
    raise RuntimeError(f"Installer patch anchor missing for compose env {key}")


def _compose_list_env_entry(key: str, value: str) -> str:
    scalar = f"{key}={value}"
    if _compose_list_env_scalar_needs_quotes(scalar):
        return f"      - {json.dumps(scalar, ensure_ascii=True)}\n"
    return f"      - {scalar}\n"


def _compose_list_env_scalar_needs_quotes(scalar: str) -> bool:
    return ": " in scalar or scalar.endswith(" ") or scalar.startswith(("{", "[", "&", "*", "!", "|", ">"))


def _compose_quote_existing_list_env(text: str, key: str) -> tuple[str, bool]:
    pattern = re.compile(rf"(?m)^(?P<indent>\s*)-\s+{re.escape(key)}=(?P<value>.*)$")

    def repl(match: re.Match[str]) -> str:
        scalar = f"{key}={match.group('value')}"
        if not _compose_list_env_scalar_needs_quotes(scalar):
            return match.group(0)
        return f"{match.group('indent')}- {json.dumps(scalar, ensure_ascii=True)}"

    updated, count = pattern.subn(repl, text)
    return updated, updated != text and count > 0


def _patch_compose_plugin_pythonpath(path: Path, dry_run: bool) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    if _compose_env_present(text, "PYTHONPATH") and "/opt/hermes/plugins/memory" not in text:
        raise RuntimeError(f"Refusing to overwrite existing compose PYTHONPATH in {path}")
    text, inserted = _compose_ensure_env(
        text,
        "PYTHONPATH",
        "/opt/hermes/plugins/memory",
        list_value="/opt/hermes/plugins/memory",
        after_keys=("HERMES_ENABLE_PROJECT_PLUGINS",),
    )
    if inserted and not dry_run:
        path.write_text(text, encoding="utf-8")
    return ["compose:plugin_pythonpath"] if inserted else []


def _patch_compose_discord_bot_mentions(path: Path, dry_run: bool) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    if _compose_env_present(text, "DISCORD_ALLOW_BOTS"):
        return []
    text, inserted = _compose_ensure_env(
        text,
        "DISCORD_ALLOW_BOTS",
        '"mentions"',
        list_value="mentions",
        after_keys=("PYTHONPATH",),
    )
    if inserted and not dry_run:
        path.write_text(text, encoding="utf-8")
    return ["compose:discord_allow_bot_mentions"] if inserted else []


def _patch_compose_terminal_workspace_cwd(path: Path, dry_run: bool) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    original = text
    patches: list[str] = []
    text, inserted = _compose_ensure_env(
        text,
        "TERMINAL_CWD",
        "/workspace",
        list_value="/workspace",
        after_keys=("DISCORD_ALLOW_BOTS",),
    )
    if inserted:
        patches.append("compose:terminal_cwd_workspace")

    if _compose_env_present(text, "PATH") and "/opt/hermes/.venv/bin" not in text:
        raise RuntimeError(f"Refusing to overwrite existing compose PATH in {path}")
    text, inserted_path = _compose_ensure_env(
        text,
        "PATH",
        "/opt/hermes/.venv/bin:/opt/data/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        list_value="/opt/hermes/.venv/bin:/opt/data/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        after_keys=("TERMINAL_CWD",),
    )
    if inserted_path:
        patches.append("compose:terminal_path_hermes_venv")

    text, inserted_mount = _compose_ensure_workspace_mount(text)
    if inserted_mount:
        patches.append("compose:workspace_mount")

    if text != original and not dry_run:
        path.write_text(text, encoding="utf-8")
    return patches


def _compose_has_workspace_mount(text: str) -> bool:
    return bool(
        re.search(r"(?m)^\s*-\s+[^#\n]+:/workspace\s*$", text)
        or re.search(r"(?m)^\s*target:\s*/workspace\s*$", text)
    )


def _compose_ensure_workspace_mount(text: str) -> tuple[str, bool]:
    if _compose_has_workspace_mount(text):
        return text, False

    mount_line = "      - ./runtime/workspace:/workspace\n"
    service_volumes = re.search(r"(?m)^    volumes:\n", text)
    if service_volumes:
        return text[: service_volumes.end()] + mount_line + text[service_volumes.end() :], True

    environment_block = re.search(r"(?ms)^    environment:\n(?:^      .+\n)+", text)
    if environment_block:
        volumes_block = "    volumes:\n" + mount_line
        return text[: environment_block.end()] + volumes_block + text[environment_block.end() :], True

    raise RuntimeError("Installer patch anchor missing for compose workspace mount")


def _patch_compose_hindsight_local_tier2_runtime(path: Path, dry_run: bool) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    old_text = text
    mapping_uses_legacy_local_llm = bool(
        re.search(r"(?m)^\s+BRAINSTACK_TIER2_HINDSIGHT_LLM_PROVIDER:\s*ollama\s*$", text)
    )
    list_uses_legacy_local_llm = bool(
        re.search(r"(?m)^\s+-\s+BRAINSTACK_TIER2_HINDSIGHT_LLM_PROVIDER=ollama\s*$", text)
    )
    if mapping_uses_legacy_local_llm:
        text = re.sub(
            r"(?m)^(\s+)BRAINSTACK_TIER2_HINDSIGHT_LLM_PROVIDER:\s*ollama\s*$",
            r"\1BRAINSTACK_TIER2_HINDSIGHT_LLM_PROVIDER: hermes_managed",
            text,
        )
        text = re.sub(
            r"(?m)^(\s+)BRAINSTACK_TIER2_HINDSIGHT_LLM_MODEL:\s*.*$",
            r'\1BRAINSTACK_TIER2_HINDSIGHT_LLM_MODEL: ""',
            text,
        )
        text = re.sub(
            r"(?m)^(\s+)BRAINSTACK_TIER2_HINDSIGHT_LLM_BASE_URL:\s*.*$",
            r'\1BRAINSTACK_TIER2_HINDSIGHT_LLM_BASE_URL: ""',
            text,
        )
    if list_uses_legacy_local_llm:
        text = re.sub(
            r"(?m)^(\s+-\s+)BRAINSTACK_TIER2_HINDSIGHT_LLM_PROVIDER=ollama\s*$",
            r"\1BRAINSTACK_TIER2_HINDSIGHT_LLM_PROVIDER=hermes_managed",
            text,
        )
        text = re.sub(
            r"(?m)^(\s+-\s+)BRAINSTACK_TIER2_HINDSIGHT_LLM_MODEL=.*$",
            r"\1BRAINSTACK_TIER2_HINDSIGHT_LLM_MODEL=",
            text,
        )
        text = re.sub(
            r"(?m)^(\s+-\s+)BRAINSTACK_TIER2_HINDSIGHT_LLM_BASE_URL=.*$",
            r"\1BRAINSTACK_TIER2_HINDSIGHT_LLM_BASE_URL=",
            text,
        )
    specs = (
        ("BRAINSTACK_TIER2_MODE", "shadow", "shadow", ("TERMINAL_CWD",)),
        ("BRAINSTACK_TIER2_HINDSIGHT_MODE", "local_embedded", "local_embedded", ("BRAINSTACK_TIER2_MODE",)),
        ("BRAINSTACK_TIER2_HINDSIGHT_PROFILE", "brainstack-tier2", "brainstack-tier2", ("BRAINSTACK_TIER2_HINDSIGHT_MODE",)),
        ("BRAINSTACK_TIER2_HINDSIGHT_BANK_ID", "brainstack-tier2", "brainstack-tier2", ("BRAINSTACK_TIER2_HINDSIGHT_PROFILE",)),
        ("BRAINSTACK_TIER2_HINDSIGHT_LLM_PROVIDER", "hermes_managed", "hermes_managed", ("BRAINSTACK_TIER2_HINDSIGHT_BANK_ID",)),
        ("BRAINSTACK_TIER2_HINDSIGHT_LLM_MODEL", '""', "", ("BRAINSTACK_TIER2_HINDSIGHT_LLM_PROVIDER",)),
        ("BRAINSTACK_TIER2_HINDSIGHT_LLM_BASE_URL", '""', "", ("BRAINSTACK_TIER2_HINDSIGHT_LLM_MODEL",)),
        ("BRAINSTACK_TIER2_HINDSIGHT_EMBEDDINGS_PROVIDER", "tei", "tei", ("BRAINSTACK_TIER2_HINDSIGHT_LLM_BASE_URL",)),
        ("BRAINSTACK_TIER2_HINDSIGHT_EMBEDDINGS_TEI_URL", "http://127.0.0.1:7997", "http://127.0.0.1:7997", ("BRAINSTACK_TIER2_HINDSIGHT_EMBEDDINGS_PROVIDER",)),
        ("BRAINSTACK_TIER2_HINDSIGHT_RERANKER_PROVIDER", "rrf", "rrf", ("BRAINSTACK_TIER2_HINDSIGHT_EMBEDDINGS_TEI_URL",)),
        ("BRAINSTACK_TIER2_HINDSIGHT_RETAIN_EXTRACTION_MODE", "chunks", "chunks", ("BRAINSTACK_TIER2_HINDSIGHT_RERANKER_PROVIDER",)),
        ("BRAINSTACK_TIER2_HINDSIGHT_RETAIN_EXTRACT_CAUSAL_LINKS", '"false"', "false", ("BRAINSTACK_TIER2_HINDSIGHT_RETAIN_EXTRACTION_MODE",)),
        ("BRAINSTACK_TIER2_HINDSIGHT_API_COMMAND", "/opt/hermes/.venv/bin/hindsight-api", "/opt/hermes/.venv/bin/hindsight-api", ("BRAINSTACK_TIER2_HINDSIGHT_RETAIN_EXTRACT_CAUSAL_LINKS",)),
        ("BRAINSTACK_TIER2_HINDSIGHT_BUDGET", "low", "low", ("BRAINSTACK_TIER2_HINDSIGHT_API_COMMAND",)),
        ("BRAINSTACK_TIER2_HINDSIGHT_TIMEOUT_SECONDS", '"180"', "180", ("BRAINSTACK_TIER2_HINDSIGHT_BUDGET",)),
        ("BRAINSTACK_TIER2_HINDSIGHT_RETAIN_ASYNC", '"false"', "false", ("BRAINSTACK_TIER2_HINDSIGHT_TIMEOUT_SECONDS",)),
    )
    applied = text != old_text
    for key, mapping_value, list_value, after_keys in specs:
        text, inserted = _compose_ensure_env(
            text,
            key,
            mapping_value,
            list_value=list_value,
            after_keys=after_keys,
        )
        applied = applied or inserted
        text, normalized = _compose_quote_existing_list_env(text, key)
        applied = applied or normalized
    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return ["compose:hindsight_local_tier2_runtime"] if applied else []


def _patch_compose_remove_discord_forced_heavy_profile(path: Path, dry_run: bool) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    old_text = text
    for line in (
        "      HERMES_DISCORD_TURN_PROFILE: heavy\n",
        "      HERMES_DISCORD_TOOL_PROFILE: heavy\n",
        "      - HERMES_DISCORD_TURN_PROFILE=heavy\n",
        "      - HERMES_DISCORD_TOOL_PROFILE=heavy\n",
    ):
        text = text.replace(line, "")
    if text == old_text:
        return []
    if not dry_run:
        path.write_text(text, encoding="utf-8")
    return ["compose:remove_discord_forced_heavy_profile"]


_LOCAL_TEI_JINA_SERVICE = """
  tei-jina:
    image: ghcr.io/huggingface/text-embeddings-inference:cpu-1.9
    container_name: tei-jina-v5
    restart: unless-stopped
    network_mode: host
    command:
      - --model-id
      - jinaai/jina-embeddings-v5-text-small-retrieval
      - --port
      - "7997"
      - --pooling
      - last-token
      - --max-batch-tokens
      - "4096"
    volumes:
      - tei-model-cache:/data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://127.0.0.1:7997/health"]
      interval: 15s
      timeout: 10s
      retries: 40
      start_period: 300s
"""


def _compose_insert_local_tei_service(text: str) -> tuple[str, bool]:
    if "  tei-jina:\n" in text:
        return text, False
    marker = "services:\n"
    if marker not in text:
        raise RuntimeError("Installer patch anchor missing for compose services")
    return text.replace(marker, marker + _LOCAL_TEI_JINA_SERVICE, 1), True


def _compose_normalize_local_tei_service(text: str) -> tuple[str, bool]:
    pattern = re.compile(r"(?ms)^  tei-jina:\n.*?(?=^  [A-Za-z0-9_.-]+:\n|^volumes:\n|\Z)")

    def _normalize(match: re.Match[str]) -> str:
        block = match.group(0)
        updated = block
        if "    network_mode: host\n" not in updated:
            updated = updated.replace(
                "    restart: unless-stopped\n",
                "    restart: unless-stopped\n    network_mode: host\n",
                1,
            )
        updated = re.sub(
            r"(?m)^      - --port\n      - \"80\"\n",
            '      - --port\n      - "7997"\n',
            updated,
            count=1,
        )
        updated = re.sub(
            r'(?m)^    ports:\n      - "7997:80"\n',
            "",
            updated,
            count=1,
        )
        updated = updated.replace(
            '      test: ["CMD", "curl", "-f", "http://localhost/health"]\n',
            '      test: ["CMD", "curl", "-f", "http://127.0.0.1:7997/health"]\n',
            1,
        )
        return updated

    normalized = pattern.sub(_normalize, text, count=1)
    return normalized, normalized != text


def _compose_insert_local_tei_dependency(text: str) -> tuple[str, bool]:
    if re.search(r"(?m)^    depends_on:\n      tei-jina:\n        condition: service_healthy\n", text):
        return text, False
    dependency = "    depends_on:\n      tei-jina:\n        condition: service_healthy\n"
    command_anchor = re.search(r'(?m)^    command: \["gateway", "run", "--replace"\]\n', text)
    if command_anchor:
        return text[: command_anchor.end()] + dependency + text[command_anchor.end() :], True
    environment_anchor = re.search(r"(?m)^    environment:\n", text)
    if environment_anchor:
        return text[: environment_anchor.start()] + dependency + text[environment_anchor.start() :], True
    raise RuntimeError("Installer patch anchor missing for compose TEI dependency")


def _compose_insert_named_volume(text: str, volume_name: str) -> tuple[str, bool]:
    if re.search(rf"(?m)^  {re.escape(volume_name)}:\n", text):
        return text, False
    if re.search(r"(?m)^volumes:\n", text):
        return re.sub(r"(?m)^volumes:\n", f"volumes:\n  {volume_name}:\n", text, count=1), True
    return text.rstrip() + f"\n\nvolumes:\n  {volume_name}:\n", True


def _patch_compose_local_tei_jina_runtime(path: Path, dry_run: bool) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    old_text = text
    applied: list[str] = []
    text, inserted_service = _compose_insert_local_tei_service(text)
    if inserted_service:
        applied.append("compose:local_tei_jina_service")
    text, normalized_service = _compose_normalize_local_tei_service(text)
    if normalized_service:
        applied.append("compose:local_tei_jina_service_normalized")
    text, inserted_dependency = _compose_insert_local_tei_dependency(text)
    if inserted_dependency:
        applied.append("compose:local_tei_jina_dependency")
    env_specs = (
        ("BRAINSTACK_EMBEDDINGS_PROVIDER", "tei", "tei", ("TERMINAL_CWD", "DISCORD_ALLOW_BOTS", "PYTHONPATH")),
        ("BRAINSTACK_EMBEDDINGS_API", "tei", "tei", ("BRAINSTACK_EMBEDDINGS_PROVIDER",)),
        ("BRAINSTACK_EMBEDDINGS_URL", "http://127.0.0.1:7997/embed", "http://127.0.0.1:7997/embed", ("BRAINSTACK_EMBEDDINGS_API",)),
        ("BRAINSTACK_EMBEDDINGS_MODEL", "jinaai/jina-embeddings-v5-text-small-retrieval", "jinaai/jina-embeddings-v5-text-small-retrieval", ("BRAINSTACK_EMBEDDINGS_URL",)),
        ("BRAINSTACK_EMBEDDINGS_QUERY_PREFIX", '"query: "', "query: ", ("BRAINSTACK_EMBEDDINGS_MODEL",)),
        ("BRAINSTACK_EMBEDDINGS_DOCUMENT_PREFIX", '"document: "', "document: ", ("BRAINSTACK_EMBEDDINGS_QUERY_PREFIX",)),
        ("BRAINSTACK_EMBEDDINGS_TIMEOUT_SECONDS", '"15"', "15", ("BRAINSTACK_EMBEDDINGS_DOCUMENT_PREFIX",)),
        ("BRAINSTACK_DISABLE_CHROMA_DEFAULT_EMBEDDING", '"true"', "true", ("BRAINSTACK_EMBEDDINGS_TIMEOUT_SECONDS",)),
        ("BRAINSTACK_TEMPORAL_EMBEDDINGS_URL", "http://127.0.0.1:7997/embed", "http://127.0.0.1:7997/embed", ("BRAINSTACK_DISABLE_CHROMA_DEFAULT_EMBEDDING",)),
        ("BRAINSTACK_TEMPORAL_EMBEDDINGS_MODEL", "jinaai/jina-embeddings-v5-text-small-retrieval", "jinaai/jina-embeddings-v5-text-small-retrieval", ("BRAINSTACK_TEMPORAL_EMBEDDINGS_URL",)),
        ("BRAINSTACK_TEMPORAL_EMBEDDINGS_QUERY_PREFIX", '"query: "', "query: ", ("BRAINSTACK_TEMPORAL_EMBEDDINGS_MODEL",)),
        ("BRAINSTACK_TEMPORAL_EMBEDDINGS_DOCUMENT_PREFIX", '"document: "', "document: ", ("BRAINSTACK_TEMPORAL_EMBEDDINGS_QUERY_PREFIX",)),
        ("BRAINSTACK_TEMPORAL_EMBEDDINGS_TIMEOUT_SECONDS", '"15"', "15", ("BRAINSTACK_TEMPORAL_EMBEDDINGS_DOCUMENT_PREFIX",)),
    )
    inserted_env = False
    for key, mapping_value, list_value, after_keys in env_specs:
        text, inserted = _compose_ensure_env(text, key, mapping_value, list_value=list_value, after_keys=after_keys)
        inserted_env = inserted_env or inserted
        text, normalized_env = _compose_quote_existing_list_env(text, key)
        inserted_env = inserted_env or normalized_env
    if inserted_env:
        applied.append("compose:local_tei_jina_environment")
    text, inserted_volume = _compose_insert_named_volume(text, "tei-model-cache")
    if inserted_volume:
        applied.append("compose:local_tei_jina_volume")
    if text != old_text and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _patch_dockerignore(path: Path, dry_run: bool) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    if "hermes-config/\nruntime/\n" in text:
        return []
    block = (
        "# Runtime data mounted into the container at /opt/data or /workspace.\n"
        "# These must stay out of the image build context:\n"
        "# - they are not needed for image construction\n"
        "# - they may have restrictive ownership from the running container user\n"
        "# - including them can break rebuilds on host-side permission checks\n"
        "hermes-config/\n"
        "runtime/\n\n"
    )
    anchor = "*.md\n"
    if anchor not in text:
        raise RuntimeError(f"Installer patch anchor missing for dockerignore in {path}")
    text = text.replace(anchor, block + anchor, 1)
    if not dry_run:
        path.write_text(text, encoding="utf-8")
    return ["dockerignore:exclude_runtime_state"]


def _patch_dockerfile_backend_dependencies(path: Path, dry_run: bool) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    backend_packages = " ".join(sorted(set(BACKEND_DEPENDENCIES.values())))
    install_line = f'uv pip install --no-cache-dir {backend_packages}'
    if install_line in text:
        return []
    existing_backend_pattern = re.compile(
        r"uv pip install --no-cache-dir (?=[^\n]*(?:chromadb|kuzu))[^\n]*"
    )
    if existing_backend_pattern.search(text):
        text = existing_backend_pattern.sub(install_line, text, count=1)
        if not dry_run:
            path.write_text(text, encoding="utf-8")
        return ["dockerfile:install_runtime_dependencies"]
    anchors = (
        '    uv pip install --no-cache-dir -e ".[all]"\n',
        "RUN uv sync --frozen --no-install-project --extra all\n",
    )
    for anchor in anchors:
        if anchor in text:
            text = text.replace(anchor, anchor + f"RUN {install_line}\n", 1)
            break
    else:
        raise RuntimeError(f"Installer patch anchor missing for docker backend deps in {path}")
    if not dry_run:
        path.write_text(text, encoding="utf-8")
    return ["dockerfile:install_backend_dependencies"]


def _patch_dockerfile_workstation_python_alias(path: Path, dry_run: bool) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    legacy_alias_line = "RUN ln -sf /usr/bin/python3 /usr/local/bin/python\n"
    wrapper_line = (
        "RUN printf '%s\\n' '#!/bin/sh' 'exec /opt/hermes/.venv/bin/python \"$@\"' "
        "> /usr/local/bin/python && chmod 0755 /usr/local/bin/python\n"
    )
    if wrapper_line in text:
        return []
    if legacy_alias_line in text:
        text = text.replace(legacy_alias_line, wrapper_line, 1)
        if not dry_run:
            path.write_text(text, encoding="utf-8")
        return ["dockerfile:workstation_python_alias"]
    anchors = (
        'RUN uv pip install --no-cache-dir --no-deps -e "."\n',
        '    uv pip install --no-cache-dir -e ".[all]"\n',
        "RUN uv sync --frozen --no-install-project --extra all\n",
    )
    for anchor in anchors:
        if anchor in text:
            text = text.replace(anchor, anchor + wrapper_line, 1)
            break
    else:
        raise RuntimeError(f"Installer patch anchor missing for Docker python alias in {path}")
    if not dry_run:
        path.write_text(text, encoding="utf-8")
    return ["dockerfile:workstation_python_alias"]


def _patch_docker_entrypoint(path: Path, dry_run: bool) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []
    ownership_block = """fix_critical_runtime_ownership() {
    target_uid=$(id -u hermes)
    target_gid=$(id -g hermes)
    for path in \\
        "$HERMES_HOME/.env" \\
        "$HERMES_HOME/config.yaml" \\
        "$HERMES_HOME/auth.json" \\
        "$HERMES_HOME/auth.lock" \\
        "$HERMES_HOME/gateway_state.json" \\
        "$HERMES_HOME/gateway.pid" \\
        "$HERMES_HOME/state.db" \\
        "$HERMES_HOME/state.db-shm" \\
        "$HERMES_HOME/state.db-wal" \\
        "$HERMES_HOME/brainstack" \\
        "$HERMES_HOME/sessions" \\
        "$HERMES_HOME/memories"
    do
        [ -e "$path" ] || continue
        owner_uid=$(stat -c %u "$path" 2>/dev/null || echo "")
        owner_gid=$(stat -c %g "$path" 2>/dev/null || echo "")
        if [ "$owner_uid" != "$target_uid" ] || [ "$owner_gid" != "$target_gid" ]; then
            chown -R hermes:hermes "$path" 2>/dev/null || \\
                echo "Warning: failed to normalize ownership for $path"
        fi
    done
}

"""
    if "fix_critical_runtime_ownership()" not in text:
        anchor = 'INSTALL_DIR="/opt/hermes"\n\n'
        if anchor not in text:
            raise RuntimeError(f"Installer patch anchor missing for docker entrypoint function in {path}")
        text = text.replace(anchor, anchor + ownership_block, 1)
        applied.append("docker_entrypoint:normalize_runtime_ownership_function")

    if "\n    fix_critical_runtime_ownership\n" not in text:
        anchor = (
            '        chown -R hermes:hermes "$HERMES_HOME" 2>/dev/null || \\\n'
            '            echo "Warning: chown failed (rootless container?) — continuing anyway"\n'
            "    fi\n\n"
        )
        inject = anchor + (
            "    # Rebuild/login flows can leave a few critical files owned by root even\n"
            "    # when the top-level volume already belongs to hermes. Normalize the\n"
            "    # small runtime-critical surface before we drop privileges so the gateway\n"
            "    # never boots with an unreadable auth/config state.\n"
            "    fix_critical_runtime_ownership\n\n"
        )
        if anchor not in text:
            raise RuntimeError(f"Installer patch anchor missing for docker entrypoint call in {path}")
        text = text.replace(anchor, inject, 1)
        applied.append("docker_entrypoint:normalize_runtime_ownership_call")

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _write_docker_healthcheck_script(target: Path, dry_run: bool) -> Path:
    script_path = target / "scripts" / "hermes-gateway-healthcheck.py"
    content = """#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _status_path() -> Path:
    hermes_home = Path(os.getenv("HERMES_HOME", "/opt/data"))
    return hermes_home / "gateway_state.json"


def _load_status() -> dict:
    path = _status_path()
    if not path.exists():
        raise RuntimeError(f"missing status file: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid status json: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("status payload is not an object")
    return payload


def _evaluate(payload: dict) -> tuple[bool, str]:
    gateway_state = str(payload.get("gateway_state") or "unknown")
    exit_reason = payload.get("exit_reason")
    platforms = payload.get("platforms")
    if not isinstance(platforms, dict):
        platforms = {}

    connected = []
    platform_states = {}
    for name, info in platforms.items():
        if not isinstance(info, dict):
            continue
        state = str(info.get("state") or "unknown")
        platform_states[name] = state
        if state == "connected":
            connected.append(name)

    if gateway_state in {"running", "degraded"} and connected:
        return True, f"{gateway_state}; connected={','.join(sorted(connected))}"

    details = [f"gateway_state={gateway_state}"]
    if exit_reason:
        details.append(f"exit_reason={exit_reason}")
    if platform_states:
        details.append(
            "platforms=" + ",".join(f"{name}:{state}" for name, state in sorted(platform_states.items()))
        )
    else:
        details.append("platforms=none")
    return False, "; ".join(details)


def main() -> int:
    parser = argparse.ArgumentParser(description="Readiness-aware Hermes gateway healthcheck")
    parser.add_argument("--quiet", action="store_true", help="Only use exit code")
    args = parser.parse_args()

    try:
        payload = _load_status()
        ok, message = _evaluate(payload)
    except Exception as exc:
        if not args.quiet:
            print(f"gateway healthcheck failed: {exc}", file=sys.stderr)
        return 1

    if not args.quiet:
        stream = sys.stdout if ok else sys.stderr
        print(message, file=stream)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
"""
    if not dry_run:
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(content, encoding="utf-8")
        script_path.chmod(0o755)
    return script_path


def _patch_compose_healthcheck(path: Path, dry_run: bool) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []
    command_plain = '    command: ["gateway", "run"]\n'
    command_replace = '    command: ["gateway", "run", "--replace"]\n'
    if command_replace not in text and command_plain in text:
        text = text.replace(command_plain, command_replace, 1)
        applied.append("compose:gateway_run_replace")
    old = '      test: ["CMD-SHELL", "tr \'\\\\000\' \' \' </proc/1/cmdline | grep -q \'hermes gateway run --replace\' || exit 1"]\n'
    new = '      test: ["CMD", "python3", "/opt/hermes/scripts/hermes-gateway-healthcheck.py", "--quiet"]\n'
    if new not in text and old in text:
        text = text.replace(old, new, 1)
        applied.append("compose:readiness_healthcheck")
    elif "hermes-gateway-healthcheck.py" not in text and command_replace in text:
        healthcheck = (
            command_replace
            + "    healthcheck:\n"
            + '      test: ["CMD", "python3", "/opt/hermes/scripts/hermes-gateway-healthcheck.py", "--quiet"]\n'
            + "      interval: 30s\n"
            + "      timeout: 10s\n"
            + "      retries: 3\n"
            + "      start_period: 20s\n"
        )
        text = text.replace(command_replace, healthcheck, 1)
        applied.append("compose:readiness_healthcheck")
    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _run_doctor(
    target: Path,
    args: argparse.Namespace,
    planned_install: bool,
    *,
    config_path: Path,
    compose_path: Path | None,
) -> int:
    doctor_path = REPO_ROOT / "scripts" / "brainstack_doctor.py"
    spec = importlib.util.spec_from_file_location("brainstack_doctor_runtime", doctor_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load doctor module from {doctor_path}")
    doctor_mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = doctor_mod
    spec.loader.exec_module(doctor_mod)

    doctor_args = argparse.Namespace(
        target=str(target),
        config=str(config_path),
        compose_file=str(compose_path) if compose_path else None,
        desktop_launcher=str(args.desktop_launcher) if args.desktop_launcher else None,
        python=str(args.python or _default_target_python(target)) if (args.python or _default_target_python(target)) else None,
        runtime=args.runtime,
        planned_install=planned_install,
        check_docker=args.runtime != "local",
        check_desktop_launcher=True,
        json=False,
    )
    code, checks = doctor_mod.run_doctor(doctor_args)
    for check in checks:
        marker = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}[check.status]
        stream = sys.stderr if check.status == "fail" else sys.stdout
        print(f"{marker} {check.name}: {check.message}", file=stream)
    return code


def _resolve_enabled_runtime_contract(args: argparse.Namespace) -> str | None:
    """Make the default full install self-consistent before planning files.

    The default embedding runtime is local TEI Jina v5. That runtime is managed
    by the Docker compose installer path, so an enabled install with
    ``--runtime auto`` must resolve to Docker instead of failing closed. An
    explicit ``--runtime local`` remains rejected because the installer does not
    manage a host-native TEI service.
    """
    if not args.enable or args.embedding_runtime != "local-tei-jina":
        return None
    if args.runtime == "auto":
        args.runtime = "docker"
        return "INFO --runtime auto resolved to docker for local TEI Jina v5 embedding runtime."
    if args.runtime != "docker":
        raise RuntimeError(
            "--embedding-runtime local-tei-jina requires Docker runtime. "
            "Use --runtime auto or --runtime docker so the installer can create/manage the TEI Jina v5 service; "
            "use --embedding-runtime external only for an operator-managed embedding endpoint, "
            "or --embedding-runtime none to configure corpus search unavailable instead of broken Chroma."
        )
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Install Brainstack into a target Hermes checkout.")
    parser.add_argument("target", help="Path to target Hermes checkout")
    parser.add_argument("--config", type=Path, help="Path to Hermes config.yaml")
    parser.add_argument("--compose-file", type=Path, help="Path to Docker compose file for doctor checks")
    parser.add_argument("--desktop-launcher", type=Path, help="Path to desktop launcher for doctor checks")
    parser.add_argument("--python", type=Path, help="Target Hermes Python interpreter for dependency install and doctor checks")
    parser.add_argument("--runtime", choices=["auto", "docker", "local"], default="auto", help="Target runtime mode")
    parser.add_argument(
        "--embedding-runtime",
        choices=["local-tei-jina", "external", "none"],
        default="local-tei-jina",
        help=(
            "Embedding runtime contract. "
            "local-tei-jina uses the Docker runtime and adds a local TEI Jina v5 service and cache volume; "
            "--runtime auto resolves to docker for this default. "
            "external expects operator-provided embedding env; none writes no embedding service."
        ),
    )
    parser.add_argument(
        "--enable",
        action="store_true",
        help="Patch config.yaml to enable Brainstack while keeping Hermes builtin memory and user profile enabled",
    )
    parser.add_argument("--skip-deps", action="store_true", help="Skip installing missing kuzu/chromadb into the target Hermes Python")
    parser.add_argument("--doctor", action="store_true", help="Run brainstack_doctor after install")
    parser.add_argument("--dry-run", action="store_true", help="Show planned actions without changing files")
    parser.add_argument(
        "--host-patch-mode",
        choices=tuple(HOST_PATCH_MODE_CATEGORIES),
        default="core",
        help=(
            "Host patch policy: core=minimal Brainstack seams only; "
            "compat=core plus opt-in provider/runtime hotfixes; "
            "legacy=previous broad host patch behavior for emergency rollback only"
        ),
    )
    parser.add_argument(
        "--gateway-patch-mode",
        choices=("auto", "skip", "require"),
        default="auto",
        help=(
            "Hermes Gateway patch policy: auto=apply Brainstack-approved Gateway patches "
            "when upstream support is missing; skip=only report status; require=fail unless "
            "upstream support exists or the patch bundle applies cleanly."
        ),
    )
    parser.add_argument(
        "--skip-hermes-gateway-patches",
        action="store_true",
        help="Deprecated alias for --gateway-patch-mode skip.",
    )
    parser.add_argument(
        "--skip-hermes-proactive-extension",
        action="store_true",
        help="Skip installing the Hermes proactive runtime extension payload. Default is safe dry-run install.",
    )
    parser.add_argument(
        "--install-hermes-proactive-extension",
        action="store_true",
        help="Deprecated no-op: the Hermes proactive runtime extension is installed by default in safe dry-run form.",
    )
    parser.add_argument(
        "--enable-kanban-workstation",
        action="store_true",
        help="Request explicit Hermes Kanban workstation opt-in. Fails closed unless a tool-surface proof level is supplied.",
    )
    parser.add_argument(
        "--kanban-tool-surface-proof",
        choices=("none", "tool_surface_exposed", "board_write_certified", "worker_lifecycle_certified"),
        default="none",
        help="Evidence level for explicit Hermes Kanban opt-in. Default install never enables Kanban write/worker tools.",
    )
    parser.add_argument(
        "--check-release-hygiene",
        action="store_true",
        help="Fail if tracked or staged files include private runtime paths or high-confidence secrets.",
    )
    args = parser.parse_args()

    release_hygiene = _check_release_hygiene(REPO_ROOT)
    if args.check_release_hygiene and release_hygiene["status"] != "pass":
        print("FAIL release hygiene gate detected private or secret-like tracked content:", file=sys.stderr)
        for key in ("private_tracked", "private_staged", "secret_like_tracked"):
            values = release_hygiene.get(key) or []
            if values:
                print(f"  {key}: {', '.join(values[:12])}", file=sys.stderr)
        return 2

    capability_enablement = build_enablement_plan(
        enable_kanban_workstation=bool(args.enable_kanban_workstation),
        kanban_tool_surface_proof=str(args.kanban_tool_surface_proof),
    )
    if capability_enablement["status"] != "pass":
        print("FAIL capability enablement policy:", file=sys.stderr)
        for failure in capability_enablement.get("optional_failures") or []:
            print(f"  {failure.get('capability')}: {failure.get('reason_code')}", file=sys.stderr)
        return 2

    target = Path(args.target).expanduser().resolve()
    if not (target / "run_agent.py").exists():
        print(f"FAIL target is not a Hermes checkout: {target}", file=sys.stderr)
        return 2
    if not SOURCE_PLUGIN.exists():
        print(f"FAIL Brainstack payload missing: {SOURCE_PLUGIN}", file=sys.stderr)
        return 2
    config_path: Path | None
    try:
        config_path = args.config.expanduser().resolve() if args.config else _default_config_path(target)
    except RuntimeError as exc:
        config_path = None
        if args.enable or args.doctor or args.runtime == "docker":
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        print(
            "INFO no Hermes agent config found; continuing in source-only install mode "
            "(payload + host patches only, no config enablement, runtime canonicalization, or doctor)."
        )
    if config_path is not None and not config_path.exists():
        print(
            f"FAIL config not found: {config_path}. Create or select an agent first, then rerun the installer.",
            file=sys.stderr,
        )
        return 2
    runtime_resolution = None
    try:
        runtime_resolution = _resolve_enabled_runtime_contract(args)
    except RuntimeError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 2
    if runtime_resolution:
        print(runtime_resolution)

    compose_path: Path | None = None
    if args.runtime == "docker" or args.compose_file:
        if config_path is None and not args.compose_file:
            print(
                "FAIL Docker runtime install requires a concrete agent config or an explicit --compose-file.",
                file=sys.stderr,
            )
            return 2
        if args.compose_file:
            compose_path = args.compose_file.expanduser().resolve()
        else:
            try:
                compose_path = _default_compose_path(target, config_path)
            except RuntimeError as exc:
                if args.runtime == "docker":
                    if config_path is None:
                        print("FAIL Docker runtime install requires a concrete agent config.", file=sys.stderr)
                        return 2
                    try:
                        compose_path = _generated_compose_path(target, config_path)
                    except RuntimeError:
                        print(f"FAIL {exc}", file=sys.stderr)
                        return 2
                else:
                    print(f"FAIL {exc}", file=sys.stderr)
                    return 2

    plugin_target = target / "plugins" / "memory" / "brainstack"
    selected_python = args.python.expanduser() if args.python else _default_target_python(target)
    files = _copy_tree(SOURCE_PLUGIN, plugin_target, args.dry_run)
    _assert_no_private_payload_files(files)
    helper_files: list[dict[str, str]] = []
    shadow_probe_script = REPO_ROOT / "scripts" / "run_hindsight_runtime_shadow_probe.py"
    if shadow_probe_script.exists():
        helper_files.append(
            _copy_file(
                shadow_probe_script,
                target / "scripts" / "run_hindsight_runtime_shadow_probe.py",
                args.dry_run,
            )
        )
    local_mode_matrix_script = REPO_ROOT / "scripts" / "run_hindsight_local_mode_matrix.py"
    if local_mode_matrix_script.exists():
        helper_files.append(
            _copy_file(
                local_mode_matrix_script,
                target / "scripts" / "run_hindsight_local_mode_matrix.py",
                args.dry_run,
            )
        )

    generated_files: list[dict[str, str]] = []
    if args.runtime == "docker":
        if config_path is None:
            print("FAIL Docker runtime install requires a concrete agent config.", file=sys.stderr)
            return 2
        assert compose_path is not None
        if not compose_path.exists():
            generated_compose = _write_docker_compose_file(
                target,
                config_path,
                compose_path,
                args.dry_run,
                embedding_runtime=args.embedding_runtime,
            )
            generated_files.append({"source": "generated:docker-compose", "target": str(generated_compose)})
        docker_start = _write_docker_start_script(target, config_path, compose_path, args.dry_run)
        generated_files.append({"source": "generated:hermes-brainstack-start.sh", "target": str(docker_start)})
        docker_healthcheck = _write_docker_healthcheck_script(target, args.dry_run)
        generated_files.append({"source": "generated:hermes-gateway-healthcheck.py", "target": str(docker_healthcheck)})

    config_result = None
    if args.enable:
        assert config_path is not None
        config_result = _patch_config(config_path, args.dry_run, embedding_runtime=args.embedding_runtime)
    deps_result = _ensure_backend_dependencies(selected_python, dry_run=args.dry_run, skip_deps=args.skip_deps)

    host_helper_files: list[dict[str, str]] = []
    hermes_proactive_extension: dict[str, Any] = {"status": "skipped", "reason": "explicitly_skipped"}
    if not args.skip_hermes_proactive_extension:
        extension_target = target / "extensions" / "hermes_proactive"
        extension_files = _copy_tree(SOURCE_HERMES_PROACTIVE_EXTENSION, extension_target, args.dry_run)
        hermes_proactive_extension = {
            "status": "planned" if args.dry_run else "installed",
            "source": str(SOURCE_HERMES_PROACTIVE_EXTENSION),
            "target": str(extension_target),
            "files": extension_files,
            "mode": DEFAULT_PROACTIVE_RUNTIME_MODE,
            "delivery_default": "no_delivery_unless_config_mode_live_and_pulse_create_outbox_requested",
            "dependency_policy": "stdlib_plus_brainstack_sdk",
        }

    proactive_runtime: dict[str, Any] = {"status": "skipped", "reason": "no_config_path"}
    if not args.skip_hermes_proactive_extension and config_path is not None:
        try:
            runtime_home = _docker_runtime_home_dir(target, config_path) if args.runtime == "docker" else config_path.parent
            proactive_runtime = {
                "status": "planned" if args.dry_run else "installed",
                "runtime_home": str(runtime_home),
                "cron_gate_script": _write_hermes_proactive_cron_gate_script(runtime_home, target, args.dry_run),
                "cron_job": _upsert_hermes_proactive_cron_job(runtime_home, args.dry_run),
            }
        except RuntimeError as exc:
            print(f"FAIL Hermes proactive runtime install: {exc}", file=sys.stderr)
            return 2

    gateway_patch_mode = "skip" if args.skip_hermes_gateway_patches else args.gateway_patch_mode
    try:
        if gateway_patch_mode == "skip":
            hermes_gateway_patches = inspect_gateway_patch_support(target)
            hermes_gateway_patches["mode"] = "skip"
        else:
            hermes_gateway_patches = apply_gateway_patch_bundle(target, dry_run=args.dry_run)
            hermes_gateway_patches["mode"] = gateway_patch_mode
    except RuntimeError as exc:
        print(f"FAIL Hermes Gateway patch support: {exc}", file=sys.stderr)
        return 2

    host_patches: list[str] = []
    host_patches.extend(_run_host_patch("_patch_run_agent_cache_evict_memory_provider_shutdown", target / "run_agent.py", args.dry_run, host_patch_mode=args.host_patch_mode))
    host_patches.extend(_run_host_patch("_patch_run_agent_tool_call_interim_boundary", target / "run_agent.py", args.dry_run, host_patch_mode=args.host_patch_mode))
    host_patches.extend(_run_host_patch("_patch_run_agent", target / "run_agent.py", args.dry_run, host_patch_mode=args.host_patch_mode))
    host_patches.extend(_run_host_patch("_patch_run_agent_deferred_tool_continuation", target / "run_agent.py", args.dry_run, host_patch_mode=args.host_patch_mode))
    host_patches.extend(_run_host_patch("_patch_run_agent_memory_output_validation_seam", target / "run_agent.py", args.dry_run, host_patch_mode=args.host_patch_mode))
    host_patches.extend(_run_host_patch("_patch_run_agent_terminal_final_guard_seam", target / "run_agent.py", args.dry_run, host_patch_mode=args.host_patch_mode))
    host_patches.extend(_run_host_patch("_patch_deferred_tool_loader_contract", target / "hermes_deferred_tools.py", args.dry_run, host_patch_mode=args.host_patch_mode))
    host_patches.extend(_run_host_patch("_patch_memory_answer_renderer_language", target / "gateway" / "memory_answer_renderer.py", args.dry_run, host_patch_mode=args.host_patch_mode))
    host_patches.extend(_run_host_patch("_patch_terminal_tool_result_hygiene", target / "tools" / "terminal_tool.py", args.dry_run, host_patch_mode=args.host_patch_mode))
    host_patches.extend(_run_host_patch("_patch_prompt_builder", target / "agent" / "prompt_builder.py", args.dry_run, host_patch_mode=args.host_patch_mode))
    host_patches.extend(_run_host_patch("_patch_cron_jobs", target / "cron" / "jobs.py", args.dry_run, host_patch_mode=args.host_patch_mode))
    host_patches.extend(_run_host_patch("_patch_cron_scheduler", target / "cron" / "scheduler.py", args.dry_run, host_patch_mode=args.host_patch_mode))
    host_patches.extend(_run_host_patch("_patch_cron_scheduler_tests", target / "tests" / "cron" / "test_scheduler.py", args.dry_run, host_patch_mode=args.host_patch_mode))
    host_patches.extend(_run_host_patch("_patch_cron_tests", target / "tests" / "cron" / "test_jobs.py", args.dry_run, host_patch_mode=args.host_patch_mode))
    host_patches.extend(_run_host_patch("_patch_auxiliary_client", target / "agent" / "auxiliary_client.py", args.dry_run, host_patch_mode=args.host_patch_mode))
    host_patches.extend(_run_host_patch("_patch_session_search_total_deadline", target / "tools" / "session_search_tool.py", args.dry_run, host_patch_mode=args.host_patch_mode))
    host_patches.extend(_run_host_patch("_patch_discord_typing_backoff", target / "gateway" / "platforms" / "discord.py", args.dry_run, host_patch_mode=args.host_patch_mode))
    host_patches.extend(_run_host_patch("_patch_run_agent_ebadf_transport_recovery", target / "run_agent.py", args.dry_run, host_patch_mode=args.host_patch_mode))
    host_patches.extend(_run_host_patch("_patch_credential_pool", target / "agent" / "credential_pool.py", args.dry_run, host_patch_mode=args.host_patch_mode))
    host_patches.extend(_run_host_patch("_patch_credential_pool_tests", target / "tests" / "agent" / "test_credential_pool.py", args.dry_run, host_patch_mode=args.host_patch_mode))
    host_patches.extend(_run_host_patch("_patch_memory_provider", target / "agent" / "memory_provider.py", args.dry_run, host_patch_mode=args.host_patch_mode))
    host_patches.extend(_run_host_patch("_patch_memory_manager_required_seam", target / "agent" / "memory_manager.py", args.dry_run, host_patch_mode=args.host_patch_mode))
    host_patches.extend(_run_host_patch("_patch_memory_manager_output_validation_seam", target / "agent" / "memory_manager.py", args.dry_run, host_patch_mode=args.host_patch_mode))
    host_patches.extend(_run_host_patch("_patch_memory_manager", target / "agent" / "memory_manager.py", args.dry_run, host_patch_mode=args.host_patch_mode))
    host_patches.extend(_run_host_patch("_patch_gateway_background_process_output_boundary", target / "gateway" / "run.py", args.dry_run, host_patch_mode=args.host_patch_mode))
    host_patches.extend(_run_host_patch("_patch_gateway_run", target / "gateway" / "run.py", args.dry_run, host_patch_mode=args.host_patch_mode))
    host_patches.extend(_run_host_patch("_patch_gateway_turn_profiles_capability_preserving_default", target / "gateway" / "turn_profiles.py", args.dry_run, host_patch_mode=args.host_patch_mode))
    host_patches.extend(_run_host_patch("_patch_gateway_run_turn_profile_resolution", target / "gateway" / "run.py", args.dry_run, host_patch_mode=args.host_patch_mode))
    if args.runtime == "docker":
        assert compose_path is not None
        host_patches.extend(_run_host_patch("_patch_compose_healthcheck", compose_path, args.dry_run, host_patch_mode=args.host_patch_mode))
        host_patches.extend(_run_host_patch("_patch_compose_runtime_identity", compose_path, args.dry_run, host_patch_mode=args.host_patch_mode))
        host_patches.extend(_run_host_patch("_patch_compose_plugin_pythonpath", compose_path, args.dry_run, host_patch_mode=args.host_patch_mode))
        host_patches.extend(_run_host_patch("_patch_compose_discord_bot_mentions", compose_path, args.dry_run, host_patch_mode=args.host_patch_mode))
        host_patches.extend(_run_host_patch("_patch_compose_terminal_workspace_cwd", compose_path, args.dry_run, host_patch_mode=args.host_patch_mode))
        if args.embedding_runtime == "local-tei-jina":
            host_patches.extend(_run_host_patch("_patch_compose_local_tei_jina_runtime", compose_path, args.dry_run, host_patch_mode=args.host_patch_mode))
        host_patches.extend(_run_host_patch("_patch_compose_hindsight_local_tier2_runtime", compose_path, args.dry_run, host_patch_mode=args.host_patch_mode))
        host_patches.extend(_run_host_patch("_patch_compose_remove_discord_forced_heavy_profile", compose_path, args.dry_run, host_patch_mode=args.host_patch_mode))
        host_patches.extend(_run_host_patch("_patch_dockerignore", target / ".dockerignore", args.dry_run, host_patch_mode=args.host_patch_mode))
        host_patches.extend(_run_host_patch("_patch_dockerfile_backend_dependencies", target / "Dockerfile", args.dry_run, host_patch_mode=args.host_patch_mode))
        host_patches.extend(_run_host_patch("_patch_dockerfile_workstation_python_alias", target / "Dockerfile", args.dry_run, host_patch_mode=args.host_patch_mode))
        host_patches.extend(_run_host_patch("_patch_docker_entrypoint", target / "docker" / "entrypoint.sh", args.dry_run, host_patch_mode=args.host_patch_mode))

    if gateway_patch_mode != "skip" and not args.dry_run:
        hermes_gateway_patches["after_host_patches"] = inspect_gateway_patch_support(target)
        if hermes_gateway_patches["after_host_patches"]["status"] != "upstream_gateway_supported":
            print(
                "Hermes Gateway patch did not reach supported state after host patches: "
                f"{hermes_gateway_patches['after_host_patches']['status']}",
                file=sys.stderr,
            )
            return 2

    if config_path is not None:
        runtime_state_canonicalization = _canonicalize_runtime_user_profile(config_path, args.dry_run)
        runtime_db_canonicalization = _canonicalize_runtime_brainstack_db(
            target,
            config_path,
            python_bin=selected_python,
            dry_run=args.dry_run,
        )
    else:
        runtime_state_canonicalization = {"status": "skipped", "reason": "source_only_install"}
        runtime_db_canonicalization = {"status": "skipped", "reason": "source_only_install"}

    manifest = {
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": args.dry_run,
        "source_repo": str(REPO_ROOT),
        "target_hermes": str(target),
        "runtime_mode": args.runtime,
        "host_patch_mode": args.host_patch_mode,
        "source_only_install": config_path is None,
        "plugin_target": str(plugin_target),
        "files": files,
        "helper_files": helper_files,
        "host_helper_files": host_helper_files,
        "hermes_proactive_extension": hermes_proactive_extension,
        "hermes_proactive_runtime": proactive_runtime,
        "host_patches": host_patches,
        "host_patch_inventory": _selected_host_patch_inventory(args.runtime, args.host_patch_mode),
        "hermes_gateway_patches": hermes_gateway_patches,
        "capability_enablement": capability_enablement,
        "release_hygiene": release_hygiene,
        "generated_files": generated_files,
        "config_path": str(config_path) if config_path is not None else None,
        "config": config_result,
        "dependency_install": deps_result,
        "runtime_state_canonicalization": runtime_state_canonicalization,
        "runtime_db_canonicalization": runtime_db_canonicalization,
        "secrets_included": False,
    }
    _write_manifest(target, manifest, args.dry_run)

    action = "DRY-RUN" if args.dry_run else "INSTALLED"
    print(f"{action} Brainstack payload files: {len(files)}")
    print(f"{action} helper files: {len(helper_files)}")
    print(f"{action} Hermes proactive extension: {hermes_proactive_extension.get('status')}")
    print(f"{action} Hermes proactive runtime: {proactive_runtime.get('status')}")
    capability_summary = summarize_enablement_plan(capability_enablement)
    print(
        f"{action} capability policy: {capability_summary['status']} "
        f"(required_enabled={capability_summary['required_enabled_count']}, "
        f"side_effectful_default={capability_summary['side_effectful_tools_enabled_by_default']}, "
        f"kanban={capability_summary['kanban_status']})"
    )
    inventory = _selected_host_patch_inventory(args.runtime, args.host_patch_mode)
    selected_inventory = [item for item in inventory if item.get("selected")]
    skipped_inventory = [item for item in inventory if not item.get("selected")]
    print(
        f"{action} host patch mode: {args.host_patch_mode} "
        f"({len(selected_inventory)} selected, {len(skipped_inventory)} skipped)"
    )
    if args.dry_run:
        if selected_inventory:
            selected_labels = ", ".join(
                f"{item['patcher']}[{item['category']}]" for item in selected_inventory
            )
            print(f"{action} selected installer patchers: {selected_labels}")
        if skipped_inventory:
            skipped_labels = ", ".join(
                f"{item['patcher']}[{item['category']}]" for item in skipped_inventory
            )
            print(f"{action} skipped installer patchers: {skipped_labels}")
    if host_helper_files:
        print(f"{action} host helper files: {len(host_helper_files)}")
    if host_patches:
        print(f"{action} host patches: {len(host_patches)}")
    if hermes_gateway_patches:
        print(f"{action} Hermes Gateway patches: {hermes_gateway_patches.get('status')}")
    if generated_files:
        print(f"{action} generated files: {len(generated_files)}")
    if config_result:
        print(f"{action} config: {config_result['config_path']}")
    elif config_path is None:
        print(f"{action} config: source-only (no agent config)")
    if deps_result.get("status") in {"planned", "installed", "already_satisfied"}:
        print(f"{action} backend deps: {deps_result['status']}")
    elif deps_result.get("status") == "skipped":
        print(f"{action} backend deps: skipped ({deps_result.get('reason')})")
    if not args.dry_run:
        print(f"Wrote manifest: {target / '.brainstack-install-manifest.json'}")

    if args.doctor:
        if config_path is None:
            print("FAIL Doctor requires a concrete agent config.", file=sys.stderr)
            return 2
        return _run_doctor(
            target,
            args,
            planned_install=args.dry_run,
            config_path=config_path,
            compose_path=compose_path,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
