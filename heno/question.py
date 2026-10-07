from __future__ import annotations

import re

QUESTION_PATTERNS = [
    r"\?$",
    # French direct questions / requests
    r"\b(pouvez[- ]vous|peux[- ]tu|pourriez[- ]vous|est[- ]ce que)\b",
    r"\b(comment|pourquoi|quand|où|quel|quelle|quels|quelles|combien|qui)\b",
    r"\b(confirmer|expliquer|préciser|clarifier|répondre|indiquer)\b",
    # English WH questions / auxiliaries / meeting requests
    r"\b(what|why|when|where|which|who|whom|whose|how)\b",
    r"\b(can you|could you|would you|will you|do you|did you|are you|is there|are there|have you|has anyone)\b",
    r"\b(confirm|explain|clarify|specify|tell us|tell me|indicate|describe|elaborate|update us|update me)\b",
]


def looks_like_question(text: str) -> bool:
    cleaned = text.strip().lower()
    if len(cleaned) < 8:
        return False
    return any(re.search(pattern, cleaned, flags=re.I) for pattern in QUESTION_PATTERNS)
