from __future__ import annotations

import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from .inference.image_engine import generate_image_asset
from .inference.llm_engine import generate_node_text
from .lore_engine import scan_lorebook
from .models import (
    CharacterCard,
    GalleryAsset,
    InferenceConfig,
    Lorebook,
    NodeExecutionTrace,
    WorkflowExecutionResult,
    WorkflowGraph,
    WorkflowNode,
)


def topological_sort_nodes(workflow: WorkflowGraph) -> list[WorkflowNode]:
    node_map = {n.id: n for n in workflow.nodes}
    in_degree: dict[str, int] = {n.id: 0 for n in workflow.nodes}
    adj: dict[str, list[str]] = defaultdict(list)

    for edge in workflow.edges:
        if edge.source in node_map and edge.target in node_map:
            adj[edge.source].append(edge.target)
            in_degree[edge.target] += 1

    queue = deque([nid for nid, deg in in_degree.items() if deg == 0])
    ordered: list[WorkflowNode] = []

    while queue:
        curr = queue.popleft()
        ordered.append(node_map[curr])
        for nxt in adj[curr]:
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                queue.append(nxt)

    # Append any remaining nodes if there was a cycle
    seen = {n.id for n in ordered}
    for n in workflow.nodes:
        if n.id not in seen:
            ordered.append(n)

    return ordered


