from __future__ import annotations

import asyncio
import hashlib
import io
import json
import math
import platform
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from ..logger import logger
from ..models import InferenceConfig
from .llm_engine import build_anatomical_and_clothing_overrides, build_face_detailer_prompt, is_dynamic_action_scene

try:
    import torch
    TORCH_AVAILABLE = True
    MPS_AVAILABLE = bool(hasattr(torch.backends, "mps") and torch.backends.mps.is_available())
    TORCH_VERSION = torch.__version__
except Exception:
    TORCH_AVAILABLE = False
    MPS_AVAILABLE = False
    TORCH_VERSION = "unavailable"


_MPS_PIPELINE_CACHE: dict[str, Any] = {}


def get_apple_silicon_telemetry() -> dict[str, Any]:
    return {
        "architecture": platform.machine(),
        "system": platform.system(),
        "processor": platform.processor() or "Apple Silicon arm64",
        "is_apple_silicon": platform.system() == "Darwin" and platform.machine() == "arm64",
        "torch_available": TORCH_AVAILABLE,
        "torch_version": TORCH_VERSION,
        "mps_available": MPS_AVAILABLE,
        "mps_loaded_models": list(_MPS_PIPELINE_CACHE.keys()),
    }


async def check_comfyui_status(base_url: str) -> dict[str, Any]:
    candidates = [base_url.rstrip("/")]
    for fallback in ("http://127.0.0.1:8188", "http://127.0.0.1:8000"):
        if fallback not in candidates:
            candidates.append(fallback)

    async with httpx.AsyncClient(timeout=5.0) as client:
        for url in candidates:
            try:
                resp = await client.get(f"{url}/system_stats")
                if resp.status_code == 200:
                    stats = resp.json()
                    checkpoints: list[str] = []
                    face_detectors: list[str] = []
                    try:
                        ckpt_resp = await client.get(f"{url}/object_info/CheckpointLoaderSimple")
                        if ckpt_resp.status_code == 200:
                            ckpt_data = ckpt_resp.json()
                            raw_list = (
                                ckpt_data.get("CheckpointLoaderSimple", {})
                                .get("input", {})
                                .get("required", {})
                                .get("ckpt_name", [[]])[0]
                            )
                            if isinstance(raw_list, list):
                                checkpoints = [str(c) for c in raw_list]
                    except Exception:
                        pass
                    try:
                        mp_resp = await client.get(f"{url}/object_info/LoadMediaPipeFaceLandmarker")
                        if mp_resp.status_code == 200:
                            mp_data = mp_resp.json()
                            mp_input = (
                                mp_data.get("LoadMediaPipeFaceLandmarker", {})
                                .get("input", {})
                                .get("required", {})
                                .get("model_name", [])
                            )
                            if len(mp_input) >= 2 and isinstance(mp_input[1], dict):
                                opts = mp_input[1].get("options", [])
                                if isinstance(opts, list):
                                    face_detectors = [str(o) for o in opts]
                            elif len(mp_input) >= 1 and isinstance(mp_input[0], list):
                                face_detectors = [str(o) for o in mp_input[0]]
                    except Exception:
                        pass
                    return {
                        "online": True,
                        "active_url": url,
                        "checkpoints": checkpoints,
                        "face_detectors": face_detectors,
                        "stats": stats,
                    }
            except Exception:
                continue
    return {"online": False, "active_url": base_url, "checkpoints": [], "face_detectors": [], "stats": {}}


