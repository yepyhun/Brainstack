"""Runtime context accounting helpers for Hermes/Brainstack sessions.

This module is intentionally observe-only. It counts context pressure without
storing raw user/tool content in the report.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence


SCHEMA_VERSION = "brainstack.runtime_context_accounting.v1"

PREFLIGHT_RE = re.compile(r"Preflight compression:\s*~?([\d,]+)\s+tokens", re.I)
COMPRESSION_FAILURE_RE = re.compile(
    r"(compression summary failed|summary generation failed|auxiliary.*timeout|compression.*timeout)",
    re.I,
)
COMPRESSION_SUCCESS_RE = re.compile(r"(compression summary succeeded|summary generated|compaction succeeded)", re.I)

TOOL_CATEGORY_MAP = {
    "skill_view": "skill_view",
    "skills_list": "skill_catalog",
    "read_file": "read_file",
    "search_files": "search_files",
    "terminal": "terminal",
    "kanban": "kanban",
    "kanban_list": "kanban",
    "kanban_show": "kanban",
    "brainstack_recall": "brainstack",
    "brainstack_inspect": "brainstack",
    "brainstack_stats": "brainstack",
    "brainstack_remember": "brainstack",
}


def estimate_tokens_from_chars(chars: int) -> int:
    return max(1, int(chars) // 4) if chars else 0


def _content_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, Mapping):
                if isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif isinstance(item.get("content"), str):
                    parts.append(item["content"])
                else:
                    parts.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    if isinstance(value, Mapping):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _iter_messages(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, list):
        for item in value:
            yield from _iter_messages(item)
        return
    if not isinstance(value, Mapping):
        return
    if "role" in value and ("content" in value or "tool_calls" in value):
        yield value
    for key in ("messages", "turns", "history", "items"):
        nested = value.get(key)
        if isinstance(nested, (list, Mapping)):
            yield from _iter_messages(nested)


def _messages_from_payload(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping) and isinstance(value.get("messages"), list):
        return [item for item in value["messages"] if isinstance(item, Mapping)]
    return list(_iter_messages(value))


def _tool_name_from_message(message: Mapping[str, Any]) -> str:
    for key in ("name", "tool_name", "tool"):
        value = message.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    content = _content_to_text(message.get("content"))
    match = re.search(r"\b(skill_view|read_file|search_files|terminal|kanban_[a-z_]+|brainstack_[a-z_]+)\b", content)
    if match:
        return match.group(1)
    return "unknown_tool"


def _tool_call_name_map(messages: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for message in messages:
        if message.get("role") != "assistant":
            continue
        for tool_call in message.get("tool_calls") or []:
            if not isinstance(tool_call, Mapping):
                continue
            function = tool_call.get("function")
            name = function.get("name") if isinstance(function, Mapping) else None
            if not isinstance(name, str) or not name:
                continue
            for key in ("id", "call_id"):
                call_id = tool_call.get(key)
                if isinstance(call_id, str) and call_id:
                    mapping[call_id] = name
    return mapping


def classify_tool(tool_name: str) -> str:
    name = str(tool_name or "").strip()
    if name in TOOL_CATEGORY_MAP:
        return TOOL_CATEGORY_MAP[name]
    for prefix, category in (
        ("brainstack_", "brainstack"),
        ("kanban_", "kanban"),
        ("skill_", "skill_view"),
    ):
        if name.startswith(prefix):
            return category
    return "other_tool"


@dataclass(frozen=True)
class MessageAccounting:
    role: str
    chars: int
    tool_name: str | None = None
    tool_category: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CompressionAccounting:
    preflight_events: int
    preflight_min_tokens: int | None
    preflight_max_tokens: int | None
    preflight_avg_tokens: float | None
    failure_lines: int
    success_lines: int
    verdict: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_compression_accounting(log_text: str) -> CompressionAccounting:
    preflight_tokens: list[int] = []
    failure_lines = 0
    success_lines = 0
    for line in (log_text or "").splitlines():
        match = PREFLIGHT_RE.search(line)
        if match:
            preflight_tokens.append(int(match.group(1).replace(",", "")))
        if COMPRESSION_FAILURE_RE.search(line):
            failure_lines += 1
        if COMPRESSION_SUCCESS_RE.search(line):
            success_lines += 1
    if failure_lines and not success_lines:
        verdict = "critical"
    elif failure_lines:
        verdict = "degraded"
    elif preflight_tokens:
        verdict = "observed"
    else:
        verdict = "not_observed"
    avg = (sum(preflight_tokens) / len(preflight_tokens)) if preflight_tokens else None
    return CompressionAccounting(
        preflight_events=len(preflight_tokens),
        preflight_min_tokens=min(preflight_tokens) if preflight_tokens else None,
        preflight_max_tokens=max(preflight_tokens) if preflight_tokens else None,
        preflight_avg_tokens=round(avg, 1) if avg is not None else None,
        failure_lines=failure_lines,
        success_lines=success_lines,
        verdict=verdict,
    )


def account_session_payload(payload: Any) -> list[MessageAccounting]:
    rows: list[MessageAccounting] = []
    if isinstance(payload, Mapping):
        system_prompt = payload.get("system_prompt")
        if isinstance(system_prompt, str) and system_prompt:
            rows.append(MessageAccounting(role="system", chars=len(system_prompt)))
        tools = payload.get("tools")
        if isinstance(tools, (list, Mapping)):
            rows.append(MessageAccounting(role="tool_schema", chars=len(_content_to_text(tools))))

    messages = _messages_from_payload(payload)
    call_names = _tool_call_name_map(messages)
    for message in messages:
        role = str(message.get("role") or "unknown")
        text = _content_to_text(message.get("content"))
        chars = len(text)
        if role == "tool":
            tool_call_id = message.get("tool_call_id")
            tool_name = call_names.get(tool_call_id) if isinstance(tool_call_id, str) else None
            tool_name = tool_name or _tool_name_from_message(message)
            rows.append(
                MessageAccounting(
                    role=role,
                    chars=chars,
                    tool_name=tool_name,
                    tool_category=classify_tool(tool_name),
                )
            )
        else:
            rows.append(MessageAccounting(role=role, chars=chars))
    return rows


def account_session_file(path: Path) -> list[MessageAccounting]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return []
    return account_session_payload(payload)


def build_context_accounting_report(
    session_paths: Sequence[Path],
    *,
    log_text: str = "",
    max_top_tools: int = 20,
) -> dict[str, Any]:
    role_chars: Counter[str] = Counter()
    role_messages: Counter[str] = Counter()
    tool_chars: Counter[str] = Counter()
    tool_messages: Counter[str] = Counter()
    category_chars: Counter[str] = Counter()
    category_messages: Counter[str] = Counter()
    files_read = 0
    files_failed = 0

    for path in session_paths:
        rows = account_session_file(path)
        if rows:
            files_read += 1
        else:
            files_failed += 1
        for row in rows:
            role_chars[row.role] += row.chars
            role_messages[row.role] += 1
            if row.tool_name:
                tool_chars[row.tool_name] += row.chars
                tool_messages[row.tool_name] += 1
            if row.tool_category:
                category_chars[row.tool_category] += row.chars
                category_messages[row.tool_category] += 1

    tools: list[dict[str, Any]] = []
    for name, chars in tool_chars.most_common(max_top_tools):
        tools.append(
            {
                "name": name,
                "category": classify_tool(name),
                "chars": chars,
                "messages": tool_messages[name],
                "tokens_est": estimate_tokens_from_chars(chars),
            }
        )

    categories: list[dict[str, Any]] = []
    for category, chars in category_chars.most_common():
        categories.append(
            {
                "category": category,
                "chars": chars,
                "messages": category_messages[category],
                "tokens_est": estimate_tokens_from_chars(chars),
            }
        )

    roles = {
        role: {
            "chars": role_chars[role],
            "messages": role_messages[role],
            "tokens_est": estimate_tokens_from_chars(role_chars[role]),
        }
        for role in sorted(role_chars)
    }
    compression = parse_compression_accounting(log_text)
    total_chars = sum(role_chars.values())
    return {
        "schema": SCHEMA_VERSION,
        "session_files": {
            "read": files_read,
            "failed_or_empty": files_failed,
            "input_count": len(session_paths),
        },
        "totals": {
            "chars": total_chars,
            "tokens_est": estimate_tokens_from_chars(total_chars),
        },
        "roles": roles,
        "tool_categories": categories,
        "top_tools": tools,
        "compression": compression.to_dict(),
        "privacy": {
            "raw_content_included": False,
            "paths_included": False,
        },
    }


def newest_session_paths(session_dir: Path, *, limit: int = 30) -> list[Path]:
    if not session_dir.exists():
        return []
    paths = [path for path in session_dir.rglob("*.json") if path.is_file()]
    paths.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return paths[:limit]
