from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any, Iterable

from .db import BrainstackStore


FILE_CORPUS_SOURCE_SCHEMA = "brainstack.file_corpus_source.v1"
DEFAULT_MAX_FILE_BYTES = 128_000
DEFAULT_MAX_SECTIONS = 24
DEFAULT_SECTION_CHAR_LIMIT = 900

DENY_NAME_MARKERS: tuple[str, ...] = (
    ".env",
    "auth",
    "cookie",
    "credential",
    "key",
    "login",
    "secret",
    "session",
    "token",
)

DENY_SUFFIXES: tuple[str, ...] = (
    ".json",
    ".lock",
    ".pem",
    ".sqlite",
    ".sqlite3",
    ".yaml",
    ".yml",
)


@dataclass(frozen=True)
class FileCorpusSourceConfig:
    source_root: Path
    allow_patterns: tuple[str, ...]
    source_adapter: str = "file_corpus"
    doc_kind: str = "file_document"
    principal_scope_key: str = ""
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES
    max_sections: int = DEFAULT_MAX_SECTIONS
    section_char_limit: int = DEFAULT_SECTION_CHAR_LIMIT


def _hash_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _relative_posix(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _is_dot_path(relative_path: str) -> bool:
    return any(part.startswith(".") for part in Path(relative_path).parts)


def _looks_private_config(relative_path: str) -> bool:
    name = Path(relative_path).name.casefold()
    suffix = Path(relative_path).suffix.casefold()
    if suffix in DENY_SUFFIXES:
        return True
    return any(marker in name for marker in DENY_NAME_MARKERS)


def _is_binary(payload: bytes) -> bool:
    return b"\x00" in payload


def _first_heading_or_stem(relative_path: str, text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            if title:
                return title
    return Path(relative_path).stem.replace("-", " ").replace("_", " ").strip() or relative_path


def _split_sections(text: str, *, section_char_limit: int, max_sections: int) -> tuple[list[dict[str, Any]], int]:
    normalized = "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").splitlines()).strip()
    if not normalized:
        return [], 0

    blocks: list[tuple[str, str]] = []
    current_heading = "Section 1"
    current_lines: list[str] = []
    for line in normalized.splitlines():
        if line.startswith("#") and line.lstrip("#").strip():
            if current_lines:
                blocks.append((current_heading, "\n".join(current_lines).strip()))
                current_lines = []
            current_heading = line.lstrip("#").strip()
            continue
        current_lines.append(line)
    if current_lines:
        blocks.append((current_heading, "\n".join(current_lines).strip()))
    if not blocks:
        blocks = [(current_heading, normalized)]

    sections: list[dict[str, Any]] = []
    for heading, block in blocks:
        paragraphs = [part.strip() for part in block.split("\n\n") if part.strip()]
        current = ""
        for paragraph in paragraphs:
            if not current:
                current = paragraph
                continue
            if len(current) + 2 + len(paragraph) <= section_char_limit:
                current = f"{current}\n\n{paragraph}"
                continue
            sections.append({"heading": heading, "content": current})
            current = paragraph
        if current:
            sections.append({"heading": heading, "content": current})

    skipped = max(0, len(sections) - max_sections)
    return sections[:max_sections], skipped


def _iter_allowed_files(root: Path, allow_patterns: Iterable[str]) -> list[Path]:
    files: dict[str, Path] = {}
    for pattern in allow_patterns:
        pattern_text = str(pattern or "").strip()
        if not pattern_text:
            continue
        for path in root.glob(pattern_text):
            if path.is_file() or path.is_symlink():
                files[str(path)] = path
    return [files[key] for key in sorted(files)]


