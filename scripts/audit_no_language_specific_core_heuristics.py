#!/usr/bin/env python3
"""Fail if Brainstack core contains live-case language patches."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_ACCENT_CODEPOINTS = {
    0x00C1,
    0x00C9,
    0x00CD,
    0x00D3,
    0x00D6,
    0x00DA,
    0x00DC,
    0x00E1,
    0x00E9,
    0x00ED,
    0x00F3,
    0x00F6,
    0x00FA,
    0x00FC,
    0x0150,
    0x0151,
    0x0170,
    0x0171,
}
FORBIDDEN_ASCII_TERMS = tuple(bytes.fromhex(value).decode("utf-8") for value in ("4578616d706c654e616d65446174697665",))


def _contains_forbidden_literal(text: str) -> bool:
    lowered = text.casefold()
    if any(term.casefold() in lowered for term in FORBIDDEN_ASCII_TERMS):
        return True
    return any(ord(char) in FORBIDDEN_ACCENT_CODEPOINTS for char in text)


def main() -> int:
    hits: list[str] = []
    for path in (ROOT / "brainstack").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if _contains_forbidden_literal(text):
            hits.append(str(path.relative_to(ROOT)))
    if hits:
        print("FAIL language-specific core heuristic hits:")
        print("\n".join(hits))
        return 1
    print("PASS no language-specific core heuristic hits")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
