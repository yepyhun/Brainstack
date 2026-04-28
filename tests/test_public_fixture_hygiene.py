from __future__ import annotations

from pathlib import Path

from scripts.check_public_test_hygiene import scan_paths, scan_text


FIXTURE_DIR = Path("tests/fixtures/public_memory_kernel")


def test_public_fixture_hygiene_passes_for_committed_corpus() -> None:
    assert scan_paths([FIXTURE_DIR]) == []


def test_hygiene_scanner_rejects_seeded_fake_secrets() -> None:
    seeded = "\n".join(
        [
            "token = " + "ghp_" + "a" * 28,
            "discord = " + ".".join(("a" * 24, "b" * 6, "c" * 28)),
            "path = " + "/" + "home/example/private/project",
            "url = " + "https://" + "discord.com/channels/1/2/3",
        ]
    )
    kinds = {finding.kind for finding in scan_text(seeded)}

    assert "github_token" in kinds
    assert "discord_token" in kinds
    assert "absolute_home_path" in kinds
    assert "live_discord_url" in kinds
