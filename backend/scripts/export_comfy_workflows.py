"""Export Hivemind's 4 ComfyUI render pipelines as native ComfyUI UI-format JSON workflows."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


class ComfyUIWorkflowBuilder:
    """Builds LiteGraph / ComfyUI UI-format workflow JSON with automatic link wiring."""

    def __init__(self) -> None:
        self.nodes: list[dict[str, Any]] = []
        self.links: list[list[Any]] = []
        self._node_seq = 0
        self._link_seq = 0
        self._by_id: dict[int, dict[str, Any]] = {}

    def add_node(
        self,
        node_type: str,
        pos: tuple[int, int],
        size: tuple[int, int],
        inputs: list[tuple[str, str]],
        outputs: list[tuple[str, str]],
        widgets_values: list[Any],
        title: str | None = None,
    ) -> int:
        self._node_seq += 1
        nid = self._node_seq
        node: dict[str, Any] = {
            "id": nid,
            "type": node_type,
            "pos": [pos[0], pos[1]],
            "size": [size[0], size[1]],
            "flags": {},
            "order": nid - 1,
            "mode": 0,
            "inputs": [{"name": name, "type": typ, "link": None} for name, typ in inputs],
            "outputs": [
                {"name": name, "type": typ, "links": [], "slot_index": idx}
                for idx, (name, typ) in enumerate(outputs)
            ],
            "properties": {"Node name for S&R": node_type},
            "widgets_values": widgets_values,
        }
        if title:
            node["title"] = title
        self.nodes.append(node)
        self._by_id[nid] = node
        return nid

    def connect(self, src_id: int, src_slot: int, dst_id: int, dst_slot: int) -> None:
        self._link_seq += 1
        lid = self._link_seq
        src = self._by_id[src_id]
        dst = self._by_id[dst_id]
        typ = src["outputs"][src_slot]["type"]
        src["outputs"][src_slot]["links"].append(lid)
        dst["inputs"][dst_slot]["link"] = lid
        self.links.append([lid, src_id, src_slot, dst_id, dst_slot, typ])

    def build(self) -> dict[str, Any]:
        return {
            "last_node_id": self._node_seq,
            "last_link_id": self._link_seq,
            "nodes": self.nodes,
            "links": self.links,
            "groups": [],
            "config": {},
            "extra": {"ds": {"scale": 0.85, "offset": [40, 40]}},
            "version": 0.4,
        }


def _add_face_detailer_stage(
    b: ComfyUIWorkflowBuilder,
    x_offset: int,
    image_src: tuple[int, int],
    model_src: tuple[int, int],
    clip_src: tuple[int, int],
    vae_src: tuple[int, int],
    scale_factor: float,
    face_steps: int,
    face_cfg: float,
    face_sampler: str,
    face_denoise: float,
    pos_face_prompt: str,
    neg_face_prompt: str,
) -> tuple[int, int]:
    scale = b.add_node(
        "ImageScaleBy",
        (x_offset, 80),
        (260, 82),
        [("image", "IMAGE")],
        [("IMAGE", "IMAGE")],
        ["lanczos", scale_factor],
    )
    b.connect(image_src[0], image_src[1], scale, 0)

    loader = b.add_node(
        "LoadMediaPipeFaceLandmarker",
        (x_offset, 220),
        (290, 58),
        [],
        [("FACE_DETECTION_MODEL", "FACE_DETECTION_MODEL")],
        ["mediapipe_face_fp32.safetensors"],
    )
    landmarker = b.add_node(
        "MediaPipeFaceLandmarker",
        (x_offset + 340, 140),
        (300, 150),
        [("face_detection_model", "FACE_DETECTION_MODEL"), ("image", "IMAGE")],
        [("FACE_LANDMARKS", "FACE_LANDMARKS")],
        ["both", 1, 0.30, "empty"],
    )
    b.connect(loader, 0, landmarker, 0)
    b.connect(scale, 0, landmarker, 1)

    mask = b.add_node(
        "MediaPipeFaceMask",
        (x_offset + 680, 140),
        (240, 82),
        [("face_landmarks", "FACE_LANDMARKS")],
        [("MASK", "MASK")],
        ["all"],
    )
    b.connect(landmarker, 0, mask, 0)

    grow = b.add_node(
        "GrowMask",
        (x_offset + 680, 270),
        (240, 82),
        [("mask", "MASK")],
        [("MASK", "MASK")],
        [28, True],
    )
    b.connect(mask, 0, grow, 0)

    feather = b.add_node(
        "FeatherMask",
        (x_offset + 680, 400),
        (240, 130),
        [("mask", "MASK")],
        [("MASK", "MASK")],
        [20, 20, 20, 20],
    )
    b.connect(grow, 0, feather, 0)

    vae_enc = b.add_node(
        "VAEEncode",
        (x_offset + 960, 80),
        (210, 46),
        [("pixels", "IMAGE"), ("vae", "VAE")],
        [("LATENT", "LATENT")],
        [],
    )
    b.connect(scale, 0, vae_enc, 0)
    b.connect(vae_src[0], vae_src[1], vae_enc, 1)

    noise_mask = b.add_node(
        "SetLatentNoiseMask",
        (x_offset + 960, 180),
        (230, 46),
        [("samples", "LATENT"), ("mask", "MASK")],
        [("LATENT", "LATENT")],
        [],
    )
    b.connect(vae_enc, 0, noise_mask, 0)
    b.connect(feather, 0, noise_mask, 1)

    pos_enc = b.add_node(
        "CLIPTextEncode",
        (x_offset + 960, 280),
        (320, 110),
        [("clip", "CLIP")],
        [("CONDITIONING", "CONDITIONING")],
        [pos_face_prompt],
        title="Face Detailer Positive",
    )
    neg_enc = b.add_node(
        "CLIPTextEncode",
        (x_offset + 960, 430),
        (320, 110),
        [("clip", "CLIP")],
        [("CONDITIONING", "CONDITIONING")],
        [neg_face_prompt],
        title="Face Detailer Negative",
    )
    b.connect(clip_src[0], clip_src[1], pos_enc, 0)
    b.connect(clip_src[0], clip_src[1], neg_enc, 0)

    ksampler = b.add_node(
        "KSampler",
        (x_offset + 1320, 140),
        (315, 262),
        [
            ("model", "MODEL"),
            ("positive", "CONDITIONING"),
            ("negative", "CONDITIONING"),
            ("latent_image", "LATENT"),
        ],
        [("LATENT", "LATENT")],
        [4277, "randomize", face_steps, face_cfg, face_sampler, "karras", face_denoise],
        title="FaceDetailer KSampler",
    )
    b.connect(model_src[0], model_src[1], ksampler, 0)
    b.connect(pos_enc, 0, ksampler, 1)
    b.connect(neg_enc, 0, ksampler, 2)
    b.connect(noise_mask, 0, ksampler, 3)

    vae_dec = b.add_node(
        "VAEDecode",
        (x_offset + 1680, 140),
        (210, 46),
        [("samples", "LATENT"), ("vae", "VAE")],
        [("IMAGE", "IMAGE")],
        [],
    )
    b.connect(ksampler, 0, vae_dec, 0)
    b.connect(vae_src[0], vae_src[1], vae_dec, 1)
    return vae_dec, 0


def build_single_base() -> dict[str, Any]:
    b = ComfyUIWorkflowBuilder()
    ckpt = b.add_node(
        "CheckpointLoaderSimple",
        (40, 140),
        (330, 98),
        [],
        [("MODEL", "MODEL"), ("CLIP", "CLIP"), ("VAE", "VAE")],
        ["CyberRealisticPony_V18.0_F16.safetensors"],
    )
    clip_skip = b.add_node(
        "CLIPSetLastLayer",
        (420, 260),
        (260, 58),
        [("clip", "CLIP")],
        [("CLIP", "CLIP")],
        [-2],
    )
    b.connect(ckpt, 1, clip_skip, 0)

    latent = b.add_node(
        "EmptyLatentImage",
        (420, 60),
        (260, 106),
        [],
        [("LATENT", "LATENT")],
        [512, 768, 1],
    )
    pos = b.add_node(
        "CLIPTextEncode",
        (730, 180),
        (340, 120),
        [("clip", "CLIP")],
        [("CONDITIONING", "CONDITIONING")],
        ["score_9, score_8_up, score_7_up, masterpiece, stylized glamour digital art, 1girl, solo, warm golden hour"],
        title="Positive Prompt",
    )
    neg = b.add_node(
        "CLIPTextEncode",
        (730, 340),
        (340, 120),
        [("clip", "CLIP")],
        [("CONDITIONING", "CONDITIONING")],
        ["score_4, score_5, score_6, blurry, low quality, deformed, bad anatomy, 2girls, multiple girls"],
        title="Negative Prompt",
    )
    b.connect(clip_skip, 0, pos, 0)
    b.connect(clip_skip, 0, neg, 0)

    sampler = b.add_node(
        "KSampler",
        (1120, 120),
        (315, 262),
        [("model", "MODEL"), ("positive", "CONDITIONING"), ("negative", "CONDITIONING"), ("latent_image", "LATENT")],
        [("LATENT", "LATENT")],
        [4200, "randomize", 20, 6.0, "dpmpp_2m", "karras", 1.0],
    )
    b.connect(ckpt, 0, sampler, 0)
    b.connect(pos, 0, sampler, 1)
    b.connect(neg, 0, sampler, 2)
    b.connect(latent, 0, sampler, 3)

    dec = b.add_node(
        "VAEDecode",
        (1480, 120),
        (210, 46),
        [("samples", "LATENT"), ("vae", "VAE")],
        [("IMAGE", "IMAGE")],
        [],
    )
    b.connect(sampler, 0, dec, 0)
    b.connect(ckpt, 2, dec, 1)

    save = b.add_node(
        "SaveImage",
        (1740, 120),
        (280, 270),
        [("images", "IMAGE")],
        [],
        ["Hivemind_Single"],
    )
    b.connect(dec, 0, save, 0)
    return b.build()


def build_single_with_facedetailer() -> dict[str, Any]:
    b = ComfyUIWorkflowBuilder()
    ckpt = b.add_node(
        "CheckpointLoaderSimple",
        (40, 140),
        (330, 98),
        [],
        [("MODEL", "MODEL"), ("CLIP", "CLIP"), ("VAE", "VAE")],
        ["CyberRealisticPony_V18.0_F16.safetensors"],
    )
    clip_skip = b.add_node(
        "CLIPSetLastLayer",
        (420, 260),
        (260, 58),
        [("clip", "CLIP")],
        [("CLIP", "CLIP")],
        [-2],
    )
    b.connect(ckpt, 1, clip_skip, 0)

    latent = b.add_node(
        "EmptyLatentImage",
        (420, 60),
        (260, 106),
        [],
        [("LATENT", "LATENT")],
        [512, 768, 1],
    )
    pos = b.add_node(
        "CLIPTextEncode",
        (730, 180),
        (340, 120),
        [("clip", "CLIP")],
        [("CONDITIONING", "CONDITIONING")],
        ["score_9, score_8_up, score_7_up, masterpiece, stylized glamour digital art, 1girl, solo, warm golden hour"],
        title="Positive Prompt",
    )
    neg = b.add_node(
        "CLIPTextEncode",
        (730, 340),
        (340, 120),
        [("clip", "CLIP")],
        [("CONDITIONING", "CONDITIONING")],
        ["score_4, score_5, score_6, blurry, low quality, deformed, bad anatomy, 2girls, multiple girls"],
        title="Negative Prompt",
    )
    b.connect(clip_skip, 0, pos, 0)
    b.connect(clip_skip, 0, neg, 0)

    sampler = b.add_node(
        "KSampler",
        (1120, 120),
        (315, 262),
        [("model", "MODEL"), ("positive", "CONDITIONING"), ("negative", "CONDITIONING"), ("latent_image", "LATENT")],
        [("LATENT", "LATENT")],
        [4200, "randomize", 20, 6.0, "dpmpp_2m", "karras", 1.0],
    )
    b.connect(ckpt, 0, sampler, 0)
    b.connect(pos, 0, sampler, 1)
    b.connect(neg, 0, sampler, 2)
    b.connect(latent, 0, sampler, 3)

    dec = b.add_node(
        "VAEDecode",
        (1480, 120),
        (210, 46),
        [("samples", "LATENT"), ("vae", "VAE")],
        [("IMAGE", "IMAGE")],
        [],
    )
    b.connect(sampler, 0, dec, 0)
    b.connect(ckpt, 2, dec, 1)

    face_img = _add_face_detailer_stage(
        b=b,
        x_offset=1750,
        image_src=(dec, 0),
        model_src=(ckpt, 0),
        clip_src=(clip_skip, 0),
        vae_src=(ckpt, 2),
        scale_factor=1.5,
        face_steps=10,
        face_cfg=5.0,
        face_sampler="dpmpp_2m",
        face_denoise=0.36,
        pos_face_prompt="score_9, score_8_up, score_7_up, detailed face, symmetrical eyes, intricate iris, natural skin texture",
        neg_face_prompt="score_4, score_5, score_6, blurry, asymmetrical eyes, deformed face",
    )

    save = b.add_node(
        "SaveImage",
        (3680, 140),
        (280, 270),
        [("images", "IMAGE")],
        [],
        ["Hivemind_Single_FaceDetailer"],
    )
    b.connect(face_img[0], face_img[1], save, 0)
    return b.build()


def _build_hybrid_with_facedetailer(
    stage1_ckpt: str,
    stage1_clip_layer: int,
    stage1_steps: int,
    stage2_ckpt: str,
    stage2_clip_layer: int,
    stage2_steps: int,
    stage2_cfg: float,
    stage2_denoise: float,
    face_steps: int,
    face_cfg: float,
    face_sampler: str,
    save_prefix: str,
) -> dict[str, Any]:
    b = ComfyUIWorkflowBuilder()
    ckpt1 = b.add_node(
        "CheckpointLoaderSimple",
        (40, 140),
        (330, 98),
        [],
        [("MODEL", "MODEL"), ("CLIP", "CLIP"), ("VAE", "VAE")],
        [stage1_ckpt],
        title="Stage 1 Base Checkpoint",
    )
    clip1 = b.add_node(
        "CLIPSetLastLayer",
        (420, 260),
        (260, 58),
        [("clip", "CLIP")],
        [("CLIP", "CLIP")],
        [stage1_clip_layer],
    )
    b.connect(ckpt1, 1, clip1, 0)

    latent = b.add_node(
        "EmptyLatentImage",
        (420, 60),
        (260, 106),
        [],
        [("LATENT", "LATENT")],
        [512, 768, 1],
    )
    pos1 = b.add_node(
        "CLIPTextEncode",
        (730, 180),
        (320, 110),
        [("clip", "CLIP")],
        [("CONDITIONING", "CONDITIONING")],
        ["masterpiece, photorealistic, 8k, 1girl, solo, dynamic action shot, mid-motion"],
        title="Stage 1 Positive",
    )
    neg1 = b.add_node(
        "CLIPTextEncode",
        (730, 330),
        (320, 110),
        [("clip", "CLIP")],
        [("CONDITIONING", "CONDITIONING")],
        ["blurry, low quality, deformed, bad anatomy, 2girls, multiple girls"],
        title="Stage 1 Negative",
    )
    b.connect(clip1, 0, pos1, 0)
    b.connect(clip1, 0, neg1, 0)

    samp1 = b.add_node(
        "KSampler",
        (1100, 120),
        (315, 262),
        [("model", "MODEL"), ("positive", "CONDITIONING"), ("negative", "CONDITIONING"), ("latent_image", "LATENT")],
        [("LATENT", "LATENT")],
        [4200, "randomize", stage1_steps, 5.5, "dpmpp_2m", "karras", 1.0],
        title="Stage 1 KSampler",
    )
    b.connect(ckpt1, 0, samp1, 0)
    b.connect(pos1, 0, samp1, 1)
    b.connect(neg1, 0, samp1, 2)
    b.connect(latent, 0, samp1, 3)

    dec1 = b.add_node(
        "VAEDecode",
        (1460, 120),
        (210, 46),
        [("samples", "LATENT"), ("vae", "VAE")],
        [("IMAGE", "IMAGE")],
        [],
    )
    b.connect(samp1, 0, dec1, 0)
    b.connect(ckpt1, 2, dec1, 1)

    ckpt2 = b.add_node(
        "CheckpointLoaderSimple",
        (1460, 260),
        (330, 98),
        [],
        [("MODEL", "MODEL"), ("CLIP", "CLIP"), ("VAE", "VAE")],
        [stage2_ckpt],
        title="Stage 2 Refiner Checkpoint",
    )
    clip2 = b.add_node(
        "CLIPSetLastLayer",
        (1840, 340),
        (260, 58),
        [("clip", "CLIP")],
        [("CLIP", "CLIP")],
        [stage2_clip_layer],
    )
    b.connect(ckpt2, 1, clip2, 0)

    enc2 = b.add_node(
        "VAEEncode",
        (1840, 120),
        (210, 46),
        [("pixels", "IMAGE"), ("vae", "VAE")],
        [("LATENT", "LATENT")],
        [],
    )
    b.connect(dec1, 0, enc2, 0)
    b.connect(ckpt2, 2, enc2, 1)

    pos2 = b.add_node(
        "CLIPTextEncode",
        (2140, 220),
        (320, 110),
        [("clip", "CLIP")],
        [("CONDITIONING", "CONDITIONING")],
        ["score_9, score_8_up, score_7_up, masterpiece, photorealistic, 8k, 1girl, solo, dynamic action shot, mid-motion"],
        title="Stage 2 Positive",
    )
    neg2 = b.add_node(
        "CLIPTextEncode",
        (2140, 370),
        (320, 110),
        [("clip", "CLIP")],
        [("CONDITIONING", "CONDITIONING")],
        ["score_4, score_5, score_6, blurry, low quality, deformed, bad anatomy, 2girls"],
        title="Stage 2 Negative",
    )
    b.connect(clip2, 0, pos2, 0)
    b.connect(clip2, 0, neg2, 0)

    samp2 = b.add_node(
        "KSampler",
        (2510, 120),
        (315, 262),
        [("model", "MODEL"), ("positive", "CONDITIONING"), ("negative", "CONDITIONING"), ("latent_image", "LATENT")],
        [("LATENT", "LATENT")],
        [4201, "randomize", stage2_steps, stage2_cfg, "dpmpp_2m", "karras", stage2_denoise],
        title="Stage 2 Refine KSampler",
    )
    b.connect(ckpt2, 0, samp2, 0)
    b.connect(pos2, 0, samp2, 1)
    b.connect(neg2, 0, samp2, 2)
    b.connect(enc2, 0, samp2, 3)

    dec2 = b.add_node(
        "VAEDecode",
        (2870, 120),
        (210, 46),
        [("samples", "LATENT"), ("vae", "VAE")],
        [("IMAGE", "IMAGE")],
        [],
    )
    b.connect(samp2, 0, dec2, 0)
    b.connect(ckpt2, 2, dec2, 1)

    face_img = _add_face_detailer_stage(
        b=b,
        x_offset=3140,
        image_src=(dec2, 0),
        model_src=(ckpt2, 0),
        clip_src=(ckpt2, 1),
        vae_src=(ckpt2, 2),
        scale_factor=1.25,
        face_steps=face_steps,
        face_cfg=face_cfg,
        face_sampler=face_sampler,
        face_denoise=0.36,
        pos_face_prompt="detailed face, symmetrical eyes, intricate iris, natural skin texture",
        neg_face_prompt="blurry, asymmetrical eyes, deformed face",
    )

    save = b.add_node(
        "SaveImage",
        (5070, 140),
        (280, 270),
        [("images", "IMAGE")],
        [],
        [save_prefix],
    )
    b.connect(face_img[0], face_img[1], save, 0)
    return b.build()


def build_world_map() -> dict[str, Any]:
    b = ComfyUIWorkflowBuilder()
    ckpt = b.add_node(
        "CheckpointLoaderSimple",
        (40, 140),
        (330, 98),
        [],
        [("MODEL", "MODEL"), ("CLIP", "CLIP"), ("VAE", "VAE")],
        ["Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors"],
    )
    clip_skip = b.add_node(
        "CLIPSetLastLayer",
        (420, 260),
        (260, 58),
        [("clip", "CLIP")],
        [("CLIP", "CLIP")],
        [-1],
    )
    b.connect(ckpt, 1, clip_skip, 0)

    latent = b.add_node(
        "EmptyLatentImage",
        (420, 60),
        (260, 106),
        [],
        [("LATENT", "LATENT")],
        [1024, 768, 1],
    )
    pos = b.add_node(
        "CLIPTextEncode",
        (730, 180),
        (340, 120),
        [("clip", "CLIP")],
        [("CONDITIONING", "CONDITIONING")],
        [
            "top-down aerial resort map, realistic architectural masterplan site view, "
            "private garden villa surrounded by large hedge garden and green grass, "
            "private teakwood cabana overlooking warm turquoise lagoon, "
            "beachside resort tropical cove with private oceanfront cabanas, sunset infinity pools, "
            "clean pathways, palm trees, realistic lighting, compass rose"
        ],
        title="World Map Positive Prompt",
    )
    neg = b.add_node(
        "CLIPTextEncode",
        (730, 340),
        (340, 120),
        [("clip", "CLIP")],
        [("CONDITIONING", "CONDITIONING")],
        [
            "horizon, sky, eye-level view, street level, ground level, person, woman, man, people, "
            "portrait, close-up face, text, letters, words, watermark, cartoon, anime, sketch, "
            "blurry, low quality, deformed"
        ],
        title="World Map Negative Prompt",
    )
    b.connect(clip_skip, 0, pos, 0)
    b.connect(clip_skip, 0, neg, 0)

    sampler = b.add_node(
        "KSampler",
        (1120, 120),
        (315, 262),
        [("model", "MODEL"), ("positive", "CONDITIONING"), ("negative", "CONDITIONING"), ("latent_image", "LATENT")],
        [("LATENT", "LATENT")],
        [4200, "randomize", 22, 5.5, "dpmpp_2m", "karras", 1.0],
    )
    b.connect(ckpt, 0, sampler, 0)
    b.connect(pos, 0, sampler, 1)
    b.connect(neg, 0, sampler, 2)
    b.connect(latent, 0, sampler, 3)

    dec = b.add_node(
        "VAEDecode",
        (1480, 120),
        (210, 46),
        [("samples", "LATENT"), ("vae", "VAE")],
        [("IMAGE", "IMAGE")],
        [],
    )
    b.connect(sampler, 0, dec, 0)
    b.connect(ckpt, 2, dec, 1)

    save = b.add_node(
        "SaveImage",
        (1740, 120),
        (280, 270),
        [("images", "IMAGE")],
        [],
        ["Hivemind_WorldMap"],
    )
    b.connect(dec, 0, save, 0)
    return b.build()


def build_location_scene() -> dict[str, Any]:
    b = ComfyUIWorkflowBuilder()
    ckpt = b.add_node(
        "CheckpointLoaderSimple",
        (40, 140),
        (330, 98),
        [],
        [("MODEL", "MODEL"), ("CLIP", "CLIP"), ("VAE", "VAE")],
        ["Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors"],
    )
    clip_skip = b.add_node(
        "CLIPSetLastLayer",
        (420, 260),
        (260, 58),
        [("clip", "CLIP")],
        [("CLIP", "CLIP")],
        [-1],
    )
    b.connect(ckpt, 1, clip_skip, 0)

    latent = b.add_node(
        "EmptyLatentImage",
        (420, 60),
        (260, 106),
        [],
        [("LATENT", "LATENT")],
        [1024, 768, 1],
    )
    pos = b.add_node(
        "CLIPTextEncode",
        (730, 180),
        (340, 120),
        [("clip", "CLIP")],
        [("CONDITIONING", "CONDITIONING")],
        [
            "The Luxury Garden Villa, A private garden villa, surrounded by a large hedge garden, green well maintained grass, "
            "warm golden hour beachside resort, architectural environment scene, wide angle, high detail"
        ],
        title="Location Positive Prompt",
    )
    neg = b.add_node(
        "CLIPTextEncode",
        (730, 340),
        (340, 120),
        [("clip", "CLIP")],
        [("CONDITIONING", "CONDITIONING")],
        ["person, woman, man, people, portrait, close-up face, crowd, text, watermark, blurry, low quality, deformed"],
        title="Location Negative Prompt",
    )
    b.connect(clip_skip, 0, pos, 0)
    b.connect(clip_skip, 0, neg, 0)

    sampler = b.add_node(
        "KSampler",
        (1120, 120),
        (315, 262),
        [("model", "MODEL"), ("positive", "CONDITIONING"), ("negative", "CONDITIONING"), ("latent_image", "LATENT")],
        [("LATENT", "LATENT")],
        [4200, "randomize", 22, 5.5, "dpmpp_2m", "karras", 1.0],
    )
    b.connect(ckpt, 0, sampler, 0)
    b.connect(pos, 0, sampler, 1)
    b.connect(neg, 0, sampler, 2)
    b.connect(latent, 0, sampler, 3)

    dec = b.add_node(
        "VAEDecode",
        (1480, 120),
        (210, 46),
        [("samples", "LATENT"), ("vae", "VAE")],
        [("IMAGE", "IMAGE")],
        [],
    )
    b.connect(sampler, 0, dec, 0)
    b.connect(ckpt, 2, dec, 1)

    save = b.add_node(
        "SaveImage",
        (1740, 120),
        (280, 270),
        [("images", "IMAGE")],
        [],
        ["Hivemind_Location"],
    )
    b.connect(dec, 0, save, 0)
    return b.build()


def get_all_workflows() -> dict[str, dict[str, Any]]:
    return {
        "Hivemind_1_Single_Base.json": build_single_base(),
        "Hivemind_2_Single_FaceDetailer.json": build_single_with_facedetailer(),
        "Hivemind_3_Action_Hybrid_FaceDetailer.json": _build_hybrid_with_facedetailer(
            stage1_ckpt="Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors",
            stage1_clip_layer=-1,
            stage1_steps=12,
            stage2_ckpt="CyberRealisticPony_V18.0_F16.safetensors",
            stage2_clip_layer=-2,
            stage2_steps=10,
            stage2_cfg=5.5,
            stage2_denoise=0.40,
            face_steps=8,
            face_cfg=5.0,
            face_sampler="dpmpp_2m",
            save_prefix="Hivemind_ActionHybrid",
        ),
        "Hivemind_4_Hybrid_Refiner_FaceDetailer.json": _build_hybrid_with_facedetailer(
            stage1_ckpt="CyberRealisticPony_V18.0_F16.safetensors",
            stage1_clip_layer=-2,
            stage1_steps=16,
            stage2_ckpt="DreamShaperXL_Turbo_v2_1.safetensors",
            stage2_clip_layer=-1,
            stage2_steps=14,
            stage2_cfg=5.0,
            stage2_denoise=0.36,
            face_steps=6,
            face_cfg=2.0,
            face_sampler="dpmpp_sde",
            save_prefix="Hivemind_HybridRefiner",
        ),
        "Hivemind_5_World_Map.json": build_world_map(),
        "Hivemind_6_Location_Scene.json": build_location_scene(),
    }


def main() -> None:
    target_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/Users/aymondelbridge/ComfyUI/user/default/workflows")
    target_dir.mkdir(parents=True, exist_ok=True)
    workflows = get_all_workflows()
    for filename, payload in workflows.items():
        out_path = target_dir / filename
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote {out_path} ({len(payload['nodes'])} nodes, {len(payload['links'])} links)")


if __name__ == "__main__":
    main()
