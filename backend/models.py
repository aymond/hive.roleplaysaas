from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4
from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:10]}"


class CharacterCard(BaseModel):
    id: str = Field(default_factory=lambda: new_id("char"))
    name: str
    title: str = ""
    description: str = ""
    personality: str = ""
    scenario: str = ""
    first_mes: str = ""
    mes_example: str = ""
    system_prompt: str = ""
    post_history_instructions: str = ""
    creator_notes: str = ""
    tags: list[str] = Field(default_factory=list)
    visual_prompt_tags: str = ""
    negative_prompt_tags: str = "blurry, low quality, deformed, watermark"
    avatar_url: str = ""
    world_id: str | None = None
    default_workflow_id: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class LoreEntry(BaseModel):
    id: str = Field(default_factory=lambda: new_id("lore"))
    title: str
    keys: list[str] = Field(default_factory=list)
    secondary_keys: list[str] = Field(default_factory=list)
    category: Literal[
        "location",
        "faction",
        "magic_tech",
        "history",
        "artifact",
        "relationship",
        "rule",
    ] = "location"
    content: str
    visual_description: str = ""
    image_url: str = ""
    map_x: float | None = None
    map_y: float | None = None
    constant: bool = False
    enabled: bool = True
    priority: int = 50


class Lorebook(BaseModel):
    id: str = Field(default_factory=lambda: new_id("world"))
    name: str
    subtitle: str = ""
    description: str = ""
    aesthetic_style: str = "cinematic concept art, intricate lighting, rich atmosphere, 8k"
    map_image_url: str = ""
    map_prompt: str = ""
    entries: list[LoreEntry] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class TriggeredLoreInfo(BaseModel):
    entry_id: str
    title: str
    category: str
    matched_keys: list[str]
    snippet: str
    visual_description: str = ""


class ChatMessage(BaseModel):
    id: str = Field(default_factory=lambda: new_id("msg"))
    role: Literal["user", "assistant", "system"]
    sender_name: str
    content: str
    swipes: list[str] = Field(default_factory=list)
    active_swipe: int = 0
    image_url: str | None = None
    image_prompt: str | None = None
    image_seed: int | None = None
    image_metadata_url: str | None = None
    triggered_lore: list[TriggeredLoreInfo] = Field(default_factory=list)
    timings: dict[str, Any] | None = None
    created_at: str = Field(default_factory=utc_now_iso)


class SceneState(BaseModel):
    location: str = ""
    time_and_lighting: str = ""
    weather: str = ""
    atmosphere: str = ""
    attire: str = ""
    hairstyle: str = ""
    makeup: str = ""
    skin_and_condition: str = ""
    pose_and_action: str = ""
    pinned_fields: list[str] = Field(default_factory=list)


class ChatSession(BaseModel):
    id: str = Field(default_factory=lambda: new_id("chat"))
    title: str
    character_id: str
    world_id: str | None = None
    user_persona_name: str = "Traveler"
    user_persona_desc: str = "An observant wanderer exploring the realm."
    messages: list[ChatMessage] = Field(default_factory=list)
    situation_checkpoint: str = ""
    checkpoint_msg_count: int = 0
    scene_state: SceneState = Field(default_factory=SceneState)
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


NodeType = Literal[
    "character_source",
    "lore_injector",
    "prompt_template",
    "llm_generator",
    "image_generator",
    "image_preview",
]


class WorkflowNode(BaseModel):
    id: str
    type: NodeType
    position: dict[str, float] = Field(default_factory=lambda: {"x": 0.0, "y": 0.0})
    data: dict[str, Any] = Field(default_factory=dict)


class WorkflowEdge(BaseModel):
    id: str
    source: str
    target: str
    sourceHandle: str | None = None
    targetHandle: str | None = None


class WorkflowGraph(BaseModel):
    id: str = Field(default_factory=lambda: new_id("wf"))
    name: str
    description: str = ""
    category: str = "Character & Scene"
    nodes: list[WorkflowNode] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class NodeExecutionTrace(BaseModel):
    node_id: str
    node_type: NodeType
    status: Literal["completed", "error"] = "completed"
    duration_ms: float = 0.0
    outputs: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class WorkflowExecutionResult(BaseModel):
    workflow_id: str
    status: Literal["completed", "error"] = "completed"
    total_duration_ms: float = 0.0
    node_traces: dict[str, NodeExecutionTrace] = Field(default_factory=dict)
    generated_images: list[str] = Field(default_factory=list)
    final_text: str = ""


class InferenceConfig(BaseModel):
    log_level: Literal["INFO", "DEBUG"] = "INFO"
    llm_provider: Literal["auto", "ollama", "openai_compat", "builtin_synth"] = "auto"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2:latest"
    prompt_refiner_model: str = "llama3.2:latest"
    openai_base_url: str = "http://127.0.0.1:1234/v1"
    openai_api_key: str = "lm-studio"
    openai_model: str = "local-model"
    temperature: float = 0.75
    max_tokens: int = 512

    image_provider: Literal["auto", "mps_diffusers", "comfyui", "procedural_art"] = "auto"
    mps_model_id: str = "segmind/tiny-sd"
    mps_use_fp16: bool = True
    mps_attention_slicing: bool = True
    comfyui_base_url: str = "http://127.0.0.1:8188"
    comfyui_checkpoint: str = "CyberRealisticPony_V18.0_F16.safetensors"
    comfyui_render_mode: Literal[
        "hybrid_refiner",
        "single_stylized",
        "single_raw",
        "action_hybrid",
    ] = "action_hybrid"
    comfyui_refiner_checkpoint: str = "sd_xl_base_1.0_0.9vae.safetensors"
    comfyui_landscape_checkpoint: str = "Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors"
    comfyui_refiner_switch: float = 0.65
    comfyui_face_detailer_enabled: bool = True
    comfyui_face_detailer_model: str = "same"
    comfyui_face_detailer_denoise: float = 0.36
    comfyui_face_detailer_scale: float = 1.25
    comfyui_sampler: str = "dpmpp_2m"
    comfyui_scheduler: str = "karras"
    default_width: int = 768
    default_height: int = 1024
    default_steps: int = 20
    default_cfg: float = 6.0


class GalleryAsset(BaseModel):
    id: str = Field(default_factory=lambda: new_id("img"))
    url: str
    prompt: str
    negative_prompt: str = ""
    provider: str
    width: int = 512
    height: int = 512
    seed: int = 42
    metadata_url: str | None = None
    character_id: str | None = None
    world_id: str | None = None
    location_entry_id: str | None = None
    workflow_id: str | None = None
    duration_ms: float | None = None
    created_at: str = Field(default_factory=utc_now_iso)