def collect_file_corpus_sources(config: FileCorpusSourceConfig) -> dict[str, Any]:
    root = config.source_root.expanduser().resolve()
    if not config.allow_patterns:
        raise ValueError("file corpus source requires explicit allow_patterns")
    if not root.exists() or not root.is_dir():
        raise ValueError("file corpus source_root must be an existing directory")

    sources: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for candidate in _iter_allowed_files(root, config.allow_patterns):
        raw_path = candidate
        resolved = candidate.resolve()
        if not _is_relative_to(resolved, root):
            skipped.append({"path": str(raw_path), "reason": "symlink_traversal_denied"})
            continue
        relative_path = _relative_posix(resolved, root)
        if raw_path.is_symlink():
            skipped.append({"path": relative_path, "reason": "symlink_denied"})
            continue
        if _is_dot_path(relative_path):
            skipped.append({"path": relative_path, "reason": "dotfile_denied"})
            continue
        if _looks_private_config(relative_path):
            skipped.append({"path": relative_path, "reason": "private_or_config_name_denied"})
            continue
        size = resolved.stat().st_size
        if size > config.max_file_bytes:
            skipped.append({"path": relative_path, "reason": "oversized_file_denied", "byte_count": size})
            continue
        payload = resolved.read_bytes()
        if _is_binary(payload):
            skipped.append({"path": relative_path, "reason": "binary_file_denied"})
            continue
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError:
            skipped.append({"path": relative_path, "reason": "decode_failed"})
            continue

        content_hash = _hash_bytes(payload)
        sections, skipped_sections = _split_sections(
            text,
            section_char_limit=max(240, int(config.section_char_limit)),
            max_sections=max(1, int(config.max_sections)),
        )
        if not sections:
            skipped.append({"path": relative_path, "reason": "empty_file_denied"})
            continue
        if skipped_sections:
            skipped.append(
                {
                    "path": relative_path,
                    "reason": "section_cap_exceeded",
                    "skipped_section_count": skipped_sections,
                }
            )

        stable_key = f"{config.source_adapter}:{relative_path}"
        source_id = relative_path
        section_payloads = []
        for index, section in enumerate(sections):
            section_payloads.append(
                {
                    "heading": str(section["heading"]),
                    "content": str(section["content"]),
                    "metadata": {
                        "file_corpus_source": {
                            "schema": FILE_CORPUS_SOURCE_SCHEMA,
                            "relative_path": relative_path,
                            "content_hash": content_hash,
                            "section_index": index,
                        },
                    },
                }
            )
        sources.append(
            {
                "source_adapter": config.source_adapter,
                "source_id": source_id,
                "stable_key": stable_key,
                "title": _first_heading_or_stem(relative_path, text),
                "doc_kind": config.doc_kind,
                "source_uri": str(resolved),
                "sections": section_payloads,
                "metadata": {
                    "principal_scope_key": config.principal_scope_key,
                    "authority_class": "corpus_supporting",
                    "canonical": False,
                    "file_corpus_source": {
                        "schema": FILE_CORPUS_SOURCE_SCHEMA,
                        "relative_path": relative_path,
                        "content_hash": content_hash,
                        "byte_count": size,
                        "section_count": len(section_payloads),
                    },
                },
            }
        )

    return {
        "schema": FILE_CORPUS_SOURCE_SCHEMA,
        "source_root": str(root),
        "allow_patterns": list(config.allow_patterns),
        "source_adapter": config.source_adapter,
        "doc_kind": config.doc_kind,
        "sources": sources,
        "skipped": skipped,
        "source_count": len(sources),
        "skipped_count": len(skipped),
    }


def ingest_file_corpus_sources(store: BrainstackStore, config: FileCorpusSourceConfig) -> dict[str, Any]:
    collected = collect_file_corpus_sources(config)
    receipts = [store.ingest_corpus_source(source) for source in collected["sources"]]
    statuses: dict[str, int] = {}
    for receipt in receipts:
        status = str(receipt.get("status") or "unknown")
        statuses[status] = statuses.get(status, 0) + 1
    return {
        "schema": FILE_CORPUS_SOURCE_SCHEMA,
        "source_root": collected["source_root"],
        "source_count": collected["source_count"],
        "skipped_count": collected["skipped_count"],
        "skipped": collected["skipped"],
        "receipt_count": len(receipts),
        "statuses": statuses,
        "receipts": receipts,
    }
