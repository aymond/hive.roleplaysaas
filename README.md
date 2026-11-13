# Hivemind Studio — Apple Silicon Character, World & Node Workflow Engine

**Hivemind** is a browser-based creative studio built for **Apple Silicon (`arm64` / Metal / PyTorch MPS)** that combines:
1. **SillyTavern-Style Roleplay & Lorebooks**:
   - **Character Forge**: Full `chara_card_v2` persona editor with one-click portrait synthesis and **TavernPNG (`.png`) / `.json` import & export**.
   - **World Codex**: Keyword-triggered World Info / Lorebooks across Locations, Factions, Magic/Tech, Artifacts, History, and Relationships, with a live **Lore Scanner Testbench**.
   - **Interactive Roleplay Chat**: Multi-turn roleplay with response swiping, live **Triggered World Info** badges, and one-click inline **Scene Illustration**.
2. **ComfyUI-Style Visual Node Workflow Studio**:
   - Interactive `@xyflow/react` node graph editor where you wire **Character Card Loaders**, **World Lore Scanners**, **Prompt Combiners**, **LLM Visual/Lore Directors**, **Apple Silicon Image Synthesizers**, and **Preview / Avatar Savers**.
3. **Hybrid Apple Silicon Inference Layer**:
   - **LLM Providers**: Local **Ollama** (`localhost:11434`), **OpenAI-compatible** servers (`localhost:1234/v1` for LM Studio / `mlx_lm.server`), plus a zero-config **Built-in Narrative & Prompt Synthesizer**.
   - **Image Providers**: Native **PyTorch Metal MPS (`diffusers` on `torch.device("mps")`)**, external **ComfyUI API bridge** (`localhost:8188`), and an **Instant Procedural Concept Art Synthesizer** (<150ms).

## Quick Start

```bash
chmod +x run.sh
./run.sh
```

Then open **http://localhost:5173** in your browser.

## Running Automated Tests

```bash
./.venv/bin/python3 -m pytest backend/tests/test_hivemind.py -v
```
