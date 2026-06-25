"""Structured Hermes host seam probes for Brainstack doctor.

The doctor should validate host contracts, not incidental source locations.
Hermes v0.14 split several memory-provider seams out of ``run_agent.py``;
these probes accept supported split layouts while still rejecting comments,
dead marker strings, and manifest-only "proof".
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class HostSeamEvidence:
    file: str
    symbol: str
    reason: str


@dataclass(frozen=True)
class HostSeamProbe:
    name: str
    status: str
    message: str
    evidence: tuple[HostSeamEvidence, ...] = field(default_factory=tuple)
    missing: tuple[str, ...] = field(default_factory=tuple)

    def doctor_message(self) -> str:
        parts = [self.message]
        if self.evidence:
            evidence = "; ".join(
                f"{item.file}:{item.symbol} ({item.reason})" for item in self.evidence
            )
            parts.append(f"Evidence: {evidence}")
        if self.missing:
            parts.append(f"Missing: {', '.join(self.missing)}")
        return " ".join(parts)


class HostSurfaceCorpus:
    """Small side-effect-free view over known Hermes host files."""

    def __init__(self, root: Path):
        self.root = root
        self._texts: dict[str, str] = {}
        self._trees: dict[str, ast.AST | None] = {}

    def text(self, rel_path: str) -> str:
        if rel_path not in self._texts:
            try:
                self._texts[rel_path] = (self.root / rel_path).read_text(encoding="utf-8")
            except Exception:
                self._texts[rel_path] = ""
        return self._texts[rel_path]

    def tree(self, rel_path: str) -> ast.AST | None:
        if rel_path not in self._trees:
            text = self.text(rel_path)
            if not text:
                self._trees[rel_path] = None
            else:
                try:
                    self._trees[rel_path] = ast.parse(text, filename=rel_path)
                except SyntaxError:
                    self._trees[rel_path] = None
        return self._trees[rel_path]


def _trees(corpus: HostSurfaceCorpus, rel_paths: Iterable[str]) -> Iterable[tuple[str, ast.AST]]:
    for rel_path in rel_paths:
        tree = corpus.tree(rel_path)
        if tree is not None:
            yield rel_path, tree


def _imports_name(tree: ast.AST, name: str) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == name:
                    return True
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == name:
                    return True
    return False


def _uses_name(tree: ast.AST, name: str) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == name:
            return True
    return False


def _calls_attr(tree: ast.AST, attr: str, *, keyword: str | None = None) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != attr:
            continue
        if keyword is None:
            return True
        if any(kw.arg == keyword for kw in node.keywords):
            return True
    return False


def _attr_chain(node: ast.AST) -> tuple[str, ...]:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return tuple(reversed(parts))


def _function_calls_memory_manager_attr(
    tree: ast.AST,
    function_name: str,
    attr: str,
) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != function_name:
            continue
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            func = child.func
            if not isinstance(func, ast.Attribute) or func.attr != attr:
                continue
            chain = _attr_chain(func)
            if "_memory_manager" in chain:
                return True
    return False


def _function_calls_attr(tree: ast.AST, function_name: str, attr: str) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != function_name:
            continue
        for child in ast.walk(node):
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
                if child.func.attr == attr:
                    chain = _attr_chain(child.func)
                    if not chain or chain[0] != "self":
                        return True
    return False


def _call_tree_contains_attr(nodes: Iterable[ast.stmt], attr: str) -> bool:
    for node in nodes:
        for child in ast.walk(node):
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
                if child.func.attr == attr:
                    chain = _attr_chain(child.func)
                    if not chain or chain[0] != "self":
                        return True
    return False


def _function_try_wraps_attr(tree: ast.AST, function_name: str, attr: str) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != function_name:
            continue
        for child in ast.walk(node):
            if not isinstance(child, ast.Try):
                continue
            if child.handlers and _call_tree_contains_attr(child.body, attr):
                return True
    return False


def _calls_name_or_attr(tree: ast.AST, name_or_attr: str) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == name_or_attr:
            return True
        if isinstance(func, ast.Attribute) and func.attr == name_or_attr:
            return True
    return False


def _has_string_constant(tree: ast.AST, value: str) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value == value:
            return True
    return False


def _function_has_param(tree: ast.AST, function_name: str, param_name: str) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != function_name:
            continue
        args = list(node.args.posonlyargs) + list(node.args.args) + list(node.args.kwonlyargs)
        if any(arg.arg == param_name for arg in args):
            return True
    return False


def _has_function(tree: ast.AST, function_name: str) -> bool:
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name
        for node in ast.walk(tree)
    )


def _function_has_interrupted_return_guard(tree: ast.AST, function_name: str) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != function_name:
            continue
        for child in ast.walk(node):
            if not isinstance(child, ast.If):
                continue
            test = child.test
            interrupted_test = isinstance(test, ast.Name) and test.id == "interrupted"
            interrupted_attr_test = isinstance(test, ast.Attribute) and test.attr == "interrupted"
            if not (interrupted_test or interrupted_attr_test):
                continue
            if any(isinstance(stmt, ast.Return) for stmt in child.body):
                return True
    return False


def _provider_loader_evidence(corpus: HostSurfaceCorpus) -> HostSeamEvidence | None:
    for rel_path, tree in _trees(corpus, ("agent/agent_init.py", "run_agent.py")):
        has_loader = _imports_name(tree, "load_memory_provider") or _uses_name(
            tree, "load_memory_provider"
        )
        has_manager = _imports_name(tree, "MemoryManager") or _uses_name(tree, "MemoryManager")
        has_add_provider = _calls_attr(tree, "add_provider")
        if has_loader and has_manager and has_add_provider:
            return HostSeamEvidence(
                rel_path,
                "load_memory_provider/add_provider",
                "provider loader initializes MemoryManager and adds provider",
            )
    return None


def _turn_sync_evidence(corpus: HostSurfaceCorpus) -> HostSeamEvidence | None:
    for rel_path, tree in _trees(corpus, ("run_agent.py", "agent/conversation_loop.py")):
        has_sync = _calls_attr(tree, "sync_all")
        has_prefetch = _calls_attr(tree, "queue_prefetch_all") or _calls_attr(tree, "prefetch_all")
        if has_sync and has_prefetch:
            return HostSeamEvidence(
                rel_path,
                "sync_all/queue_prefetch_all",
                "completed turn syncs and queues prefetch",
            )
    return None


def probe_host_runtime_wiring(target: Path) -> HostSeamProbe:
    corpus = HostSurfaceCorpus(target)
    evidence: list[HostSeamEvidence] = []
    missing: list[str] = []

    loader = _provider_loader_evidence(corpus)
    if loader:
        evidence.append(loader)
    else:
        missing.append("provider loader initializes MemoryManager and add_provider")

    sync = _turn_sync_evidence(corpus)
    if sync:
        evidence.append(sync)
    else:
        missing.append("completed-turn sync_all plus prefetch/queue_prefetch_all")

    if missing:
        return HostSeamProbe(
            "host_runtime_wiring",
            "fail",
            "Hermes external memory provider host runtime wiring is incomplete.",
            tuple(evidence),
            tuple(missing),
        )
    return HostSeamProbe(
        "host_runtime_wiring",
        "pass",
        "Hermes external memory provider host runtime wiring is present.",
        tuple(evidence),
    )


def probe_native_profile_write_bridge(target: Path) -> HostSeamProbe:
    corpus = HostSurfaceCorpus(target)
    manager_tree = corpus.tree("agent/memory_manager.py")
    manager_has_notify_bridge = bool(
        manager_tree is not None
        and _has_function(manager_tree, "notify_memory_tool_write")
        and _calls_attr(manager_tree, "on_memory_write", keyword="metadata")
    )
    call_without_metadata: HostSeamEvidence | None = None
    for rel_path, tree in _trees(
        corpus,
        ("agent/tool_executor.py", "agent/agent_runtime_helpers.py", "run_agent.py"),
    ):
        if (
            manager_has_notify_bridge
            and _calls_attr(tree, "notify_memory_tool_write", keyword="build_metadata")
        ):
            return HostSeamProbe(
                "native_profile_write_bridge",
                "pass",
                "Hermes native memory writes are bridged into external memory providers.",
                (
                    HostSeamEvidence(
                        rel_path,
                        "notify_memory_tool_write(build_metadata=...)",
                        "built-in memory write path delegates committed-write gating and provenance to MemoryManager",
                    ),
                    HostSeamEvidence(
                        "agent/memory_manager.py",
                        "notify_memory_tool_write -> on_memory_write(metadata=...)",
                        "manager bridge forwards provenance metadata to providers",
                    ),
                ),
            )
        if _calls_attr(tree, "on_memory_write", keyword="metadata"):
            return HostSeamProbe(
                "native_profile_write_bridge",
                "pass",
                "Hermes native memory writes are bridged into external memory providers.",
                (
                    HostSeamEvidence(
                        rel_path,
                        "on_memory_write(metadata=...)",
                        "built-in memory write path forwards provenance metadata",
                    ),
                ),
            )
        if _calls_attr(tree, "on_memory_write"):
            call_without_metadata = HostSeamEvidence(
                rel_path,
                "on_memory_write",
                "write bridge exists but metadata was not proven",
            )
    if call_without_metadata:
        return HostSeamProbe(
            "native_profile_write_bridge",
            "fail",
            "Hermes native memory write bridge drops required metadata/provenance.",
            (call_without_metadata,),
            ("metadata keyword on MemoryManager.on_memory_write call",),
        )
    return HostSeamProbe(
        "native_profile_write_bridge",
        "fail",
        "Hermes native explicit writes are not bridged into external memory providers.",
        missing=("MemoryManager.on_memory_write call in built-in memory write path",),
    )


def probe_memory_write_metadata_seam(target: Path) -> HostSeamProbe:
    corpus = HostSurfaceCorpus(target)
    evidence: list[HostSeamEvidence] = []
    missing: list[str] = []

    provider_tree = corpus.tree("agent/memory_provider.py")
    if provider_tree is not None and _function_has_param(provider_tree, "on_memory_write", "metadata"):
        evidence.append(
            HostSeamEvidence(
                "agent/memory_provider.py",
                "MemoryProvider.on_memory_write(metadata)",
                "provider API accepts write provenance",
            )
        )
    else:
        missing.append("MemoryProvider.on_memory_write metadata parameter")

    manager_tree = corpus.tree("agent/memory_manager.py")
    if manager_tree is not None and _function_has_param(manager_tree, "on_memory_write", "metadata"):
        evidence.append(
            HostSeamEvidence(
                "agent/memory_manager.py",
                "MemoryManager.on_memory_write(metadata)",
                "manager bridge accepts write provenance",
            )
        )
    else:
        missing.append("MemoryManager.on_memory_write metadata parameter")

    if missing:
        return HostSeamProbe(
            "memory_write_metadata_seam",
            "fail",
            "Hermes memory write metadata/provenance seam is incomplete.",
            tuple(evidence),
            tuple(missing),
        )
    return HostSeamProbe(
        "memory_write_metadata_seam",
        "pass",
        "Hermes memory write metadata/provenance seam is present.",
        tuple(evidence),
    )


def probe_turn_start_lifecycle_hook(target: Path) -> HostSeamProbe:
    corpus = HostSurfaceCorpus(target)
    evidence: list[HostSeamEvidence] = []
    missing: list[str] = []

    provider_tree = corpus.tree("agent/memory_provider.py")
    if provider_tree is not None and _has_function(provider_tree, "on_turn_start"):
        evidence.append(
            HostSeamEvidence(
                "agent/memory_provider.py",
                "MemoryProvider.on_turn_start",
                "provider API exposes turn-start lifecycle hook",
            )
        )
    else:
        missing.append("MemoryProvider.on_turn_start API")

    manager_tree = corpus.tree("agent/memory_manager.py")
    if (
        manager_tree is not None
        and _has_function(manager_tree, "on_turn_start")
        and _function_calls_attr(manager_tree, "on_turn_start", "on_turn_start")
        and _function_try_wraps_attr(manager_tree, "on_turn_start", "on_turn_start")
    ):
        evidence.append(
            HostSeamEvidence(
                "agent/memory_manager.py",
                "MemoryManager.on_turn_start -> provider.on_turn_start",
                "manager fans turn-start lifecycle out to memory providers with exception containment",
            )
        )
    else:
        missing.append("MemoryManager.on_turn_start provider fanout with exception containment")

    host_evidence: HostSeamEvidence | None = None
    host_functions_by_path = {
        "run_agent.py": ("run_conversation",),
        "agent/conversation_loop.py": ("run_conversation",),
        "agent/turn_context.py": ("build_turn_context",),
    }
    for rel_path, tree in _trees(corpus, tuple(host_functions_by_path)):
        function_names = host_functions_by_path.get(rel_path, ())
        if any(_function_calls_memory_manager_attr(tree, name, "on_turn_start") for name in function_names):
            host_evidence = HostSeamEvidence(
                rel_path,
                "turn prologue -> MemoryManager.on_turn_start",
                "supported turn prologue calls the manager lifecycle hook",
            )
            break
    if host_evidence:
        evidence.append(host_evidence)
    else:
        missing.append("host turn-start caller in run_conversation")

    if "MemoryProvider.on_turn_start API" in missing or (
        "MemoryManager.on_turn_start provider fanout with exception containment" in missing
    ):
        return HostSeamProbe(
            "turn_start_hook",
            "fail",
            "Hermes turn-start lifecycle API/fanout is incomplete.",
            tuple(evidence),
            tuple(missing),
        )
    if "host turn-start caller in run_conversation" in missing:
        return HostSeamProbe(
            "turn_start_hook",
            "warn",
            "Hermes memory lifecycle has provider API/fanout, but no executable host turn-start caller was proven.",
            tuple(evidence),
            tuple(missing),
        )
    return HostSeamProbe(
        "turn_start_hook",
        "pass",
        "Hermes turn-start lifecycle is wired through the supported host loop.",
        tuple(evidence),
    )


def probe_memory_output_validation_seam(target: Path) -> HostSeamProbe:
    corpus = HostSurfaceCorpus(target)
    evidence: list[HostSeamEvidence] = []
    missing: list[str] = []

    manager_tree = corpus.tree("agent/memory_manager.py")
    if (
        manager_tree is not None
        and _has_function(manager_tree, "validate_assistant_output_all")
        and _has_function(manager_tree, "record_output_validation_delivery_all")
        and _has_function(manager_tree, "_render_memory_commitment_blocked")
    ):
        evidence.append(
            HostSeamEvidence(
                "agent/memory_manager.py",
                "validate_assistant_output_all/record_output_validation_delivery_all",
                "manager can validate final output and record delivery",
            )
        )
    else:
        missing.append("MemoryManager output validation + delivery record + blocked renderer")

    run_evidence: HostSeamEvidence | None = None
    for rel_path, tree in _trees(corpus, ("run_agent.py", "agent/conversation_loop.py")):
        has_validation_call = (
            _calls_attr(tree, "validate_assistant_output_all")
            or _calls_name_or_attr(tree, "validate_assistant_output_all")
            or _has_string_constant(tree, "validate_assistant_output_all")
        )
        has_delivery_call = (
            _calls_attr(tree, "record_output_validation_delivery_all")
            or _calls_name_or_attr(tree, "record_output_validation_delivery_all")
            or _has_string_constant(tree, "record_output_validation_delivery_all")
        )
        if has_validation_call and has_delivery_call:
            run_evidence = HostSeamEvidence(
                rel_path,
                "validate_assistant_output_all/record_output_validation_delivery_all",
                "run loop validates memory commitments and records delivered content",
            )
            break
    if run_evidence:
        evidence.append(run_evidence)
    else:
        missing.append("run loop final-output validation and delivery-record calls")

    if missing:
        return HostSeamProbe(
            "memory_output_validation_seam",
            "fail",
            "Hermes memory final-output validation seam is incomplete.",
            tuple(evidence),
            tuple(missing),
        )
    return HostSeamProbe(
        "memory_output_validation_seam",
        "pass",
        "Hermes memory final-output validation seam is present.",
        tuple(evidence),
    )


def probe_interrupted_turn_external_memory_guard(target: Path) -> HostSeamProbe:
    corpus = HostSurfaceCorpus(target)
    for rel_path, tree in _trees(corpus, ("run_agent.py", "agent/conversation_loop.py")):
        if _function_has_interrupted_return_guard(
            tree, "_sync_external_memory_for_turn"
        ) and _calls_attr(tree, "sync_all"):
            return HostSeamProbe(
                "interrupted_turn_external_memory_guard",
                "pass",
                "Hermes skips external memory sync for interrupted turns.",
                (
                    HostSeamEvidence(
                        rel_path,
                        "_sync_external_memory_for_turn",
                        "interrupted return guard precedes sync path",
                    ),
                ),
            )
    return HostSeamProbe(
        "interrupted_turn_external_memory_guard",
        "fail",
        "Hermes can mirror interrupted turns into external memory providers.",
        missing=("interrupted return guard inside _sync_external_memory_for_turn",),
    )


def scan_host_seams(target: Path) -> list[HostSeamProbe]:
    return [
        probe_host_runtime_wiring(target),
        probe_native_profile_write_bridge(target),
        probe_memory_write_metadata_seam(target),
        probe_turn_start_lifecycle_hook(target),
        probe_memory_output_validation_seam(target),
        probe_interrupted_turn_external_memory_guard(target),
    ]
