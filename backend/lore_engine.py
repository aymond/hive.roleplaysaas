from __future__ import annotations

import re
from dataclasses import dataclass
from .models import Lorebook, TriggeredLoreInfo


@dataclass
class LoreScanResult:
    triggered: list[TriggeredLoreInfo]
    context_block: str
    visual_tags_block: str


def replace_tavern_macros(text: str, char_name: str = "Character", user_name: str = "Traveler") -> str:
    if not text:
        return ""
    out = re.sub(r"\{\{\s*char\s*\}\}", char_name, text, flags=re.IGNORECASE)
    out = re.sub(r"\{\{\s*user\s*\}\}", user_name, out, flags=re.IGNORECASE)
    return out


def scan_lorebook(
    lorebook: Lorebook | None,
    text_to_scan: str,
    char_name: str = "Character",
    user_name: str = "Traveler",
    max_entries: int = 8,
) -> LoreScanResult:
    if not lorebook or not lorebook.entries:
        return LoreScanResult(triggered=[], context_block="", visual_tags_block="")

    haystack = (text_to_scan or "").lower()
    matched_entries = []

    for entry in lorebook.entries:
        if not entry.enabled:
            continue

        matched_keys: list[str] = []
        if entry.constant:
            matched_keys.append("[Constant]")
        else:
            for key in entry.keys:
                k_clean = key.strip()
                if not k_clean:
                    continue
                if k_clean.lower() in haystack:
                    matched_keys.append(k_clean)

        if not matched_keys:
            continue

        if entry.secondary_keys and not entry.constant:
            sec_matches = [
                sk.strip()
                for sk in entry.secondary_keys
                if sk.strip() and sk.strip().lower() in haystack
            ]
            if not sec_matches:
                continue
            matched_keys.extend(sec_matches)

        matched_entries.append((entry, matched_keys))

    # Sort by priority descending
    matched_entries.sort(key=lambda item: item[0].priority, reverse=True)
    matched_entries = matched_entries[:max_entries]

    triggered_info: list[TriggeredLoreInfo] = []
    context_lines: list[str] = []
    visual_parts: list[str] = []

    if lorebook.aesthetic_style:
        visual_parts.append(lorebook.aesthetic_style)

    for entry, m_keys in matched_entries:
        resolved_content = replace_tavern_macros(entry.content, char_name=char_name, user_name=user_name)
        resolved_visual = replace_tavern_macros(entry.visual_description, char_name=char_name, user_name=user_name)

        triggered_info.append(
            TriggeredLoreInfo(
                entry_id=entry.id,
                title=entry.title,
                category=entry.category,
                matched_keys=m_keys,
                snippet=resolved_content[:200] + ("..." if len(resolved_content) > 200 else ""),
                visual_description=resolved_visual,
            )
        )
        context_lines.append(f"[{entry.category.upper()}: {entry.title}]\n{resolved_content}")
        if resolved_visual:
            visual_parts.append(resolved_visual)

    context_block = "\n\n".join(context_lines)
    visual_tags_block = ", ".join(dict.fromkeys(p.strip() for p in visual_parts if p.strip()))

    return LoreScanResult(
        triggered=triggered_info,
        context_block=context_block,
        visual_tags_block=visual_tags_block,
    )
