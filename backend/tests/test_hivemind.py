from __future__ import annotations

import asyncio
from pathlib import Path

from backend.inference.image_engine import _render_procedural_artwork, get_apple_silicon_telemetry
from backend.inference.llm_engine import (
    build_anatomical_and_clothing_overrides,
    build_contextual_scene_prompt,
    build_face_detailer_prompt,
    clean_character_visual_tags_for_scene,
    extract_action_and_scene_beats,
    fallback_extract_sdxl_keywords,
)
from backend.lore_engine import scan_lorebook
from backend.main import app
from backend.models import CharacterCard, ChatMessage, InferenceConfig
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




