import React, { useEffect, useRef, useState } from 'react';
import { Cpu, Check, X, Server } from 'lucide-react';
import { api } from '../api';
import type { ImagePipelineProfile, InferenceConfig, SystemStatus } from '../types';

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
  const [activeProfileTab, setActiveProfileTab] = useState<
    'portrait_profile' | 'scene_profile' | 'scenery_profile' | 'workflow_profile'
  >('portrait_profile');
  const [metrics, setMetrics] = useState<{
    chat: { count: number; avg_ms: number | null; p50_ms: number | null; latest_ms: number | null };
    scene: { count: number; avg_ms: number | null; p50_ms: number | null; latest_ms: number | null };
    studio: { count: number; avg_ms: number | null; p50_ms: number | null; latest_ms: number | null };
  } | null>(null);

  useEffect(() => {
    if (isOpen) {
      api.getSystemMetrics().then(setMetrics).catch(() => setMetrics(null));
    }
  }, [isOpen]);

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
              Inference &amp; Connector Settings
            </h2>
            <p className="text-xs text-slate-400">
              Configure Vertex AI, Cloud Run GPU / ComfyUI, OpenAI-compatible (vLLM / Ollama), and SFW guardrails
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
              PyTorch {status.hardware.torch_version} •{' '}
              <strong className="text-emerald-300">
                {status.hardware.cuda_available
                  ? `CUDA (${status.hardware.cuda_device || 'GPU'})`
                  : status.hardware.mps_available
                  ? 'Metal MPS ACTIVE'
                  : status.hardware.cloud_run
                  ? 'GCP Cloud Run'
                  : 'CPU'}
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
                  <option value="auto">Auto (Vertex AI → Ollama → OpenAI-Compat → Built-in Synth)</option>
                  <option value="vertex_ai">Google Cloud Vertex AI (Gemini)</option>
                  <option value="ollama">Ollama API (Self-Hosted / Cloud Run)</option>
                  <option value="openai_compat">OpenAI-Compatible (vLLM / Cloud Run / LM Studio)</option>
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
                  <option value="vertex_imagen">Google Cloud Vertex AI Imagen (SFW Managed)</option>
                  <option value="runpod_serverless">RunPod Serverless ComfyUI (Pay-per-second)</option>
                  <option value="procedural_art">
                    Instant Procedural Concept Art Synth (&lt;150ms)
                  </option>
                </select>
                <label className="mt-2 flex items-center gap-1.5 text-xs text-emerald-300 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={draftConfig.sfw_mode ?? true}
                    onChange={(e) =>
                      setDraftConfig({ ...draftConfig, sfw_mode: e.target.checked })
                    }
                  />
                  Enforce SFW Mode (Pre-flight trigger-word filter + SFW negative blockers)
                </label>
                <label className="mt-1.5 flex items-center gap-1.5 text-xs text-cyan-300 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={draftConfig.use_specialist_image_models ?? true}
                    onChange={(e) =>
                      setDraftConfig({
                        ...draftConfig,
                        use_specialist_image_models: e.target.checked,
                      })
                    }
                  />
                  Use Specialist Models per Pipeline (uncheck for one model for all)
                </label>
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
                  <option value="action_hybrid">
                    Action Hybrid (Juggernaut Action → Pony Refine → FacePolish)
                  </option>
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
                <div className="col-span-2">
                  <label className="block text-[11px] text-slate-300 mb-1">
                    Face Pass Upscale Factor
                  </label>
                  <select
                    value={String(draftConfig.comfyui_face_detailer_scale ?? 1.25)}
                    onChange={(e) =>
                      setDraftConfig({
                        ...draftConfig,
                        comfyui_face_detailer_scale: Number(e.target.value),
                      })
                    }
                    className="w-full bg-[#0d111b] border border-white/15 rounded-lg px-2.5 py-1.5 text-xs text-white"
                  >
                    <option value="1.25">1.25x — Faster (~6–8s saved per render, Recommended)</option>
                    <option value="1.5">1.5x — High-Res Detail (slower)</option>
                  </select>
                </div>
              </div>
              {metrics && (
                <div className="mt-2 p-2.5 rounded-lg bg-[#0d111b] border border-white/10 text-[11px] text-slate-300 flex flex-wrap items-center justify-between gap-2">
                  <span className="font-semibold text-amber-300">Local Performance Metrics:</span>
                  <span className="font-mono text-slate-300">
                    Chat p50: {metrics.chat.p50_ms ? `${(metrics.chat.p50_ms / 1000).toFixed(1)}s` : '—'} ({metrics.chat.count}) ·
                    Scene p50: {metrics.scene.p50_ms ? `${(metrics.scene.p50_ms / 1000).toFixed(1)}s` : '—'} ({metrics.scene.count}) ·
                    Studio p50: {metrics.studio.p50_ms ? `${(metrics.studio.p50_ms / 1000).toFixed(1)}s` : '—'} ({metrics.studio.count})
                  </span>
                </div>
              )}
            </div>

            {/* Specialist Per-Pipeline Image Profiles (Portraits, Scenes, Scenery, Comfy Nodes) */}
            {(draftConfig.use_specialist_image_models ?? true) && (() => {
              const emptyProfile: ImagePipelineProfile = {
                provider: 'inherit',
                checkpoint: '',
                vertex_model: '',
                render_mode: 'inherit',
                face_detailer: null,
                steps: null,
                cfg: null,
              };
              const currentProfile: ImagePipelineProfile = {
                ...emptyProfile,
                ...(draftConfig[activeProfileTab] || {}),
              };
              const updateProfile = (patch: Partial<ImagePipelineProfile>) => {
                setDraftConfig({
                  ...draftConfig,
                  [activeProfileTab]: { ...currentProfile, ...patch },
                });
              };
              return (
                <div className="p-3.5 rounded-xl bg-[#121724] border border-cyan-500/25 space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-xs font-bold uppercase tracking-wider text-cyan-300">
                      Specialist Pipeline Profiles
                    </span>
                    <div className="flex flex-wrap gap-1">
                      {(
                        [
                          ['portrait_profile', 'Portraits'],
                          ['scene_profile', 'Scenes'],
                          ['scenery_profile', 'Scenery & Maps'],
                          ['workflow_profile', 'Comfy Nodes'],
                        ] as const
                      ).map(([key, label]) => (
                        <button
                          key={key}
                          type="button"
                          onClick={() => setActiveProfileTab(key)}
                          className={`px-2.5 py-1 rounded-lg text-[11px] font-semibold cursor-pointer transition ${
                            activeProfileTab === key
                              ? 'bg-cyan-500 text-slate-950'
                              : 'bg-white/5 text-slate-300 hover:bg-white/10'
                          }`}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                    <div>
                      <label className="block text-[11px] text-slate-400 mb-1">Provider</label>
                      <select
                        value={currentProfile.provider}
                        onChange={(e) =>
                          updateProfile({
                            provider: e.target.value as ImagePipelineProfile['provider'],
                          })
                        }
                        className="w-full bg-[#0d111b] border border-white/15 rounded-lg px-2.5 py-1.5 text-xs text-white"
                      >
                        <option value="inherit">Inherit Global ({draftConfig.image_provider})</option>
                        <option value="comfyui">ComfyUI (Cloud Run GPU / Local)</option>
                        <option value="vertex_imagen">Vertex AI Imagen</option>
                        <option value="runpod_serverless">RunPod Serverless</option>
                        <option value="procedural_art">Procedural Canvas</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-[11px] text-slate-400 mb-1">
                        ComfyUI Checkpoint (blank = inherit)
                      </label>
                      <input
                        type="text"
                        list="comfyui-checkpoints-list"
                        value={currentProfile.checkpoint}
                        onChange={(e) => updateProfile({ checkpoint: e.target.value })}
                        placeholder={draftConfig.comfyui_checkpoint}
                        className="w-full bg-[#0d111b] border border-white/15 rounded-lg px-2.5 py-1.5 text-xs text-cyan-200 font-mono"
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] text-slate-400 mb-1">Render Mode</label>
                      <select
                        value={currentProfile.render_mode}
                        onChange={(e) => updateProfile({ render_mode: e.target.value })}
                        className="w-full bg-[#0d111b] border border-white/15 rounded-lg px-2.5 py-1.5 text-xs text-white"
                      >
                        <option value="inherit">Inherit Global</option>
                        <option value="single_stylized">single_stylized</option>
                        <option value="single_raw">single_raw</option>
                        <option value="hybrid_refiner">hybrid_refiner</option>
                        <option value="action_hybrid">action_hybrid</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-[11px] text-slate-400 mb-1">
                        Steps (blank = default)
                      </label>
                      <input
                        type="number"
                        value={currentProfile.steps ?? ''}
                        onChange={(e) =>
                          updateProfile({
                            steps: e.target.value ? Number(e.target.value) : null,
                          })
                        }
                        placeholder={String(draftConfig.default_steps)}
                        className="w-full bg-[#0d111b] border border-white/15 rounded-lg px-2.5 py-1.5 text-xs text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] text-slate-400 mb-1">
                        CFG (blank = default)
                      </label>
                      <input
                        type="number"
                        step="0.5"
                        value={currentProfile.cfg ?? ''}
                        onChange={(e) =>
                          updateProfile({
                            cfg: e.target.value ? Number(e.target.value) : null,
                          })
                        }
                        placeholder={String(draftConfig.default_cfg)}
                        className="w-full bg-[#0d111b] border border-white/15 rounded-lg px-2.5 py-1.5 text-xs text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] text-slate-400 mb-1">FaceDetailer</label>
                      <select
                        value={
                          currentProfile.face_detailer === null
                            ? 'inherit'
                            : currentProfile.face_detailer
                            ? 'on'
                            : 'off'
                        }
                        onChange={(e) =>
                          updateProfile({
                            face_detailer:
                              e.target.value === 'inherit'
                                ? null
                                : e.target.value === 'on',
                          })
                        }
                        className="w-full bg-[#0d111b] border border-white/15 rounded-lg px-2.5 py-1.5 text-xs text-white"
                      >
                        <option value="inherit">Inherit Global</option>
                        <option value="on">Enabled</option>
                        <option value="off">Disabled</option>
                      </select>
                    </div>
                  </div>
                </div>
              );
            })()}

            <details className="rounded-xl border border-white/10 bg-[#0d111b]/80 p-3 space-y-2.5">
              <summary className="text-xs font-bold uppercase tracking-wider text-cyan-300 cursor-pointer select-none flex items-center justify-between">
                <span>Prompt Integration Templates (Scene, Studio, Portrait, Location, Map)</span>
                <span className="text-[10px] font-normal text-slate-400">Expand to customize</span>
              </summary>
              <div className="pt-2 space-y-2.5">
                {[
                  {
                    key: 'scene_prompt_template' as const,
                    label: 'Chat Scene Illustration Template',
                    fallback:
                      '{quality}, {anatomical_overrides}, {solo}, {action_tags}, {character_traits}, {scene_state}, {location_lore}, {dialog_scene}',
                    hint: 'Placeholders: {quality}, {anatomical_overrides}, {solo}, {action_tags}, {character_traits}, {scene_state}, {location_lore}, {dialog_scene}, {style}',
                  },
                  {
                    key: 'studio_prompt_template' as const,
                    label: 'Image Studio (Backstory-Grounded) Template',
                    fallback:
                      '{quality}, {anatomical_overrides}, {scene_state}, {character_traits}, {location_lore}, {dialog_scene}',
                    hint: 'Placeholders: {quality}, {anatomical_overrides}, {scene_state}, {character_traits}, {location_lore}, {dialog_scene}, {harmonized_scene}, {style}',
                  },
                  {
                    key: 'portrait_prompt_template' as const,
                    label: 'Character Portrait Template',
                    fallback: '{character_traits}, {world_style}, {portrait_style}',
                    hint: 'Placeholders: {character_traits}, {world_style}, {portrait_style}',
                  },
                  {
                    key: 'location_prompt_template' as const,
                    label: 'Location / Lore Entry Template',
                    fallback: '{title}, {lore_content}, {custom_visuals}, {world_style}, {category_style}',
                    hint: 'Placeholders: {title}, {lore_content}, {custom_visuals}, {world_style}, {category_style}',
                  },
                  {
                    key: 'world_map_prompt_template' as const,
                    label: 'World Map Template',
                    fallback: '{map_style}, {landmarks}, {world_geography}, {map_closing}',
                    hint: 'Placeholders: {map_style}, {landmarks}, {world_geography}, {map_closing}, {world_name}',
                  },
                ].map((tpl) => (
                  <div key={tpl.key} className="space-y-1">
                    <div className="flex items-center justify-between">
                      <label className="text-[11px] font-semibold text-slate-300">{tpl.label}</label>
                      <button
                        type="button"
                        onClick={() =>
                          setDraftConfig({ ...draftConfig, [tpl.key]: tpl.fallback })
                        }
                        className="text-[10px] text-cyan-300 hover:underline cursor-pointer"
                      >
                        Reset Default
                      </button>
                    </div>
                    <input
                      type="text"
                      value={draftConfig[tpl.key] ?? tpl.fallback}
                      onChange={(e) =>
                        setDraftConfig({ ...draftConfig, [tpl.key]: e.target.value })
                      }
                      className="w-full bg-[#121724] border border-white/15 rounded-lg px-2.5 py-1.5 text-[11px] font-mono text-slate-200 focus:outline-none focus:border-cyan-400"
                    />
                    <p className="text-[10px] text-slate-500">{tpl.hint}</p>
                  </div>
                ))}
              </div>
            </details>

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
