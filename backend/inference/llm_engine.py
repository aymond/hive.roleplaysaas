from __future__ import annotations

import difflib
import hashlib
import os
import re
import time
import httpx
from typing import Any

from ..logger import logger
from ..lore_engine import replace_tavern_macros
from ..models import CharacterCard, ChatMessage, InferenceConfig, TriggeredLoreInfo


async def check_ollama_status(base_url: str) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            resp = await client.get(f"{base_url.rstrip('/')}/api/tags")
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
                return {"online": True, "models": models}
    except Exception:
        pass
    return {"online": False, "models": []}


async def check_openai_compat_status(base_url: str, api_key: str = "lm-studio") -> dict[str, Any]:
    try:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        async with httpx.AsyncClient(timeout=1.5) as client:
            resp = await client.get(f"{base_url.rstrip('/')}/models", headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("id", "") for m in data.get("data", []) if m.get("id")]
                return {"online": True, "models": models}
    except Exception:
        pass
    return {"online": False, "models": []}


def build_tavern_system_prompt(
    character: CharacterCard,
    lore_context: str,
    user_name: str = "Traveler",
    user_desc: str = "",
) -> str:
    parts: list[str] = []
    if character.system_prompt:
        parts.append(replace_tavern_macros(character.system_prompt, character.name, user_name))
    else:
        parts.append(
            f"Write {character.name}'s next reply in a vivid, character-driven roleplay with {user_name}. "
            f"Stay true to {character.name}'s voice, mannerisms, and world lore. Use *italics* for actions and physical description, and quotes for spoken dialogue."
        )

    parts.append(f"### Character Persona: {character.name} ({character.title})")
    if character.description:
        parts.append(replace_tavern_macros(character.description, character.name, user_name))
    if character.personality:
        parts.append(f"Personality: {replace_tavern_macros(character.personality, character.name, user_name)}")
    if character.scenario:
        parts.append(f"Scenario: {replace_tavern_macros(character.scenario, character.name, user_name)}")
    if user_desc:
        parts.append(f"User Persona ({user_name}): {user_desc}")
    if lore_context:
        parts.append(f"### Active World Lorebook Context:\n{lore_context}")
    if character.mes_example:
        parts.append(f"### Example Dialogue:\n{replace_tavern_macros(character.mes_example, character.name, user_name)}")
    if character.post_history_instructions:
        parts.append(replace_tavern_macros(character.post_history_instructions, character.name, user_name))

    return "\n\n".join(parts)


async def _call_ollama_chat(
    config: InferenceConfig,
    messages: list[dict[str, str]],
    purpose: str = "chat",
    temperature_override: float | None = None,
    repeat_penalty: float = 1.18,
    seed: int | None = None,
) -> str | None:
    status = await check_ollama_status(config.ollama_base_url)
    if not status["online"] or not status["models"]:
        return None
    available = status["models"]
    target = (config.ollama_model or "").strip()
    if target in available:
        model_to_use = target
    else:
        partial = next((m for m in available if target.lower() in m.lower()), None)
        if partial:
            model_to_use = partial
        else:
            hermes_match = next((m for m in available if "hermes" in m.lower()), None)
            model_to_use = hermes_match or available[0]
    t0 = time.perf_counter()
    temp = temperature_override if temperature_override is not None else config.temperature
    call_seed = seed if seed is not None else int.from_bytes(os.urandom(4), "big")
    last_user = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")
    logger.info(
        "🤖 OLLAMA→  | purpose=%s | model=%s | temp=%.2f | repeat_penalty=%.2f | input=%r",
        purpose,
        model_to_use,
        temp,
        repeat_penalty,
        (last_user[:120] + "...") if len(last_user) > 120 else last_user,
    )
    logger.debug("🤖 OLLAMA→  | Full messages payload: %s", messages)
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(
                f"{config.ollama_base_url.rstrip('/')}/api/chat",
                json={
                    "model": model_to_use,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": temp,
                        "num_predict": config.max_tokens,
                        "repeat_penalty": repeat_penalty,
                        "repeat_last_n": 256,
                        "top_p": 0.92,
                        "min_p": 0.05,
                        "seed": call_seed,
                    },
                },
            )
            elapsed = time.perf_counter() - t0
            if resp.status_code == 200:
                data = resp.json()
                content = data.get("message", {}).get("content", "").strip()
                if content:
                    logger.info(
                        "✅ OLLAMA←  | purpose=%s | %.2fs | output=%r",
                        purpose,
                        elapsed,
                        (content[:160] + "...") if len(content) > 160 else content,
                    )
                    logger.debug("✅ OLLAMA←  | Full reply: %s", content)
                    return content
            else:
                logger.warning("⚠️ OLLAMA←  | HTTP %d after %.2fs", resp.status_code, elapsed)
    except Exception as exc:
        logger.warning("⚠️ OLLAMA←  | Error calling Ollama (%s): %s", purpose, exc)
    return None


