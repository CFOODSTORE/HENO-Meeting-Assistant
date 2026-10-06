from __future__ import annotations

import re

QUESTION_PATTERNS = [
    r"\?$",
    r"\b(pouvez[- ]vous|peux[- ]tu|pourriez[- ]vous)\b",
    r"\b(comment|pourquoi|quand|où|quel|quelle|quels|quelles|combien|qui|est[- ]ce que)\b",
    r"\b(confirm|confirmer|expliquer|préciser|clarifier|répondre|indiquer)\b",
]


def looks_like_question(text: str) -> bool:
    cleaned = text.strip().lower()
    if len(cleaned) < 8:
        return False
    return any(re.search(pattern, cleaned, flags=re.I) for pattern in QUESTION_PATTERNS)
