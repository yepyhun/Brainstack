from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_installer():
    repo_root = Path(__file__).resolve().parents[1]
    installer_path = repo_root / "scripts" / "install_into_hermes.py"
    spec = importlib.util.spec_from_file_location("brainstack_installer", installer_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_memory_provider_patch_skips_native_metadata_seam(tmp_path: Path) -> None:
    installer = _load_installer()
    provider = tmp_path / "memory_provider.py"
    provider.write_text(
        """
class MemoryProvider:
    def on_memory_write(
        self,
        action: str,
        target: str,
        content: str,
        metadata: dict[str, object] | None = None,
    ) -> None:
        pass
""".lstrip(),
        encoding="utf-8",
    )

    assert installer._patch_memory_provider(provider, dry_run=False) == []


def test_memory_provider_patch_keeps_legacy_compat_path(tmp_path: Path) -> None:
    installer = _load_installer()
    provider = tmp_path / "memory_provider.py"
    provider.write_text(
        """
class MemoryProvider:
    def on_memory_write(self, action: str, target: str, content: str) -> None:
        \"\"\"Mirror write.

        action: 'add', 'replace', or 'remove'
        target: 'memory' or 'user'
        content: the entry content

        Use to mirror built-in memory writes to your backend.
        \"\"\"
        pass
""".lstrip(),
        encoding="utf-8",
    )

    labels = installer._patch_memory_provider(provider, dry_run=False)

    assert labels == [
        "memory_provider:memory_write_metadata_signature",
        "memory_provider:memory_write_metadata_doc",
    ]
    assert "metadata: dict[str, Any] | None = None" in provider.read_text(
        encoding="utf-8"
    )


def test_memory_manager_patch_skips_native_metadata_bridge(tmp_path: Path) -> None:
    installer = _load_installer()
    manager = tmp_path / "memory_manager.py"
    manager.write_text(
        """
import inspect

class MemoryManager:
    def on_memory_write(
        self,
        action: str,
        target: str,
        content: str,
        metadata: dict[str, object] | None = None,
    ) -> None:
        signature = inspect.signature(provider.on_memory_write)
        if "metadata" in signature.parameters:
            provider.on_memory_write(action, target, content, metadata=dict(metadata or {}))
""".lstrip(),
        encoding="utf-8",
    )

    assert installer._patch_memory_manager_required_seam(manager, dry_run=False) == []


def test_run_agent_patch_skips_native_background_review_origin(
    tmp_path: Path,
) -> None:
    installer = _load_installer()
    run_agent = tmp_path / "run_agent.py"
    run_agent.write_text(
        """
class Agent:
    def run(self):
        if self._memory_manager and final_response and original_user_message:
            try:
                self._memory_manager.sync_all(original_user_message, final_response)
                self._memory_manager.queue_prefetch_all(original_user_message)
            except Exception:
                pass

        if background_review:
            review_agent._memory_store = self._memory_store
            review_agent._memory_enabled = self._memory_enabled
            review_agent._user_profile_enabled = self._user_profile_enabled
            review_agent._memory_write_origin = "background_review"
            review_agent._memory_write_context = "background_review"
            review_agent._memory_nudge_interval = 0
            review_agent._skill_nudge_interval = 0

        self._memory_manager.on_memory_write(
            function_args.get("action", ""),
            target,
            function_args.get("content", ""),
            metadata=self._build_memory_write_metadata(),
        )
""".lstrip(),
        encoding="utf-8",
    )

    assert installer._patch_run_agent(run_agent, dry_run=False) == [
        "run_agent:skip_interrupted_transcript_sync"
    ]
    patched = run_agent.read_text(encoding="utf-8")
    assert "_brainstack_memory_write_origin" not in patched
    assert "and not interrupted" in patched


def test_run_agent_patch_accepts_upstream_interrupted_sync_helper(
    tmp_path: Path,
) -> None:
    installer = _load_installer()
    run_agent = tmp_path / "run_agent.py"
    run_agent.write_text(
        '''
class Agent:
    def _sync_external_memory_for_turn(self, *, original_user_message, final_response, interrupted):
        """Mirror a completed turn into external memory providers.

        Interrupted turns are skipped entirely (#15218).
        """
        if interrupted:
            return
        if not (self._memory_manager and final_response and original_user_message):
            return
        try:
            self._memory_manager.sync_all(original_user_message, final_response)
            self._memory_manager.queue_prefetch_all(original_user_message)
        except Exception:
            pass

    def run(self):
        if background_review:
            review_agent._memory_store = self._memory_store
            review_agent._memory_enabled = self._memory_enabled
            review_agent._user_profile_enabled = self._user_profile_enabled
            review_agent._memory_write_origin = "background_review"
            review_agent._memory_write_context = "background_review"
            review_agent._memory_nudge_interval = 0
            review_agent._skill_nudge_interval = 0
'''.lstrip(),
        encoding="utf-8",
    )

    assert installer._patch_run_agent(run_agent, dry_run=False) == []


def test_file_search_timeout_patch_caps_search_command_timeouts(tmp_path: Path) -> None:
    installer = _load_installer()
    file_operations = tmp_path / "file_operations.py"
    file_operations.write_text(
        '''
import os
from pathlib import Path
from typing import Optional

_HOME = str(Path.home())
WRITE_DENIED_PATHS = build_write_denied_paths(_HOME)
WRITE_DENIED_PREFIXES = build_write_denied_prefixes(_HOME)


def _get_safe_write_root() -> Optional[str]:
    return None

class ShellFileOperations:
    def _search_files(self):
        result = self._exec(cmd, timeout=60)
        result = self._exec(cmd_simple, timeout=60)

    def _search_files_rg(self):
        result = self._exec(cmd_sorted, timeout=60)
        result = self._exec(cmd_plain, timeout=60)

    def _search_with_rg(self):
        result = self._exec(cmd, timeout=60)

    def _search_with_grep(self):
        result = self._exec(cmd, timeout=60)
'''.lstrip(),
        encoding="utf-8",
    )

    labels = installer._patch_file_search_timeout_cap(file_operations, dry_run=False)

    patched = file_operations.read_text(encoding="utf-8")
    assert labels == [
        "file_operations:search_timeout_constant",
        "file_operations:search_timeout_cap",
    ]
    assert "HERMES_SEARCH_FILES_TIMEOUT" in patched
    assert "DEFAULT_SEARCH_COMMAND_TIMEOUT" in patched
    assert "timeout=60)" not in patched
    assert patched.count("timeout=DEFAULT_SEARCH_COMMAND_TIMEOUT)") == 6


def test_file_search_timeout_patch_is_idempotent(tmp_path: Path) -> None:
    installer = _load_installer()
    file_operations = tmp_path / "file_operations.py"
    file_operations.write_text(
        '''
import os
from pathlib import Path
from typing import Optional

_HOME = str(Path.home())
WRITE_DENIED_PATHS = build_write_denied_paths(_HOME)
WRITE_DENIED_PREFIXES = build_write_denied_prefixes(_HOME)

# File search is used in live gateway turns. It must fail fast instead of
# occupying the agent until the gateway's inactivity watchdog fires.
# Override for unusual large-repo maintenance: HERMES_SEARCH_FILES_TIMEOUT=15.
def _brainstack_env_int(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(minimum, value)


DEFAULT_SEARCH_COMMAND_TIMEOUT = _brainstack_env_int("HERMES_SEARCH_FILES_TIMEOUT", 8)


def _get_safe_write_root() -> Optional[str]:
    return None

class ShellFileOperations:
    def _search_with_rg(self):
        result = self._exec(cmd, timeout=DEFAULT_SEARCH_COMMAND_TIMEOUT)
'''.lstrip(),
        encoding="utf-8",
    )

    assert installer._patch_file_search_timeout_cap(file_operations, dry_run=False) == []
