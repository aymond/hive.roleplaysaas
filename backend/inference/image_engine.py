from __future__ import annotations

import asyncio
import hashlib
import io
import math
import platform
import uuid
from pathlib import Path
from typing import Any

import httpx
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from ..models import InferenceConfig

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

    async with httpx.AsyncClient(timeout=2.0) as client:
        for url in candidates:
            try:
                resp = await client.get(f"{url}/system_stats")
                if resp.status_code == 200:
                    stats = resp.json()
                    checkpoints: list[str] = []
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
                    return {
                        "online": True,
                        "active_url": url,
                        "checkpoints": checkpoints,
                        "stats": stats,
                    }
            except Exception:
                continue
    return {"online": False, "active_url": base_url, "checkpoints": [], "stats": {}}


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
) -> tuple[bytes | None, str]:
    status = await check_comfyui_status(config.comfyui_base_url)
    if not status["online"]:
        return None, ""

    base = status.get("active_url", config.comfyui_base_url).rstrip("/")
    available_ckpts: list[str] = status.get("checkpoints", [])
    ckpt_to_use = config.comfyui_checkpoint
    if available_ckpts and ckpt_to_use not in available_ckpts:
        matched = next(
            (c for c in available_ckpts if ckpt_to_use.lower() in c.lower() or "sd_xl_base" in c.lower()),
            available_ckpts[0],
        )
        ckpt_to_use = matched

    active_mode = render_mode_override or getattr(config, "comfyui_render_mode", "hybrid_refiner")
    sampler_name = getattr(config, "comfyui_sampler", "dpmpp_2m_sde") or "dpmpp_2m_sde"
    scheduler_name = getattr(config, "comfyui_scheduler", "karras") or "karras"

    # Determine if we can run the 2-stage Hybrid Refiner (Pony/Base -> Artistic SDXL Refiner)
    refiner_ckpt = getattr(config, "comfyui_refiner_checkpoint", "sd_xl_base_1.0_0.9vae.safetensors")
    if available_ckpts and refiner_ckpt not in available_ckpts:
        refiner_match = next(
            (c for c in available_ckpts if "sd_xl_base" in c.lower() or "dreamshaper" in c.lower() or "juggernaut" in c.lower()),
            None,
        )
        if refiner_match:
            refiner_ckpt = refiner_match

    use_hybrid = (
        active_mode == "hybrid_refiner"
        and bool(refiner_ckpt)
        and refiner_ckpt != ckpt_to_use
        and (not available_ckpts or refiner_ckpt in available_ckpts)
    )

    is_pony_primary = "pony" in ckpt_to_use.lower()
    neg_text = (
        negative_prompt
        or "score_4, score_5, score_6, blurry, low quality, flat lighting, washed out, amateur snapshot, deformed, bad anatomy"
    )

    if use_hybrid:
        # Stage 1 (Uncensored Pose & Anatomy on Primary Model, e.g. CyberRealisticPony) ->
        # Stage 2 (Golden-Hour Painterly Aesthetic & Celebrity Facial Polish on Refiner Model, e.g. sd_xl_base_1.0)
        switch_ratio = max(0.35, min(0.85, float(getattr(config, "comfyui_refiner_switch", 0.65))))
        split_step = max(1, min(steps - 1, int(round(steps * switch_ratio))))
        # Strip Pony-only score tags for the non-Pony refiner CLIP so it focuses on artistic style & facial features
        refiner_prompt = (
            prompt.replace("score_9, score_8_up, score_7_up,", "")
            .replace("score_9, score_8_up, score_7_up", "")
            .strip()
        )
        refiner_prompt = (
            f"masterpiece stylized glamour digital art, warm golden hour sunset rim lighting, "
            f"luminous bronze and amber color grading, {refiner_prompt}"
        )

        workflow_payload: dict[str, Any] = {
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
                "class_type": "KSamplerAdvanced",
                "inputs": {
                    "add_noise": "enable",
                    "noise_seed": seed,
                    "steps": steps,
                    "cfg": cfg,
                    "sampler_name": sampler_name,
                    "scheduler": scheduler_name,
                    "positive": ["6", 0],
                    "negative": ["7", 0],
                    "latent_image": ["5", 0],
                    "start_at_step": 0,
                    "end_at_step": split_step,
                    "return_with_leftover_noise": "enable",
                    "model": ["4", 0],
                },
            },
            "11": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": refiner_ckpt},
            },
            "12": {
                "class_type": "CLIPTextEncode",
                "inputs": {"clip": ["11", 1], "text": refiner_prompt},
            },
            "13": {
                "class_type": "CLIPTextEncode",
                "inputs": {"clip": ["11", 1], "text": negative_prompt or "blurry, low quality, deformed"},
            },
            "14": {
                "class_type": "KSamplerAdvanced",
                "inputs": {
                    "add_noise": "disable",
                    "noise_seed": seed,
                    "steps": steps,
                    "cfg": cfg,
                    "sampler_name": sampler_name,
                    "scheduler": scheduler_name,
                    "positive": ["12", 0],
                    "negative": ["13", 0],
                    "latent_image": ["3", 0],
                    "start_at_step": split_step,
                    "end_at_step": steps,
                    "return_with_leftover_noise": "disable",
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
        provider_label = f"comfyui_hybrid ({ckpt_to_use} → {refiner_ckpt})"
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

    try:
        async with httpx.AsyncClient(timeout=240.0) as client:
            resp = await client.post(f"{base}/prompt", json={"prompt": workflow_payload})
            if resp.status_code != 200:
                return None, ""
            prompt_id = resp.json().get("prompt_id")
            if not prompt_id:
                return None, ""

            for _ in range(240):
                await asyncio.sleep(1.0)
                hist_resp = await client.get(f"{base}/history/{prompt_id}")
                if hist_resp.status_code == 200:
                    hist_data = hist_resp.json()
                    if prompt_id in hist_data:
                        outputs = hist_data[prompt_id].get("outputs", {})
                        for node_out in outputs.values():
                            images = node_out.get("images", [])
                            if images:
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
                                    return view_resp.content, provider_label
    except Exception:
        pass
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

    img_bytes: bytes | None = None
    provider_used = "procedural_art (Apple Silicon Instant Canvas)"

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
    }
