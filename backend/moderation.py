from __future__ import annotations

import re
from fastapi import HTTPException
from pydantic import BaseModel, Field

from .models import ModerationPolicy


class ModerationResult(BaseModel):
    blocked: bool = False
    matched_terms: list[str] = Field(default_factory=list)
    sanitized_texts: list[str] = Field(default_factory=list)


def scan_for_trigger_words(
    texts: list[str],
    policy: ModerationPolicy | None,
) -> ModerationResult:
    """
    Scans input texts against admin-configured trigger words and regex patterns
    BEFORE any LLM or image generation API call is dispatched.
    """
    if not policy or not policy.enabled:
        return ModerationResult(blocked=False, matched_terms=[], sanitized_texts=list(texts))

    words = [w.strip() for w in (policy.trigger_words or []) if w and w.strip()]
    patterns = [p.strip() for p in (policy.regex_patterns or []) if p and p.strip()]
    if not words and not patterns:
        return ModerationResult(blocked=False, matched_terms=[], sanitized_texts=list(texts))

    word_regex: re.Pattern[str] | None = None
    if words:
        escaped = "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))
        word_regex = re.compile(rf"\b(?:{escaped})\b", flags=re.IGNORECASE)

    compiled_custom: list[re.Pattern[str]] = []
    for pat in patterns:
        try:
            compiled_custom.append(re.compile(pat, flags=re.IGNORECASE))
        except re.error:
            continue

    matched: list[str] = []
    seen_lower: set[str] = set()
    sanitized: list[str] = []

    for text in texts:
        current = text or ""
        if word_regex and current:
            for m in word_regex.finditer(current):
                term = m.group(0)
                if term.lower() not in seen_lower:
                    seen_lower.add(term.lower())
                    matched.append(term)
            if policy.mode == "redact":
                current = word_regex.sub("[redacted]", current)
        for rx in compiled_custom:
            if not current:
                continue
            for m in rx.finditer(current):
                term = m.group(0)
                if term.lower() not in seen_lower:
                    seen_lower.add(term.lower())
                    matched.append(term)
            if policy.mode == "redact":
                current = rx.sub("[redacted]", current)
        sanitized.append(current)

    blocked = bool(matched) and policy.mode == "block"
    return ModerationResult(
        blocked=blocked,
        matched_terms=matched,
        sanitized_texts=sanitized,
    )


def enforce_moderation_or_422(
    texts: list[str],
    policy: ModerationPolicy | None,
    context_label: str = "request",
) -> list[str]:
    """
    Validates texts against the admin ModerationPolicy.
    Raises HTTP 422 before any LLM or image generation API call when blocked.
    Returns sanitized texts (useful when policy.mode == 'redact').
    """
    res = scan_for_trigger_words(texts, policy)
    if res.blocked:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Blocked by SFW moderation policy ({context_label}): "
                f"detected trigger term(s): {', '.join(res.matched_terms)}"
            ),
        )
    return res.sanitized_texts
