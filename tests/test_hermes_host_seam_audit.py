from __future__ import annotations

from pathlib import Path

from scripts.hermes_host_seam_audit import build_report
from scripts.install_into_hermes import _selected_host_patch_inventory


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _native_target(root: Path) -> Path:
    _write(
        root / "plugins" / "memory" / "__init__.py",
        '''
"""User memory providers live in $HERMES_HOME/plugins/<name>."""
def _get_user_plugins_dir(): pass
def _is_memory_provider_dir(path): pass
def find_provider_dir(name): pass
'''.lstrip(),
    )
    _write(
        root / "agent" / "memory_provider.py",
        '''
class MemoryProvider:
    def on_memory_write(self, action, target, content, metadata=None):
        pass
'''.lstrip(),
    )
    _write(
        root / "agent" / "memory_manager.py",
        '''
class MemoryManager:
    def on_memory_write(self, action, target, content, metadata=None):
        provider.on_memory_write(action, target, content, metadata=dict(metadata or {}))
'''.lstrip(),
    )
    _write(
        root / "run_agent.py",
        '''
class Agent:
    def __init__(self):
        user_name = chat_id = chat_name = chat_type = thread_id = None
        _init_kwargs = {"user_name": user_name, "chat_id": chat_id, "chat_name": chat_name, "chat_type": chat_type, "thread_id": thread_id}

    def _build_memory_write_metadata(self):
        return {"write_origin": self._memory_write_origin}

    def _sync_external_memory_for_turn(self, *, original_user_message, final_response, interrupted):
        """Interrupted turns are skipped entirely (#15218)."""
        if interrupted:
            return
        self._memory_manager.sync_all(original_user_message, final_response)

    def write(self):
        self._memory_manager.on_memory_write("add", "memory", "x", metadata=self._build_memory_write_metadata())
'''.lstrip(),
    )
    _write(root / ".dockerignore", "auth.json\nsessions\nhermes-config\nbrainstack\n")
    return root


def test_core_host_patch_inventory_skips_native_metadata_compat_seams() -> None:
    inventory = {
        item["patcher"]: item
        for item in _selected_host_patch_inventory("docker", host_patch_mode="core")
    }

    assert inventory["_patch_run_agent"]["selected"] is False
    assert inventory["_patch_memory_provider"]["selected"] is False
    assert inventory["_patch_memory_manager_required_seam"]["selected"] is False
    assert inventory["_patch_dockerfile_backend_dependencies"]["selected"] is True
    assert inventory["_patch_dockerignore"]["selected"] is True
    assert inventory["_patch_compose_plugin_pythonpath"]["selected"] is True


def test_host_seam_audit_classifies_native_write_metadata_as_narrow(tmp_path: Path) -> None:
    target = _native_target(tmp_path / "hermes")

    report = build_report(target, runtime_mode="docker")
    seams = report["native_seams"]
    decisions = {row["patcher"]: row for row in report["patch_decisions"]}

    assert seams["user_memory_provider_discovery"]["status"] == "pass"
    assert seams["memory_provider_write_metadata"]["status"] == "pass"
    assert seams["memory_manager_write_metadata_forwarding"]["status"] == "pass"
    assert seams["run_agent_write_origin_metadata"]["status"] == "pass"
    assert seams["interrupted_external_memory_sync_guard"]["status"] == "pass"

    assert decisions["_patch_run_agent"]["decision"] == "narrow"
    assert decisions["_patch_run_agent"]["native_coverage_complete"] is True
    assert decisions["_patch_memory_provider"]["decision"] == "narrow"
    assert decisions["_patch_memory_manager_required_seam"]["decision"] == "narrow"
    assert decisions["_patch_dockerfile_backend_dependencies"]["decision"] == "keep"
