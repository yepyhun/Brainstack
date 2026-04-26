#!/usr/bin/env python3
"""Generate a source payload manifest for Brainstack installer parity checks."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

EXCLUDED_PARTS = {
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}

EXCLUDED_SUFFIXES = {
    ".pyc",
    ".pyo",
}

REQUIRED_REFACTORED_MODULES = {
    "brainstack/storage/store_runtime.py",
    "brainstack/provider/runtime.py",
    "brainstack/retrieval_pipeline/orchestrator.py",
}

PRIVATE_PATH_MARKERS = (
    "/home/",
    "\\home\\",
    "lauratom",
    "Asztal",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _payload_files(root: Path) -> list[Path]:
    brainstack_root = root / "brainstack"
    return sorted(
        path
        for path in brainstack_root.rglob("*")
        if path.is_file()
        and not any(part in EXCLUDED_PARTS for part in path.parts)
        and path.suffix not in EXCLUDED_SUFFIXES
    )


def build_manifest(root: Path) -> dict[str, Any]:
    root = root.resolve()
    entries = [
        {
            "path": path.relative_to(root).as_posix(),
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
        }
        for path in _payload_files(root)
    ]
    paths = {str(entry["path"]) for entry in entries}
    missing_required = sorted(REQUIRED_REFACTORED_MODULES - paths)
    private_path_hits = sorted(
        path
        for path in paths
        if any(marker in path for marker in PRIVATE_PATH_MARKERS)
    )
    return {
        "schema": "brainstack.payload_manifest.v1",
        "root": root.name,
        "file_count": len(entries),
        "files": entries,
        "required_refactor_modules_present": not missing_required,
        "missing_required_refactor_modules": missing_required,
        "private_path_hits": private_path_hits,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--summary", action="store_true", help="emit compact check summary")
    args = parser.parse_args()
    manifest = build_manifest(args.root)
    if args.summary:
        payload = {
            "schema": manifest["schema"],
            "file_count": manifest["file_count"],
            "required_refactor_modules_present": manifest[
                "required_refactor_modules_present"
            ],
            "missing_required_refactor_modules": manifest[
                "missing_required_refactor_modules"
            ],
            "private_path_hits": manifest["private_path_hits"],
        }
    else:
        payload = manifest
    print(json.dumps(payload, indent=2, sort_keys=True))
    if args.check and (
        not manifest["required_refactor_modules_present"] or manifest["private_path_hits"]
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