async def _call_openai_compat_chat(
    config: InferenceConfig,
    messages: list[dict[str, str]],
) -> str | None:
    try:
        headers = {"Authorization": f"Bearer {config.openai_api_key}"} if config.openai_api_key else {}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{config.openai_base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json={
                    "model": config.openai_model,
                    "messages": messages,
                    "temperature": config.temperature,
                    "max_tokens": config.max_tokens,
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                choices = data.get("choices", [])
                if choices:
                    content = choices[0].get("message", {}).get("content", "").strip()
                    if content:
                        return content
    except Exception:
        pass
    return None


def _synthesize_roleplay_reply(
    character: CharacterCard,
    user_message: str,
    triggered_lore: list[TriggeredLoreInfo],
    user_name: str = "Traveler",
    variation_index: int = 0,
) -> str:
    seed_bytes = hashlib.sha256(
        f"{character.id}:{user_message}:{variation_index}".encode("utf-8")
    ).digest()
    pick = seed_bytes[0] % 3

    lore_mention = ""
    if triggered_lore:
        top_lore = triggered_lore[0]
        lore_mention = (
            f" *A faint resonance stirs at the mention of **{top_lore.title}**—{top_lore.snippet[:110].rstrip('.')}...* "
        )

    clean_user = user_message.strip() or "approaches quietly"
    trait = (character.personality.split(",")[0].strip() if character.personality else "observant").lower()

    if pick == 0:
        return (
            f"*{character.name} pauses, {trait} eyes catching the ambient light as {user_name} speaks.*"
            f"{lore_mention}\n\n"
            f"\"You speak of `{clean_user[:65]}` as though the currents here aren't already shifting,\" "
            f"*{character.name} murmurs, stepping closer to examine the surroundings.* "
            f"\"If we mean to press deeper into {character.scenario[:70] if character.scenario else 'this realm'}, "
            f"we'll need more than curiosity. Tell me—what did you see before you crossed the threshold?\""
        )
    elif pick == 1:
        return (
            f"*A subtle smile crosses {character.name}'s expression, tempered by {trait} poise.*"
            f"{lore_mention}\n\n"
            f"\"Careful, {user_name}. Words carry weight in places like this.\"\n\n"
            f"*{character.name} traces a slow arc through the air, the atmosphere thickening with quiet tension.* "
            f"\"Still... your instinct regarding '{clean_user[:55]}' aligns with what I've suspected since we arrived. "
            f"Shall we test that theory together, or fortify our position first?\""
        )
    else:
        return (
            f"*{character.name} turns toward {user_name}, cloak shifting softly as the environment responds.*"
            f"{lore_mention}\n\n"
            f"\"I wondered when you'd bring that up,\" *{character.name} says in a low, measured cadence.* "
            f"\"Every record I've studied points back to this exact convergence. Lead the way, {user_name}—I'm right behind you.\""
        )


async def generate_roleplay_reply(
    config: InferenceConfig,
    character: CharacterCard,
    history: list[ChatMessage],
    lore_context: str,
    triggered_lore: list[TriggeredLoreInfo],
    user_name: str = "Traveler",
    user_desc: str = "",
    variation_index: int = 0,
) -> tuple[str, str]:
    """Returns (reply_text, provider_used)."""
    sys_prompt = build_tavern_system_prompt(character, lore_context, user_name, user_desc)
    messages: list[dict[str, str]] = [{"role": "system", "content": sys_prompt}]
    for msg in history[-12:]:
        role = "assistant" if msg.role == "assistant" else "user"
        messages.append({"role": role, "content": msg.content})

    last_user_msg = next((m.content for m in reversed(history) if m.role == "user"), "Hello.")
    prev_assistant_msg = next((m.content for m in reversed(history) if m.role == "assistant"), "")

    if config.llm_provider in ("auto", "ollama"):
        temp_ov = min(1.0, config.temperature + 0.15) if variation_index > 0 else None
        rep_pen = 1.22 if variation_index > 0 else 1.18
        res = await _call_ollama_chat(
            config,
            messages,
            purpose=f"roleplay_reply({character.name})",
            temperature_override=temp_ov,
            repeat_penalty=rep_pen,
        )
        if res and prev_assistant_msg:
            sim = difflib.SequenceMatcher(None, prev_assistant_msg.strip(), res.strip()).ratio()
            if sim > 0.82:
                logger.warning(
                    "⚠️ OLLAMA↻  | Detected near-duplicate reply (similarity=%.2f) for %s — retrying with anti-repeat prompt",
                    sim,
                    character.name,
                )
                retry_messages = [
                    *messages,
                    {
                        "role": "system",
                        "content": (
                            f"[Important: Your previous reply already happened. Write a completely fresh, "
                            f"non-repetitive response from {character.name} directly addressing {user_name}'s latest message "
                            f"and advancing the scene. Do NOT reuse the same opening or sentences.]"
                        ),
                    },
                ]
                retry_res = await _call_ollama_chat(
                    config,
                    retry_messages,
                    purpose=f"roleplay_reply_retry({character.name})",
                    temperature_override=min(1.05, config.temperature + 0.22),
                    repeat_penalty=1.28,
                )
                if retry_res:
                    res = retry_res
        if res:
            return res, f"ollama ({config.ollama_model})"

    if config.llm_provider in ("auto", "openai_compat"):
        res = await _call_openai_compat_chat(config, messages)
        if res:
            return res, f"openai_compat ({config.openai_model})"

    reply = _synthesize_roleplay_reply(
        character=character,
        user_message=last_user_msg,
        triggered_lore=triggered_lore,
        user_name=user_name,
        variation_index=variation_index,
    )
    return reply, "builtin_synth (Apple Silicon Local Narrative Engine)"


async def generate_node_text(
    config: InferenceConfig,
    system_instruction: str,
    user_prompt: str,
    mode: str = "visual_prompt",
) -> tuple[str, str]:
    """Executes an LLM node inside the ComfyUI-style workflow graph."""
    messages = [
        {"role": "system", "content": system_instruction or "You are a creative world-building and visual prompt director."},
        {"role": "user", "content": user_prompt},
    ]

    if config.llm_provider in ("auto", "ollama"):
        res = await _call_ollama_chat(config, messages, purpose=f"workflow_node({mode})")
        if res:
            return res, f"ollama ({config.ollama_model})"

    if config.llm_provider in ("auto", "openai_compat"):
        res = await _call_openai_compat_chat(config, messages)
        if res:
            return res, f"openai_compat ({config.openai_model})"

    # Built-in Apple Silicon deterministic prompt & lore expander
    cleaned = " ".join(user_prompt.strip().split())
    if mode == "lore_expand":
        expanded = (
            f"[Codex Chronicle Synthesis]\n"
            f" Core Premise: {cleaned}\n"
            f" Architectural & Cultural Signatures: Obsidian-forged spires veined with luminescent aether conduits, "
            f"watched over by sentinel orders who record history in crystalline memory vaults.\n"
            f" Dramatic Hook: Beneath the surface calm, rival factions contest the ancient calibration relays."
        )
    else:
        expanded = (
            f"masterpiece cinematic keyframe, {cleaned}, dramatic volumetric rim lighting, "
            f"intricate costume and environmental storytelling, anamorphic lens flare, "
            f"rich color grading, ultra-detailed concept art, 8k resolution"
        )
    return expanded, "builtin_synth"


def clean_character_visual_tags_for_scene(visual_tags: str, scene_text: str) -> str:
    """
    Preserves the character's attractive core beauty, facial, and physical traits while removing
    only conflicting static outfit tags when the active scene specifies its own attire/body state.
    """
    if not visual_tags:
        return ""
    s_lower = scene_text.lower()
    has_custom_attire_or_body_state = any(
        kw in s_lower
        for kw in (
            "bikini",
            "swim",
            "nude",
            "naked",
            "undress",
            "unclasp",
            "topless",
            "bare",
            "lingerie",
            "gown",
            "towel",
            "water",
            "waves",
            "lagoon",
            "pool",
            "bed",
            "sheet",
            "skin",
            "breasts",
            "nipple",
            "labia",
            "vulva",
            "pussy",
            "clit",
            "vagina",
            "thighs",
            "full body",
        )
    )

    segments = [seg.strip() for seg in visual_tags.split(",") if seg.strip()]
    filtered: list[str] = []
    for seg in segments:
        seg_l = seg.lower()
        # Strip 'portrait of ' or 'photographic portrait of ' so full-body / action scenes aren't cropped into headshots
        if "portrait of " in seg_l:
            idx = seg_l.find("portrait of ") + len("portrait of ")
            remainder = seg[idx:].strip()
            seg = remainder if "stunning" in remainder.lower() or "woman" in remainder.lower() else f"stunning {remainder}"
            seg_l = seg.lower()

        if has_custom_attire_or_body_state and any(
            cloth in seg_l for cloth in ("dress", "cloak", "trenchcoat", "coat", "gown", "robe", "armor", "suit")
        ):
            continue
        if seg_l in ("8k", "photorealistic", "masterpiece"):
            continue
        filtered.append(seg)

    return ", ".join(filtered)


def build_anatomical_and_clothing_overrides(
    scene_text: str,
    distilled_keywords: str = "",
) -> tuple[str, str, str]:
    """
    Detects explicit nudity / breast / vulva / labia requests in the active turn or distilled tags
    and returns:
      (weighted_positive_boost_tags, cleaned_distilled_keywords, negative_clothing_blockers)
    so that Pony / SDXL models strictly obey anatomical requests without defaulting back to bikinis/crops.
    """
    combined = f"{scene_text} {distilled_keywords}".lower()

    wants_lower_nudity = any(
        k in combined
        for k in (
            "labia",
            "vulva",
            "pussy",
            "vagina",
            "clit",
            "clitoris",
            "cleft of venus",
            "spread legs",
            "spreading legs",
            "spread her legs",
            "between her legs",
            "pubic",
        )
    )
    wants_upper_nudity = any(
        k in combined
        for k in (
            "breast",
            "breasts",
            "nipple",
            "nipples",
            "areola",
            "topless",
            "bare chest",
            "expose",
            "exposing",
            "unclasp",
            "pulls down top",
            "slides off top",
        )
    )
    wants_full_nudity = any(
        k in combined
        for k in (
            "nude",
            "naked",
            "nudist",
            "undress",
            "strips",
            "slipping off",
            "slips off",
            "without clothes",
            "bare skin",
        )
    )

    pos_boosts: list[str] = []
    neg_blockers: list[str] = []

    if wants_lower_nudity:
        pos_boosts.extend(
            [
                "(nsfw, uncensored, completely nude, naked:1.35)",
                "(pussy, detailed vulva, labia, cleft of venus:1.4)",
                "(spread legs, open thighs, full body, lower body focus:1.3)",
            ]
        )
        neg_blockers.extend(
            [
                "clothed",
                "bikini",
                "swimsuit",
                "swimwear",
                "panties",
                "underwear",
                "bottoms",
                "shorts",
                "skirt",
                "dress",
                "covered pussy",
                "censored",
                "mosaic censorship",
                "bar censor",
                "close-up face portrait",
            ]
        )

    if wants_upper_nudity:
        if not wants_lower_nudity:
            pos_boosts.append("(nsfw, uncensored, topless, nude:1.3)")
        pos_boosts.append("(bare breasts, exposed breasts, detailed nipples, areolae:1.35)")
        if not wants_lower_nudity:
            pos_boosts.append("(cowboy shot, upper body and waist visible:1.2)")
        neg_blockers.extend(
            [
                "bra",
                "bikini top",
                "swimsuit",
                "covered breasts",
                "covered nipples",
                "pasties",
                "dress",
                "shirt",
                "clothed",
                "censored",
            ]
        )

    if wants_full_nudity and not (wants_lower_nudity or wants_upper_nudity):
        pos_boosts.extend(
            [
                "(nsfw, uncensored, completely nude, naked:1.3)",
                "(bare breasts, nipples, pussy, full body:1.25)",
            ]
        )
        neg_blockers.extend(
            [
                "clothed",
                "bikini",
                "swimsuit",
                "swimwear",
                "underwear",
                "bra",
                "panties",
                "dress",
                "towel",
                "censored",
            ]
        )

    # If the user wants nudity/exposed anatomy, strip any lingering 'bikini'/'dress'/'swimsuit' words
    # from the LLM-distilled keywords so CLIP doesn't draw a bikini anyway
    cleaned_kw = distilled_keywords
    if wants_lower_nudity or wants_upper_nudity or wants_full_nudity:
        filtered_tags: list[str] = []
        for tag in distilled_keywords.split(","):
            t_clean = tag.strip()
            t_low = t_clean.lower()
            if any(
                cloth in t_low
                for cloth in ("bikini", "swimsuit", "sundress", "dress", "linen", "clothed", "bra", "panties")
            ):
                continue
            if t_clean:
                filtered_tags.append(t_clean)
        cleaned_kw = ", ".join(filtered_tags)

    dedup_neg = ", ".join(dict.fromkeys(neg_blockers))
    return ", ".join(pos_boosts), cleaned_kw, dedup_neg


def build_face_detailer_prompt(base_prompt: str, is_pony: bool = True) -> tuple[str, str]:
    """
    Builds a dedicated (positive_face_prompt, negative_face_prompt) for the 768x768 ADetailer
    face crop pass. Keeps facial/hair/eye/lighting descriptors from base_prompt while stripping
    full-body, torso, and lower-body tags so the face pass focuses 100% on facial symmetry and eyes.
    """
    body_and_wide_terms = (
        "full body",
        "cowboy shot",
        "lower body",
        "spread legs",
        "open thighs",
        "pussy",
        "vulva",
        "labia",
        "cleft of venus",
        "clit",
        "bare breasts",
        "exposed breasts",
        "nipples",
        "areola",
        "topless",
        "waist-deep",
        "standing",
        "walking",
        "lying",
        "kneeling",
        "sitting",
        "legs",
        "thighs",
        "hips",
        "waist",
        "feet",
        "barefoot",
    )

    kept_traits: list[str] = []
    for raw_seg in base_prompt.split(","):
        seg = raw_seg.strip(" ()")
        seg_l = seg.lower()
        if not seg or seg_l.startswith("score_"):
            continue
        if any(term in seg_l for term in body_and_wide_terms):
            continue
        if any(
            face_kw in seg_l
            for face_kw in (
                "face",
                "eye",
                "hair",
                "lips",
                "smile",
                "gaze",
                "cheek",
                "skin",
                "kunis",
                "jovovich",
                "resemblance",
                "woman",
                "chronomancer",
                "queen",
                "sun-kissed",
                "golden hour",
                "sunset",
                "lighting",
                "glamour",
                "painterly",
            )
        ):
            # Remove weight suffixes like :1.35 if present
            clean_seg = re.sub(r":\d+(\.\d+)?", "", seg).strip()
            if clean_seg and clean_seg not in kept_traits:
                kept_traits.append(clean_seg)

    prefix = "score_9, score_8_up, score_7_up, masterpiece" if is_pony else "masterpiece, 8k"
    face_core = (
        "(closeup portrait of face:1.2), (detailed symmetrical eyes, sharp circular iris and pupils, "
        "natural eye catchlights:1.3), breathtakingly beautiful face, natural skin texture, "
        "soft detailed lips, subtle warm expression"
    )
    traits_str = ", ".join(kept_traits[:10])
    pos_face = ", ".join(p for p in (prefix, face_core, traits_str) if p)

    neg_prefix = "score_4, score_5, score_6, " if is_pony else ""
    neg_face = (
        f"{neg_prefix}asymmetric eyes, cross-eyed, strabismus, deformed pupils, irregular iris, "
        "blurry face, melted face, red nose, glowing nose, clown makeup, oversaturated skin, "
        "extra eyes, multiple faces, full body, torso, breasts, bad anatomy, deformed, watermark"
    )
    return pos_face, neg_face


_PROSE_STOPWORDS = {
    "the", "and", "for", "that", "this", "with", "from", "your", "have", "are", "was", "were",
    "into", "over", "under", "where", "when", "while", "after", "before", "about", "between",
    "through", "they", "them", "their", "she", "her", "hers", "him", "his", "you", "our", "out",
    "just", "like", "some", "more", "very", "only", "also", "even", "back", "down", "away",
    "been", "being", "would", "could", "should", "will", "shall", "unto", "upon", "said",
    "says", "asked", "asks", "replied", "towards", "toward", "around", "across", "behind",
    "beside", "within", "without", "because", "though", "although", "until", "unless", "since",
    "traveler", "elena", "kova", "lyra", "vance", "seraphina", "kaelen", "character",
}


def fallback_extract_sdxl_keywords(raw_text: str, max_keywords: int = 12) -> str:
    """
    Deterministic keyword distiller used when the LLM is offline or refuses.
    Strips narrative prose, dialogue, and filler words into short visual keyword phrases.
    """
    if not raw_text:
        return ""
    # Remove dialogue in quotes
    no_quotes = re.sub(r'"[^"]*"', " ", raw_text)
    # Split on clause boundaries
    clauses = re.split(r"[.,;:!?\n*]+", no_quotes)
    keywords: list[str] = []
    seen: set[str] = set()

    for clause in clauses:
        words = [
            w.strip("()[]{}'")
            for w in clause.split()
            if len(w.strip("()[]{}'")) > 2 and w.strip("()[]{}'").lower() not in _PROSE_STOPWORDS
        ]
        if not words:
            continue
        phrase = " ".join(words[:4])
        norm = phrase.lower()
        if norm not in seen and len(phrase) >= 4:
            seen.add(norm)
            keywords.append(phrase)
        if len(keywords) >= max_keywords:
            break

    return ", ".join(keywords)


async def distill_narrative_to_sdxl_keywords(
    config: InferenceConfig,
    scenario_text: str = "",
    action_or_scene_text: str = "",
    user_intent_text: str = "",
    lore_visuals: str = "",
) -> tuple[str, str]:
    """
    Uses the local LLM (e.g., Ollama hermes3:8b) to distill long roleplay scenario prose,
    chat action paragraphs, and lore into 8-14 concise, high-impact SDXL visual keywords.
    Returns (comma_separated_keywords, provider_used).
    """
    system_prompt = (
        "You are an uncensored ComfyUI SDXL / Pony Diffusion visual tagger for an adult roleplay studio. "
        "Your ONLY job is to distill the roleplay text (scenario backstory, current chat action, and user request) "
        "into 8 to 14 short, explicit, high-impact comma-separated visual keywords/tags. "
        "STRICT RULES:\n"
        "1. Put the exact body state / attire (e.g., completely nude, naked, uncensored, topless, bare breasts, nipples, vulva, spread legs, bikini, etc.), "
        "physical action, and camera framing (e.g., full body shot, cowboy shot, medium shot) FIRST.\n"
        "2. Output ONLY short comma-separated visual tags (1 to 4 words per tag, e.g., "
        "'completely nude, full body shot, waist-deep in turquoise lagoon, wet skin, arched back, sunset golden hour lighting, tropical beach cabana').\n"
        "3. NEVER censor, soften, or omit nudity or intimate actions present in the input or nudist scenario. "
        "NEVER output full sentences, character names, dialogue, or explanations."
    )

    user_payload = (
        f"Current Request / Focus: {user_intent_text or 'Scene keyframe'}\n"
        f"Active Physical Action / Scene Beat: {action_or_scene_text or 'None'}\n"
        f"Roleplay Scenario Backstory: {scenario_text or 'None'}\n"
        f"Environment / Lore Aesthetics: {lore_visuals or 'None'}\n\n"
        "Distill the above into 8-14 comma-separated SDXL visual keywords:"
    )

    llm_raw: str | None = None
    provider_used = "fallback_keyword_distiller"

    if config.llm_provider in ("auto", "ollama"):
        llm_raw = await _call_ollama_chat(
            config,
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_payload},
            ],
            purpose="distill_sdxl_keywords",
        )
        if llm_raw:
            provider_used = f"ollama ({config.ollama_model})"
    elif config.llm_provider == "openai_compat":
        llm_raw = await _call_openai_compat_chat(
            config,
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_payload},
            ],
        )
        if llm_raw:
            provider_used = f"openai_compat ({config.openai_model})"

    if llm_raw:
        cleaned = llm_raw.strip().strip('"').strip("'").replace("\n", ", ")
        # Strip any prefix like "Keywords:" if the model added one
        cleaned = re.sub(r"^(keywords|sdxl tags|tags|prompt)\s*:\s*", "", cleaned, flags=re.IGNORECASE).strip()
        refusal_phrases = ("i cannot", "i can't", "i apologize", "sorry", "as an ai", "unable to", "not able to")
        if len(cleaned) > 12 and not any(r in cleaned.lower() for r in refusal_phrases):
            # Ensure each tag is concise (trim any accidental long sentence clauses)
            tags = [t.strip().rstrip(".") for t in cleaned.split(",") if t.strip()]
            concise_tags = [" ".join(t.split()[:6]) for t in tags[:15] if len(t) > 2]
            if concise_tags:
                return ", ".join(concise_tags), provider_used

    fallback_kw = fallback_extract_sdxl_keywords(
        f"{user_intent_text}, {action_or_scene_text}, {scenario_text}, {lore_visuals}",
        max_keywords=12,
    )
    return fallback_kw, "fallback_keyword_distiller"


