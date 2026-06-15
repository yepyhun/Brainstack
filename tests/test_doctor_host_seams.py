from __future__ import annotations

from pathlib import Path

from scripts import brainstack_doctor


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _base_hermes_target(tmp_path: Path) -> Path:
    target = tmp_path / "hermes"
    _write(
        target / "agent" / "memory_provider.py",
        """
class MemoryProvider:
    def initialize(self): pass
    def prefetch(self): pass
    def sync_turn(self): pass
    def on_turn_start(self, turn_number, message, **kwargs): pass
    def on_pre_compress(self): pass
    def on_session_end(self, messages): pass
    def on_memory_write(self, action, target, content, metadata=None): pass
""",
    )
    _write(
        target / "agent" / "memory_manager.py",
        """
def _render_memory_commitment_blocked(provider_results):
    return "blocked"

class MemoryManager:
    def add_provider(self, provider): pass
    def prefetch_all(self, query, *, session_id=""): pass
    def queue_prefetch_all(self, query, *, session_id=""): pass
    def sync_all(self, user_content, assistant_content, *, session_id=""): pass
    def on_turn_start(self, turn_number, message, **kwargs):
        for provider in self._providers:
            try:
                provider.on_turn_start(turn_number, message, **kwargs)
            except Exception:
                pass
    def on_pre_compress(self): pass
    def on_session_end(self, messages): pass
    def shutdown_all(self): pass
    def validate_assistant_output_all(self, content, *, user_content="", session_id=""): pass
    def record_output_validation_delivery_all(self, result, *, delivered_content=""): pass
    def on_memory_write(self, action, target, content, metadata=None):
        for provider in self._providers:
            provider.on_memory_write(action, target, content, metadata=metadata)

def build_memory_context_block(raw_context):
    return "<memory-context>NOT new user input</memory-context>"

def sanitize_context(raw_context):
    return raw_context
""",
    )
    _write(
        target / "plugins" / "memory" / "__init__.py",
        """
from plugins.memory.brainstack import BrainstackProvider

def load_memory_provider(name):
    return BrainstackProvider()
""",
    )
    _write(target / "plugins" / "memory" / "brainstack" / "retrieval.py", "")
    _write(target / "agent" / "brainstack_mode.py", "")
    _write(
        target / "agent" / "prompt_builder.py",
        """
def build_skills_system_prompt():
    return "Before replying, scan the skills below. Load a skill only when it is directly relevant. Do not reload the same skill in the same session."
""",
    )
    _write(
        target / "tools" / "skills_tool.py",
        """
DEFAULT_SKILL_VIEW_AUTO_FULL_CHAR_LIMIT = 8000
def _skill_view_content_fields():
    return {"content_hash": "abc", "already_loaded_in_session": False}
""",
    )
    _write(
        target / "gateway" / "run.py",
        """
def on_session_finalize():
    return "session:end"
""",
    )
    _write(
        target / "gateway" / "platforms" / "discord.py",
        """
self._post_connect_task: Optional[asyncio.Task] = None
async def _run_post_connect_initialization(self) -> None: pass
adapter_self._ready_event.set()
adapter_self._post_connect_task = asyncio.create_task(self._run_post_connect_initialization())
""",
    )
    return target


def _checks_by_name(target: Path) -> dict[str, brainstack_doctor.Check]:
    return {check.name: check for check in brainstack_doctor._check_host_surfaces(target)}


def test_doctor_accepts_v014_split_external_memory_host_wiring(tmp_path: Path) -> None:
    target = _base_hermes_target(tmp_path)
    _write(
        target / "agent" / "agent_init.py",
        """
def init_agent(agent, mem_config, skip_memory=False):
    _mem_provider_name = mem_config.get("provider", "")
    if _mem_provider_name:
        from agent.memory_manager import MemoryManager as _MemoryManager
        from plugins.memory import load_memory_provider as _load_mem
        agent._memory_manager = _MemoryManager()
        _mp = _load_mem(_mem_provider_name)
        if _mp and _mp.is_available():
            agent._memory_manager.add_provider(_mp)
""",
    )
    _write(
        target / "run_agent.py",
        """
def _validate_external_memory_final_response(self, original_user_message, final_response, interrupted):
    result = self._memory_manager.validate_assistant_output_all(final_response, user_content=original_user_message, session_id=self.session_id)
    return result["content"]

def _record_external_memory_validation_delivery(self, delivered_content):
    self._memory_manager.record_output_validation_delivery_all(self._last_memory_output_validation, delivered_content=str(delivered_content))

def _sync_external_memory_for_turn(self, original_user_message, final_response, interrupted):
    if interrupted:
        return
    self._memory_manager.sync_all(original_user_message, final_response, session_id=self.session_id)
    self._memory_manager.queue_prefetch_all(original_user_message, session_id=self.session_id)
""",
    )
    _write(
        target / "agent" / "tool_executor.py",
        """
def call_memory_tool(agent, function_args, target):
    if agent._memory_manager and function_args.get("action") in {"add", "replace"}:
        agent._memory_manager.on_memory_write(
            function_args.get("action", ""),
            target,
            function_args.get("content", ""),
            metadata=agent._build_memory_write_metadata(task_id="t1"),
        )
""",
    )

    checks = _checks_by_name(target)

    assert checks["host_runtime_wiring"].status == "pass"
    assert "agent/agent_init.py" in checks["host_runtime_wiring"].message
    assert checks["native_profile_write_bridge"].status == "pass"
    assert "agent/tool_executor.py" in checks["native_profile_write_bridge"].message
    assert checks["memory_output_validation_seam"].status == "pass"


