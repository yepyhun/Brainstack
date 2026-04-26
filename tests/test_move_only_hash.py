from __future__ import annotations

from pathlib import Path

from scripts.brainstack_move_only_hash import symbol_ast_hash


def test_symbol_ast_hash_ignores_comments_and_whitespace(tmp_path: Path) -> None:
    first = tmp_path / "first.py"
    second = tmp_path / "second.py"
    first.write_text(
        "def target(value: int) -> int:\n"
        "    # comment ignored by AST\n"
        "    return value + 1\n",
        encoding="utf-8",
    )
    second.write_text(
        "\n\n"
        "def target(value: int) -> int:\n"
        "    return value + 1\n",
        encoding="utf-8",
    )

    assert symbol_ast_hash(first, "target")["ast_sha256"] == symbol_ast_hash(
        second, "target"
    )["ast_sha256"]


def test_symbol_ast_hash_detects_behavior_body_change(tmp_path: Path) -> None:
    first = tmp_path / "first.py"
    second = tmp_path / "second.py"
    first.write_text("def target(value: int) -> int:\n    return value + 1\n", encoding="utf-8")
    second.write_text("def target(value: int) -> int:\n    return value + 2\n", encoding="utf-8")

    assert symbol_ast_hash(first, "target")["ast_sha256"] != symbol_ast_hash(
        second, "target"
    )["ast_sha256"]
