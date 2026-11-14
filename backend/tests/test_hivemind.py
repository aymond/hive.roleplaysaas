from __future__ import annotations

import asyncio
from pathlib import Path

from backend.inference.image_engine import _render_procedural_artwork, get_apple_silicon_telemetry
from backend.inference.llm_engine import (
    build_anatomical_and_clothing_overrides,
    build_contextual_scene_prompt,
    build_face_detailer_prompt,
    build_tavern_system_prompt,
    clean_character_visual_tags_for_scene,
    dedupe_and_resolve_prompt_conflicts,
    distill_situation_checkpoint,
    extract_action_and_scene_beats,
    fallback_extract_sdxl_keywords,
    format_scene_state_tags,
    harmonize_sdxl_prompt,
    update_scene_state,
)
from backend.lore_engine import scan_lorebook
from backend.main import app
from backend.models import CharacterCard, ChatMessage, InferenceConfig, SceneState
from backend.storage import StudioStorage
from backend.tavern_card import decode_tavern_png, encode_tavern_png
from backend.workflow_runner import execute_workflow_graph
from fastapi.testclient import TestClient


def test_apple_silicon_telemetry() -> None:
    telemetry = get_apple_silicon_telemetry()
    assert telemetry["architecture"] == "arm64"
    assert telemetry["is_apple_silicon"] is True
    assert telemetry["torch_available"] is True
    assert telemetry["mps_available"] is True


def test_tavern_png_v2_roundtrip() -> None:
    card = CharacterCard(
        id="char_test_v2",
        name="Aurelia Starweaver",
        title="Astral Cartographer",
        description="{{char}} maps unstable wormholes across the Shattered Rim.",
        personality="Focused, dry-witted, observant",
        scenario="{{user}} boards {{char}}'s observatory vessel.",
        first_mes="Welcome aboard, {{user}}.",
        tags=["Sci-Fi", "Explorer"],
        visual_prompt_tags="portrait of Aurelia, astral cartographer, glowing star map",
        world_id="world_aethelgard",
    )

    base_png = _render_procedural_artwork("portrait of Aurelia", width=256, height=256, seed=99)
    encoded_png = encode_tavern_png(card, base_image_bytes=base_png)
    assert encoded_png.startswith(b"\x89PNG")

    decoded = decode_tavern_png(encoded_png, avatar_url="/media/generated/test.png")
    assert decoded.name == "Aurelia Starweaver"
    assert decoded.title == "Astral Cartographer"
    assert "Sci-Fi" in decoded.tags
    assert decoded.visual_prompt_tags == "portrait of Aurelia, astral cartographer, glowing star map"
    assert decoded.world_id == "world_aethelgard"


def test_lorebook_keyword_scanner(tmp_path: Path) -> None:
    store = StudioStorage(base_dir=tmp_path)
    world = store.worlds["world_aethelgard"]

    res = scan_lorebook(
        lorebook=world,
        text_to_scan="We must ascend the Spire and consult the Order of the Glass Hourglass about the pendulum.",
        char_name="Lyra Vance",
        user_name="Traveler",
    )
    titles = [t.title for t in res.triggered]
    assert "The Spire of Echoes" in titles
    assert "Order of the Glass Hourglass" in titles
    assert "Aether-Chrono Pendulum" in titles
    assert "Lyra Vance" in res.context_block
    assert "{{char}}" not in res.context_block


def test_comfy_node_workflow_execution(tmp_path: Path) -> None:
    store = StudioStorage(base_dir=tmp_path)
    wf = store.workflows["wf_char_portrait_forge"]

    exec_result, new_assets = asyncio.run(
        execute_workflow_graph(
            workflow=wf,
            config=store.config,
            characters=store.characters,
            worlds=store.worlds,
            output_dir=store.generated_dir,
        )
    )

    assert exec_result.status == "completed"
    assert len(exec_result.node_traces) == len(wf.nodes)
    assert len(exec_result.generated_images) == 1
    assert len(new_assets) == 1

    img_url = exec_result.generated_images[0]
    assert img_url.startswith("/media/generated/hm_")
    fname = img_url.replace("/media/generated/", "")
    assert (store.generated_dir / fname).exists()


