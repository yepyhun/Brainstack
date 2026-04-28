#!/usr/bin/env python3
"""Public fixture hygiene scanner.

Default scope is intentionally narrow: public memory-kernel fixtures and public
trace docs. Live/private Discord scripts are excluded unless passed explicitly.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


DEFAULT_PATHS = (
    Path("tests/fixtures/public_memory_kernel"),
    Path("docs/EVIDENCE_TRACE_REASON_CODES.md"),
)

SECRET_PATTERNS = {
    "discord_token": re.compile(r"[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{20,}"),
    "github_token": re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
    "openai_key": re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    "absolute_home_path": re.compile(r"/home/[A-Za-z0-9_.-]+/"),
    "desktop_local_path": re.compile(r"Asztal" r"/ai/"),
    "live_discord_url": re.compile(r"https://discord\.com/channels/"),
}


@dataclass(frozen=True)
class HygieneFinding:
    path: str
    line: int
    kind: str
    preview: str


def iter_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if not path.exists():
            continue
        if path.is_file():
            files.append(path)
        else:
            files.extend(p for p in sorted(path.rglob("*")) if p.is_file())
    return files


def scan_text(text: str, *, path: str = "<memory>") -> list[HygieneFinding]:
    findings: list[HygieneFinding] = []
    for line_no, line in enumerate(text.splitlines(), 1):
        for kind, pattern in SECRET_PATTERNS.items():
            if pattern.search(line):
                findings.append(
                    HygieneFinding(
                        path=path,
                        line=line_no,
                        kind=kind,
                        preview=line.strip()[:160],
                    )
                )
    return findings


def scan_paths(paths: list[Path]) -> list[HygieneFinding]:
    findings: list[HygieneFinding] = []
    for path in iter_files(paths):
        try:
            text = path.read_text(errors="ignore")
        except OSError as exc:
            findings.append(HygieneFinding(str(path), 0, "read_error", str(exc)))
            continue
        findings.extend(scan_text(text, path=str(path)))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", help="Optional paths. Defaults to public fixtures.")
    args = parser.parse_args()
    paths = [Path(item) for item in args.paths] if args.paths else list(DEFAULT_PATHS)
    findings = scan_paths(paths)
    for finding in findings:
        print(f"{finding.path}:{finding.line}: {finding.kind}: {finding.preview}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
