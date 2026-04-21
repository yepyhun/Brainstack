from __future__ import annotations

from typing import Any, Dict, List


def build_profile_stable_key(category: str, content: str) -> str:
    normalized_category = " ".join(str(category or "").strip().lower().split())
    normalized_content = " ".join(str(content or "").strip().lower().split())
    return f"{normalized_category}:{normalized_content}" if normalized_category or normalized_content else ""


def extract_profile_candidates(text: str) -> List[Dict[str, Any]]:
    del text
    return []