def test_doctor_rejects_comment_only_host_seam_markers(tmp_path: Path) -> None:
    target = _base_hermes_target(tmp_path)
    _write(
        target / "run_agent.py",
        """
# memory.provider load_memory_provider prefetch_all sync_all
# self._memory_manager.on_memory_write(
# validate_assistant_output_all record_output_validation_delivery_all
""",
    )

    checks = _checks_by_name(target)

    assert checks["host_runtime_wiring"].status == "fail"
    assert checks["native_profile_write_bridge"].status == "fail"
    assert checks["memory_output_validation_seam"].status == "fail"


def test_doctor_rejects_loader_without_add_provider(tmp_path: Path) -> None:
    target = _base_hermes_target(tmp_path)
    _write(
        target / "agent" / "agent_init.py",
        """
def init_agent(agent, mem_config):
    from agent.memory_manager import MemoryManager
    from plugins.memory import load_memory_provider
    agent._memory_manager = MemoryManager()
    provider = load_memory_provider(mem_config.get("provider"))
    return provider
""",
    )
    _write(
        target / "run_agent.py",
        """
def _sync_external_memory_for_turn(self, original_user_message, final_response, interrupted):
    if interrupted:
        return
    self._memory_manager.sync_all(original_user_message, final_response, session_id=self.session_id)
    self._memory_manager.queue_prefetch_all(original_user_message, session_id=self.session_id)
""",
    )

    checks = _checks_by_name(target)

    assert checks["host_runtime_wiring"].status == "fail"
    assert "add_provider" in checks["host_runtime_wiring"].message


def test_doctor_rejects_write_bridge_without_metadata(tmp_path: Path) -> None:
    target = _base_hermes_target(tmp_path)
    _write(
        target / "agent" / "agent_init.py",
        """
def init_agent(agent, mem_config):
    from agent.memory_manager import MemoryManager
    from plugins.memory import load_memory_provider
    agent._memory_manager = MemoryManager()
    agent._memory_manager.add_provider(load_memory_provider(mem_config.get("provider")))
""",
    )
    _write(
        target / "run_agent.py",
        """
def _sync_external_memory_for_turn(self, original_user_message, final_response, interrupted):
    if interrupted:
        return
    self._memory_manager.sync_all(original_user_message, final_response, session_id=self.session_id)
    self._memory_manager.queue_prefetch_all(original_user_message, session_id=self.session_id)
""",
    )
    _write(
        target / "agent" / "tool_executor.py",
        """
def call_memory_tool(agent, function_args, target):
    agent._memory_manager.on_memory_write(
        function_args.get("action", ""),
        target,
        function_args.get("content", ""),
    )
""",
    )

    checks = _checks_by_name(target)

    assert checks["native_profile_write_bridge"].status == "fail"
    assert "metadata" in checks["native_profile_write_bridge"].message


def test_doctor_rejects_validation_without_delivery_record(tmp_path: Path) -> None:
    target = _base_hermes_target(tmp_path)
    _write(
        target / "run_agent.py",
        """
def _validate_external_memory_final_response(self, original_user_message, final_response, interrupted):
    result = self._memory_manager.validate_assistant_output_all(final_response, user_content=original_user_message, session_id=self.session_id)
    return result["content"]

def _sync_external_memory_for_turn(self, original_user_message, final_response, interrupted):
    if interrupted:
        return
    self._memory_manager.sync_all(original_user_message, final_response, session_id=self.session_id)
    self._memory_manager.queue_prefetch_all(original_user_message, session_id=self.session_id)
""",
    )

    checks = _checks_by_name(target)

    assert checks["memory_output_validation_seam"].status == "fail"
    assert "delivery-record" in checks["memory_output_validation_seam"].message


