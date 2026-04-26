#!/usr/bin/env python3
"""AST-normalized symbol hash for MOVE_ONLY refactor proof."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any


class SymbolNotFound(LookupError):
    pass


def _iter_symbol_children(node: ast.AST) -> list[ast.AST]:
    children: list[ast.AST] = []
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            children.append(child)
    return children


def find_symbol(tree: ast.Module, symbol_path: str) -> ast.AST:
    parts = [part for part in symbol_path.split(".") if part]
    if not parts:
        raise ValueError("symbol_path must be non-empty")

    current: ast.AST = tree
    for part in parts:
        for child in _iter_symbol_children(current):
            if getattr(child, "name", None) == part:
                current = child
                break
        else:
            raise SymbolNotFound(symbol_path)
    return current


def normalized_ast_hash(node: ast.AST) -> str:
    payload = ast.dump(node, annotate_fields=True, include_attributes=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def symbol_ast_hash(path: Path, symbol_path: str) -> dict[str, Any]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    node = find_symbol(tree, symbol_path)
    return {
        "path": str(path),
        "symbol": symbol_path,
        "node_type": type(node).__name__,
        "ast_sha256": normalized_ast_hash(node),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("symbol")
    args = parser.parse_args()
    print(json.dumps(symbol_ast_hash(args.path, args.symbol), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