async def execute_workflow_graph(
    workflow: WorkflowGraph,
    config: InferenceConfig,
    characters: dict[str, CharacterCard],
    worlds: dict[str, Lorebook],
    output_dir: Path,
) -> tuple[WorkflowExecutionResult, list[GalleryAsset]]:
    t_start = time.perf_counter()
    ordered_nodes = topological_sort_nodes(workflow)

    # Map: node_id -> dict of output handles
    node_outputs: dict[str, dict[str, Any]] = {}
    traces: dict[str, NodeExecutionTrace] = {}
    generated_images: list[str] = []
    new_gallery_assets: list[GalleryAsset] = []
    final_text = ""

    def gather_inputs(target_node_id: str) -> dict[str, Any]:
        collected: dict[str, Any] = {}
        for edge in workflow.edges:
            if edge.target == target_node_id and edge.source in node_outputs:
                src_out = node_outputs[edge.source]
                src_handle = edge.sourceHandle or "output"
                tgt_handle = edge.targetHandle or "input"
                val = src_out.get(src_handle)
                if val is None:
                    # Fallback to primary string output
                    val = src_out.get("text") or src_out.get("prompt") or src_out.get("image_url") or ""
                if tgt_handle in collected and isinstance(collected[tgt_handle], str) and isinstance(val, str):
                    collected[tgt_handle] = f"{collected[tgt_handle]}, {val}"
                else:
                    collected[tgt_handle] = val
                # Also store by source node type for convenience
                for k, v in src_out.items():
                    collected.setdefault(f"upstream_{k}", v)
        return collected

    for node in ordered_nodes:
        n_start = time.perf_counter()
        inputs = gather_inputs(node.id)
        data = node.data or {}
        out: dict[str, Any] = {}

        try:
            if node.type == "character_source":
                char_id = data.get("character_id") or next(iter(characters.keys()), "")
                card = characters.get(char_id)
                if card:
                    persona_summary = (
                        f"{card.name} ({card.title}): {card.description} "
                        f"Personality: {card.personality}. Scenario: {card.scenario}."
                    )
                    visual_tags = card.visual_prompt_tags or f"portrait of {card.name}, {card.title}, detailed fantasy character"
                    out = {
                        "character_id": card.id,
                        "character_name": card.name,
                        "persona": persona_summary,
                        "visual_tags": visual_tags,
                        "negative_tags": card.negative_prompt_tags,
                        "world_id": card.world_id,
                        "text": visual_tags,
                        "prompt": visual_tags,
                    }
                else:
                    fallback_name = data.get("custom_name", "Wanderer")
                    fallback_tags = data.get("visual_tags", "cinematic character portrait, detailed armor, dramatic lighting")
                    out = {
                        "character_name": fallback_name,
                        "persona": fallback_name,
                        "visual_tags": fallback_tags,
                        "text": fallback_tags,
                        "prompt": fallback_tags,
                    }

            elif node.type == "lore_injector":
                world_id = data.get("world_id") or inputs.get("upstream_world_id") or next(iter(worlds.keys()), "")
                lorebook = worlds.get(world_id)
                scan_query = (
                    data.get("query_text")
                    or inputs.get("query")
                    or inputs.get("text")
                    or inputs.get("persona")
                    or ""
                )
                char_name = inputs.get("upstream_character_name", "Character")
                scan_res = scan_lorebook(lorebook, str(scan_query), char_name=char_name)

                # If user picked a specific entry_id or nothing matched, include top entry
                specific_entry_id = data.get("entry_id")
                if lorebook and specific_entry_id:
                    for entry in lorebook.entries:
                        if entry.id == specific_entry_id:
                            scan_res.context_block = f"[{entry.category.upper()}: {entry.title}]\n{entry.content}"
                            scan_res.visual_tags_block = f"{lorebook.aesthetic_style}, {entry.visual_description}".strip(", ")
                            break
                elif lorebook and not scan_res.context_block and lorebook.entries:
                    first_entry = lorebook.entries[0]
                    scan_res.context_block = f"[{first_entry.category.upper()}: {first_entry.title}]\n{first_entry.content}"
                    scan_res.visual_tags_block = f"{lorebook.aesthetic_style}, {first_entry.visual_description}".strip(", ")

                out = {
                    "world_id": world_id,
                    "world_name": lorebook.name if lorebook else "Custom World",
                    "lore_context": scan_res.context_block,
                    "lore_visuals": scan_res.visual_tags_block,
                    "triggered_count": len(scan_res.triggered),
                    "triggered_titles": [t.title for t in scan_res.triggered],
                    "text": scan_res.visual_tags_block or scan_res.context_block,
                    "prompt": scan_res.visual_tags_block,
                }

            elif node.type == "prompt_template":
                template = data.get(
                    "template",
                    "{{char}}, {{lore}}, {{style}}, masterpiece concept art, volumetric lighting",
                )
                style = data.get("style", "cinematic digital painting, intricate details, 8k")
                char_part = (
                    inputs.get("char")
                    or inputs.get("visual_tags")
                    or inputs.get("upstream_visual_tags")
                    or data.get("char_fallback", "dramatic protagonist")
                )
                lore_part = (
                    inputs.get("lore")
                    or inputs.get("lore_visuals")
                    or inputs.get("upstream_lore_visuals")
                    or inputs.get("upstream_lore_context")
                    or data.get("lore_fallback", "mystical ancient sanctuary")
                )

                assembled = (
                    template.replace("{{char}}", str(char_part))
                    .replace("{{lore}}", str(lore_part))
                    .replace("{{style}}", str(style))
                )
                # Clean duplicate commas
                assembled = ", ".join(p.strip() for p in assembled.split(",") if p.strip())
                out = {
                    "prompt": assembled,
                    "text": assembled,
                }
                final_text = assembled

            elif node.type == "llm_generator":
                mode = data.get("mode", "visual_prompt")
                sys_inst = data.get(
                    "system_prompt",
                    "You are an expert visual director. Transform the character and world lore inputs into a vivid, comma-separated image generation prompt.",
                )
                upstream_parts = [
                    str(v)
                    for k, v in inputs.items()
                    if k in ("prompt", "text", "char", "lore", "upstream_persona", "upstream_lore_context") and v
                ]
                user_in = data.get("user_prompt", "")
                combined_in = "\n".join([p for p in [user_in, *upstream_parts] if p.strip()]) or "Create a vivid fantasy character portrait."

                generated_txt, provider_used = await generate_node_text(
                    config=config,
                    system_instruction=sys_inst,
                    user_prompt=combined_in,
                    mode=mode,
                )
                out = {
                    "text": generated_txt,
                    "prompt": generated_txt,
                    "provider": provider_used,
                }
                final_text = generated_txt

            elif node.type == "image_generator":
                prompt_in = (
                    inputs.get("prompt")
                    or inputs.get("text")
                    or data.get("prompt")
                    or "masterpiece fantasy concept art, glowing citadel"
                )
                neg_in = (
                    inputs.get("negative_prompt")
                    or inputs.get("upstream_negative_tags")
                    or data.get("negative_prompt", "blurry, low quality, deformed, watermark")
                )
                width = int(data.get("width", config.default_width))
                height = int(data.get("height", config.default_height))
                steps = int(data.get("steps", config.default_steps))
                cfg = float(data.get("cfg", config.default_cfg))
                seed_val = data.get("seed")
                seed = int(seed_val) if seed_val is not None and str(seed_val).strip() != "" else None

                img_meta = await generate_image_asset(
                    config=config,
                    output_dir=output_dir,
                    prompt=str(prompt_in),
                    negative_prompt=str(neg_in),
                    width=width,
                    height=height,
                    steps=steps,
                    cfg=cfg,
                    seed=seed,
                    pipeline_role="workflow",
                )
                generated_images.append(img_meta["url"])
                out = {
                    "image_url": img_meta["url"],
                    "prompt": img_meta["prompt"],
                    "seed": img_meta["seed"],
                    "provider": img_meta["provider"],
                    "width": img_meta["width"],
                    "height": img_meta["height"],
                }

                asset = GalleryAsset(
                    url=img_meta["url"],
                    prompt=img_meta["prompt"],
                    negative_prompt=img_meta["negative_prompt"],
                    provider=img_meta["provider"],
                    width=img_meta["width"],
                    height=img_meta["height"],
                    seed=img_meta["seed"],
                    character_id=inputs.get("upstream_character_id"),
                    world_id=inputs.get("upstream_world_id"),
                    workflow_id=workflow.id,
                )
                new_gallery_assets.append(asset)

            elif node.type == "image_preview":
                img_url = inputs.get("image") or inputs.get("image_url") or inputs.get("upstream_image_url") or ""
                caption = inputs.get("text") or inputs.get("prompt") or inputs.get("upstream_prompt") or ""
                out = {
                    "image_url": img_url,
                    "caption": caption,
                    "apply_to_character_id": data.get("apply_to_character_id") or inputs.get("upstream_character_id"),
                }

            duration_ms = round((time.perf_counter() - n_start) * 1000.0, 2)
            node_outputs[node.id] = out
            traces[node.id] = NodeExecutionTrace(
                node_id=node.id,
                node_type=node.type,
                status="completed",
                duration_ms=duration_ms,
                outputs=out,
            )
        except Exception as exc:
            duration_ms = round((time.perf_counter() - n_start) * 1000.0, 2)
            traces[node.id] = NodeExecutionTrace(
                node_id=node.id,
                node_type=node.type,
                status="error",
                duration_ms=duration_ms,
                outputs={},
                error=str(exc),
            )

    total_ms = round((time.perf_counter() - t_start) * 1000.0, 2)
    result = WorkflowExecutionResult(
        workflow_id=workflow.id,
        status="completed",
        total_duration_ms=total_ms,
        node_traces=traces,
        generated_images=generated_images,
        final_text=final_text,
    )
    return result, new_gallery_assets