def test_doctor_accepts_turn_start_hook_in_split_conversation_loop(tmp_path: Path) -> None:
    target = _base_hermes_target(tmp_path)
    _write(
        target / "agent" / "conversation_loop.py",
        """
def run_conversation(agent, original_user_message):
    if agent._memory_manager:
        agent._memory_manager.on_turn_start(agent._user_turn_count, original_user_message)
    agent._memory_manager.prefetch_all(original_user_message)
""",
    )

    checks = _checks_by_name(target)

    assert checks["turn_start_hook"].status == "pass"
    assert "agent/conversation_loop.py" in checks["turn_start_hook"].message
    assert "MemoryManager.on_turn_start" in checks["turn_start_hook"].message


def test_doctor_accepts_turn_start_hook_in_split_turn_context(tmp_path: Path) -> None:
    target = _base_hermes_target(tmp_path)
    _write(
        target / "agent" / "turn_context.py",
        """
def build_turn_context(agent, original_user_message):
    if agent._memory_manager:
        agent._memory_manager.on_turn_start(agent._user_turn_count, original_user_message)
    return {}
""",
    )

    checks = _checks_by_name(target)

    assert checks["turn_start_hook"].status == "pass"
    assert "agent/turn_context.py" in checks["turn_start_hook"].message
    assert "MemoryManager.on_turn_start" in checks["turn_start_hook"].message


def test_doctor_rejects_turn_start_provider_api_without_host_caller(tmp_path: Path) -> None:
    target = _base_hermes_target(tmp_path)

    checks = _checks_by_name(target)

    assert checks["turn_start_hook"].status == "warn"
    assert "host turn-start caller" in checks["turn_start_hook"].message


def test_doctor_rejects_comment_only_turn_start_marker(tmp_path: Path) -> None:
    target = _base_hermes_target(tmp_path)
    _write(
        target / "run_agent.py",
        """
# agent._memory_manager.on_turn_start(agent._user_turn_count, original_user_message)
""",
    )

    checks = _checks_by_name(target)

    assert checks["turn_start_hook"].status == "warn"
    assert "host turn-start caller" in checks["turn_start_hook"].message


def test_doctor_rejects_dead_turn_start_helper(tmp_path: Path) -> None:
    target = _base_hermes_target(tmp_path)
    _write(
        target / "run_agent.py",
        """
def unused_turn_start_helper(agent, original_user_message):
    agent._memory_manager.on_turn_start(agent._user_turn_count, original_user_message)
""",
    )

    checks = _checks_by_name(target)

    assert checks["turn_start_hook"].status == "warn"
    assert "host turn-start caller" in checks["turn_start_hook"].message


def test_doctor_accepts_gateway_session_boundary_in_split_slash_commands(tmp_path: Path) -> None:
    target = _base_hermes_target(tmp_path)
    _write(target / "gateway" / "run.py", "")
    _write(
        target / "gateway" / "slash_commands.py",
        """
async def reset_session(self, session_key):
    from hermes_cli.plugins import invoke_hook
    invoke_hook("on_session_finalize", session_id="old", reason="new_session")
    await self.hooks.emit("session:end", {"session_key": session_key})
""",
    )
    _write(
        target / "run_agent.py",
        """
def shutdown(self, messages):
    self._memory_manager.on_session_end(messages or [])
""",
    )

    checks = _checks_by_name(target)

    assert checks["gateway_session_boundary_gate"].status == "pass"
    assert "upstream session-finalize" in checks["gateway_session_boundary_gate"].message


def test_doctor_rejects_turn_start_fanout_without_exception_containment(
    tmp_path: Path,
) -> None:
    target = _base_hermes_target(tmp_path)
    _write(
        target / "agent" / "memory_manager.py",
        """
class MemoryManager:
    def add_provider(self, provider): pass
    def prefetch_all(self, query, *, session_id=""): pass
    def queue_prefetch_all(self, query, *, session_id=""): pass
    def sync_all(self, user_content, assistant_content, *, session_id=""): pass
    def on_turn_start(self, turn_number, message, **kwargs):
        for provider in self._providers:
            provider.on_turn_start(turn_number, message, **kwargs)
    def on_pre_compress(self): pass
    def on_session_end(self, messages): pass
    def shutdown_all(self): pass
    def validate_assistant_output_all(self, content, *, user_content="", session_id=""): pass
    def record_output_validation_delivery_all(self, result, *, delivered_content=""): pass
    def on_memory_write(self, action, target, content, metadata=None): pass
""",
    )
    _write(
        target / "agent" / "conversation_loop.py",
        """
def run_conversation(agent, original_user_message):
    agent._memory_manager.on_turn_start(agent._user_turn_count, original_user_message)
""",
    )

    checks = _checks_by_name(target)

    assert checks["turn_start_hook"].status == "fail"
    assert "exception containment" in checks["turn_start_hook"].message