def extract_action_and_scene_beats(messages: list[ChatMessage], target_msg: ChatMessage) -> tuple[str, str]:
    """
    Extracts (user_intent, character_action_beats) from the target message and its surrounding turn.
    Reads the ENTIRE message (all paragraphs), prioritizing *italicized physical actions* and user requests.
    """
    try:
        idx = messages.index(target_msg)
    except ValueError:
        idx = len(messages) - 1

    # Gather surrounding turn context (previous user msg + target msg + next assistant msg if target is user)
    start_idx = max(0, idx - 1)
    end_idx = min(len(messages), idx + 2)
    window = messages[start_idx:end_idx]

    user_parts: list[str] = []
    action_parts: list[str] = []

    for m in window:
        content = m.content.strip()
        if not content:
            continue
        if m.role == "user":
            user_parts.append(content.replace("*", "").replace('"', "").strip())
        else:
            # Extract all *italicized* action blocks across all paragraphs
            italics = re.findall(r"\*([^*]+)\*", content)
            if italics:
                action_parts.extend(i.strip() for i in italics if i.strip())
            else:
                # Remove spoken dialogue in quotes to focus on visual description
                no_quotes = re.sub(r'"[^"]*"', "", content)
                cleaned = " ".join(no_quotes.split())
                if cleaned:
                    action_parts.append(cleaned)

    # Also ensure the target message's own actions are placed at the very front
    target_italics = re.findall(r"\*([^*]+)\*", target_msg.content)
    if target_italics:
        # Put the most dramatic/later action paragraphs of target_msg first
        prioritized = list(reversed([i.strip() for i in target_italics if i.strip()]))
        action_parts = prioritized + [a for a in action_parts if a not in prioritized]

    user_intent = "; ".join(dict.fromkeys(user_parts))
    char_actions = ". ".join(dict.fromkeys(action_parts))
    return user_intent, char_actions


