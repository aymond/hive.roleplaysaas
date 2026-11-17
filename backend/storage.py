from __future__ import annotations

import json
from pathlib import Path

from .inference.image_engine import _render_procedural_artwork
from .models import (
    CharacterCard,
    ChatMessage,
    ChatSession,
    GalleryAsset,
    InferenceConfig,
    Lorebook,
    LoreEntry,
    ModerationPolicy,
    TriggeredLoreInfo,
    WorkflowEdge,
    WorkflowGraph,
    WorkflowNode,
)


class StudioStorage:
    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or (Path(__file__).resolve().parent / "data")
        self.generated_dir = self.base_dir / "generated"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.generated_dir.mkdir(parents=True, exist_ok=True)

        self.state_file = self.base_dir / "studio_state.json"

        self.config: InferenceConfig = InferenceConfig()
        self.moderation_policy: ModerationPolicy = ModerationPolicy()
        self.characters: dict[str, CharacterCard] = {}
        self.worlds: dict[str, Lorebook] = {}
        self.chats: dict[str, ChatSession] = {}
        self.workflows: dict[str, WorkflowGraph] = {}
        self.gallery: list[GalleryAsset] = []

        self.load_or_seed()

    def _ensure_seed_artwork(self, filename: str, prompt: str, seed: int) -> str:
        target = self.generated_dir / filename
        if not target.exists():
            png_bytes = _render_procedural_artwork(prompt=prompt, width=512, height=512, seed=seed)
            target.write_bytes(png_bytes)
        return f"/media/generated/{filename}"

    def load_or_seed(self) -> None:
        if self.state_file.exists():
            try:
                raw = json.loads(self.state_file.read_text(encoding="utf-8"))
                self.config = InferenceConfig.model_validate(raw.get("config", {}))
                self.moderation_policy = ModerationPolicy.model_validate(raw.get("moderation_policy", {}))
                self.characters = {
                    k: CharacterCard.model_validate(v) for k, v in raw.get("characters", {}).items()
                }
                self.worlds = {
                    k: Lorebook.model_validate(v) for k, v in raw.get("worlds", {}).items()
                }
                self.chats = {
                    k: ChatSession.model_validate(v) for k, v in raw.get("chats", {}).items()
                }
                self.workflows = {
                    k: WorkflowGraph.model_validate(v) for k, v in raw.get("workflows", {}).items()
                }
                self.gallery = [GalleryAsset.model_validate(g) for g in raw.get("gallery", [])]
                if self.characters and self.worlds and self.workflows:
                    return
            except Exception:
                pass

        self._seed_defaults()
        self.save()

    def save(self) -> None:
        payload = {
            "config": self.config.model_dump(),
            "moderation_policy": self.moderation_policy.model_dump(),
            "characters": {k: v.model_dump() for k, v in self.characters.items()},
            "worlds": {k: v.model_dump() for k, v in self.worlds.items()},
            "chats": {k: v.model_dump() for k, v in self.chats.items()},
            "workflows": {k: v.model_dump() for k, v in self.workflows.items()},
            "gallery": [g.model_dump() for g in self.gallery],
        }
        self.state_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def _seed_defaults(self) -> None:
        # 1. Seed Worlds / Lorebooks
        world_aethelgard = Lorebook(
            id="world_aethelgard",
            name="Aethelgard: The Shattered Chrono-Realm",
            subtitle="Astral High-Fantasy & Temporal Ruins",
            description=(
                "A continent suspended over an astral abyss where time fractures along crystalline leylines. "
                "Chronomancers and Star-Forgers vie for control of the Spire of Echoes."
            ),
            aesthetic_style="astral high fantasy concept art, golden chronomancy rings, obsidian spires, volumetric starlight",
            entries=[
                LoreEntry(
                    id="lore_spire",
                    title="The Spire of Echoes",
                    keys=["spire", "echoes", "citadel", "observatory"],
                    category="location",
                    content=(
                        "Rising three thousand cubits above the Astral Rift, the Spire of Echoes houses the Great Horologium. "
                        "Within its halls, past and future overlap as shimmering phantoms."
                    ),
                    visual_description="towering obsidian citadel spire with floating golden astrolabe rings and starlight bridges",
                    constant=True,
                    priority=90,
                ),
                LoreEntry(
                    id="lore_conclave",
                    title="Order of the Glass Hourglass",
                    keys=["hourglass", "order", "conclave", "chronomancer", "exile"],
                    category="faction",
                    content=(
                        "The ruling synod of Chronomancers who forbid altering anchor points in history. "
                        "{{char}} was once their youngest Arch-Weaver before uncovering the First Paradox."
                    ),
                    visual_description="hooded astral scholars wearing velvet cloaks embroidered with glowing constellations",
                    priority=80,
                ),
                LoreEntry(
                    id="lore_chronocore",
                    title="Aether-Chrono Pendulum",
                    keys=["pendulum", "artifact", "relic", "aether", "time"],
                    category="artifact",
                    content=(
                        "A palm-sized gyroscope forged from fallen star-iron that can rewind local causality by six heartbeats."
                    ),
                    visual_description="intricate brass and crystal celestial gyroscope radiating amber and violet sparks",
                    priority=75,
                ),
            ],
        )

        world_veridia = Lorebook(
            id="world_veridia",
            name="Neo-Veridia 2199: Neural Rain",
            subtitle="Biopunk & Cyber-Noir Megacity",
            description=(
                "A vertical megacity perpetually drenched in luminescent acid rain, where memory brokers trade "
                "recorded dreams inside subterranean neon vaults."
            ),
            aesthetic_style="cyberpunk noir, rain-slicked neon streets, cyan and magenta holograms, anamorphic lens flare",
            entries=[
                LoreEntry(
                    id="lore_subvault",
                    title="Sector 9 Mnemonic Vaults",
                    keys=["sector 9", "vault", "memory", "archive", "mnemosyne"],
                    category="location",
                    content=(
                        "Submerged beneath Neo-Veridia's floodgates, the Mnemonic Vaults store banned neural engrams "
                        "in liquid-nitrogen glass columns."
                    ),
                    visual_description="cyberpunk underground server cathedral with glowing cyan cryo-tubes and neon mist",
                    constant=True,
                    priority=85,
                ),
                LoreEntry(
                    id="lore_syndicate",
                    title="The Ghost-Wire Syndicate",
                    keys=["syndicate", "ghost-wire", "brokers", "neural", "hacker"],
                    category="faction",
                    content=(
                        "Clandestine netrunners and archivist-smugglers who extract corporate secrets from erased android cores."
                    ),
                    visual_description="cyber-noir operatives in high-collar techwear coats with glowing optical visors",
                    priority=70,
                ),
            ],
        )

        self.worlds = {
            world_aethelgard.id: world_aethelgard,
            world_veridia.id: world_veridia,
        }

        # 2. Seed Artwork for Characters & Scenes
        lyra_avatar = self._ensure_seed_artwork(
            "seed_lyra_portrait.png",
            "portrait of Lyra Vance chronomancer mage woman, astral gold and violet halo, ornate cloak",
            seed=101,
        )
        kaelen_avatar = self._ensure_seed_artwork(
            "seed_kaelen_portrait.png",
            "portrait of Kaelen Voss cyber noir archivist hacker, neon cyan and magenta visor, rain",
            seed=202,
        )
        seraphina_avatar = self._ensure_seed_artwork(
            "seed_seraphina_portrait.png",
            "portrait of Queen Seraphina crimson gothic sunless citadel sovereign, velvet and gold crown",
            seed=303,
        )
        spire_scene = self._ensure_seed_artwork(
            "seed_spire_scene.png",
            "The Spire of Echoes astral citadel monolith with golden astrolabe rings and starlight",
            seed=404,
        )

        # 3. Seed Characters
        char_lyra = CharacterCard(
            id="char_lyra",
            name="Lyra Vance",
            title="Exiled Chronomancer of the Glass Hourglass",
            description=(
                "{{char}} is a brilliant, sharp-witted temporal scholar exiled from the Spire of Echoes after "
                "refusing to erase a fractured timeline. She carries the Aether-Chrono Pendulum at her belt and "
                "perceives faint golden echoes of choices yet unmade."
            ),
            personality="Inquisitive, poised, quietly rebellious, poetic, fiercely protective of free will",
            scenario=(
                "{{user}} ascends the shattered causeway of the Spire of Echoes during an astral eclipse, "
                "finding {{char}} calibrating an ancient astrolabe over the abyss."
            ),
            first_mes=(
                "*Sparks of amber chronomancy drift from the brass astrolabe as Lyra Vance turns toward your footsteps, "
                "her violet cloak catching the updraft from the Astral Rift below.*\n\n"
                "\"You're either three minutes early, {{user}}, or the Order of the Glass Hourglass sent someone "
                "unusually quiet this time.\" *She taps the Aether-Chrono Pendulum at her waist, a faint smile "
                "warming her intense gaze.* \"Step into the light of the Spire—before this timeline shifts again.\""
            ),
            mes_example=(
                "<START>\n"
                "{{user}}: What happens if we touch the Spire's core?\n"
                "{{char}}: *Lyra's eyes gleam with golden light as she adjusts her brass gauntlet.* "
                "\"The Conclave claims it will unravel the century. My calculations say it will finally set us free.\""
            ),
            system_prompt=(
                "Write {{char}}'s next response in an immersive astral-fantasy roleplay with {{user}}. "
                "Incorporate sensory details of temporal magic, starlight, and ancient clockwork."
            ),
            creator_notes="Starter flagship character bound to the Aethelgard Lorebook.",
            tags=["Fantasy", "Chronomancer", "Aethelgard", "Magic", "Mystery"],
            visual_prompt_tags=(
                "portrait of Lyra Vance, female chronomancer exile, luminous amber eyes, silver-streaked dark hair, "
                "velvet astral cloak with golden clockwork filigree, floating celestial astrolabe halo"
            ),
            avatar_url=lyra_avatar,
            world_id=world_aethelgard.id,
            default_workflow_id="wf_char_portrait_forge",
        )

        char_kaelen = CharacterCard(
            id="char_kaelen",
            name="Kaelen Voss",
            title="Mnemonic Broker of Sector 9",
            description=(
                "{{char}} operates a hidden memory-restoration parlor beneath Neo-Veridia's floodgates. "
                "With cybernetic optical lenses that read residual emotional wavelengths, he helps clients recover "
                "stolen memories from the Ghost-Wire Syndicate."
            ),
            personality="Dry-humored, analytical, street-smart, unexpectedly empathetic beneath a cynical shell",
            scenario=(
                "Neon rain hammers the reinforced glass of Sector 9 as {{user}} brings a corrupted neural shard "
                "into {{char}}'s subterranean studio."
            ),
            first_mes=(
                "*Holographic waveforms flicker in cyan and magenta across Kaelen Voss's workbench as he slots "
                "a cooling unit into his neural deck.*\n\n"
                "\"Lock the bulkhead behind you, {{user}}. If the Ghost-Wire Syndicate tracked that shard through "
                "Sector 9, we have aboutfourteen minutes before the grid goes hot.\" *He gestures toward the "
                "immersion chair.* \"Let's see what memory they tried so hard to burn out of your cortex.\""
            ),
            mes_example=(
                "<START>\n"
                "{{user}}: Can you decode this encrypted engram?\n"
                "{{char}}: *Kaelen's cybernetic iris narrows as cyan telemetry reflects off the rain-streaked glass.* "
                "\"Military-grade ice. Good thing I wrote half the firmware they stole it from.\""
            ),
            tags=["Cyberpunk", "Sci-Fi", "Noir", "Netrunner", "Neo-Veridia"],
            visual_prompt_tags=(
                "portrait of Kaelen Voss, cyber-noir memory archivist, glowing cyan optical implant, high-collar "
                "dark techwear trenchcoat, neon magenta rain reflections, holographic data streams"
            ),
            avatar_url=kaelen_avatar,
            world_id=world_veridia.id,
            default_workflow_id="wf_char_portrait_forge",
        )

        char_seraphina = CharacterCard(
            id="char_seraphina",
            name="Queen Seraphina",
            title="Sovereign of the Sunless Citadel",
            description=(
                "An immortal monarch who rules a subterranean court lit by bioluminescent crimson starlight. "
                "She trades in ancient oaths and forgotten kingdom lore."
            ),
            personality="Regal, enigmatic, commanding, velvet-voiced, calculating yet bound by sacred hospitality",
            scenario="{{user}} is granted a rare midnight audience in the Crimson Throne Room of the Sunless Citadel.",
            first_mes=(
                "*A hush falls over the obsidian pillars of the Sunless Citadel as Queen Seraphina rises from her "
                "throne of woven star-iron, crimson lanterns reflecting in her gaze.*\n\n"
                "\"Few mortals cross the threshold of my court without a bargain on their lips, {{user}}. "
                "Speak plainly—what truth or crown do you seek in the dark?\""
            ),
            tags=["Gothic", "Royalty", "Dark Fantasy", "Nobility"],
            visual_prompt_tags=(
                "portrait of Queen Seraphina, gothic sovereign of the Sunless Citadel, ornate crimson and black velvet gown, "
                "filigree gold crown, dramatic chiaroscuro candlelight, regal expression"
            ),
            avatar_url=seraphina_avatar,
            world_id=world_aethelgard.id,
            default_workflow_id="wf_char_portrait_forge",
        )

        self.characters = {
            char_lyra.id: char_lyra,
            char_kaelen.id: char_kaelen,
            char_seraphina.id: char_seraphina,
        }

        # 4. Seed Starter Roleplay Chat Session
        starter_chat = ChatSession(
            id="chat_default_lyra",
            title="Eclipse at the Spire of Echoes",
            character_id=char_lyra.id,
            world_id=world_aethelgard.id,
            user_persona_name="Traveler",
            user_persona_desc="A seeker carrying a mysterious astral compass.",
            messages=[
                ChatMessage(
                    id="msg_seed_1",
                    role="assistant",
                    sender_name=char_lyra.name,
                    content=char_lyra.first_mes.replace("{{user}}", "Traveler").replace("{{char}}", char_lyra.name),
                    swipes=[char_lyra.first_mes.replace("{{user}}", "Traveler").replace("{{char}}", char_lyra.name)],
                    image_url=spire_scene,
                    image_prompt="The Spire of Echoes astral citadel monolith with golden astrolabe rings and starlight",
                    triggered_lore=[
                        TriggeredLoreInfo(
                            entry_id="lore_spire",
                            title="The Spire of Echoes",
                            category="location",
                            matched_keys=["spire"],
                            snippet=world_aethelgard.entries[0].content,
                            visual_description=world_aethelgard.entries[0].visual_description,
                        ),
                        TriggeredLoreInfo(
                            entry_id="lore_conclave",
                            title="Order of the Glass Hourglass",
                            category="faction",
                            matched_keys=["hourglass", "order"],
                            snippet=world_aethelgard.entries[1].content.replace("{{char}}", char_lyra.name),
                            visual_description=world_aethelgard.entries[1].visual_description,
                        ),
                    ],
                )
            ],
        )
        self.chats = {starter_chat.id: starter_chat}

        # 5. Seed ComfyUI-Style Visual Node Workflows
        wf_portrait = WorkflowGraph(
            id="wf_char_portrait_forge",
            name="Character Concept & Portrait Forge",
            description=(
                "Chained pipeline: Loads a SillyTavern Character Card + World Lorebook context, fuses them into a "
                "cinematic prompt, expands visual details with the LLM Director, and renders on Apple Silicon."
            ),
            category="Character & Avatar",
            nodes=[
                WorkflowNode(
                    id="node_char_1",
                    type="character_source",
                    position={"x": 40, "y": 60},
                    data={"character_id": "char_lyra", "label": "Character Card Loader"},
                ),
                WorkflowNode(
                    id="node_lore_1",
                    type="lore_injector",
                    position={"x": 40, "y": 310},
                    data={
                        "world_id": "world_aethelgard",
                        "query_text": "spire chronomancer pendulum",
                        "label": "World Lorebook Scanner",
                    },
                ),
                WorkflowNode(
                    id="node_tmpl_1",
                    type="prompt_template",
                    position={"x": 380, "y": 170},
                    data={
                        "label": "Lore + Persona Prompt Combiner",
                        "template": "{{char}}, set within {{lore}}, {{style}}",
                        "style": "masterpiece character portrait, volumetric rim lighting, intricate costume details, 8k",
                    },
                ),
                WorkflowNode(
                    id="node_llm_1",
                    type="llm_generator",
                    position={"x": 710, "y": 170},
                    data={
                        "label": "LLM Visual Art Director",
                        "mode": "visual_prompt",
                        "system_prompt": "Refine the combined character and lore tags into a vivid keyframe image prompt.",
                        "user_prompt": "Focus on dramatic lighting, facial expression, and world atmosphere.",
                    },
                ),
                WorkflowNode(
                    id="node_img_1",
                    type="image_generator",
                    position={"x": 1040, "y": 150},
                    data={
                        "label": "Apple Silicon Image Synthesizer",
                        "width": 512,
                        "height": 512,
                        "steps": 20,
                        "cfg": 7.0,
                        "seed": 777,
                        "negative_prompt": "blurry, low quality, deformed, watermark, text",
                    },
                ),
                WorkflowNode(
                    id="node_prev_1",
                    type="image_preview",
                    position={"x": 1380, "y": 150},
                    data={
                        "label": "Portrait Output & Card Saver",
                        "image_url": lyra_avatar,
                        "apply_to_character_id": "char_lyra",
                    },
                ),
            ],
            edges=[
                WorkflowEdge(
                    id="e1",
                    source="node_char_1",
                    target="node_tmpl_1",
                    sourceHandle="visual_tags",
                    targetHandle="char",
                ),
                WorkflowEdge(
                    id="e2",
                    source="node_lore_1",
                    target="node_tmpl_1",
                    sourceHandle="lore_visuals",
                    targetHandle="lore",
                ),
                WorkflowEdge(
                    id="e3",
                    source="node_tmpl_1",
                    target="node_llm_1",
                    sourceHandle="prompt",
                    targetHandle="prompt",
                ),
                WorkflowEdge(
                    id="e4",
                    source="node_llm_1",
                    target="node_img_1",
                    sourceHandle="prompt",
                    targetHandle="prompt",
                ),
                WorkflowEdge(
                    id="e5",
                    source="node_img_1",
                    target="node_prev_1",
                    sourceHandle="image_url",
                    targetHandle="image",
                ),
            ],
        )

        wf_scene = WorkflowGraph(
            id="wf_world_scene_illustrator",
            name="Lore-Grounded World Scene Illustrator",
            description="Scans a world lorebook for locations and factions, then renders environmental concept art.",
            category="World & Environment",
            nodes=[
                WorkflowNode(
                    id="node_lore_s1",
                    type="lore_injector",
                    position={"x": 60, "y": 140},
                    data={
                        "world_id": "world_veridia",
                        "query_text": "sector 9 vault syndicate neural",
                        "label": "Neo-Veridia Lore Scanner",
                    },
                ),
                WorkflowNode(
                    id="node_tmpl_s1",
                    type="prompt_template",
                    position={"x": 420, "y": 140},
                    data={
                        "label": "Environment Scene Composer",
                        "template": "wide angle environmental concept art, {{lore}}, {{style}}",
                        "style": "cyberpunk rain reflections, towering architecture, atmospheric fog, 8k",
                    },
                ),
                WorkflowNode(
                    id="node_img_s1",
                    type="image_generator",
                    position={"x": 780, "y": 120},
                    data={
                        "label": "Apple Silicon Scene Renderer",
                        "width": 512,
                        "height": 512,
                        "steps": 20,
                        "cfg": 7.5,
                        "seed": 2199,
                        "negative_prompt": "blurry, low resolution, cropped",
                    },
                ),
                WorkflowNode(
                    id="node_prev_s1",
                    type="image_preview",
                    position={"x": 1140, "y": 120},
                    data={
                        "label": "Environment Keyframe Preview",
                        "image_url": spire_scene,
                    },
                ),
            ],
            edges=[
                WorkflowEdge(
                    id="es1",
                    source="node_lore_s1",
                    target="node_tmpl_s1",
                    sourceHandle="lore_visuals",
                    targetHandle="lore",
                ),
                WorkflowEdge(
                    id="es2",
                    source="node_tmpl_s1",
                    target="node_img_s1",
                    sourceHandle="prompt",
                    targetHandle="prompt",
                ),
                WorkflowEdge(
                    id="es3",
                    source="node_img_s1",
                    target="node_prev_s1",
                    sourceHandle="image_url",
                    targetHandle="image",
                ),
            ],
        )

        self.workflows = {
            wf_portrait.id: wf_portrait,
            wf_scene.id: wf_scene,
        }

        self.gallery = [
            GalleryAsset(
                id="img_seed_lyra",
                url=lyra_avatar,
                prompt=char_lyra.visual_prompt_tags,
                provider="procedural_art (Apple Silicon Instant Canvas)",
                seed=101,
                character_id=char_lyra.id,
                world_id=world_aethelgard.id,
            ),
            GalleryAsset(
                id="img_seed_kaelen",
                url=kaelen_avatar,
                prompt=char_kaelen.visual_prompt_tags,
                provider="procedural_art (Apple Silicon Instant Canvas)",
                seed=202,
                character_id=char_kaelen.id,
                world_id=world_veridia.id,
            ),
            GalleryAsset(
                id="img_seed_seraphina",
                url=seraphina_avatar,
                prompt=char_seraphina.visual_prompt_tags,
                provider="procedural_art (Apple Silicon Instant Canvas)",
                seed=303,
                character_id=char_seraphina.id,
                world_id=world_aethelgard.id,
            ),
            GalleryAsset(
                id="img_seed_spire",
                url=spire_scene,
                prompt="The Spire of Echoes astral citadel monolith with golden astrolabe rings and starlight",
                provider="procedural_art (Apple Silicon Instant Canvas)",
                seed=404,
                world_id=world_aethelgard.id,
            ),
        ]