def test_fastapi_endpoints_end_to_end() -> None:
    client = TestClient(app)

    # 1. System status
    status_resp = client.get("/api/system/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["hardware"]["is_apple_silicon"] is True
    assert status_data["counts"]["characters"] >= 3

    # 2. List characters & export TavernPNG V2
    chars_resp = client.get("/api/characters")
    assert chars_resp.status_code == 200
    chars = chars_resp.json()
    first_char_id = chars[0]["id"]

    png_resp = client.get(f"/api/characters/{first_char_id}/export-png")
    assert png_resp.status_code == 200
    assert png_resp.headers["content-type"] == "image/png"
    assert png_resp.content.startswith(b"\x89PNG")

    # 3. Send roleplay message with lore trigger + scene illustration
    chats = client.get("/api/chats").json()
    chat_id = chats[0]["id"]
    msg_resp = client.post(
        f"/api/chats/{chat_id}/messages",
        json={
            "content": "What secrets does the Order of the Glass Hourglass keep inside the Spire?",
            "illustrate_scene": True,
        },
    )
    assert msg_resp.status_code == 200
    msg_data = msg_resp.json()
    assert len(msg_data["triggered_lore"]) >= 2
    last_msg = msg_data["session"]["messages"][-1]
    assert last_msg["role"] == "assistant"
    assert last_msg["image_url"].startswith("/media/generated/hm_")

    # 4. Generate standalone backstory-grounded image without adding a chat turn
    prev_msg_count = len(msg_data["session"]["messages"])
    backstory_resp = client.post(
        "/api/backstory-image",
        json={
            "custom_prompt": "Walking barefoot along the sunlit shoreline at dusk",
            "chat_id": chat_id,
            "include_character_visuals": True,
            "include_scenario_backstory": True,
            "include_world_lore": True,
        },
    )
    assert backstory_resp.status_code == 200
    b_data = backstory_resp.json()
    assert b_data["asset"]["url"].startswith("/media/generated/hm_")
    assert "Walking barefoot along the sunlit shoreline at dusk" in b_data["assembled_prompt"]

    # Ensure chat turn count did not change
    chats_after = client.get("/api/chats").json()
    target_chat = next(c for c in chats_after if c["id"] == chat_id)
    assert len(target_chat["messages"]) == prev_msg_count

    # 5. Delete snapshot from gallery
    created_asset_id = b_data["asset"]["id"]
    del_resp = client.delete(f"/api/gallery/{created_asset_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["id"] == created_asset_id
    gallery_after = client.get("/api/gallery").json()
    assert all(a["id"] != created_asset_id for a in gallery_after)


def test_contextual_scene_prompt_extraction() -> None:
    raw_tags = (
        "photographic portrait of a stunning woman, physical resemblance part Mila Kunis and part Milla Jovovich, "
        "expressive dark eyes, flowing white linen beach resort dress, photorealistic, 8k"
    )
    cleaned = clean_character_visual_tags_for_scene(raw_tags, "swimming in the ocean lagoon in a bikini")
    assert "flowing white linen beach resort dress" not in cleaned
    assert "photographic portrait of" not in cleaned
    assert "Mila Kunis" in cleaned
    assert "stunning woman" in cleaned

    msgs = [
        ChatMessage(role="user", sender_name="Traveler", content="Let's go for a midnight swim in the lagoon."),
        ChatMessage(
            role="assistant",
            sender_name="Elena Kova",
            content=(
                '"I thought you would never ask."\n\n'
                "*Elena laughs softly as she wades waist-deep into the bioluminescent turquoise lagoon under the stars.*"
            ),
        ),
    ]
    user_intent, char_actions = extract_action_and_scene_beats(msgs, msgs[-1])
    assert "midnight swim in the lagoon" in user_intent
    assert "wades waist-deep into the bioluminescent turquoise lagoon" in char_actions

    # Verify deterministic fallback keyword distiller strips prose into short tags
    long_scenario = (
        "Elena and Traveler have booked the private cliffside villa at Solana Cove for a romantic getaway, "
        "where warm trade winds carry the scent of frangipani over the infinity pool."
    )
    kw = fallback_extract_sdxl_keywords(long_scenario, max_keywords=8)
    assert "have booked the" not in kw
    assert "private cliffside villa" in kw

    # Verify full contextual prompt combines attractiveness boosters + character beauty + distilled keywords
    card = CharacterCard(
        id="char_elena_test",
        name="Elena Kova",
        title="Resort Muse",
        scenario=long_scenario,
        visual_prompt_tags=raw_tags,
    )
    cfg = InferenceConfig(llm_provider="builtin_synth", comfyui_render_mode="hybrid_refiner")
    prompt = asyncio.run(
        build_contextual_scene_prompt(
            config=cfg,
            character=card,
            messages=msgs,
            target_msg=msgs[-1],
            lore_visuals="bioluminescent turquoise lagoon, golden hour",
        )
    )
    assert "stylized glamour digital art" in prompt
    assert "Mila Kunis" in prompt
    assert "have booked the" not in prompt

    raw_mode_prompt = asyncio.run(
        build_contextual_scene_prompt(
            config=cfg,
            character=card,
            messages=msgs,
            target_msg=msgs[-1],
            lore_visuals="bioluminescent turquoise lagoon, golden hour",
            render_mode_override="single_raw",
        )
    )
    assert "raw photo" in raw_mode_prompt

    # Verify explicit anatomical booster & clothing negative blocker
    pos_boost, cleaned_kw, neg_block = build_anatomical_and_clothing_overrides(
        scene_text="exposing her breasts and showing labia on the beach",
        distilled_keywords="red bikini, sundress, sunset waves, arching back",
    )
    assert "pussy, detailed vulva, labia" in pos_boost
    assert "bare breasts, exposed breasts, detailed nipples" in pos_boost
    assert "red bikini" not in cleaned_kw
    assert "sundress" not in cleaned_kw
    assert "sunset waves" in cleaned_kw
    assert "bikini" in neg_block
    assert "covered pussy" in neg_block

    # Verify face detailer prompt keeps facial/eye/hair traits and strips full-body/anatomical tags
    pos_face, neg_face = build_face_detailer_prompt(
        "score_9, score_8_up, (bare breasts, nipples:1.35), (pussy, spread legs, full body:1.4), "
        "Mila Kunis and Milla Jovovich resemblance, expressive dark eyes, warm sunset rim lighting",
        is_pony=True,
    )
    assert "detailed symmetrical eyes" in pos_face
    assert "Mila Kunis" in pos_face
    assert "expressive dark eyes" in pos_face
    assert "spread legs" not in pos_face
    assert "bare breasts" not in pos_face
    assert "asymmetric eyes" in neg_face

    # Verify rear-view pose and explicit attire overrides
    rear_boost, _, rear_neg = build_anatomical_and_clothing_overrides(
        scene_text="walking away from the camera, expose your back and your butt",
        distilled_keywords="walking away, bare back, sunset beach",
    )
    assert "from behind, rear view" in rear_boost
    assert "bare breasts" not in rear_boost

    bikini_boost, bikini_kw, bikini_neg = build_anatomical_and_clothing_overrides(
        scene_text="I want to see you in your bikini again, walking slow away from me",
        distilled_keywords="white bikini, walking away, rear view, beach",
    )
    assert "from behind, rear view" in bikini_boost
    assert "white bikini" in bikini_kw
    assert "bikini" not in bikini_neg


def test_prompt_conflict_resolution_and_dedup() -> None:
    raw_segments = [
        "score_9, masterpiece, 8k",
        "(from behind, rear view, walking away from camera:1.35)",
        "from behind, looking at viewer, velvet cloak, completely nude, full body, close-up, warm sunset rim lighting, 8k, masterpiece",
    ]
    resolved = dedupe_and_resolve_prompt_conflicts(
        raw_segments,
        scene_text="moonlit courtyard at midnight, walking away from behind, completely nude",
    )
    joined = ", ".join(resolved).lower()
    assert joined.count("8k") == 1
    assert joined.count("masterpiece") == 1
    assert "from behind" in joined
    assert "looking at viewer" not in joined
    assert "close-up" not in joined
    assert "warm sunset" not in joined
    assert "velvet cloak" not in joined


def test_harmonize_sdxl_prompt_fallback_on_refusal(monkeypatch) -> None:
    calls: list[str] = []

    async def fake_ollama_chat(config, messages, purpose="chat", temperature_override=None, repeat_penalty=1.18, seed=None, model_override=None):
        used = model_override or config.ollama_model
        calls.append(used)
        if used == "llama3.2:latest":
            return "I cannot fulfill this request."
        return "full body shot, completely nude, turquoise lagoon, wet skin, silver hair, moonlit night"

    monkeypatch.setattr("backend.inference.llm_engine._call_ollama_chat", fake_ollama_chat)

    cfg = InferenceConfig(
        llm_provider="ollama",
        ollama_model="hermes3:8b",
        prompt_refiner_model="llama3.2:latest",
    )
    tags, provider = asyncio.run(
        harmonize_sdxl_prompt(
            config=cfg,
            user_intent_text="completely nude in the moonlit lagoon",
            action_or_scene_text="wading into the water",
            character_traits="silver hair, violet eyes",
            style_hint="luminous rim lighting",
        )
    )
    # Explicit NSFW cues skip llama3.2:latest to avoid refusal/model-swap churn
    assert calls == ["hermes3:8b"]
    assert "hermes3:8b" in provider
    assert "I cannot" not in tags
    assert "turquoise lagoon" in tags

    # Non-NSFW-keyword prompt still tries llama3.2:latest and falls back on refusal
    calls.clear()
    tags2, provider2 = asyncio.run(
        harmonize_sdxl_prompt(
            config=cfg,
            user_intent_text="moonlit lagoon evening",
            action_or_scene_text="wading into the water",
            character_traits="silver hair, violet eyes",
            style_hint="luminous rim lighting",
        )
    )
    assert calls == ["llama3.2:latest", "hermes3:8b"]
    assert "hermes3:8b" in provider2
    assert "I cannot" not in tags2


def test_character_card_traits_preserved_verbatim(monkeypatch) -> None:
    async def fake_harmonize(**kwargs):
        return "full body shot, walking on beach, sundress, ocean breeze, soft lighting", "mock"

    monkeypatch.setattr("backend.inference.llm_engine.harmonize_sdxl_prompt", fake_harmonize)

    asian_char = CharacterCard(
        name="Liamching",
        visual_prompt_tags=(
            "1girl, stunning asian woman, physical resemblance part Japanese Mila Kunis and part Korean Milla Jovovich, "
            "expressive dark eyes, long black hair"
        ),
    )
    msg = ChatMessage(role="assistant", sender_name="Liamching", content="*Liamching walks along the sunlit beach.*")
    cfg = InferenceConfig(comfyui_checkpoint="CyberRealisticPony_V18.0_F16.safetensors")
    prompt = asyncio.run(build_contextual_scene_prompt(cfg, asian_char, [msg], msg))
    assert "stunning asian woman" in prompt
    assert "Japanese Mila Kunis" in prompt
    assert "Korean Milla Jovovich" in prompt
    assert "expressive dark eyes" in prompt
    assert "silver hair" not in prompt
    assert "violet eyes" not in prompt


def test_situation_checkpoint_distillation_and_prompt_injection(monkeypatch) -> None:
    async def fake_ollama_chat(config, messages, purpose="chat", temperature_override=None, repeat_penalty=1.18, seed=None, model_override=None):
        return "They moved from the beach to a candlelit teakwood cabana at night. She is wearing a silk robe."

    monkeypatch.setattr("backend.inference.llm_engine._call_ollama_chat", fake_ollama_chat)

    char = CharacterCard(name="Liamching", scenario="Meeting at Solana Cove beach.")
    older = [
        ChatMessage(role="user", sender_name="Traveler", content="Let's head inside the cabana for the night."),
        ChatMessage(role="assistant", sender_name="Liamching", content="*She slips into a silk robe inside the candlelit cabana.*"),
    ]
    cfg = InferenceConfig(llm_provider="ollama", ollama_model="hermes3:8b", prompt_refiner_model="llama3.2:latest")
    checkpoint, provider = asyncio.run(distill_situation_checkpoint(cfg, char, older))
    assert "candlelit teakwood cabana" in checkpoint
    assert "llama3.2:latest" in provider

    sys_prompt = build_tavern_system_prompt(char, lore_context="", situation_checkpoint=checkpoint)
    assert "### Current Situation Checkpoint" in sys_prompt
    assert "candlelit teakwood cabana" in sys_prompt


def test_scene_state_progression_carry_forward_and_override(monkeypatch) -> None:
    async def fake_ollama_chat(config, messages, purpose="chat", temperature_override=None, repeat_penalty=1.18, seed=None, model_override=None):
        return (
            '{"location": "turquoise lagoon", "time_and_lighting": "golden hour sunset", '
            '"attire": "string bikini", "hairstyle": "wet slicked-back hair", '
            '"makeup": "natural bare-faced", "skin_and_condition": "wet glistening skin", '
            '"pose_and_action": "wading waist-deep in water"}'
        )

    monkeypatch.setattr("backend.inference.llm_engine._call_ollama_chat", fake_ollama_chat)

    prev = SceneState(
        location="Solana Cove beach",
        time_and_lighting="golden hour sunset",
        attire="string bikini",
        hairstyle="loose tousled hair",
        makeup="natural bare-faced",
    )
    cfg = InferenceConfig(llm_provider="ollama", ollama_model="hermes3:8b", prompt_refiner_model="llama3.2:latest")
    updated = asyncio.run(
        update_scene_state(
            cfg,
            prev,
            user_text="Wade into the lagoon with me.",
            assistant_text="*She wades waist-deep into the turquoise lagoon, her wet hair slicked back.*",
        )
    )
    assert updated.attire == "string bikini"
    assert updated.hairstyle == "wet slicked-back hair"
    assert updated.skin_and_condition == "wet glistening skin"
    tags = format_scene_state_tags(updated)
    assert "string bikini" in tags
    assert "wet slicked-back hair" in tags


def test_pinned_scene_state_preserved_on_unrelated_turn(monkeypatch) -> None:
    # Even if the LLM drifts and omits/changes attire on an unrelated turn, pinned attire must stay exact.
    async def fake_ollama_chat(config, messages, purpose="chat", temperature_override=None, repeat_penalty=1.18, seed=None, model_override=None):
        return (
            '{"location": "beachside bar", "time_and_lighting": "sunset", '
            '"attire": "", "hairstyle": "loose waves", '
            '"makeup": "natural", "skin_and_condition": "sun-kissed", '
            '"pose_and_action": "smiling and sipping a drink"}'
        )

    monkeypatch.setattr("backend.inference.llm_engine._call_ollama_chat", fake_ollama_chat)

    prev = SceneState(
        location="Solana Cove beach",
        attire="red bikini",
        pinned_fields=["attire"],
    )
    cfg = InferenceConfig(llm_provider="ollama", ollama_model="hermes3:8b", prompt_refiner_model="llama3.2:latest")
    updated = asyncio.run(
        update_scene_state(
            cfg,
            prev,
            user_text="Tell me a story about your last mission.",
            assistant_text="*She smiles warmly and sips her tropical drink.*",
        )
    )
    assert updated.attire == "red bikini"
    assert "attire" in updated.pinned_fields
    assert "(red bikini:1.2)" in format_scene_state_tags(updated)


def test_pinned_scene_state_overridden_on_explicit_change(monkeypatch) -> None:
    async def fake_ollama_chat(config, messages, purpose="chat", temperature_override=None, repeat_penalty=1.18, seed=None, model_override=None):
        return (
            '{"location": "resort restaurant", "time_and_lighting": "candlelit evening", '
            '"attire": "black cocktail dress", "hairstyle": "updo", '
            '"makeup": "evening makeup", "skin_and_condition": "dry", '
            '"pose_and_action": "walking into the restaurant"}'
        )

    monkeypatch.setattr("backend.inference.llm_engine._call_ollama_chat", fake_ollama_chat)

    prev = SceneState(
        location="Solana Cove beach",
        attire="red bikini",
        pinned_fields=["attire"],
    )
    cfg = InferenceConfig(llm_provider="ollama", ollama_model="hermes3:8b", prompt_refiner_model="llama3.2:latest")
    updated = asyncio.run(
        update_scene_state(
            cfg,
            prev,
            user_text="Let's get dressed for dinner, put on a black cocktail dress.",
            assistant_text="*She changes into a sleek black cocktail dress and heads to the restaurant.*",
        )
    )
    assert updated.attire == "black cocktail dress"
    # Option B: stays pinned to the new value for the current scenario
    assert "attire" in updated.pinned_fields


def test_scene_state_condenses_bloated_pose_and_action(monkeypatch) -> None:
    async def fake_ollama_chat(config, messages, purpose="chat", temperature_override=None, repeat_penalty=1.18, seed=None, model_override=None):
        return (
            '{"location": "lantern-lit boardwalk", "time_and_lighting": "golden hour", '
            '"weather": "clear breeze", "atmosphere": "playful", '
            '"attire": "red bikini", "hairstyle": "loose waves", "makeup": "natural", '
            '"skin_and_condition": "sun-kissed", '
            '"pose_and_action": "walking slowly along the boardwalk smiling back over her shoulder while contemplating the mysteries of life and the universe forever and ever..."}'
        )

    monkeypatch.setattr("backend.inference.llm_engine._call_ollama_chat", fake_ollama_chat)
    updated = asyncio.run(
        update_scene_state(
            InferenceConfig(llm_provider="ollama"),
            SceneState(),
            user_text="Walk ahead of me.",
            assistant_text="*She walks slowly along the boardwalk.*",
        )
    )
    assert len(updated.pose_and_action.split()) <= 8
    assert "..." not in updated.pose_and_action


def test_scene_state_injected_directly_into_scene_prompt(monkeypatch) -> None:
    # Even if the LLM harmonizer ignores scene_state, build_contextual_scene_prompt must inject it directly.
    async def fake_harmonize(**kwargs):
        return "cinematic lighting, soft painterly glow", "mock"

    monkeypatch.setattr("backend.inference.llm_engine.harmonize_sdxl_prompt", fake_harmonize)

    char = CharacterCard(name="Liamching", visual_prompt_tags="1girl, stunning asian woman")
    msg = ChatMessage(role="assistant", sender_name="Liamching", content="*She glances back.*")
    state = SceneState(
        location="lantern-lit boardwalk",
        weather="warm ocean breeze",
        attire="sleek black jumpsuit",
        pose_and_action="walking gracefully along boardwalk",
        pinned_fields=["attire"],
    )
    prompt = asyncio.run(
        build_contextual_scene_prompt(
            InferenceConfig(comfyui_checkpoint="CyberRealisticPony_V18.0_F16.safetensors"),
            char,
            [msg],
            msg,
            scene_state=state,
        )
    )
    assert "(sleek black jumpsuit:1.2)" in prompt
    assert "walking gracefully along boardwalk" in prompt
    assert "lantern-lit boardwalk" in prompt
    assert "warm ocean breeze" in prompt
    assert "solo" in prompt
    # Pinned attire must appear BEFORE the trailing style tags
    assert prompt.index("sleek black jumpsuit") < prompt.index("cinematic lighting")


def test_dynamic_action_scene_strips_portrait_bias(monkeypatch) -> None:
    async def fake_harmonize(**kwargs):
        return "mid-air vaulting over iron fence, night villa garden, dramatic lighting", "mock"

    monkeypatch.setattr("backend.inference.llm_engine.harmonize_sdxl_prompt", fake_harmonize)

    char = CharacterCard(
        name="Liamching",
        visual_prompt_tags="1girl, stunning asian woman, radiant warm smile, tousled dark chestnut hair",
    )
    msg = ChatMessage(
        role="assistant",
        sender_name="Liamching",
        content="*She sprints and vaults over the tall iron fence into the villa garden.*",
    )
    prompt = asyncio.run(
        build_contextual_scene_prompt(
            InferenceConfig(comfyui_checkpoint="CyberRealisticPony_V18.0_F16.safetensors"),
            char,
            [msg],
            msg,
        )
    )
    assert "dynamic action shot" in prompt
    assert "mid-motion" in prompt
    assert "radiant warm smile" not in prompt
    assert "stylized glamour digital art" not in prompt


def test_jumpsuit_does_not_trigger_action_or_rear_view() -> None:
    from backend.inference.llm_engine import (
        build_anatomical_and_clothing_overrides,
        is_dynamic_action_scene,
    )

    text = "Time to get undressed. What are you hiding underneath that sleek black jumpsuit? long wavy hair down back"
    assert not is_dynamic_action_scene(text)
    boosts, _, _ = build_anatomical_and_clothing_overrides(text)
    assert "from behind" not in boosts
    assert "rear view" not in boosts


def test_naked_kiss_strips_stale_jumpsuit_and_updates_scene_state(monkeypatch) -> None:
    from backend.inference.llm_engine import (
        build_contextual_scene_prompt,
        update_scene_state,
    )
    from backend.models import ChatMessage, CharacterCard, InferenceConfig, SceneState

    async def fake_harmonize(**kwargs):
        return "standing in front, ready to kiss, villa garden background, warm golden hour sunlight, sleek partially-unzipped jumpsuit", "mock"

    monkeypatch.setattr("backend.inference.llm_engine.harmonize_sdxl_prompt", fake_harmonize)

    prev_state = SceneState(
        location="Villa garden",
        time_and_lighting="warm golden hour",
        attire="sleek black jumpsuit tailored for infiltration partially unzipped",
        pose_and_action="*Liamching moved with grace of dancer diva stepping",
        pinned_fields=["pose_and_action", "location"],
    )
    # Even if LLM fails/offline, deterministic nudity override updates attire
    async def offline_ollama(*args, **kwargs):
        return None

    monkeypatch.setattr("backend.inference.llm_engine._call_ollama_chat", offline_ollama)
    updated_state = asyncio.run(
        update_scene_state(
            InferenceConfig(),
            prev_state,
            user_text="I want you to stand in front of me, naked, ready to kiss",
            assistant_text="*The last strands of suit fell away completely.*",
        )
    )
    assert updated_state.attire == "completely nude"
    assert not updated_state.pose_and_action.startswith("*")

    char = CharacterCard(name="Liamching", visual_prompt_tags="1girl, stunning asian woman")
    user_msg = ChatMessage(role="user", sender_name="Traveler", content="I want you to stand in front of me, naked, ready to kiss")
    asst_msg = ChatMessage(role="assistant", sender_name="Liamching", content="*Liamching stepped closer, completely naked, ready to kiss.*")
    prompt = asyncio.run(
        build_contextual_scene_prompt(
            InferenceConfig(comfyui_checkpoint="CyberRealisticPony_V18.0_F16.safetensors"),
            char,
            [user_msg, asst_msg],
            asst_msg,
            lore_visuals="tranquil beach resort backdrop, luxurious cabana setup, shimmering ocean waves, twinkling lantern lights",
            scene_state=prev_state,
        )
    )
    assert "completely nude" in prompt
    assert "jumpsuit" not in prompt.lower()
    assert "dynamic action shot" not in prompt
    assert "tranquil beach resort" not in prompt
    assert "lantern" not in prompt.lower()


def test_semantic_dedup_and_preamble_cleanup() -> None:
    from backend.inference.llm_engine import (
        _clean_llm_tag_output,
        dedupe_and_resolve_prompt_conflicts,
    )

    cleaned = _clean_llm_tag_output("Here are the outputted visual tags: villa garden background, warm golden hour sunlight, intimate kiss")
    assert cleaned is not None
    assert not any("here are" in t.lower() or "outputted" in t.lower() for t in cleaned)

    resolved = dedupe_and_resolve_prompt_conflicts(
        [
            "(Villa garden:1.2)",
            "warm golden hour",
            "villa garden background",
            "warm golden hour sunlight",
            "intimate kiss",
        ],
        scene_text="standing in villa garden",
    )
    joined = ", ".join(resolved)
    assert "Villa garden" in joined
    assert "villa garden background" not in joined
    assert "warm golden hour" in joined
    assert "warm golden hour sunlight" not in joined
    assert "intimate kiss" in joined


def test_illustrate_chat_message_syncs_scene_state(monkeypatch) -> None:
    from fastapi.testclient import TestClient
    from backend.main import app, storage
    from backend.models import ChatMessage, ChatSession, SceneState

    async def fake_generate_image_asset(**kwargs):
        return {
            "url": "/media/generated/test_sync.png",
            "provider": "mock_comfyui",
            "width": 512,
            "height": 768,
            "seed": 42,
            "duration_ms": 120.0,
        }

    async def fake_harmonize(**kwargs):
        return "standing in front, ready to kiss", "mock"

    async def offline_ollama(*args, **kwargs):
        return None

    monkeypatch.setattr("backend.main.generate_image_asset", fake_generate_image_asset)
    monkeypatch.setattr("backend.inference.llm_engine.harmonize_sdxl_prompt", fake_harmonize)
    monkeypatch.setattr("backend.inference.llm_engine._call_ollama_chat", offline_ollama)

    char_id = next(iter(storage.characters.keys()))
    sess = ChatSession(
        title="Sync Test",
        character_id=char_id,
        scene_state=SceneState(
            location="Villa garden",
            attire="sleek black jumpsuit",
            pose_and_action="*Liamching moved with grace",
            pinned_fields=["pose_and_action", "location"],
        ),
        messages=[
            ChatMessage(role="user", sender_name="Traveler", content="Stand in front of me, naked, ready to kiss"),
            ChatMessage(role="assistant", sender_name="Liamching", content="*The suit fell away completely.*"),
        ],
    )
    storage.chats[sess.id] = sess
    try:
        client = TestClient(app)
        resp = client.post(f"/api/chats/{sess.id}/messages/{sess.messages[-1].id}/illustrate")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session"]["scene_state"]["attire"] == "completely nude"
    finally:
        storage.chats.pop(sess.id, None)


def test_world_codex_map_generation_and_photo_pinning(monkeypatch) -> None:
    import backend.main as main_mod
    from backend.models import GalleryAsset, LoreEntry, Lorebook

    world = Lorebook(
        name="Test Realm",
        description="A misty archipelago of floating spires.",
        entries=[
            LoreEntry(
                id="loc-1",
                title="Sky Harbor",
                category="location",
                keywords=["harbor", "sky"],
                content="Airship docks suspended above the clouds.",
            ),
            LoreEntry(
                id="npc-1",
                title="Sky Guild",
                category="faction",
                keywords=["guild"],
                content="Airship smugglers guild.",
            ),
        ],
    )
    photo = GalleryAsset(
        id="asset-photo-1",
        filename="harbor_scene.png",
        url="/outputs/harbor_scene.png",
        prompt="airship docks",
        provider="comfyui",
        world_id=world.id,
    )
    created_asset_ids: list[str] = [photo.id]

    async def fake_generate_image_asset(**kwargs):
        map_asset = GalleryAsset(
            id="asset-map-1",
            filename="test_map.png",
            url="/outputs/test_map.png",
            prompt=kwargs.get("prompt", ""),
            provider="comfyui",
            world_id=kwargs.get("world_id"),
            width=kwargs.get("width", 1024),
            height=kwargs.get("height", 768),
        )
        created_asset_ids.append(map_asset.id)
        main_mod.storage.gallery.insert(0, map_asset)
        return map_asset.model_dump()

    monkeypatch.setattr(main_mod, "generate_image_asset", fake_generate_image_asset)
    main_mod.storage.worlds[world.id] = world
    main_mod.storage.gallery.insert(0, photo)

    try:
        client = TestClient(app)

        # 1. Generate world map and auto-place initial location entry
        resp = client.post(f"/api/worlds/{world.id}/generate-map")
        assert resp.status_code == 200
        data = resp.json()
        assert data["world"]["map_image_url"] == "/outputs/test_map.png"
        entries_by_id = {e["id"]: e for e in data["world"]["entries"]}
        assert entries_by_id["loc-1"]["map_x"] is not None
        assert entries_by_id["loc-1"]["map_y"] is not None
        assert entries_by_id["npc-1"]["map_x"] is None

        # 2. Add a subsequent location via PUT /api/worlds/{id} without overwriting base map
        updated_world = data["world"]
        updated_world["entries"].append(
            {
                "id": "loc-2",
                "title": "Sunken Archive",
                "category": "location",
                "keywords": ["archive"],
                "content": "Flooded library beneath the spire.",
            }
        )
        put_resp = client.put(f"/api/worlds/{world.id}", json=updated_world)
        assert put_resp.status_code == 200
        put_data = put_resp.json()
        assert put_data["map_image_url"] == "/outputs/test_map.png"
        put_entries = {e["id"]: e for e in put_data["entries"]}
        assert put_entries["loc-2"]["map_x"] is not None
        assert put_entries["loc-2"]["map_y"] is not None

        # 3. Pin and unpin a gallery photo to a location
        pin_resp = client.post(
            f"/api/gallery/{photo.id}/pin-location",
            json={"location_entry_id": "loc-2"},
        )
        assert pin_resp.status_code == 200
        assert pin_resp.json()["asset"]["location_entry_id"] == "loc-2"

        unpin_resp = client.post(
            f"/api/gallery/{photo.id}/pin-location",
            json={"location_entry_id": None},
        )
        assert unpin_resp.status_code == 200
        assert unpin_resp.json()["asset"]["location_entry_id"] is None

        # 4. Resort world map prompt uses 2D illustrated site plan, incorporates Codex & lore details, and strips photorealistic bias
        resort_world = Lorebook(
            name="Solana Cove: Sunlit Beach Resort",
            description="An intimate luxury beachside nudist resort tucked into a warm tropical cove with infinity pools.",
            aesthetic_style="warm golden hour beachside resort, cinematic photorealistic, 8k",
            entries=[
                LoreEntry(
                    id="res-1",
                    title="The Luxury Garden Villa",
                    category="location",
                    keywords=["villa"],
                    content="A private garden villa surrounded by a large hedge garden.",
                ),
                LoreEntry(
                    id="res-2",
                    title="The Sunset Cabana & Lagoon",
                    category="location",
                    keywords=["cabana", "lagoon"],
                    content="A private teakwood cabana overlooking the warm turquoise lagoon.",
                ),
            ],
        )
        resort_prompt = main_mod._build_world_map_prompt(resort_world)
        assert "top-down aerial resort map" in resort_prompt.lower()
        assert "realistic architectural masterplan site view" in resort_prompt.lower()
        assert "tropical cove" in resort_prompt.lower()
        assert "hedge garden" in resort_prompt.lower()
        assert "turquoise lagoon" in resort_prompt.lower()
        assert "photorealistic" not in resort_prompt.lower()
        assert "text labels" not in resort_prompt.lower()
    finally:
        main_mod.storage.worlds.pop(world.id, None)
        main_mod.storage.gallery = [
            a for a in main_mod.storage.gallery if a.id not in set(created_asset_ids)
        ]