async def build_contextual_scene_prompt(
    config: InferenceConfig,
    character: CharacterCard | None,
    messages: list[ChatMessage],
    target_msg: ChatMessage,
    lore_visuals: str = "",
    user_name: str = "Traveler",
    user_desc: str = "",
    render_mode_override: str | None = None,
) -> str:
    """
    Synthesizes a high-attractiveness SDXL prompt by:
    1. Preserving the character's core beauty & facial resemblance tags (e.g. Mila Kunis / Milla Jovovich blend)
    2. Using the LLM to distill the long scenario + current chat turn into 8-14 crisp SDXL visual keywords
    3. Applying the selected artistic style mode (Hybrid Refiner, Stylized Glamour Art, or Raw Photo)
    """
    char_name = character.name if character else "Character"
    scenario_text = ""
    if character and character.scenario:
        scenario_text = replace_tavern_macros(character.scenario, char_name=char_name, user_name=user_name)

    user_intent, char_actions = extract_action_and_scene_beats(messages, target_msg)
    combined_scene_text = f"{user_intent} {char_actions} {scenario_text}"

    raw_visual_tags = character.visual_prompt_tags if character else ""
    physical_traits = clean_character_visual_tags_for_scene(raw_visual_tags, combined_scene_text)

    distilled_keywords, _ = await distill_narrative_to_sdxl_keywords(
        config=config,
        scenario_text=scenario_text,
        action_or_scene_text=char_actions or target_msg.content,
        user_intent_text=user_intent,
        lore_visuals=lore_visuals,
    )

    anat_boost, cleaned_distilled_kw, _ = build_anatomical_and_clothing_overrides(
        scene_text=f"{user_intent} {char_actions or target_msg.content} {scenario_text}",
        distilled_keywords=distilled_keywords,
    )

    is_pony = "pony" in (config.comfyui_checkpoint or "").lower()
    active_mode = render_mode_override or getattr(config, "comfyui_render_mode", "hybrid_refiner")

    if active_mode == "single_raw":
        quality_prefix = (
            "score_9, score_8_up, score_7_up, masterpiece, photorealistic, 8k, breathtakingly attractive"
            if is_pony
            else "masterpiece, photorealistic, 8k, breathtakingly attractive"
        )
        style_suffix = "cinematic golden hour lighting, shallow depth of field, intricate skin texture, raw photo"
    else:
        # Both 'hybrid_refiner' and 'single_stylized' use the lush painterly golden-hour glamour illustration tags
        quality_prefix = (
            "score_9, score_8_up, score_7_up, masterpiece, stylized glamour digital art, painterly golden hour illustration, breathtakingly attractive"
            if is_pony
            else "masterpiece, stylized glamour digital art, painterly golden hour illustration, 8k, breathtakingly attractive"
        )
        style_suffix = (
            "dramatic warm sunset rim lighting, luminous bronze and amber color grading, "
            "soft painterly skin glow, romantic atmosphere, 8k"
        )

    # Front-load weighted anatomical boost tags + distilled action keywords FIRST so CLIP prioritizes the active pose & nudity!
    prompt_parts = [
        quality_prefix,
        anat_boost,
        cleaned_distilled_kw,
        physical_traits,
        style_suffix,
    ]
    return ", ".join(p.strip().rstrip(",") for p in prompt_parts if p and p.strip())