def _render_procedural_artwork(
    prompt: str,
    negative_prompt: str = "",
    width: int = 512,
    height: int = 512,
    seed: int = 42,
) -> bytes:
    """
    High-speed Apple Silicon procedural concept art & character portrait synthesizer.
    Produces rich atmospheric PNG artwork deterministically from prompt semantics + seed.
    """
    w = max(256, min(1024, width))
    h = max(256, min(1024, height))

    digest = hashlib.sha256(f"{prompt}:{seed}".encode("utf-8")).digest()
    rng = np.random.default_rng(int.from_bytes(digest[:8], "big"))

    p_lower = prompt.lower()

    # Determine palette from prompt themes
    if any(k in p_lower for k in ["cyber", "neon", "noir", "hacker", "veridia", "synth", "android"]):
        top_rgb = np.array([10, 14, 36], dtype=np.float32)
        mid_rgb = np.array([28, 18, 68], dtype=np.float32)
        bot_rgb = np.array([12, 52, 74], dtype=np.float32)
        accent_primary = (0, 240, 255)
        accent_secondary = (255, 42, 133)
        theme = "cyber"
    elif any(k in p_lower for k in ["crimson", "queen", "citadel", "sunless", "blood", "velvet", "gothic", "vampire"]):
        top_rgb = np.array([18, 8, 16], dtype=np.float32)
        mid_rgb = np.array([58, 14, 32], dtype=np.float32)
        bot_rgb = np.array([22, 10, 18], dtype=np.float32)
        accent_primary = (255, 75, 110)
        accent_secondary = (255, 195, 110)
        theme = "gothic"
    elif any(k in p_lower for k in ["forest", "emerald", "druid", "verdant", "elven", "nature"]):
        top_rgb = np.array([8, 24, 22], dtype=np.float32)
        mid_rgb = np.array([16, 56, 48], dtype=np.float32)
        bot_rgb = np.array([10, 30, 24], dtype=np.float32)
        accent_primary = (80, 255, 170)
        accent_secondary = (255, 220, 120)
        theme = "verdant"
    else:
        # Astral / Chronomancer / Fantasy Gold-Violet default
        top_rgb = np.array([12, 10, 30], dtype=np.float32)
        mid_rgb = np.array([44, 24, 78], dtype=np.float32)
        bot_rgb = np.array([20, 28, 56], dtype=np.float32)
        accent_primary = (245, 190, 95)
        accent_secondary = (155, 115, 255)
        theme = "astral"

    # Vectorized smooth gradient + radial glow via NumPy
    y_norm = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
    x_norm = np.linspace(0.0, 1.0, w, dtype=np.float32)[None, :]

    bg = np.where(
        y_norm[:, :, None] < 0.55,
        top_rgb + (mid_rgb - top_rgb) * (y_norm[:, :, None] / 0.55),
        mid_rgb + (bot_rgb - mid_rgb) * ((y_norm[:, :, None] - 0.55) / 0.45),
    )

    # Radial light source
    cx = 0.5 + (int(digest[8]) / 255.0 - 0.5) * 0.22
    cy = 0.36 + (int(digest[9]) / 255.0 - 0.5) * 0.14
    dist = np.sqrt((x_norm - cx) ** 2 + ((y_norm - cy) * (h / w)) ** 2)
    glow = np.exp(-dist * 3.2)[:, :, None]
    glow_color = np.array(accent_primary, dtype=np.float32)
    canvas_np = np.clip(bg + glow * glow_color * 0.52, 0, 255).astype(np.uint8)

    base_img = Image.fromarray(canvas_np, mode="RGB").convert("RGBA")
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    sun_x = int(cx * w)
    sun_y = int(cy * h)
    base_r = int(min(w, h) * 0.24)

    # Sacred / Astral / Cyber Halo Rings
    for i, mult in enumerate([1.35, 1.08, 0.82, 0.58]):
        r = int(base_r * mult)
        alpha = 95 - i * 15
        col = accent_primary if i % 2 == 0 else accent_secondary
        draw.ellipse(
            [sun_x - r, sun_y - r, sun_x + r, sun_y + r],
            outline=(*col, alpha),
            width=2 if i % 2 == 0 else 1,
        )

    # Geometric Runes / Orbitals around the halo
    num_spokes = 12
    angle_offset = (seed % 360) * math.pi / 180.0
    for idx in range(num_spokes):
        theta = angle_offset + idx * (2 * math.pi / num_spokes)
        r_in = base_r * 0.84
        r_out = base_r * 1.32
        x1 = sun_x + int(math.cos(theta) * r_in)
        y1 = sun_y + int(math.sin(theta) * r_in)
        x2 = sun_x + int(math.cos(theta) * r_out)
        y2 = sun_y + int(math.sin(theta) * r_out)
        draw.line([(x1, y1), (x2, y2)], fill=(*accent_primary, 55), width=1)

    is_character = any(
        k in p_lower
        for k in [
            "portrait",
            "character",
            "woman",
            "man",
            "exile",
            "archivist",
            "queen",
            "knight",
            "mage",
            "chronomancer",
            "lyra",
            "kaelen",
            "seraphina",
            "person",
            "face",
            "avatar",
        ]
    )

    # Distant architectural spires / mountain ridges
    horizon_y = int(h * 0.72)
    ridge_points = [(0, h), (0, horizon_y)]
    num_peaks = 14
    for i in range(num_peaks + 1):
        px = int(w * (i / num_peaks))
        if theme == "cyber":
            py = horizon_y - int(rng.integers(15, int(h * 0.28)))
            # Draw vertical skyscraper silhouettes
            b_w = int(w / num_peaks * 0.75)
            draw.rectangle(
                [px - b_w // 2, py, px + b_w // 2, h],
                fill=(10, 14, 28, 210),
                outline=(*accent_primary, 45),
            )
            # Neon windows
            for wy in range(py + 10, h - 20, 14):
                if rng.random() > 0.35:
                    draw.rectangle(
                        [px - b_w // 4, wy, px + b_w // 4, wy + 4],
                        fill=(*accent_secondary, 110),
                    )
        else:
            py = horizon_y - int(rng.integers(10, int(h * 0.22)))
            ridge_points.append((px, py))

    if theme != "cyber":
        ridge_points.append((w, h))
        draw.polygon(ridge_points, fill=(12, 10, 24, 220))

    if is_character:
        # Render stylized dramatic character bust / cloak / glowing eyes & emblem
        cx_char = w // 2
        head_y = int(h * 0.41)
        head_r = int(min(w, h) * 0.105)

        # Backlight aura behind character
        aura_r = int(head_r * 2.2)
        draw.ellipse(
            [cx_char - aura_r, head_y - aura_r, cx_char + aura_r, head_y + aura_r],
            fill=(*accent_primary, 38),
        )

        # Cloak & Shoulders polygon
        cloak_pts = [
            (cx_char - int(w * 0.34), h),
            (cx_char - int(w * 0.25), int(h * 0.64)),
            (cx_char - int(w * 0.11), int(h * 0.53)),
            (cx_char, int(h * 0.50)),
            (cx_char + int(w * 0.11), int(h * 0.53)),
            (cx_char + int(w * 0.25), int(h * 0.64)),
            (cx_char + int(w * 0.34), h),
        ]
        draw.polygon(cloak_pts, fill=(16, 14, 28, 248), outline=(*accent_primary, 130))

        # High collar / Pauldrons
        collar_pts = [
            (cx_char - int(w * 0.16), int(h * 0.58)),
            (cx_char - int(w * 0.19), int(h * 0.44)),
            (cx_char, int(h * 0.54)),
            (cx_char + int(w * 0.19), int(h * 0.44)),
            (cx_char + int(w * 0.16), int(h * 0.58)),
        ]
        draw.polygon(collar_pts, fill=(26, 22, 44, 245), outline=(*accent_secondary, 150))

        # Hood / Hair / Crown silhouette
        hood_r_x = int(head_r * 1.28)
        hood_r_y = int(head_r * 1.38)
        draw.ellipse(
            [cx_char - hood_r_x, head_y - hood_r_y, cx_char + hood_r_x, head_y + hood_r_y],
            fill=(20, 18, 34, 255),
            outline=(*accent_primary, 160),
            width=2,
        )

        # Head contour
        draw.ellipse(
            [cx_char - head_r, head_y - head_r, cx_char + head_r, head_y + head_r],
            fill=(34, 28, 48, 255),
            outline=(*accent_primary, 110),
            width=2,
        )

        # Glowing eyes
        eye_y = head_y + int(head_r * 0.06)
        eye_dx = int(head_r * 0.38)
        eye_w = max(5, int(head_r * 0.22))
        eye_h = max(3, int(head_r * 0.09))
        draw.ellipse(
            [cx_char - eye_dx - eye_w, eye_y - eye_h, cx_char - eye_dx + eye_w, eye_y + eye_h],
            fill=(*accent_primary, 245),
        )
        draw.ellipse(
            [cx_char + eye_dx - eye_w, eye_y - eye_h, cx_char + eye_dx + eye_w, eye_y + eye_h],
            fill=(*accent_primary, 245),
        )

        # Chest Arcane/Cyber Core Amulet
        core_y = int(h * 0.67)
        core_r = int(head_r * 0.42)
        draw.polygon(
            [
                (cx_char, core_y - core_r),
                (cx_char + core_r, core_y),
                (cx_char, core_y + core_r),
                (cx_char - core_r, core_y),
            ],
            fill=(*accent_primary, 215),
            outline=(255, 255, 255, 220),
        )
    else:
        # Grand Central Monolith / Citadel / Portal for World & Scene Illustrations
        cx_mon = sun_x
        top_y = int(h * 0.25)
        bot_y = int(h * 0.88)
        half_w = int(w * 0.11)
        monolith_pts = [
            (cx_mon, top_y),
            (cx_mon + half_w, int(h * 0.38)),
            (cx_mon + int(half_w * 1.35), bot_y),
            (cx_mon - int(half_w * 1.35), bot_y),
            (cx_mon - half_w, int(h * 0.38)),
        ]
        draw.polygon(monolith_pts, fill=(16, 14, 30, 235), outline=(*accent_primary, 180))
        # Inner portal beam
        portal_w = int(half_w * 0.38)
        draw.rectangle(
            [cx_mon - portal_w, int(h * 0.36), cx_mon + portal_w, bot_y],
            fill=(*accent_primary, 165),
        )

    # Atmospheric Floating Embers / Bokeh Particles
    for _ in range(55):
        px = int(rng.integers(12, w - 12))
        py = int(rng.integers(12, h - 12))
        pr = int(rng.integers(1, 5))
        col = accent_primary if rng.random() > 0.4 else accent_secondary
        alpha = int(rng.integers(70, 210))
        draw.ellipse([px - pr, py - pr, px + pr, py + pr], fill=(*col, alpha))

    # Subtle Vignette Frame
    draw.rectangle([4, 4, w - 5, h - 5], outline=(*accent_primary, 80), width=1)

    composed = Image.alpha_composite(base_img, overlay).convert("RGB")
    composed = composed.filter(ImageFilter.SMOOTH_MORE)

    buf = io.BytesIO()
    composed.save(buf, format="PNG")
    return buf.getvalue()


def _run_mps_diffusers_sync(
    model_id: str,
    prompt: str,
    negative_prompt: str,
    width: int,
    height: int,
    steps: int,
    cfg: float,
    seed: int,
    use_fp16: bool,
    attention_slicing: bool,
    allow_download: bool,
) -> bytes | None:
    if not (TORCH_AVAILABLE and MPS_AVAILABLE):
        return None

    try:
        from diffusers import AutoPipelineForText2Image

        cache_key = f"{model_id}:{'fp16' if use_fp16 else 'fp32'}"
        pipe = _MPS_PIPELINE_CACHE.get(cache_key)
        if pipe is None:
            dtype = torch.float16 if use_fp16 else torch.float32
            pipe = AutoPipelineForText2Image.from_pretrained(
                model_id,
                torch_dtype=dtype,
                local_files_only=not allow_download,
            )
            pipe = pipe.to("mps")
            if attention_slicing and hasattr(pipe, "enable_attention_slicing"):
                pipe.enable_attention_slicing()
            _MPS_PIPELINE_CACHE[cache_key] = pipe

        generator = torch.Generator(device="cpu").manual_seed(int(seed))
        result = pipe(
            prompt=prompt,
            negative_prompt=negative_prompt or None,
            width=max(256, (width // 8) * 8),
            height=max(256, (height // 8) * 8),
            num_inference_steps=max(1, min(50, steps)),
            guidance_scale=cfg,
            generator=generator,
        )
        img = result.images[0]
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return None


async def _fetch_comfy_node_image_bytes(
    client: httpx.AsyncClient,
    base: str,
    outputs: dict[str, Any],
    preferred_node_id: str,
) -> tuple[bytes | None, str]:
    """Fetches PNG bytes for a specific SaveImage node output (or falls back to first available)."""
    node_out = outputs.get(preferred_node_id)
    if not node_out:
        return None, ""
    images = node_out.get("images", [])
    if not images:
        return None, ""
    img_meta = images[0]
    view_resp = await client.get(
        f"{base}/view",
        params={
            "filename": img_meta["filename"],
            "subfolder": img_meta.get("subfolder", ""),
            "type": img_meta.get("type", "output"),
        },
    )
    if view_resp.status_code == 200:
        return view_resp.content, str(img_meta["filename"])
    return None, ""


async def _run_comfyui_bridge(
    config: InferenceConfig,
    prompt: str,
    negative_prompt: str,
    width: int,
    height: int,
    steps: int,
    cfg: float,
    seed: int,
    render_mode_override: str | None = None,
    face_detailer_override: bool | None = None,
) -> tuple[bytes | None, str]:
    status = await check_comfyui_status(config.comfyui_base_url)
    if not status["online"]:
        logger.warning("⚠️ COMFY⏭   | ComfyUI unreachable/offline at %s — skipping ComfyUI", config.comfyui_base_url)
        return None, ""

    base = status.get("active_url", config.comfyui_base_url).rstrip("/")
    available_ckpts: list[str] = status.get("checkpoints", [])
    face_detectors: list[str] = status.get("face_detectors", [])
    ckpt_to_use = config.comfyui_checkpoint
    if available_ckpts and ckpt_to_use not in available_ckpts:
        matched = next(
            (c for c in available_ckpts if ckpt_to_use.lower() in c.lower() or "sd_xl_base" in c.lower()),
            available_ckpts[0],
        )
        ckpt_to_use = matched

    active_mode = render_mode_override or getattr(config, "comfyui_render_mode", "single_stylized")
    sampler_name = getattr(config, "comfyui_sampler", "dpmpp_2m") or "dpmpp_2m"
    scheduler_name = getattr(config, "comfyui_scheduler", "karras") or "karras"

    # Auto-tune steps & CFG for Turbo / Lightning checkpoints so they render in ~4s and never burn/saturate faces
    is_turbo_ckpt = any(k in ckpt_to_use.lower() for k in ("turbo", "lightning", "hyper"))
    if is_turbo_ckpt and active_mode != "hybrid_refiner":
        steps = min(steps, 8)
        cfg = min(cfg, 2.2)
        sampler_name = "dpmpp_sde"
        scheduler_name = "karras"
    else:
        # Clamp CFG <= 6.0 to prevent bright red/cyan saturation burn on faces during golden hour scenes
        cfg = min(cfg, 6.0)
        if sampler_name == "dpmpp_2m_sde":
            sampler_name = "dpmpp_2m"

    # Determine if we can run a 2-stage hybrid pipeline:
    # - 'action_hybrid': Juggernaut-XL (dynamic action/physics base) -> Primary Pony checkpoint (attire/skin/anatomy refine)
    # - 'hybrid_refiner': Primary Pony checkpoint -> Artistic SDXL Refiner
    action_base_ckpt = next(
        (c for c in (available_ckpts or []) if "juggernaut" in c.lower()),
        None,
    ) or next(
        (c for c in (available_ckpts or []) if "dreamshaper" in c.lower()),
        None,
    )
    use_action_hybrid = (
        (active_mode == "action_hybrid" or (is_dynamic_action_scene(prompt) and active_mode != "single_raw"))
        and bool(action_base_ckpt)
        and action_base_ckpt != ckpt_to_use
    )

    refiner_ckpt = getattr(config, "comfyui_refiner_checkpoint", "sd_xl_base_1.0_0.9vae.safetensors")
    if available_ckpts and refiner_ckpt not in available_ckpts:
        refiner_match = next(
            (c for c in available_ckpts if "sd_xl_base" in c.lower() or "dreamshaper" in c.lower() or "juggernaut" in c.lower()),
            None,
        )
        if refiner_match:
            refiner_ckpt = refiner_match

    use_hybrid = use_action_hybrid or (
        active_mode == "hybrid_refiner"
        and bool(refiner_ckpt)
        and refiner_ckpt != ckpt_to_use
        and (not available_ckpts or refiner_ckpt in available_ckpts)
    )

    stage1_ckpt = action_base_ckpt if use_action_hybrid else ckpt_to_use
    stage2_ckpt = ckpt_to_use if use_action_hybrid else refiner_ckpt
    is_pony_primary = "pony" in stage1_ckpt.lower()
    is_pony_stage2 = "pony" in stage2_ckpt.lower()

    base_neg = (
        negative_prompt
        or "score_4, score_5, score_6, blurry, low quality, flat lighting, washed out, oversaturated, burnt face, red nose, clown makeup, deformed, bad anatomy"
    )
    _, _, neg_clothing_blockers = build_anatomical_and_clothing_overrides(prompt)
    neg_text = f"{base_neg}, {neg_clothing_blockers}" if neg_clothing_blockers else base_neg
    if not any(m in prompt.lower() for m in ("2girls", "3girls", "two women", "multiple girls", "crowd", "group", "threesome")):
        neg_text = f"{neg_text}, 2girls, multiple girls, two women, duplicate, twins"
    if (is_pony_primary or is_pony_stage2) and "score_4" not in neg_text:
        neg_text = f"score_4, score_5, score_6, {neg_text}"

    if use_hybrid:
        stage1_steps = max(10, int(round(steps * 0.6))) if use_action_hybrid else max(14, int(round(steps * 0.8)))
        clean_non_pony_prompt = (
            prompt.replace("score_9, score_8_up, score_7_up,", "")
            .replace("score_9, score_8_up, score_7_up", "")
            .strip(" ,")
        )
        if use_action_hybrid:
            stage1_prompt = clean_non_pony_prompt
            stage2_prompt = prompt
        else:
            stage1_prompt = prompt
            stage2_prompt = (
                f"masterpiece stylized glamour digital art, natural beautiful face, warm golden hour sunset rim lighting, "
                f"luminous bronze and amber color grading, {clean_non_pony_prompt}"
            )

        workflow_payload: dict[str, Any] = {
            "4": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": stage1_ckpt},
            },
            "10": {
                "class_type": "CLIPSetLastLayer",
                "inputs": {"clip": ["4", 1], "stop_at_clip_layer": -2 if is_pony_primary else -1},
            },
            "5": {
                "class_type": "EmptyLatentImage",
                "inputs": {"batch_size": 1, "height": height, "width": width},
            },
            "6": {
                "class_type": "CLIPTextEncode",
                "inputs": {"clip": ["10", 0], "text": stage1_prompt},
            },
            "7": {
                "class_type": "CLIPTextEncode",
                "inputs": {"clip": ["10", 0], "text": neg_text},
            },
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": seed,
                    "steps": stage1_steps,
                    "cfg": min(cfg, 5.5),
                    "sampler_name": "dpmpp_2m",
                    "scheduler": "karras",
                    "positive": ["6", 0],
                    "negative": ["7", 0],
                    "latent_image": ["5", 0],
                    "denoise": 1.0,
                    "model": ["4", 0],
                },
            },
            "15": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
            },
            "11": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": stage2_ckpt},
            },
            "17": {
                "class_type": "CLIPSetLastLayer",
                "inputs": {"clip": ["11", 1], "stop_at_clip_layer": -2 if is_pony_stage2 else -1},
            },
            "16": {
                "class_type": "VAEEncode",
                "inputs": {"pixels": ["15", 0], "vae": ["11", 2]},
            },
            "12": {
                "class_type": "CLIPTextEncode",
                "inputs": {"clip": ["17", 0], "text": stage2_prompt},
            },
            "13": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "clip": ["17", 0],
                    "text": neg_text if use_action_hybrid else "oversaturated, red face, glowing nose, clown makeup, blurry, low quality, deformed",
                },
            },
            "14": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": seed + 1,
                    "steps": 10 if use_action_hybrid else 14,
                    "cfg": 5.5 if use_action_hybrid else 5.0,
                    "sampler_name": "dpmpp_2m",
                    "scheduler": "karras",
                    "positive": ["12", 0],
                    "negative": ["13", 0],
                    "latent_image": ["16", 0],
                    "denoise": 0.40 if use_action_hybrid else 0.36,
                    "model": ["11", 0],
                },
            },
            "8": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["14", 0], "vae": ["11", 2]},
            },
            "9": {
                "class_type": "SaveImage",
                "inputs": {"filename_prefix": "Hivemind_Hybrid", "images": ["8", 0]},
            },
        }
        provider_label = (
            f"comfyui_action_hybrid ({stage1_ckpt} → {stage2_ckpt})"
            if use_action_hybrid
            else f"comfyui_hybrid ({stage1_ckpt} → {stage2_ckpt})"
        )
    else:
        workflow_payload = {
            "4": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": ckpt_to_use},
            },
            "10": {
                "class_type": "CLIPSetLastLayer",
                "inputs": {"clip": ["4", 1], "stop_at_clip_layer": -2 if is_pony_primary else -1},
            },
            "5": {
                "class_type": "EmptyLatentImage",
                "inputs": {"batch_size": 1, "height": height, "width": width},
            },
            "6": {
                "class_type": "CLIPTextEncode",
                "inputs": {"clip": ["10", 0], "text": prompt},
            },
            "7": {
                "class_type": "CLIPTextEncode",
                "inputs": {"clip": ["10", 0], "text": neg_text},
            },
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "cfg": cfg,
                    "denoise": 1.0,
                    "latent_image": ["5", 0],
                    "model": ["4", 0],
                    "negative": ["7", 0],
                    "positive": ["6", 0],
                    "sampler_name": sampler_name,
                    "scheduler": scheduler_name,
                    "seed": seed,
                    "steps": steps,
                },
            },
            "8": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
            },
            "9": {
                "class_type": "SaveImage",
                "inputs": {"filename_prefix": "Hivemind", "images": ["8", 0]},
            },
        }
        provider_label = f"comfyui ({ckpt_to_use}, {active_mode})"

    want_face_detailer = (
        face_detailer_override
        if face_detailer_override is not None
        else getattr(config, "comfyui_face_detailer_enabled", True)
    )
    face_detector_model = face_detectors[0] if (want_face_detailer and face_detectors) else None

    if face_detector_model:
        active_face_ckpt = refiner_ckpt if use_hybrid else ckpt_to_use
        is_pony_face = "pony" in active_face_ckpt.lower()
        is_turbo_face = any(k in active_face_ckpt.lower() for k in ("turbo", "lightning", "hyper"))
        pos_face_prompt, neg_face_prompt = build_face_detailer_prompt(prompt, is_pony=is_pony_face)
        face_denoise = float(getattr(config, "comfyui_face_detailer_denoise", 0.36) or 0.36)
        face_steps = 6 if is_turbo_face else (8 if use_hybrid else 10)
        face_cfg = 2.0 if is_turbo_face else 5.0
        face_sampler = "dpmpp_sde" if is_turbo_face else "dpmpp_2m"
        configured_scale = float(getattr(config, "comfyui_face_detailer_scale", 1.25) or 1.25)
        scale_factor = min(configured_scale, 1.25) if (use_hybrid or (width * height) >= 700_000) else configured_scale

        vae_node_id = "11" if use_hybrid else "4"
        model_node_id = "11" if use_hybrid else "4"
        clip_node_id = "11" if use_hybrid else "10"
        clip_out_idx = 1 if use_hybrid else 0

        workflow_payload["20"] = {
            "class_type": "LoadMediaPipeFaceLandmarker",
            "inputs": {"model_name": face_detector_model},
        }
        workflow_payload["21"] = {
            "class_type": "ImageScaleBy",
            "inputs": {"image": ["8", 0], "upscale_method": "lanczos", "scale_by": scale_factor},
        }
        workflow_payload["22"] = {
            "class_type": "MediaPipeFaceLandmarker",
            "inputs": {
                "face_detection_model": ["20", 0],
                "image": ["21", 0],
                "detector_variant": "both",
                "num_faces": 1,
                "min_confidence": 0.30,
                "missing_frame_fallback": "empty",
            },
        }
        workflow_payload["23"] = {
            "class_type": "MediaPipeFaceMask",
            "inputs": {
                "face_landmarks": ["22", 0],
                "regions": "all",
            },
        }
        workflow_payload["24"] = {
            "class_type": "GrowMask",
            "inputs": {"mask": ["23", 0], "expand": 28, "tapered_corners": True},
        }
        workflow_payload["25"] = {
            "class_type": "FeatherMask",
            "inputs": {"mask": ["24", 0], "left": 20, "top": 20, "right": 20, "bottom": 20},
        }
        workflow_payload["26"] = {
            "class_type": "VAEEncode",
            "inputs": {"pixels": ["21", 0], "vae": [vae_node_id, 2]},
        }
        workflow_payload["27"] = {
            "class_type": "SetLatentNoiseMask",
            "inputs": {"samples": ["26", 0], "mask": ["25", 0]},
        }
        workflow_payload["28"] = {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": [clip_node_id, clip_out_idx], "text": pos_face_prompt},
        }
        workflow_payload["29"] = {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": [clip_node_id, clip_out_idx], "text": neg_face_prompt},
        }
        workflow_payload["30"] = {
            "class_type": "KSampler",
            "inputs": {
                "model": [model_node_id, 0],
                "seed": seed + 77,
                "steps": face_steps,
                "cfg": face_cfg,
                "sampler_name": face_sampler,
                "scheduler": "karras",
                "positive": ["28", 0],
                "negative": ["29", 0],
                "latent_image": ["27", 0],
                "denoise": face_denoise,
            },
        }
        workflow_payload["31"] = {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["30", 0], "vae": [vae_node_id, 2]},
        }
        # Point the single SaveImage node ("9") to the enhanced output ["31", 0] so only ONE image is produced
        workflow_payload["9"]["inputs"]["images"] = ["31", 0]
        provider_label = f"{provider_label} + InGraph FaceEnhance ({scale_factor}x)"

    t0 = time.perf_counter()
    logger.info(
        "🎨 COMFY→   | POST /prompt | mode=%s | ckpt=%s%s | face_detailer=%s | %dx%d | steps=%d | cfg=%.1f | sampler=%s/%s | seed=%d\n"
        "                    ├─ Positive: %s\n"
        "                    └─ Negative: %s",
        "action_hybrid" if use_action_hybrid else ("hybrid_refiner" if use_hybrid else active_mode),
        stage1_ckpt if use_hybrid else ckpt_to_use,
        f" → {stage2_ckpt}" if use_hybrid else "",
        "ON (in-graph)" if face_detector_model else "OFF",
        width,
        height,
        steps,
        cfg,
        sampler_name,
        scheduler_name,
        seed,
        prompt,
        neg_text,
    )
    logger.debug("🎨 COMFY→   | Full workflow graph JSON:\n%s", json.dumps(workflow_payload, indent=2))

    try:
        async with httpx.AsyncClient(timeout=240.0) as client:
            resp = await client.post(f"{base}/prompt", json={"prompt": workflow_payload})
            if resp.status_code != 200:
                logger.warning("⚠️ COMFY←   | POST /prompt failed with HTTP %d: %s", resp.status_code, resp.text[:200])
                return None, ""
            prompt_id = resp.json().get("prompt_id")
            if not prompt_id:
                logger.warning("⚠️ COMFY←   | POST /prompt returned no prompt_id")
                return None, ""

            logger.info("⏳ COMFY…   | Queued prompt_id=%s on %s (awaiting completion)", prompt_id, base)

            for _ in range(240):
                await asyncio.sleep(1.0)
                hist_resp = await client.get(f"{base}/history/{prompt_id}")
                if hist_resp.status_code == 200:
                    hist_data = hist_resp.json()
                    if prompt_id in hist_data:
                        outputs = hist_data[prompt_id].get("outputs", {})
                        logger.debug("✅ COMFY←   | Raw history outputs for %s: %s", prompt_id, outputs)
                        base_bytes, base_fname = await _fetch_comfy_node_image_bytes(client, base, outputs, "9")
                        if not base_bytes:
                            for node_id in outputs:
                                base_bytes, base_fname = await _fetch_comfy_node_image_bytes(
                                    client, base, outputs, node_id
                                )
                                if base_bytes:
                                    break
                        if base_bytes:
                            elapsed = time.perf_counter() - t0
                            logger.info(
                                "✅ COMFY←   | Completed prompt_id=%s in %.2fs | comfy_file=%r (%d KB)",
                                prompt_id,
                                elapsed,
                                base_fname,
                                len(base_bytes) // 1024,
                            )
                            return base_bytes, provider_label
    except Exception as exc:
        logger.warning("⚠️ COMFY←   | Exception during ComfyUI bridge: %s", exc)
    return None, ""


