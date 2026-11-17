from __future__ import annotations

import base64
import io
import json
from typing import Any
from PIL import Image, PngImagePlugin

from .models import CharacterCard, utc_now_iso


def character_to_tavern_v2_dict(card: CharacterCard) -> dict[str, Any]:
    """Convert an internal CharacterCard into Character Card V2 Specification dict."""
    data = {
        "name": card.name,
        "description": card.description,
        "personality": card.personality,
        "scenario": card.scenario,
        "first_mes": card.first_mes,
        "mes_example": card.mes_example,
        "creator_notes": card.creator_notes,
        "system_prompt": card.system_prompt,
        "post_history_instructions": card.post_history_instructions,
        "tags": card.tags,
        "creator": "Hivemind Studio",
        "character_version": "1.0",
        "alternate_greetings": [],
        "extensions": {
            "hivemind": {
                "id": card.id,
                "title": card.title,
                "visual_prompt_tags": card.visual_prompt_tags,
                "negative_prompt_tags": card.negative_prompt_tags,
                "world_id": card.world_id,
                "default_workflow_id": card.default_workflow_id,
            }
        },
    }
    return {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "data": data,
    }


def tavern_dict_to_character(payload: dict[str, Any], avatar_url: str = "") -> CharacterCard:
    """Parse either V1 flat dict or V2 {'spec': 'chara_card_v2', 'data': {...}} into CharacterCard."""
    data = payload.get("data", payload) if isinstance(payload, dict) else {}
    ext = data.get("extensions", {}).get("hivemind", {}) if isinstance(data.get("extensions"), dict) else {}

    tags = data.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]

    return CharacterCard(
        name=data.get("name") or payload.get("name") or "Unnamed Character",
        title=ext.get("title") or data.get("creator_notes", "")[:60] or "Wanderer",
        description=data.get("description") or payload.get("description") or "",
        personality=data.get("personality") or payload.get("personality") or "",
        scenario=data.get("scenario") or payload.get("scenario") or "",
        first_mes=data.get("first_mes") or payload.get("first_mes") or "",
        mes_example=data.get("mes_example") or payload.get("mes_example") or "",
        system_prompt=data.get("system_prompt") or "",
        post_history_instructions=data.get("post_history_instructions") or "",
        creator_notes=data.get("creator_notes") or "",
        tags=tags,
        visual_prompt_tags=ext.get("visual_prompt_tags") or data.get("visual_prompt_tags") or "",
        negative_prompt_tags=ext.get("negative_prompt_tags") or "blurry, low quality, deformed, watermark",
        avatar_url=avatar_url,
        world_id=ext.get("world_id"),
        default_workflow_id=ext.get("default_workflow_id"),
        updated_at=utc_now_iso(),
    )


def encode_tavern_png(card: CharacterCard, base_image_bytes: bytes | None = None) -> bytes:
    """Embed Character Card V2 JSON metadata into a PNG 'chara' tEXt chunk."""
    if base_image_bytes:
        img = Image.open(io.BytesIO(base_image_bytes)).convert("RGBA")
    else:
        img = Image.new("RGBA", (512, 512), (24, 24, 38, 255))

    v2_dict = character_to_tavern_v2_dict(card)
    json_bytes = json.dumps(v2_dict, ensure_ascii=False).encode("utf-8")
    b64_chara = base64.b64encode(json_bytes).decode("ascii")

    png_info = PngImagePlugin.PngInfo()
    png_info.add_text("chara", b64_chara)

    out = io.BytesIO()
    img.save(out, format="PNG", pnginfo=png_info)
    return out.getvalue()


def decode_tavern_png(png_bytes: bytes, avatar_url: str = "") -> CharacterCard:
    """Extract Character Card V1/V2 metadata from a PNG 'chara' or 'ccv3' tEXt chunk."""
    img = Image.open(io.BytesIO(png_bytes))
    info = img.info or {}

    raw_b64 = info.get("chara") or info.get("ccv3")
    if not raw_b64:
        raise ValueError("PNG file does not contain a 'chara' Character Card metadata chunk.")

    decoded_bytes = base64.b64decode(raw_b64)
    payload = json.loads(decoded_bytes.decode("utf-8"))
    return tavern_dict_to_character(payload, avatar_url=avatar_url)
