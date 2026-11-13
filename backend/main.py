from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .inference.image_engine import (
    check_comfyui_status,
    generate_image_asset,
    get_apple_silicon_telemetry,
)
from .inference.llm_engine import (
    build_contextual_scene_prompt,
    check_ollama_status,
    check_openai_compat_status,
    clean_character_visual_tags_for_scene,
    distill_narrative_to_sdxl_keywords,
    fallback_extract_sdxl_keywords,
    generate_node_text,
    generate_roleplay_reply,
)
from .lore_engine import replace_tavern_macros, scan_lorebook
from .models import (
    CharacterCard,
    ChatMessage,
    ChatSession,
    GalleryAsset,
    InferenceConfig,
    Lorebook,
    WorkflowGraph,
    utc_now_iso,
)
from .storage import StudioStorage
from .tavern_card import (
    character_to_tavern_v2_dict,
    decode_tavern_png,
    encode_tavern_png,
    tavern_dict_to_character,
)
from .workflow_runner import execute_workflow_graph

app = FastAPI(
    title="Hivemind Studio API",
    description="Apple Silicon Character, World Lorebook & ComfyUI-Style Node Workflow Engine",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

storage = StudioStorage()

app.mount(
    "/media/generated",
    StaticFiles(directory=str(storage.generated_dir)),
    name="generated_media",
)


class SendMessageRequest(BaseModel):
    content: str
    illustrate_scene: bool = False


class SwipeMessageRequest(BaseModel):
    direction: str = "next"  # "next", "prev", or "regenerate"


class LoreScanRequest(BaseModel):
    text: str
    character_name: str = "Character"
    user_name: str = "Traveler"


class CreateChatRequest(BaseModel):
    character_id: str
    world_id: str | None = None
    title: str | None = None
    user_persona_name: str = "Traveler"
    user_persona_desc: str = "An observant wanderer exploring the realm."


class DirectImageRequest(BaseModel):
    prompt: str
    negative_prompt: str = "blurry, low quality, deformed, watermark"
    width: int = 512
    height: int = 512
    steps: int = 20
    cfg: float = 7.0
    seed: int | None = None
    character_id: str | None = None
    world_id: str | None = None


class BackstoryImageRequest(BaseModel):
    custom_prompt: str
    character_id: str | None = None
    world_id: str | None = None
    chat_id: str | None = None
    include_character_visuals: bool = True
    include_scenario_backstory: bool = True
    include_world_lore: bool = True
    use_llm_director: bool = True
    render_mode: str | None = None
    width: int = 512
    height: int = 512
    steps: int = 20
    cfg: float = 7.0
    seed: int | None = None


@app.get("/api/system/status")
async def get_system_status() -> dict[str, Any]:
    hw = get_apple_silicon_telemetry()
    ollama = await check_ollama_status(storage.config.ollama_base_url)
    openai_compat = await check_openai_compat_status(
        storage.config.openai_base_url, storage.config.openai_api_key
    )
    comfyui = await check_comfyui_status(storage.config.comfyui_base_url)

    return {
        "hardware": hw,
        "providers": {
            "ollama": ollama,
            "openai_compat": openai_compat,
            "comfyui": comfyui,
        },
        "config": storage.config.model_dump(),
        "counts": {
            "characters": len(storage.characters),
            "worlds": len(storage.worlds),
            "chats": len(storage.chats),
            "workflows": len(storage.workflows),
            "gallery": len(storage.gallery),
        },
    }


@app.put("/api/system/config")
async def update_system_config(new_config: InferenceConfig) -> dict[str, Any]:
    storage.config = new_config
    storage.save()
    return {"status": "ok", "config": storage.config.model_dump()}


# --- Character Forge Endpoints ---


@app.get("/api/characters")
async def list_characters() -> list[CharacterCard]:
    return list(storage.characters.values())


@app.post("/api/characters")
async def create_character(card: CharacterCard) -> CharacterCard:
    if not card.avatar_url:
        prompt = card.visual_prompt_tags or f"portrait of {card.name}, {card.title}, fantasy character concept art"
        img_meta = await generate_image_asset(
            config=storage.config,
            output_dir=storage.generated_dir,
            prompt=prompt,
            negative_prompt=card.negative_prompt_tags,
        )
        card.avatar_url = img_meta["url"]
    card.updated_at = utc_now_iso()
    storage.characters[card.id] = card
    storage.save()
    return card


@app.put("/api/characters/{char_id}")
async def update_character(char_id: str, card: CharacterCard) -> CharacterCard:
    card.id = char_id
    card.updated_at = utc_now_iso()
    storage.characters[char_id] = card
    storage.save()
    return card


@app.delete("/api/characters/{char_id}")
async def delete_character(char_id: str) -> dict[str, str]:
    if char_id not in storage.characters:
        raise HTTPException(status_code=404, detail="Character not found")
    del storage.characters[char_id]
    storage.save()
    return {"status": "deleted"}


@app.post("/api/characters/{char_id}/generate-avatar")
async def generate_character_avatar(char_id: str, seed: int | None = None) -> dict[str, Any]:
    card = storage.characters.get(char_id)
    if not card:
        raise HTTPException(status_code=404, detail="Character not found")

    world_style = ""
    if card.world_id and card.world_id in storage.worlds:
        world_style = storage.worlds[card.world_id].aesthetic_style

    base_tags = card.visual_prompt_tags or f"portrait of {card.name}, {card.title}, {card.personality}"
    full_prompt = ", ".join(p for p in [base_tags, world_style, "masterpiece character portrait, 8k"] if p)

    img_meta = await generate_image_asset(
        config=storage.config,
        output_dir=storage.generated_dir,
        prompt=full_prompt,
        negative_prompt=card.negative_prompt_tags,
        seed=seed,
    )
    card.avatar_url = img_meta["url"]
    card.updated_at = utc_now_iso()

    asset = GalleryAsset(
        url=img_meta["url"],
        prompt=full_prompt,
        negative_prompt=card.negative_prompt_tags,
        provider=img_meta["provider"],
        width=img_meta["width"],
        height=img_meta["height"],
        seed=img_meta["seed"],
        character_id=card.id,
        world_id=card.world_id,
    )
    storage.gallery.insert(0, asset)
    storage.save()
    return {"character": card.model_dump(), "asset": asset.model_dump()}


@app.get("/api/characters/{char_id}/export-png")
async def export_character_tavern_png(char_id: str) -> Response:
    card = storage.characters.get(char_id)
    if not card:
        raise HTTPException(status_code=404, detail="Character not found")

    base_bytes: bytes | None = None
    if card.avatar_url and card.avatar_url.startswith("/media/generated/"):
        fname = card.avatar_url.replace("/media/generated/", "")
        fpath = storage.generated_dir / fname
        if fpath.exists():
            base_bytes = fpath.read_bytes()

    png_bytes = encode_tavern_png(card, base_image_bytes=base_bytes)
    safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in card.name.lower())
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}_tavern_v2.png"'},
    )