async def generate_image_asset(
    config: InferenceConfig,
    output_dir: Path,
    prompt: str,
    negative_prompt: str = "",
    width: int | None = None,
    height: int | None = None,
    steps: int | None = None,
    cfg: float | None = None,
    seed: int | None = None,
    render_mode_override: str | None = None,
    face_detailer_override: bool | None = None,
) -> dict[str, Any]:
    """
    Generates an image using the configured Apple Silicon Image Engine, writes it to output_dir,
    and returns metadata including the relative URL (`/media/generated/...`).
    """
    w = width or config.default_width
    h = height or config.default_height
    st = steps or config.default_steps
    guidance = cfg if cfg is not None else config.default_cfg
    actual_seed = seed if seed is not None else int.from_bytes(uuid.uuid4().bytes[:4], "big") % 1_000_000

    t_start = time.perf_counter()
    img_bytes: bytes | None = None
    provider_used = "procedural_art (Apple Silicon Instant Canvas)"

    logger.info(
        "🎨 IMAGE→   | provider=%s | %dx%d | steps=%d | cfg=%.1f | seed=%d",
        config.image_provider,
        w,
        h,
        st,
        guidance,
        actual_seed,
    )

    # 1. Try ComfyUI if configured or auto
    if config.image_provider in ("comfyui", "auto"):
        img_bytes, comfy_label = await _run_comfyui_bridge(
            config=config,
            prompt=prompt,
            negative_prompt=negative_prompt,
            width=w,
            height=h,
            steps=st,
            cfg=guidance,
            seed=actual_seed,
            render_mode_override=render_mode_override,
            face_detailer_override=face_detailer_override,
        )
        if img_bytes:
            provider_used = comfy_label or f"comfyui ({config.comfyui_checkpoint})"

    # 2. Try Native Apple Silicon PyTorch MPS Diffusers
    if img_bytes is None and config.image_provider in ("mps_diffusers", "auto"):
        allow_download = config.image_provider == "mps_diffusers"
        img_bytes = await asyncio.to_thread(
            _run_mps_diffusers_sync,
            config.mps_model_id,
            prompt,
            negative_prompt,
            w,
            h,
            st,
            guidance,
            actual_seed,
            config.mps_use_fp16,
            config.mps_attention_slicing,
            allow_download,
        )
        if img_bytes:
            provider_used = f"mps_diffusers ({config.mps_model_id} on Apple Metal MPS)"

    # 3. Fallback to Instant Procedural Concept Art Synthesizer
    if img_bytes is None:
        logger.warning(
            "⚠️ FALLBACK | Using procedural_art (%dx%d) — configured image_provider=%r did not produce an image",
            w,
            h,
            config.image_provider,
        )
        img_bytes = await asyncio.to_thread(
            _render_procedural_artwork,
            prompt,
            negative_prompt,
            w,
            h,
            actual_seed,
        )
        provider_used = "procedural_art (Apple Silicon Instant Canvas)"

    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"hm_{uuid.uuid4().hex[:12]}.png"
    file_path = output_dir / filename
    file_path.write_bytes(img_bytes)

    try:
        with Image.open(io.BytesIO(img_bytes)) as _im:
            w, h = _im.size
    except Exception:
        pass

    elapsed = time.perf_counter() - t_start
    logger.info(
        "⏱️ IMAGE←   | provider=%s | %dx%d | total=%.2fs",
        provider_used,
        w,
        h,
        elapsed,
    )

    return {
        "filename": filename,
        "url": f"/media/generated/{filename}",
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "width": w,
        "height": h,
        "steps": st,
        "cfg": guidance,
        "seed": actual_seed,
        "provider": provider_used,
        "duration_ms": round(elapsed * 1000, 1),
    }
