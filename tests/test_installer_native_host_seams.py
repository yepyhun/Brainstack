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


def test_latest_compat_mode_does_not_select_legacy_terminal_guard() -> None:
    installer = _load_installer()
    inventory = {
        item["patcher"]: item
        for item in installer._selected_host_patch_inventory(
            "docker",
            host_patch_mode="compat",
        )
    }

    assert inventory["_patch_run_agent_terminal_final_guard_seam"]["category"] == (
        "legacy_host_patch"
    )
    assert inventory["_patch_run_agent_terminal_final_guard_seam"]["selected"] is False
    assert inventory["_patch_run_agent"]["selected"] is True


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


def test_run_agent_patch_skips_split_native_background_review_origin(
    tmp_path: Path,
) -> None:
    installer = _load_installer()
    run_agent = tmp_path / "run_agent.py"
    (tmp_path / "agent").mkdir()
    (tmp_path / "agent" / "background_review.py").write_text(
        '''
def build_memory_write_metadata(agent, *, task_id=None):
    return {"write_origin": getattr(agent, "_memory_write_origin", "assistant_tool")}


def prepare_background_review_agent(review_agent):
    review_agent._memory_write_origin = "background_review"
    review_agent._memory_write_context = "background_review"
'''.lstrip(),
        encoding="utf-8",
    )
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

    def _build_memory_write_metadata(self, *, task_id=None):
        return build_memory_write_metadata(self, task_id=task_id)

    def write(self):
        self._memory_manager.on_memory_write(
            function_args.get("action", ""),
            target,
            function_args.get("content", ""),
            metadata=self._build_memory_write_metadata(task_id=task_id),
        )
'''.lstrip(),
        encoding="utf-8",
    )

    assert installer._patch_run_agent(run_agent, dry_run=False) == []
    assert "_brainstack_memory_write_origin" not in run_agent.read_text(
        encoding="utf-8"
    )


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
