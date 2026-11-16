from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .inference.image_engine import (
    check_comfyui_status,
    generate_image_asset,
    get_apple_silicon_telemetry,
)
from .inference.llm_engine import (
    build_anatomical_and_clothing_overrides,
    build_contextual_scene_prompt,
    check_ollama_status,
    check_openai_compat_status,
    clean_character_visual_tags_for_scene,
    dedupe_and_resolve_prompt_conflicts,
    distill_narrative_to_sdxl_keywords,
    distill_situation_checkpoint,
    fallback_extract_sdxl_keywords,
    format_scene_state_tags,
    generate_roleplay_reply,
    harmonize_sdxl_prompt,
    render_prompt_template,
    stream_roleplay_reply,
    update_scene_state,
)
from .logger import logger, set_hivemind_log_level
from .lore_engine import replace_tavern_macros, scan_lorebook
from .models import (
    CharacterCard,
    ChatMessage,
    ChatSession,
    GalleryAsset,
    InferenceConfig,
    Lorebook,
    SceneState,
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
set_hivemind_log_level(getattr(storage.config, "log_level", "INFO"))

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


class IllustrateMessageRequest(BaseModel):
    custom_prompt: str | None = None
    reuse_prompt: bool = False


class CheckpointRequest(BaseModel):
    refresh: bool = True
    custom_checkpoint: str | None = None


async def _maybe_update_chat_checkpoint(
    session: ChatSession,
    card: CharacterCard | None,
    force: bool = False,
) -> str:
    """Updates session.situation_checkpoint when >= 8 new messages accumulate since last checkpoint, or when forced."""
    total = len(session.messages)
    keep_recent = 6
    if not force:
        if total < 8 or (total - session.checkpoint_msg_count) < 8:
            return session.situation_checkpoint
        older_slice = session.messages[session.checkpoint_msg_count : max(0, total - keep_recent)]
        new_count = max(0, total - keep_recent)
    else:
        older_slice = session.messages
        new_count = total

    checkpoint_text, provider = await distill_situation_checkpoint(
        config=storage.config,
        character=card,
        older_messages=older_slice,
        previous_checkpoint=session.situation_checkpoint,
        user_name=session.user_persona_name,
    )
    if checkpoint_text:
        session.situation_checkpoint = checkpoint_text
        session.checkpoint_msg_count = new_count
        logger.info(
            "📌 CHECKPT  | chat=%r | folded=%d/%d msgs | provider=%s",
            session.title,
            new_count,
            total,
            provider,
        )
    return session.situation_checkpoint


_METRICS_PATH = Path(__file__).resolve().parent / "data" / "metrics.jsonl"


def _record_metric(kind: str, payload: dict[str, Any]) -> None:
    try:
        _METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {"ts": utc_now_iso(), "kind": kind, **payload}
        with _METRICS_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except Exception as exc:
        logger.debug("Metrics write skipped: %s", exc)


@app.get("/api/system/metrics")
async def get_system_metrics() -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    if _METRICS_PATH.exists():
        try:
            lines = _METRICS_PATH.read_text(encoding="utf-8").splitlines()[-200:]
            for line in lines:
                if line.strip():
                    records.append(json.loads(line))
        except Exception:
            records = []

    def _summarize(kind: str) -> dict[str, Any]:
        vals = sorted(float(r["total_ms"]) for r in records if r.get("kind") == kind and r.get("total_ms") is not None)
        if not vals:
            return {"count": 0, "avg_ms": None, "p50_ms": None, "p95_ms": None, "latest_ms": None}
        n = len(vals)
        latest = next((r.get("total_ms") for r in reversed(records) if r.get("kind") == kind), vals[-1])
        return {
            "count": n,
            "avg_ms": round(sum(vals) / n, 1),
            "p50_ms": round(vals[n // 2], 1),
            "p95_ms": round(vals[min(n - 1, int(n * 0.95))], 1),
            "latest_ms": latest,
        }

    return {
        "chat": _summarize("chat"),
        "scene": _summarize("scene"),
        "studio": _summarize("studio"),
        "recent": records[-15:][::-1],
    }


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
    face_detailer: bool | None = None
    width: int = 768
    height: int = 1024
    steps: int = 20
    cfg: float = 6.0
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
    set_hivemind_log_level(new_config.log_level)
    storage.save()
    logger.info(
        "▶ ACTION   | update_system_config | llm=%s (%s) | comfy_ckpt=%s | mode=%s | log_level=%s",
        new_config.llm_provider,
        new_config.ollama_model,
        new_config.comfyui_checkpoint,
        new_config.comfyui_render_mode,
        new_config.log_level,
    )
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

    logger.info("▶ ACTION   | generate_character_avatar(char=%r, id=%s)", card.name, char_id)

    world_style = ""
    if card.world_id and card.world_id in storage.worlds:
        world_style = storage.worlds[card.world_id].aesthetic_style

    base_tags = card.visual_prompt_tags or f"portrait of {card.name}, {card.title}, {card.personality}"
    portrait_parts = render_prompt_template(
        storage.config.portrait_prompt_template,
        {
            "character_traits": base_tags,
            "world_style": world_style,
            "portrait_style": "masterpiece character portrait, 8k",
        },
    )
    full_prompt = ", ".join(portrait_parts)

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


def _auto_place_map_locations(world: Lorebook) -> None:
    """Assigns spaced (map_x, map_y) percentage coordinates to location entries that lack them."""
    existing_coords = [
        (e.map_x, e.map_y)
        for e in world.entries
        if e.category == "location" and e.map_x is not None and e.map_y is not None
    ]
    # Candidate grid positions (percentage 0-100) avoiding map borders
    candidates = [
        (50.0, 48.0), (28.0, 34.0), (72.0, 34.0), (30.0, 68.0), (70.0, 68.0),
        (50.0, 24.0), (50.0, 76.0), (20.0, 50.0), (80.0, 50.0), (38.0, 48.0),
        (62.0, 48.0), (38.0, 26.0), (62.0, 26.0), (38.0, 74.0), (62.0, 74.0),
        (22.0, 22.0), (78.0, 22.0), (22.0, 78.0), (78.0, 78.0),
    ]
    for entry in world.entries:
        if entry.category != "location":
            continue
        if entry.map_x is not None and entry.map_y is not None:
            continue
        best = None
        best_dist = -1.0
        for cx, cy in candidates:
            if not existing_coords:
                best = (cx, cy)
                break
            min_d = min(((cx - ex) ** 2 + (cy - ey) ** 2) ** 0.5 for ex, ey in existing_coords)
            if min_d > best_dist:
                best_dist = min_d
                best = (cx, cy)
        px, py = best or (50.0, 50.0)
        entry.map_x = round(px, 1)
        entry.map_y = round(py, 1)
        existing_coords.append((entry.map_x, entry.map_y))


def _resolve_location_entry_id(
    world: Lorebook | None,
    triggered_lore: list[Any],
    scene_location: str = "",
) -> str | None:
    """Finds the best matching location LoreEntry id for auto-pinning a generated photo to the world map."""
    if not world:
        return None
    loc_entries = [e for e in world.entries if e.category == "location"]
    if not loc_entries:
        return None
    loc_by_id = {e.id: e for e in loc_entries}
    for t in triggered_lore or []:
        tid = getattr(t, "entry_id", None) or (t.get("entry_id") if isinstance(t, dict) else None)
        if tid and tid in loc_by_id:
            return tid
    loc_l = (scene_location or "").strip().lower()
    if loc_l:
        for e in loc_entries:
            title_l = e.title.lower()
            if title_l in loc_l or loc_l in title_l or any(k.lower() in loc_l for k in e.keys if len(k) >= 3):
                return e.id
    return None


@app.get("/api/worlds")
async def list_worlds() -> list[Lorebook]:
    return list(storage.worlds.values())


@app.post("/api/worlds")
async def create_world(world: Lorebook) -> Lorebook:
    world.updated_at = utc_now_iso()
    if world.map_image_url:
        _auto_place_map_locations(world)
    storage.worlds[world.id] = world
    storage.save()
    return world


@app.put("/api/worlds/{world_id}")
async def update_world(world_id: str, world: Lorebook) -> Lorebook:
    world.id = world_id
    if world.map_image_url:
        _auto_place_map_locations(world)
    world.updated_at = utc_now_iso()
    storage.worlds[world_id] = world
    storage.save()
    return world


class MapGenerateRequest(BaseModel):
    custom_prompt: str | None = None


_MAP_STRIP_PHRASES = (
    "cinematic photorealistic",
    "photorealistic",
    "dramatic concept art",
    "atmospheric lighting",
    "detailed architecture",
    "warm golden hour",
    "golden hour",
    "sunset rim lighting",
    "8k",
    "4k",
    "nudist",
    "naked",
    "intimate",
    "romantic",
    "luxury",
    "tucked into",
    "where silk curtains billow in the evening sea breeze and",
    "well maintained",
    "an ",
    "a ",
)


def _clean_map_text(text: str, max_words: int = 12) -> str:
    cleaned = f" {text.strip()} "
    for phrase in _MAP_STRIP_PHRASES:
        cleaned = re.sub(rf"(?<!\w){re.escape(phrase)}(?!\w)", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.;:-")
    words = cleaned.split()
    if len(words) > max_words:
        cleaned = " ".join(words[:max_words]).rstrip(" ,.;:-")
    return cleaned


def _build_world_map_prompt(world: Lorebook, custom_prompt: str | None = None) -> str:
    enabled_entries = [e for e in world.entries if getattr(e, "enabled", True)]
    location_entries = sorted(
        [e for e in enabled_entries if e.category == "location" and e.title.strip()],
        key=lambda e: getattr(e, "priority", 0),
        reverse=True,
    )

    # Put location descriptions FIRST (highest CLIP token weight)
    location_phrases: list[str] = []
    for entry in location_entries[:5]:
        title = entry.title.strip()
        detail_src = entry.content.strip() or getattr(entry, "visual_description", "").strip()
        detail = _clean_map_text(detail_src, max_words=12)
        if detail and detail.lower() not in title.lower():
            location_phrases.append(detail)
        else:
            location_phrases.append(title)

    # Include non-location enabled lore entries if fewer than 5 locations
    if len(location_phrases) < 5:
        other_entries = [e for e in enabled_entries if e.category != "location" and e.title.strip()]
        for entry in other_entries[: 5 - len(location_phrases)]:
            detail = _clean_map_text(entry.content.strip(), max_words=8)
            if detail:
                location_phrases.append(detail)

    landmarks = ", ".join(location_phrases)
    codex_geo = _clean_map_text(world.description, max_words=12) if world.description else ""

    if custom_prompt and custom_prompt.strip():
        custom = custom_prompt.strip()
        if any(k in custom.lower() for k in ("map", "plan", "cartography", "diagram", "blueprint")):
            return ", ".join(p for p in (custom, landmarks, codex_geo) if p)
        return ", ".join(
            p
            for p in (
                "top-down aerial map, realistic architectural site plan",
                custom,
                landmarks,
                codex_geo,
            )
            if p
        )

    combined = " ".join(
        [
            world.name,
            world.description,
            world.aesthetic_style,
            " ".join(e.title for e in enabled_entries),
            " ".join(e.content for e in enabled_entries[:6]),
        ]
    ).lower()

    if any(
        k in combined
        for k in (
            "resort",
            "cove",
            "beach",
            "cabana",
            "villa",
            "lagoon",
            "pool",
            "hotel",
            "spa",
            "boardwalk",
            "island",
            "coastal",
            "marina",
            "harbor",
        )
    ):
        base_style = "top-down aerial resort map, realistic architectural masterplan site view"
        closing = "clean pathways, palm trees, realistic lighting, compass rose"
    elif any(k in combined for k in ("cyber", "neon", "station", "orbital", "sci-fi", "sector", "space", "holo")):
        base_style = "top-down tactical sector map, realistic architectural overhead plan"
        closing = "transit lines, districts, compass rose"
    else:
        base_style = "top-down cartographic map, realistic terrain relief, overhead satellite view"
        closing = "roads, terrain, compass rose"

    map_parts = render_prompt_template(
        storage.config.world_map_prompt_template,
        {
            "map_style": base_style,
            "landmarks": landmarks,
            "world_geography": codex_geo,
            "map_closing": closing,
            "world_name": world.name,
        },
    )
    return ", ".join(map_parts)


@app.post("/api/worlds/{world_id}/generate-map")
async def generate_world_map(
    world_id: str,
    req: MapGenerateRequest | None = None,
) -> dict[str, Any]:
    world = storage.worlds.get(world_id)
    if not world:
        raise HTTPException(status_code=404, detail="World not found")

    map_prompt = _build_world_map_prompt(world, req.custom_prompt if req else None)
    img_meta = await generate_image_asset(
        config=storage.config,
        output_dir=storage.generated_dir,
        prompt=map_prompt,
        negative_prompt=(
            "horizon, sky, eye-level view, street level, ground level, person, woman, man, people, "
            "portrait, close-up face, text, letters, words, watermark, cartoon, anime, sketch, "
            "blurry, low quality, deformed"
        ),
        width=1024,
        height=768,
        steps=22,
        cfg=5.5,
        render_mode_override="single_stylized",
        face_detailer_override=False,
        landscape_mode=True,
    )
    world.map_image_url = img_meta["url"]
    world.map_prompt = map_prompt
    _auto_place_map_locations(world)
    world.updated_at = utc_now_iso()

    asset = GalleryAsset(
        url=img_meta["url"],
        prompt=map_prompt,
        provider=img_meta["provider"],
        width=img_meta["width"],
        height=img_meta["height"],
        seed=img_meta["seed"],
        world_id=world.id,
        duration_ms=img_meta.get("duration_ms"),
    )
    storage.gallery.insert(0, asset)
    storage.save()
    return {"world": world.model_dump(), "asset": asset.model_dump()}


class PinLocationRequest(BaseModel):
    location_entry_id: str | None = None


@app.post("/api/gallery/{asset_id}/pin-location")
async def pin_gallery_asset_to_location(asset_id: str, req: PinLocationRequest) -> dict[str, Any]:
    target = next((g for g in storage.gallery if g.id == asset_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Gallery asset not found")
    target.location_entry_id = req.location_entry_id
    storage.save()
    return {"asset": target.model_dump()}


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

    _DEFAULT_VISUAL_DESC = "dramatic concept art, atmospheric lighting, detailed architecture"
    custom_vis = (
        target_entry.visual_description.strip()
        if target_entry.visual_description
        and target_entry.visual_description.strip().lower() != _DEFAULT_VISUAL_DESC
        else ""
    )
    category_style = (
        "architectural environment scene, wide angle, high detail"
        if target_entry.category == "location"
        else f"{target_entry.category} concept art, high detail"
    )
    prompt_parts = render_prompt_template(
        storage.config.location_prompt_template,
        {
            "title": target_entry.title.strip(),
            "lore_content": target_entry.content.strip()[:220] if target_entry.content else "",
            "custom_visuals": custom_vis,
            "world_style": world.aesthetic_style,
            "category_style": category_style,
        },
    )
    full_prompt = ", ".join(prompt_parts)

    is_location = target_entry.category == "location"
    img_meta = await generate_image_asset(
        config=storage.config,
        output_dir=storage.generated_dir,
        prompt=full_prompt,
        negative_prompt=(
            "person, woman, man, people, portrait, close-up face, crowd, text, watermark, blurry, low quality, deformed"
            if is_location
            else "text, watermark, blurry, low quality, deformed"
        ),
        width=1024 if is_location else None,
        height=768 if is_location else None,
        steps=22 if is_location else None,
        cfg=5.5 if is_location else None,
        render_mode_override="single_stylized",
        face_detailer_override=False if is_location else None,
        landscape_mode=is_location,
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
        location_entry_id=target_entry.id if target_entry.category == "location" else None,
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


@app.delete("/api/chats/{chat_id}/messages/{msg_id}")
async def delete_chat_message(chat_id: str, msg_id: str) -> dict[str, Any]:
    session = storage.chats.get(chat_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    before = len(session.messages)
    session.messages = [m for m in session.messages if m.id != msg_id]
    if len(session.messages) == before:
        raise HTTPException(status_code=404, detail="Message not found")
    session.updated_at = utc_now_iso()
    storage.save()
    return {"session": session.model_dump()}


@app.post("/api/chats/{chat_id}/messages")
async def send_chat_message(chat_id: str, req: SendMessageRequest) -> dict[str, Any]:
    session = storage.chats.get(chat_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")

    card = storage.characters.get(session.character_id)
    if not card:
        raise HTTPException(status_code=404, detail="Character not found")

    logger.info(
        "▶ ACTION   | send_chat_message(chat=%r, char=%r, illustrate=%s, text=%r)",
        session.title,
        card.name,
        req.illustrate_scene,
        req.content[:90],
    )

    world = storage.worlds.get(session.world_id) if session.world_id else None

    user_msg = ChatMessage(
        role="user",
        sender_name=session.user_persona_name,
        content=req.content,
        swipes=[req.content],
    )
    session.messages.append(user_msg)

    # Scan recent context against Lorebook
    t_total0 = time.perf_counter()
    t0 = time.perf_counter()
    combined_scan_text = " ".join(m.content for m in session.messages[-3:])
    lore_res = scan_lorebook(
        lorebook=world,
        text_to_scan=combined_scan_text,
        char_name=card.name,
        user_name=session.user_persona_name,
    )
    lore_ms = (time.perf_counter() - t0) * 1000

    ckpt_ms = 0.0
    if len(session.messages) >= 8 and (len(session.messages) - session.checkpoint_msg_count) >= 8:
        async def _bg_checkpoint() -> None:
            await _maybe_update_chat_checkpoint(session, card)
            storage.save()

        asyncio.create_task(_bg_checkpoint())

    t0 = time.perf_counter()
    reply_text, provider_used = await generate_roleplay_reply(
        config=storage.config,
        character=card,
        history=session.messages,
        lore_context=lore_res.context_block,
        triggered_lore=lore_res.triggered,
        user_name=session.user_persona_name,
        user_desc=session.user_persona_desc,
        situation_checkpoint=session.situation_checkpoint,
        scene_state=session.scene_state,
    )
    reply_ms = (time.perf_counter() - t0) * 1000

    assistant_msg = ChatMessage(
        role="assistant",
        sender_name=card.name,
        content=reply_text,
        swipes=[reply_text],
        active_swipe=0,
        triggered_lore=lore_res.triggered,
    )
    session.messages.append(assistant_msg)

    t0 = time.perf_counter()
    session.scene_state = await update_scene_state(
        config=storage.config,
        previous_state=session.scene_state,
        user_text=req.content,
        assistant_text=reply_text,
        world_aesthetic=world.aesthetic_style if world else "",
    )
    scene_state_ms = (time.perf_counter() - t0) * 1000
    total_ms = (time.perf_counter() - t_total0) * 1000
    logger.info(
        "⏱️ CHAT     | total=%.2fs (lore=%.0fms, ckpt=%.0fms, reply=%.2fs, scene_state=%.2fs)",
        total_ms / 1000,
        lore_ms,
        ckpt_ms,
        reply_ms / 1000,
        scene_state_ms / 1000,
    )

    illustrate_timings: dict[str, float] | None = None
    if req.illustrate_scene:
        t_ill_prompt = time.perf_counter()
        image_prompt = await build_contextual_scene_prompt(
            config=storage.config,
            character=card,
            messages=session.messages,
            target_msg=assistant_msg,
            lore_visuals=lore_res.visual_tags_block,
            user_name=session.user_persona_name,
            user_desc=session.user_persona_desc,
            situation_checkpoint=session.situation_checkpoint,
            scene_state=session.scene_state,
        )
        ill_prompt_ms = (time.perf_counter() - t_ill_prompt) * 1000
        t_ill_render = time.perf_counter()
        img_meta = await generate_image_asset(
            config=storage.config,
            output_dir=storage.generated_dir,
            prompt=image_prompt,
            negative_prompt=card.negative_prompt_tags,
        )
        ill_render_ms = (time.perf_counter() - t_ill_render) * 1000
        illustrate_timings = {
            "prompt_ms": round(ill_prompt_ms, 1),
            "render_ms": round(ill_render_ms, 1),
        }
        assistant_msg.image_url = img_meta["url"]
        assistant_msg.image_prompt = image_prompt
        assistant_msg.image_seed = img_meta["seed"]
        assistant_msg.image_metadata_url = img_meta.get("metadata_url")
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
                metadata_url=img_meta.get("metadata_url"),
                character_id=card.id,
                world_id=session.world_id,
            ),
        )

    session.updated_at = utc_now_iso()
    storage.save()

    timings: dict[str, Any] = {
        "lore_ms": round(lore_ms, 1),
        "ckpt_ms": round(ckpt_ms, 1),
        "reply_ms": round(reply_ms, 1),
        "scene_state_ms": round(scene_state_ms, 1),
        "total_ms": round(total_ms, 1),
    }
    if illustrate_timings:
        timings["illustrate"] = illustrate_timings
    assistant_msg.timings = timings
    _record_metric("chat", {"provider": provider_used, **timings})

    session.updated_at = utc_now_iso()
    storage.save()

    return {
        "session": session.model_dump(),
        "provider": provider_used,
        "triggered_lore": [t.model_dump() for t in lore_res.triggered],
        "timings": timings,
    }


@app.post("/api/chats/{chat_id}/messages/stream")
async def stream_chat_message(chat_id: str, req: SendMessageRequest):
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

    t_total0 = time.perf_counter()
    t0 = time.perf_counter()
    combined_scan_text = " ".join(m.content for m in session.messages[-3:])
    lore_res = scan_lorebook(
        lorebook=world,
        text_to_scan=combined_scan_text,
        char_name=card.name,
        user_name=session.user_persona_name,
    )
    lore_ms = (time.perf_counter() - t0) * 1000

    if len(session.messages) >= 8 and (len(session.messages) - session.checkpoint_msg_count) >= 8:
        async def _bg_checkpoint() -> None:
            await _maybe_update_chat_checkpoint(session, card)
            storage.save()

        asyncio.create_task(_bg_checkpoint())

    async def _event_stream():
        t_reply0 = time.perf_counter()
        chunks: list[str] = []
        provider_used = f"ollama ({storage.config.ollama_model})"
        async for delta, prov in stream_roleplay_reply(
            config=storage.config,
            character=card,
            history=session.messages,
            lore_context=lore_res.context_block,
            triggered_lore=lore_res.triggered,
            user_name=session.user_persona_name,
            user_desc=session.user_persona_desc,
            situation_checkpoint=session.situation_checkpoint,
            scene_state=session.scene_state,
        ):
            provider_used = prov
            if delta:
                chunks.append(delta)
                yield f"data: {json.dumps({'type': 'delta', 'delta': delta})}\n\n"

        reply_text = "".join(chunks).strip() or "..."
        reply_ms = (time.perf_counter() - t_reply0) * 1000
        assistant_msg = ChatMessage(
            role="assistant",
            sender_name=card.name,
            content=reply_text,
            swipes=[reply_text],
            active_swipe=0,
            triggered_lore=lore_res.triggered,
        )
        session.messages.append(assistant_msg)

        t_state0 = time.perf_counter()
        session.scene_state = await update_scene_state(
            config=storage.config,
            previous_state=session.scene_state,
            user_text=req.content,
            assistant_text=reply_text,
            world_aesthetic=world.aesthetic_style if world else "",
        )
        scene_state_ms = (time.perf_counter() - t_state0) * 1000
        total_ms = (time.perf_counter() - t_total0) * 1000
        timings = {
            "lore_ms": round(lore_ms, 1),
            "ckpt_ms": 0.0,
            "reply_ms": round(reply_ms, 1),
            "scene_state_ms": round(scene_state_ms, 1),
            "total_ms": round(total_ms, 1),
        }
        assistant_msg.timings = timings
        _record_metric("chat", {"provider": provider_used, **timings})
        session.updated_at = utc_now_iso()
        storage.save()
        logger.info(
            "⏱️ CHAT(SSE) | total=%.2fs (lore=%.0fms, reply=%.2fs, scene_state=%.2fs)",
            total_ms / 1000,
            lore_ms,
            reply_ms / 1000,
            scene_state_ms / 1000,
        )
        yield f"data: {json.dumps({'type': 'done', 'session': session.model_dump(), 'provider': provider_used, 'timings': timings})}\n\n"

    return StreamingResponse(_event_stream(), media_type="text/event-stream")


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

    logger.info(
        "▶ ACTION   | swipe_chat_message(chat=%r, char=%r, msg_id=%s, direction=%s)",
        session.title,
        card.name,
        msg_id,
        req.direction,
    )

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
        situation_checkpoint=session.situation_checkpoint,
        scene_state=session.scene_state,
    )
    target_msg.swipes.append(new_reply)
    target_msg.active_swipe = len(target_msg.swipes) - 1
    target_msg.content = new_reply

    prev_user_text = next(
        (m.content for m in reversed(history_slice) if m.role == "user" and m.content.strip()),
        "",
    )
    session.scene_state = await update_scene_state(
        config=storage.config,
        previous_state=session.scene_state,
        user_text=prev_user_text,
        assistant_text=new_reply,
        world_aesthetic=world.aesthetic_style if world else "",
    )

    session.updated_at = utc_now_iso()
    storage.save()
    return {"session": session.model_dump(), "provider": provider_used}


@app.post("/api/chats/{chat_id}/messages/{msg_id}/illustrate")
async def illustrate_chat_message(
    chat_id: str,
    msg_id: str,
    req: IllustrateMessageRequest | None = None,
) -> dict[str, Any]:
    session = storage.chats.get(chat_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")

    target_msg = next((m for m in session.messages if m.id == msg_id), None)
    if not target_msg:
        raise HTTPException(status_code=404, detail="Message not found")

    card = storage.characters.get(session.character_id)
    world = storage.worlds.get(session.world_id) if session.world_id else None

    custom_prompt = req.custom_prompt.strip() if (req and req.custom_prompt and req.custom_prompt.strip()) else None
    reuse_prompt = bool(req and req.reuse_prompt and target_msg.image_prompt and target_msg.image_prompt.strip())
    locked_prompt = custom_prompt or (target_msg.image_prompt.strip() if reuse_prompt and target_msg.image_prompt else None)
    logger.info(
        "▶ ACTION   | illustrate_chat_message(chat=%r, char=%r, msg_id=%s, custom_prompt=%s, reuse_prompt=%s)",
        session.title,
        card.name if card else "None",
        msg_id,
        "YES" if custom_prompt else "NO",
        "YES" if reuse_prompt else "NO",
    )

    # Scan surrounding chat turns + character scenario against Lorebook
    t_total0 = time.perf_counter()
    t0 = time.perf_counter()
    msg_idx = session.messages.index(target_msg)
    window_msgs = session.messages[max(0, msg_idx - 1) : min(len(session.messages), msg_idx + 2)]
    scan_text = " ".join(m.content for m in window_msgs) + " " + (card.scenario if card else "")
    lore_res = scan_lorebook(
        lorebook=world,
        text_to_scan=scan_text,
        char_name=card.name if card else "Character",
        user_name=session.user_persona_name,
    )
    lore_ms = (time.perf_counter() - t0) * 1000
    has_tracked_setting = bool(
        (session.scene_state.location or "").strip()
        or (session.scene_state.time_and_lighting or "").strip()
    )
    lore_visuals = lore_res.visual_tags_block or (
        "" if has_tracked_setting else (world.aesthetic_style if world else "")
    )

    t0 = time.perf_counter()
    if locked_prompt:
        full_prompt = locked_prompt
    else:
        # Sync SceneState with the turn being illustrated so the Scene State panel matches the picture
        turn_user_text = ""
        turn_assistant_text = target_msg.content if target_msg.role == "assistant" else ""
        if target_msg.role == "user":
            turn_user_text = target_msg.content
        else:
            for m in reversed(session.messages[:msg_idx]):
                if m.role == "user" and m.content.strip():
                    turn_user_text = m.content
                    break
        session.scene_state = await update_scene_state(
            config=storage.config,
            previous_state=session.scene_state,
            user_text=turn_user_text,
            assistant_text=turn_assistant_text,
            world_aesthetic=world.aesthetic_style if world else "",
        )
        full_prompt = await build_contextual_scene_prompt(
            config=storage.config,
            character=card,
            messages=session.messages,
            target_msg=target_msg,
            lore_visuals=lore_visuals,
            user_name=session.user_persona_name,
            user_desc=session.user_persona_desc,
            situation_checkpoint=session.situation_checkpoint,
            scene_state=session.scene_state,
        )
    prompt_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    img_meta = await generate_image_asset(
        config=storage.config,
        output_dir=storage.generated_dir,
        prompt=full_prompt,
        negative_prompt=card.negative_prompt_tags if card else "blurry, low quality",
    )
    render_ms = (time.perf_counter() - t0) * 1000
    total_ms = (time.perf_counter() - t_total0) * 1000
    logger.info(
        "⏱️ SCENE    | total=%.2fs (lore=%.0fms, prompt=%.2fs, render=%.2fs)",
        total_ms / 1000,
        lore_ms,
        prompt_ms / 1000,
        render_ms / 1000,
    )
    target_msg.image_url = img_meta["url"]
    target_msg.image_prompt = full_prompt
    target_msg.image_seed = img_meta["seed"]
    target_msg.image_metadata_url = img_meta.get("metadata_url")
    if not target_msg.triggered_lore and lore_res.triggered:
        target_msg.triggered_lore = lore_res.triggered
    session.updated_at = utc_now_iso()

    scene_timings = {
        "lore_ms": round(lore_ms, 1),
        "prompt_ms": round(prompt_ms, 1),
        "render_ms": round(render_ms, 1),
        "total_ms": round(total_ms, 1),
    }
    target_msg.timings = {**(target_msg.timings or {}), **scene_timings}
    _record_metric("scene", {"provider": img_meta["provider"], **scene_timings})

    matched_loc_id = _resolve_location_entry_id(
        world,
        lore_res.triggered,
        scene_location=session.scene_state.location if session.scene_state else "",
    )
    asset = GalleryAsset(
        url=img_meta["url"],
        prompt=full_prompt,
        provider=img_meta["provider"],
        width=img_meta["width"],
        height=img_meta["height"],
        seed=img_meta["seed"],
        metadata_url=img_meta.get("metadata_url"),
        character_id=card.id if card else None,
        world_id=session.world_id,
        location_entry_id=matched_loc_id,
        duration_ms=img_meta.get("duration_ms"),
    )
    storage.gallery.insert(0, asset)
    storage.save()
    return {
        "session": session.model_dump(),
        "asset": asset.model_dump(),
        "timings": scene_timings,
    }


@app.post("/api/chats/{chat_id}/checkpoint")
async def update_chat_checkpoint(chat_id: str, req: CheckpointRequest) -> dict[str, Any]:
    session = storage.chats.get(chat_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    card = storage.characters.get(session.character_id)

    if req.custom_checkpoint is not None:
        session.situation_checkpoint = req.custom_checkpoint.strip()
        session.checkpoint_msg_count = len(session.messages)
    elif req.refresh:
        await _maybe_update_chat_checkpoint(session, card, force=True)

    session.updated_at = utc_now_iso()
    storage.save()
    return {"session": session.model_dump()}


@app.post("/api/chats/{chat_id}/scene-state")
async def update_chat_scene_state(chat_id: str, state: SceneState) -> dict[str, Any]:
    session = storage.chats.get(chat_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    session.scene_state = state
    session.updated_at = utc_now_iso()
    storage.save()
    return {"session": session.model_dump()}


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
    logger.info("▶ ACTION   | execute_workflow(name=%r, id=%s, nodes=%d)", wf.name, wf.id, len(wf.nodes))
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
    logger.info("▶ ACTION   | generate_direct_gallery_image(prompt=%r, %dx%d)", req.prompt[:90], req.width, req.height)
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
    logger.info("▶ ACTION   | delete_gallery_asset(id=%s)", asset_id)
    return {"status": "deleted", "id": asset_id}


@app.post("/api/backstory-image")
async def generate_backstory_grounded_image(req: BackstoryImageRequest) -> dict[str, Any]:
    """
    Generates a standalone image grounded in the roleplay's character persona,
    physical description, scenario backstory, and world lorebook without adding a chat turn.
    """
    t_studio_start = time.perf_counter()
    session = storage.chats.get(req.chat_id) if req.chat_id else None
    char_id = req.character_id or (session.character_id if session else None)
    world_id = req.world_id or (session.world_id if session else None)

    card = storage.characters.get(char_id) if char_id else None
    if not world_id and card and card.world_id:
        world_id = card.world_id
    world = storage.worlds.get(world_id) if world_id else None

    is_pony = "pony" in (storage.config.comfyui_checkpoint or "").lower()
    active_mode = req.render_mode or getattr(storage.config, "comfyui_render_mode", "hybrid_refiner")
    logger.info(
        "▶ ACTION   | generate_backstory_grounded_image(char=%r, world=%r, mode=%s, %dx%d, custom_prompt=%r)",
        card.name if card else "None",
        world.name if world else "None",
        active_mode,
        req.width,
        req.height,
        req.custom_prompt[:90],
    )
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

    # 3. Character visual prompt tags & physical beauty traits (cleaned of conflicting static clothing / portrait crop)
    char_traits = ""
    if req.include_character_visuals and card:
        if card.visual_prompt_tags:
            char_traits = clean_character_visual_tags_for_scene(
                card.visual_prompt_tags,
                f"{req.custom_prompt} {card.scenario or ''}",
            )
        elif card.description:
            clean_desc = replace_tavern_macros(card.description, char_name=card.name, user_name="Traveler")
            char_traits = fallback_extract_sdxl_keywords(clean_desc, max_keywords=8)

    # 4. Harmonize Scenario, Lore, and Style via small LLM (character traits stay locked verbatim!)
    llm_provider_used = None
    harmonized_kw = ""
    if scenario_to_distill or lore_visuals_to_distill or req.use_llm_director:
        if req.use_llm_director or scenario_to_distill:
            harmonized_kw, llm_provider_used = await harmonize_sdxl_prompt(
                config=storage.config,
                user_intent_text=req.custom_prompt.strip(),
                action_or_scene_text=req.custom_prompt.strip(),
                scenario_text=scenario_to_distill,
                lore_visuals=lore_visuals_to_distill,
                style_hint=style_suffix,
            )
        elif lore_visuals_to_distill:
            harmonized_kw = ", ".join(p for p in (lore_visuals_to_distill, style_suffix) if p)
    else:
        harmonized_kw = ", ".join(p for p in (req.custom_prompt.strip(), style_suffix) if p)

    session_state_tags = ""
    if req.chat_id and req.chat_id in storage.chats:
        chat_sess = storage.chats[req.chat_id]
        session_state_tags = format_scene_state_tags(chat_sess.scene_state)

    scene_focus = f"{req.custom_prompt} {scenario_to_distill} {session_state_tags}"
    anat_boost, cleaned_harmonized_kw, _ = build_anatomical_and_clothing_overrides(
        scene_text=scene_focus,
        distilled_keywords=harmonized_kw,
    )
    templated_studio_parts = render_prompt_template(
        storage.config.studio_prompt_template,
        {
            "quality": quality_prefix,
            "anatomical_overrides": anat_boost,
            "scene_state": session_state_tags,
            "character_traits": char_traits,
            "location_lore": lore_visuals_to_distill,
            "dialog_scene": req.custom_prompt.strip(),
            "harmonized_scene": cleaned_harmonized_kw,
            "style": style_suffix,
        },
    )
    if cleaned_harmonized_kw and "{harmonized_scene}" not in storage.config.studio_prompt_template:
        templated_studio_parts.append(cleaned_harmonized_kw)
    final_tags = dedupe_and_resolve_prompt_conflicts(templated_studio_parts, scene_text=scene_focus)
    assembled_prompt = ", ".join(final_tags)

    neg_prompt = card.negative_prompt_tags if card else "blurry, low quality, deformed, watermark"

    t_render_start = time.perf_counter()
    prompt_ms = (t_render_start - t_studio_start) * 1000
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
        face_detailer_override=req.face_detailer,
    )
    render_ms = (time.perf_counter() - t_render_start) * 1000
    total_ms = (time.perf_counter() - t_studio_start) * 1000
    logger.info(
        "⏱️ STUDIO   | total=%.2fs (prompt=%.2fs, render=%.2fs)",
        total_ms / 1000,
        prompt_ms / 1000,
        render_ms / 1000,
    )

    studio_timings = {
        "prompt_ms": round(prompt_ms, 1),
        "render_ms": round(render_ms, 1),
        "total_ms": round(total_ms, 1),
    }
    _record_metric("studio", {"provider": img_meta["provider"], **studio_timings})

    matched_loc_id = _resolve_location_entry_id(
        world,
        triggered_lore_list,
        scene_location=(session.scene_state.location if (session and session.scene_state) else req.custom_prompt),
    )
    asset = GalleryAsset(
        url=img_meta["url"],
        prompt=assembled_prompt,
        negative_prompt=neg_prompt,
        provider=img_meta["provider"],
        width=img_meta["width"],
        height=img_meta["height"],
        seed=img_meta["seed"],
        metadata_url=img_meta.get("metadata_url"),
        character_id=card.id if card else None,
        world_id=world.id if world else None,
        location_entry_id=matched_loc_id,
        duration_ms=img_meta.get("duration_ms"),
    )
    storage.gallery.insert(0, asset)
    storage.save()

    return {
        "asset": asset.model_dump(),
        "assembled_prompt": assembled_prompt,
        "triggered_lore": triggered_lore_list,
        "image_provider": img_meta["provider"],
        "llm_provider": llm_provider_used,
        "timings": studio_timings,
    }