@app.get("/api/characters/{char_id}/export-json")
async def export_character_tavern_json(char_id: str) -> dict[str, Any]:
    card = storage.characters.get(char_id)
    if not card:
        raise HTTPException(status_code=404, detail="Character not found")
    return character_to_tavern_v2_dict(card)


@app.post("/api/characters/import")
async def import_character_card(file: UploadFile = File(...)) -> CharacterCard:
    raw_bytes = await file.read()
    filename = (file.filename or "card.json").lower()

    if filename.endswith(".png"):
        saved_name = f"imported_{uuid.uuid4().hex[:10]}.png"
        saved_path = storage.generated_dir / saved_name
        saved_path.write_bytes(raw_bytes)
        avatar_url = f"/media/generated/{saved_name}"
        try:
            card = decode_tavern_png(raw_bytes, avatar_url=avatar_url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        try:
            payload = json.loads(raw_bytes.decode("utf-8"))
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid JSON card: {exc}") from exc
        card = tavern_dict_to_character(payload)
        img_meta = await generate_image_asset(
            config=storage.config,
            output_dir=storage.generated_dir,
            prompt=card.visual_prompt_tags or f"portrait of {card.name}, {card.title}",
        )
        card.avatar_url = img_meta["url"]

    storage.characters[card.id] = card
    storage.save()
    return card


# --- World Codex / Lorebook Endpoints ---


@app.get("/api/worlds")
async def list_worlds() -> list[Lorebook]:
    return list(storage.worlds.values())


@app.post("/api/worlds")
async def create_world(world: Lorebook) -> Lorebook:
    world.updated_at = utc_now_iso()
    storage.worlds[world.id] = world
    storage.save()
    return world


@app.put("/api/worlds/{world_id}")
async def update_world(world_id: str, world: Lorebook) -> Lorebook:
    world.id = world_id
    world.updated_at = utc_now_iso()
    storage.worlds[world_id] = world
    storage.save()
    return world


@app.delete("/api/worlds/{world_id}")
async def delete_world(world_id: str) -> dict[str, str]:
    if world_id not in storage.worlds:
        raise HTTPException(status_code=404, detail="World not found")
    del storage.worlds[world_id]
    storage.save()
    return {"status": "deleted"}


@app.post("/api/worlds/{world_id}/scan")
async def test_lorebook_scanner(world_id: str, req: LoreScanRequest) -> dict[str, Any]:
    world = storage.worlds.get(world_id)
    if not world:
        raise HTTPException(status_code=404, detail="World not found")
    res = scan_lorebook(
        lorebook=world,
        text_to_scan=req.text,
        char_name=req.character_name,
        user_name=req.user_name,
    )
    return {
        "triggered": [t.model_dump() for t in res.triggered],
        "context_block": res.context_block,
        "visual_tags_block": res.visual_tags_block,
    }


@app.post("/api/worlds/{world_id}/entries/{entry_id}/generate-image")
async def generate_lore_entry_artwork(world_id: str, entry_id: str) -> dict[str, Any]:
    world = storage.worlds.get(world_id)
    if not world:
        raise HTTPException(status_code=404, detail="World not found")

    target_entry = next((e for e in world.entries if e.id == entry_id), None)
    if not target_entry:
        raise HTTPException(status_code=404, detail="Lore entry not found")

    prompt_parts = [
        target_entry.visual_description or f"{target_entry.title}, {target_entry.content[:120]}",
        world.aesthetic_style,
        f"{target_entry.category} concept art, masterpiece, 8k",
    ]
    full_prompt = ", ".join(p for p in prompt_parts if p)

    img_meta = await generate_image_asset(
        config=storage.config,
        output_dir=storage.generated_dir,
        prompt=full_prompt,
    )
    target_entry.image_url = img_meta["url"]
    world.updated_at = utc_now_iso()

    asset = GalleryAsset(
        url=img_meta["url"],
        prompt=full_prompt,
        provider=img_meta["provider"],
        width=img_meta["width"],
        height=img_meta["height"],
        seed=img_meta["seed"],
        world_id=world.id,
    )
    storage.gallery.insert(0, asset)
    storage.save()
    return {"world": world.model_dump(), "entry": target_entry.model_dump(), "asset": asset.model_dump()}


# --- Roleplay Chat Endpoints ---


@app.get("/api/chats")
async def list_chats() -> list[ChatSession]:
    return list(storage.chats.values())


@app.post("/api/chats")
async def create_chat_session(req: CreateChatRequest) -> ChatSession:
    card = storage.characters.get(req.character_id)
    if not card:
        raise HTTPException(status_code=404, detail="Character not found")

    world_id = req.world_id or card.world_id
    world = storage.worlds.get(world_id) if world_id else None

    greeting = replace_tavern_macros(
        card.first_mes or f"*{card.name} regards you with quiet curiosity.* \"Greetings, {req.user_persona_name}.\"",
        char_name=card.name,
        user_name=req.user_persona_name,
    )
    scan_res = scan_lorebook(world, greeting, char_name=card.name, user_name=req.user_persona_name)

    first_msg = ChatMessage(
        role="assistant",
        sender_name=card.name,
        content=greeting,
        swipes=[greeting],
        active_swipe=0,
        triggered_lore=scan_res.triggered,
    )
    session = ChatSession(
        title=req.title or f"Chronicle with {card.name}",
        character_id=card.id,
        world_id=world_id,
        user_persona_name=req.user_persona_name,
        user_persona_desc=req.user_persona_desc,
        messages=[first_msg],
    )
    storage.chats[session.id] = session
    storage.save()
    return session


@app.delete("/api/chats/{chat_id}")
async def delete_chat_session(chat_id: str) -> dict[str, str]:
    if chat_id not in storage.chats:
        raise HTTPException(status_code=404, detail="Chat session not found")
    del storage.chats[chat_id]
    storage.save()
    return {"status": "deleted"}


@app.post("/api/chats/{chat_id}/messages")
async def send_chat_message(chat_id: str, req: SendMessageRequest) -> dict[str, Any]:
    session = storage.chats.get(chat_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")

    card = storage.characters.get(session.character_id)
    if not card:
        raise HTTPException(status_code=404, detail="Character not found")

    world = storage.worlds.get(session.world_id) if session.world_id else None

    user_msg = ChatMessage(
        role="user",
        sender_name=session.user_persona_name,
        content=req.content,
        swipes=[req.content],
    )
    session.messages.append(user_msg)

    # Scan recent context against Lorebook
    combined_scan_text = " ".join(m.content for m in session.messages[-3:])
    lore_res = scan_lorebook(
        lorebook=world,
        text_to_scan=combined_scan_text,
        char_name=card.name,
        user_name=session.user_persona_name,
    )

    reply_text, provider_used = await generate_roleplay_reply(
        config=storage.config,
        character=card,
        history=session.messages,
        lore_context=lore_res.context_block,
        triggered_lore=lore_res.triggered,
        user_name=session.user_persona_name,
        user_desc=session.user_persona_desc,
    )

    assistant_msg = ChatMessage(
        role="assistant",
        sender_name=card.name,
        content=reply_text,
        swipes=[reply_text],
        active_swipe=0,
        triggered_lore=lore_res.triggered,
    )
    session.messages.append(assistant_msg)

    if req.illustrate_scene:
        image_prompt = await build_contextual_scene_prompt(
            config=storage.config,
            character=card,
            messages=session.messages,
            target_msg=assistant_msg,
            lore_visuals=lore_res.visual_tags_block,
            user_name=session.user_persona_name,
            user_desc=session.user_persona_desc,
        )
        img_meta = await generate_image_asset(
            config=storage.config,
            output_dir=storage.generated_dir,
            prompt=image_prompt,
            negative_prompt=card.negative_prompt_tags,
        )
        assistant_msg.image_url = img_meta["url"]
        assistant_msg.image_prompt = image_prompt
        storage.gallery.insert(
            0,
            GalleryAsset(
                url=img_meta["url"],
                prompt=image_prompt,
                negative_prompt=card.negative_prompt_tags,
                provider=img_meta["provider"],
                width=img_meta["width"],
                height=img_meta["height"],
                seed=img_meta["seed"],
                character_id=card.id,
                world_id=session.world_id,
            ),
        )

    session.updated_at = utc_now_iso()
    storage.save()

    return {
        "session": session.model_dump(),
        "provider": provider_used,
        "triggered_lore": [t.model_dump() for t in lore_res.triggered],
    }


@app.post("/api/chats/{chat_id}/messages/{msg_id}/swipe")
async def swipe_chat_message(chat_id: str, msg_id: str, req: SwipeMessageRequest) -> dict[str, Any]:
    session = storage.chats.get(chat_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")

    target_msg = next((m for m in session.messages if m.id == msg_id), None)
    if not target_msg:
        raise HTTPException(status_code=404, detail="Message not found")

    card = storage.characters.get(session.character_id)
    if not card:
        raise HTTPException(status_code=404, detail="Character not found")

    world = storage.worlds.get(session.world_id) if session.world_id else None

    if not target_msg.swipes:
        target_msg.swipes = [target_msg.content]

    if req.direction == "prev" and target_msg.active_swipe > 0:
        target_msg.active_swipe -= 1
        target_msg.content = target_msg.swipes[target_msg.active_swipe]
        storage.save()
        return {"session": session.model_dump()}

    if req.direction == "next" and target_msg.active_swipe < len(target_msg.swipes) - 1:
        target_msg.active_swipe += 1
        target_msg.content = target_msg.swipes[target_msg.active_swipe]
        storage.save()
        return {"session": session.model_dump()}

    # Generate a new swipe variation
    msg_idx = session.messages.index(target_msg)
    history_slice = session.messages[:msg_idx]
    scan_text = " ".join(m.content for m in history_slice[-3:]) if history_slice else target_msg.content
    lore_res = scan_lorebook(world, scan_text, char_name=card.name, user_name=session.user_persona_name)

    variation_idx = len(target_msg.swipes)
    new_reply, provider_used = await generate_roleplay_reply(
        config=storage.config,
        character=card,
        history=history_slice,
        lore_context=lore_res.context_block,
        triggered_lore=lore_res.triggered,
        user_name=session.user_persona_name,
        user_desc=session.user_persona_desc,
        variation_index=variation_idx,
    )
    target_msg.swipes.append(new_reply)
    target_msg.active_swipe = len(target_msg.swipes) - 1
    target_msg.content = new_reply
    session.updated_at = utc_now_iso()
    storage.save()
    return {"session": session.model_dump(), "provider": provider_used}


@app.post("/api/chats/{chat_id}/messages/{msg_id}/illustrate")
async def illustrate_chat_message(chat_id: str, msg_id: str) -> dict[str, Any]:
    session = storage.chats.get(chat_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")

    target_msg = next((m for m in session.messages if m.id == msg_id), None)
    if not target_msg:
        raise HTTPException(status_code=404, detail="Message not found")

    card = storage.characters.get(session.character_id)
    world = storage.worlds.get(session.world_id) if session.world_id else None

    # Scan surrounding chat turns + character scenario against Lorebook
    msg_idx = session.messages.index(target_msg)
    window_msgs = session.messages[max(0, msg_idx - 1) : min(len(session.messages), msg_idx + 2)]
    scan_text = " ".join(m.content for m in window_msgs) + " " + (card.scenario if card else "")
    lore_res = scan_lorebook(
        lorebook=world,
        text_to_scan=scan_text,
        char_name=card.name if card else "Character",
        user_name=session.user_persona_name,
    )
    lore_visuals = lore_res.visual_tags_block or (world.aesthetic_style if world else "")

    full_prompt = await build_contextual_scene_prompt(
        config=storage.config,
        character=card,
        messages=session.messages,
        target_msg=target_msg,
        lore_visuals=lore_visuals,
        user_name=session.user_persona_name,
        user_desc=session.user_persona_desc,
    )

    img_meta = await generate_image_asset(
        config=storage.config,
        output_dir=storage.generated_dir,
        prompt=full_prompt,
        negative_prompt=card.negative_prompt_tags if card else "blurry, low quality",
    )
    target_msg.image_url = img_meta["url"]
    target_msg.image_prompt = full_prompt
    if not target_msg.triggered_lore and lore_res.triggered:
        target_msg.triggered_lore = lore_res.triggered
    session.updated_at = utc_now_iso()

    asset = GalleryAsset(
        url=img_meta["url"],
        prompt=full_prompt,
        provider=img_meta["provider"],
        width=img_meta["width"],
        height=img_meta["height"],
        seed=img_meta["seed"],
        character_id=card.id if card else None,
        world_id=session.world_id,
    )
    storage.gallery.insert(0, asset)
    storage.save()
    return {"session": session.model_dump(), "asset": asset.model_dump()}


# --- ComfyUI-Style Visual Node Workflows Endpoints ---


@app.get("/api/workflows")
async def list_workflows() -> list[WorkflowGraph]:
    return list(storage.workflows.values())


@app.post("/api/workflows")
async def create_workflow(wf: WorkflowGraph) -> WorkflowGraph:
    wf.updated_at = utc_now_iso()
    storage.workflows[wf.id] = wf
    storage.save()
    return wf


@app.put("/api/workflows/{wf_id}")
async def update_workflow(wf_id: str, wf: WorkflowGraph) -> WorkflowGraph:
    wf.id = wf_id
    wf.updated_at = utc_now_iso()
    storage.workflows[wf_id] = wf
    storage.save()
    return wf


@app.delete("/api/workflows/{wf_id}")
async def delete_workflow(wf_id: str) -> dict[str, str]:
    if wf_id not in storage.workflows:
        raise HTTPException(status_code=404, detail="Workflow not found")
    del storage.workflows[wf_id]
    storage.save()
    return {"status": "deleted"}


@app.post("/api/workflows/execute")
async def execute_workflow(wf: WorkflowGraph) -> dict[str, Any]:
    # Persist updated graph if it exists
    wf.updated_at = utc_now_iso()
    storage.workflows[wf.id] = wf

    exec_result, new_assets = await execute_workflow_graph(
        workflow=wf,
        config=storage.config,
        characters=storage.characters,
        worlds=storage.worlds,
        output_dir=storage.generated_dir,
    )

    # Update preview nodes in workflow state with latest generated image URLs
    for node in wf.nodes:
        trace = exec_result.node_traces.get(node.id)
        if trace and trace.outputs.get("image_url"):
            node.data["image_url"] = trace.outputs["image_url"]
            node.data["last_caption"] = trace.outputs.get("caption") or trace.outputs.get("prompt", "")
            apply_char_id = trace.outputs.get("apply_to_character_id")
            if apply_char_id and apply_char_id in storage.characters and node.data.get("auto_apply_avatar"):
                storage.characters[apply_char_id].avatar_url = trace.outputs["image_url"]

    for asset in reversed(new_assets):
        storage.gallery.insert(0, asset)

    storage.save()
    return {
        "execution": exec_result.model_dump(),
        "workflow": wf.model_dump(),
        "new_assets": [a.model_dump() for a in new_assets],
    }


# --- Gallery & Direct Image Synthesis ---


@app.get("/api/gallery")
async def list_gallery() -> list[GalleryAsset]:
    return storage.gallery


@app.post("/api/gallery/generate")
async def generate_direct_gallery_image(req: DirectImageRequest) -> GalleryAsset:
    img_meta = await generate_image_asset(
        config=storage.config,
        output_dir=storage.generated_dir,
        prompt=req.prompt,
        negative_prompt=req.negative_prompt,
        width=req.width,
        height=req.height,
        steps=req.steps,
        cfg=req.cfg,
        seed=req.seed,
    )
    asset = GalleryAsset(
        url=img_meta["url"],
        prompt=req.prompt,
        negative_prompt=req.negative_prompt,
        provider=img_meta["provider"],
        width=img_meta["width"],
        height=img_meta["height"],
        seed=img_meta["seed"],
        character_id=req.character_id,
        world_id=req.world_id,
    )
    storage.gallery.insert(0, asset)
    storage.save()
    return asset


@app.delete("/api/gallery/{asset_id}")
async def delete_gallery_asset(asset_id: str) -> dict[str, str]:
    target_idx = next((i for i, a in enumerate(storage.gallery) if a.id == asset_id), None)
    if target_idx is None:
        raise HTTPException(status_code=404, detail="Gallery asset not found")
    storage.gallery.pop(target_idx)
    storage.save()
    return {"status": "deleted", "id": asset_id}


@app.post("/api/backstory-image")
async def generate_backstory_grounded_image(req: BackstoryImageRequest) -> dict[str, Any]:
    """
    Generates a standalone image grounded in the roleplay's character persona,
    physical description, scenario backstory, and world lorebook without adding a chat turn.
    """
    session = storage.chats.get(req.chat_id) if req.chat_id else None
    char_id = req.character_id or (session.character_id if session else None)
    world_id = req.world_id or (session.world_id if session else None)

    card = storage.characters.get(char_id) if char_id else None
    if not world_id and card and card.world_id:
        world_id = card.world_id
    world = storage.worlds.get(world_id) if world_id else None

    is_pony = "pony" in (storage.config.comfyui_checkpoint or "").lower()
    active_mode = req.render_mode or getattr(storage.config, "comfyui_render_mode", "hybrid_refiner")
    if active_mode == "single_raw":
        quality_prefix = (
            "score_9, score_8_up, score_7_up, masterpiece, photorealistic, 8k, breathtakingly attractive"
            if is_pony
            else "masterpiece, photorealistic, 8k, breathtakingly attractive"
        )
        style_suffix = "cinematic golden hour lighting, shallow depth of field, intricate skin texture, raw photo"
    else:
        quality_prefix = (
            "score_9, score_8_up, score_7_up, masterpiece, stylized glamour digital art, painterly golden hour illustration, breathtakingly attractive"
            if is_pony
            else "masterpiece, stylized glamour digital art, painterly golden hour illustration, 8k, breathtakingly attractive"
        )
        style_suffix = (
            "dramatic warm sunset rim lighting, luminous bronze and amber color grading, "
            "soft painterly skin glow, romantic atmosphere, 8k"
        )
    prompt_segments: list[str] = [quality_prefix]
    triggered_lore_list = []

    # 1. User's specific scene / subject request first so it leads composition
    if req.custom_prompt.strip():
        prompt_segments.append(req.custom_prompt.strip())

    # 2. Gather Roleplay Scenario & World Codex Lore for LLM keyword distillation
    scenario_to_distill = ""
    if req.include_scenario_backstory and card and card.scenario:
        scenario_to_distill = replace_tavern_macros(card.scenario, char_name=card.name, user_name="Traveler")

    lore_visuals_to_distill = ""
    if req.include_world_lore and world:
        scan_haystack = " ".join(
            p for p in [req.custom_prompt, card.scenario if card else "", card.description if card else ""] if p
        )
        lore_res = scan_lorebook(
            lorebook=world,
            text_to_scan=scan_haystack,
            char_name=card.name if card else "Character",
            user_name=session.user_persona_name if session else "Traveler",
        )
        triggered_lore_list = [t.model_dump() for t in lore_res.triggered]
        lore_visuals_to_distill = lore_res.visual_tags_block or world.aesthetic_style or ""

    # 3. Distill Scenario & Lore into concise SDXL visual keywords and put BEFORE static character traits
    llm_provider_used = None
    if scenario_to_distill or lore_visuals_to_distill or req.use_llm_director:
        if req.use_llm_director or scenario_to_distill:
            distilled_kw, llm_provider_used = await distill_narrative_to_sdxl_keywords(
                config=storage.config,
                scenario_text=scenario_to_distill,
                action_or_scene_text=req.custom_prompt.strip(),
                user_intent_text=req.custom_prompt.strip(),
                lore_visuals=lore_visuals_to_distill,
            )
            if distilled_kw:
                prompt_segments.append(distilled_kw)
        elif lore_visuals_to_distill:
            prompt_segments.append(lore_visuals_to_distill)

    # 4. Character visual prompt tags & physical beauty traits (cleaned of conflicting static clothing / portrait crop)
    if req.include_character_visuals and card:
        if card.visual_prompt_tags:
            cleaned_tags = clean_character_visual_tags_for_scene(
                card.visual_prompt_tags,
                f"{req.custom_prompt} {card.scenario or ''}",
            )
            prompt_segments.append(cleaned_tags)
        elif card.description:
            clean_desc = replace_tavern_macros(card.description, char_name=card.name, user_name="Traveler")
            prompt_segments.append(fallback_extract_sdxl_keywords(clean_desc, max_keywords=8))

    prompt_segments.append(style_suffix)
    assembled_prompt = ", ".join(p.strip().rstrip(",") for p in prompt_segments if p and p.strip())

    neg_prompt = card.negative_prompt_tags if card else "blurry, low quality, deformed, watermark"

    img_meta = await generate_image_asset(
        config=storage.config,
        output_dir=storage.generated_dir,
        prompt=assembled_prompt,
        negative_prompt=neg_prompt,
        width=req.width,
        height=req.height,
        steps=req.steps,
        cfg=req.cfg,
        seed=req.seed,
        render_mode_override=active_mode,
    )

    asset = GalleryAsset(
        url=img_meta["url"],
        prompt=assembled_prompt,
        negative_prompt=neg_prompt,
        provider=img_meta["provider"],
        width=img_meta["width"],
        height=img_meta["height"],
        seed=img_meta["seed"],
        character_id=card.id if card else None,
        world_id=world.id if world else None,
    )
    storage.gallery.insert(0, asset)
    storage.save()

    return {
        "asset": asset.model_dump(),
        "assembled_prompt": assembled_prompt,
        "triggered_lore": triggered_lore_list,
        "image_provider": img_meta["provider"],
        "llm_provider": llm_provider_used,
    }
