import React, { useEffect, useRef, useState } from 'react';
import { Cpu, Check, X, Server } from 'lucide-react';
import { api } from '../api';
import type { InferenceConfig, SystemStatus } from '../types';

interface EngineSettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  status: SystemStatus | null;
  onStatusUpdated: () => void;
}

export const EngineSettingsModal: React.FC<EngineSettingsModalProps> = ({
  isOpen,
  onClose,
  status,
  onStatusUpdated,
}) => {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [draftConfig, setDraftConfig] = useState<InferenceConfig | null>(
    status?.config || null
  );
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (status?.config) {
      setDraftConfig({ ...status.config });
    }
  }, [status]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    if (isOpen && !dialog.open) {
      dialog.showModal();
    } else if (!isOpen && dialog.open) {
      dialog.close();
    }
  }, [isOpen]);

  // MANDATORY fallback for browsers without native dialog closedby="any" support (e.g. Safari)
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    const handleClose = () => {
      dialog.returnValue = '';
      onClose();
    };
    dialog.addEventListener('close', handleClose);

    let cleanupFallback = () => {};
    if (!('closedBy' in HTMLDialogElement.prototype)) {
      const handleClick = (event: MouseEvent) => {
        if (event.target !== dialog) return;
        const rect = dialog.getBoundingClientRect();
        const isDialogContent =
          rect.top <= event.clientY &&
          event.clientY <= rect.top + rect.height &&
          rect.left <= event.clientX &&
          event.clientX <= rect.left + rect.width;
        if (isDialogContent) return;
        dialog.close();
      };
      dialog.addEventListener('click', handleClick);
      cleanupFallback = () => dialog.removeEventListener('click', handleClick);
    }

    return () => {
      dialog.removeEventListener('close', handleClose);
      cleanupFallback();
    };
  }, [onClose]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!draftConfig) return;
    setSaving(true);
    try {
      await api.updateSystemConfig(draftConfig);
      onStatusUpdated();
      dialogRef.current?.close();
    } finally {
      setSaving(false);
    }
  };

  return (
    <dialog
      ref={dialogRef}
      {...({ closedby: 'any' } as any)}
      aria-labelledby="engine-settings-title"
      className="m-auto w-full max-w-2xl rounded-2xl bg-[#111521] text-slate-100 border border-white/15 shadow-2xl p-0 open:block"
    >
      <div className="p-5 border-b border-white/10 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-xl bg-amber-500/15 text-amber-400 border border-amber-500/30">
            <Cpu className="w-5 h-5" />
          </div>
          <div>
            <h2 id="engine-settings-title" className="text-base font-bold text-white">
              Apple Silicon Inference & Connector Settings
            </h2>
            <p className="text-xs text-slate-400">
              Configure local Metal / PyTorch MPS, Ollama, LM Studio, and ComfyUI bridges
            </p>
          </div>
        </div>
        <form method="dialog">
          <button
            type="submit"
            aria-label="Close settings dialog"
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </form>
      </div>

      {draftConfig && status && (
        <form onSubmit={handleSave} className="p-5 space-y-5">
          {/* Hardware Telemetry Banner */}
          <div className="p-3.5 rounded-xl bg-[#0b0e17] border border-emerald-500/30 flex flex-wrap items-center justify-between gap-2 text-xs">
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse" />
              <span className="font-semibold text-emerald-300">
                {status.hardware.processor} ({status.hardware.architecture})
              </span>
            </div>
            <div className="text-slate-300 font-mono text-[11px]">
              PyTorch {status.hardware.torch_version} • Metal MPS:{' '}
              <strong className="text-emerald-300">
                {status.hardware.mps_available ? 'ACTIVE' : 'UNAVAILABLE'}
              </strong>
            </div>
          </div>

          {/* LLM Engine Configuration */}
          <div className="space-y-3">
            <h3 className="text-xs font-bold uppercase tracking-wider text-amber-300 flex items-center gap-1.5">
              <Server className="w-3.5 h-3.5" />
              Language Model Engine (Roleplay & Prompt Expansion)
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-slate-300 mb-1">Active LLM Provider</label>
                <select
                  autoFocus
                  value={draftConfig.llm_provider}
                  onChange={(e) =>
                    setDraftConfig({
                      ...draftConfig,
                      llm_provider: e.target.value as InferenceConfig['llm_provider'],
                    })
                  }
                  className="w-full bg-[#171c2b] border border-white/15 rounded-xl px-3 py-2 text-xs text-white"
                >
                  <option value="auto">Auto (Ollama → OpenAI-Compat → Built-in Synth)</option>
                  <option value="ollama">Ollama Local Metal API (localhost:11434)</option>
                  <option value="openai_compat">OpenAI-Compatible (LM Studio / mlx_lm)</option>
                  <option value="builtin_synth">Built-in Instant Story Engine</option>
                </select>
              </div>
              <div>
                <label className="block text-xs text-slate-300 mb-1">
                  Ollama Model ({status.providers.ollama.online ? 'Online' : 'Offline'})
                </label>
                <input
                  type="text"
                  list="ollama-models-list"
                  value={draftConfig.ollama_model}
                  onChange={(e) =>
                    setDraftConfig({ ...draftConfig, ollama_model: e.target.value })
                  }
                  className="w-full bg-[#171c2b] border border-white/15 rounded-xl px-3 py-2 text-xs text-white font-mono"
                />
                <datalist id="ollama-models-list">
                  {status.providers.ollama.models.map((m) => (
                    <option key={m} value={m} />
                  ))}
                </datalist>
                {status.providers.ollama.models.length > 0 && (
                  <div className="mt-1 flex flex-wrap gap-1">
                    {status.providers.ollama.models.map((m) => (
                      <button
                        key={m}
                        type="button"
                        onClick={() => setDraftConfig({ ...draftConfig, ollama_model: m })}
                        className={`text-[10px] px-1.5 py-0.5 rounded border cursor-pointer ${
                          draftConfig.ollama_model === m
                            ? 'bg-amber-500/20 border-amber-400 text-amber-200'
                            : 'bg-white/5 border-white/10 text-slate-400 hover:text-white'
                        }`}
                      >
                        {m}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-slate-300 mb-1">
                  OpenAI-Compatible Endpoint URL
                </label>
                <input
                  type="text"
                  value={draftConfig.openai_base_url}
                  onChange={(e) =>
                    setDraftConfig({ ...draftConfig, openai_base_url: e.target.value })
                  }
                  className="w-full bg-[#171c2b] border border-white/15 rounded-xl px-3 py-2 text-xs text-white font-mono"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-300 mb-1">Temperature</label>
                <input
                  type="number"
                  step="0.05"
                  min="0"
                  max="2"
                  value={draftConfig.temperature}
                  onChange={(e) =>
                    setDraftConfig({
                      ...draftConfig,
                      temperature: Number(e.target.value),
                    })
                  }
                  className="w-full bg-[#171c2b] border border-white/15 rounded-xl px-3 py-2 text-xs text-white"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-300 mb-1">
                  Hivemind Terminal Log Level
                </label>
                <select
                  value={draftConfig.log_level || 'INFO'}
                  onChange={(e) =>
                    setDraftConfig({
                      ...draftConfig,
                      log_level: e.target.value as 'INFO' | 'DEBUG',
                    })
                  }
                  className="w-full bg-[#171c2b] border border-white/15 rounded-xl px-3 py-2 text-xs text-emerald-300 font-mono"
                >
                  <option value="INFO">
                    INFO (User Actions, Ollama Distillations &amp; ComfyUI Prompts)
                  </option>
                  <option value="DEBUG">
                    DEBUG (+ Full ComfyUI Workflow JSON &amp; Raw LLM Payloads)
                  </option>
                </select>
              </div>
            </div>
          </div>

          {/* Image Generation Engine Configuration */}
          <div className="space-y-3 pt-2 border-t border-white/10">
            <h3 className="text-xs font-bold uppercase tracking-wider text-cyan-300 flex items-center gap-1.5">
              <Cpu className="w-3.5 h-3.5" />
              Image Synthesis Engine (Portraits, Scenes & Comfy Nodes)
            </h3>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-slate-300 mb-1">
                  Active Image Provider
                </label>
                <select
                  value={draftConfig.image_provider}
                  onChange={(e) =>
                    setDraftConfig({
                      ...draftConfig,
                      image_provider: e.target.value as InferenceConfig['image_provider'],
                    })
                  }
                  className="w-full bg-[#171c2b] border border-white/15 rounded-xl px-3 py-2 text-xs text-white"
                >
                  <option value="auto">
                    Auto (ComfyUI → Cached MPS Diffusers → Instant Procedural Art)
                  </option>
                  <option value="mps_diffusers">
                    PyTorch Metal MPS Diffusers (Downloads HF Model if needed)
                  </option>
                  <option value="comfyui">External ComfyUI API Server (localhost:8188)</option>
                  <option value="procedural_art">
                    Instant Procedural Concept Art Synth (&lt;150ms)
                  </option>
                </select>
              </div>
              <div>
                <label className="block text-xs text-slate-300 mb-1">
                  HuggingFace Diffusers Model ID (MPS)
                </label>
                <input
                  type="text"
                  value={draftConfig.mps_model_id}
                  onChange={(e) =>
                    setDraftConfig({ ...draftConfig, mps_model_id: e.target.value })
                  }
                  className="w-full bg-[#171c2b] border border-white/15 rounded-xl px-3 py-2 text-xs text-white font-mono"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-slate-300 mb-1">
                  ComfyUI Server URL ({status.providers.comfyui.online ? 'Online' : 'Offline'})
                </label>
                <input
                  type="text"
                  value={draftConfig.comfyui_base_url}
                  onChange={(e) =>
                    setDraftConfig({ ...draftConfig, comfyui_base_url: e.target.value })
                  }
                  className="w-full bg-[#171c2b] border border-white/15 rounded-xl px-3 py-2 text-xs text-white font-mono"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-300 mb-1">
                  Primary ComfyUI Checkpoint (Base / Anatomy)
                </label>
                <input
                  type="text"
                  list="comfyui-checkpoints-list"
                  value={draftConfig.comfyui_checkpoint}
                  onChange={(e) =>
                    setDraftConfig({ ...draftConfig, comfyui_checkpoint: e.target.value })
                  }
                  className="w-full bg-[#171c2b] border border-white/15 rounded-xl px-3 py-2 text-xs text-cyan-200 font-mono"
                />
                <datalist id="comfyui-checkpoints-list">
                  {(status.providers.comfyui.checkpoints || []).map((ckpt) => (
                    <option key={ckpt} value={ckpt} />
                  ))}
                </datalist>
                {(status.providers.comfyui.checkpoints || []).length > 0 && (
                  <div className="mt-1 flex flex-wrap gap-1">
                    {(status.providers.comfyui.checkpoints || []).map((ckpt) => (
                      <button
                        key={ckpt}
                        type="button"
                        onClick={() =>
                          setDraftConfig({ ...draftConfig, comfyui_checkpoint: ckpt })
                        }
                        className={`text-[10px] px-1.5 py-0.5 rounded border cursor-pointer font-mono ${
                          draftConfig.comfyui_checkpoint === ckpt
                            ? 'bg-cyan-500/20 border-cyan-400 text-cyan-200'
                            : 'bg-white/5 border-white/10 text-slate-400 hover:text-white'
                        }`}
                      >
                        {ckpt}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* ComfyUI Render Style Mode & Refiner Pipeline */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
              <div>
                <label className="block text-xs text-slate-300 mb-1">
                  Artistic Style &amp; Pipeline Mode
                </label>
                <select
                  value={draftConfig.comfyui_render_mode || 'hybrid_refiner'}
                  onChange={(e) =>
                    setDraftConfig({
                      ...draftConfig,
                      comfyui_render_mode: e.target.value as InferenceConfig['comfyui_render_mode'],
                    })
                  }
                  className="w-full bg-[#171c2b] border border-white/15 rounded-xl px-3 py-2 text-xs text-amber-200"
                >
                  <option value="hybrid_refiner">
                    Option 1: 2-Stage Hybrid (Uncensored Pony Base → Golden-Hour SDXL Refiner)
                  </option>
                  <option value="single_stylized">
                    Option 2: Single Model + Painterly Golden-Hour Glamour Style
                  </option>
                  <option value="single_raw">
                    Option 3: Single Model + Raw Unfiltered Photo Style
                  </option>
                </select>
              </div>

              <div>
                <label className="block text-xs text-slate-300 mb-1">
                  Stage-2 Artistic Refiner Checkpoint (used in Hybrid Mode)
                </label>
                <input
                  type="text"
                  list="comfyui-checkpoints-list"
                  value={
                    draftConfig.comfyui_refiner_checkpoint ||
                    'sd_xl_base_1.0_0.9vae.safetensors'
                  }
                  onChange={(e) =>
                    setDraftConfig({
                      ...draftConfig,
                      comfyui_refiner_checkpoint: e.target.value,
                    })
                  }
                  className="w-full bg-[#171c2b] border border-white/15 rounded-xl px-3 py-2 text-xs text-amber-200 font-mono"
                />
              </div>
            </div>

            {/* Final Face Detailer Pass (ADetailer-style MediaPipe 768x768 Crop & Refine) */}
            <div className="p-3 rounded-xl bg-[#131825] border border-emerald-500/25 space-y-2.5">
              <div className="flex items-center justify-between gap-2">
                <label className="flex items-center gap-2 text-xs font-semibold text-emerald-300 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={draftConfig.comfyui_face_detailer_enabled ?? true}
                    onChange={(e) =>
                      setDraftConfig({
                        ...draftConfig,
                        comfyui_face_detailer_enabled: e.target.checked,
                      })
                    }
                  />
                  <span>Automatic Final Face Detailer Pass (MediaPipe 768×768 Crop &amp; Refine)</span>
                </label>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-[11px] text-slate-300 mb-1">
                    Face Pass Checkpoint
                  </label>
                  <select
                    value={draftConfig.comfyui_face_detailer_model || 'same'}
                    onChange={(e) =>
                      setDraftConfig({
                        ...draftConfig,
                        comfyui_face_detailer_model: e.target.value,
                      })
                    }
                    className="w-full bg-[#171c2b] border border-white/15 rounded-xl px-3 py-1.5 text-xs text-emerald-200 font-mono"
                  >
                    <option value="same">same (Fastest — Reuses Active Model in VRAM, +3.5s)</option>
                    {(status.providers.comfyui.checkpoints || []).map((ckpt) => (
                      <option key={ckpt} value={ckpt}>
                        {ckpt}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-[11px] text-slate-300 mb-1">
                    Face Pass Denoise Strength ({(draftConfig.comfyui_face_detailer_denoise ?? 0.36).toFixed(2)})
                  </label>
                  <input
                    type="range"
                    min={0.2}
                    max={0.55}
                    step={0.02}
                    value={draftConfig.comfyui_face_detailer_denoise ?? 0.36}
                    onChange={(e) =>
                      setDraftConfig({
                        ...draftConfig,
                        comfyui_face_detailer_denoise: Number(e.target.value),
                      })
                    }
                    className="w-full accent-emerald-400"
                  />
                </div>
              </div>
            </div>

            <div className="flex items-center gap-4 pt-1">
              <label className="flex items-center gap-1.5 text-xs text-slate-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={draftConfig.mps_use_fp16}
                  onChange={(e) =>
                    setDraftConfig({ ...draftConfig, mps_use_fp16: e.target.checked })
                  }
                />
                MPS Float16
              </label>
              <label className="flex items-center gap-1.5 text-xs text-slate-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={draftConfig.mps_attention_slicing}
                  onChange={(e) =>
                    setDraftConfig({
                      ...draftConfig,
                      mps_attention_slicing: e.target.checked,
                    })
                  }
                />
                Attention Slicing
              </label>
            </div>
          </div>

          <div className="pt-3 border-t border-white/10 flex justify-end gap-2">
            <button
              type="button"
              onClick={() => dialogRef.current?.close()}
              className="px-4 py-2 rounded-xl bg-white/5 hover:bg-white/10 text-xs text-slate-300 cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs flex items-center gap-1.5 cursor-pointer"
            >
              <Check className="w-4 h-4" />
              {saving ? 'Applying...' : 'Save Configuration'}
            </button>
          </div>
        </form>
      )}
    </dialog>
  );
};
