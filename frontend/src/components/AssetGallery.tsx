import React, { useState } from 'react';
import { Sparkles, Download, Image as ImageIcon, Layers, Trash2 } from 'lucide-react';
import { api } from '../api';
import type { CharacterCard, GalleryAsset, Lorebook } from '../types';
import { GenerationProgressCard } from './GenerationFeedback';

interface AssetGalleryProps {
  assets: GalleryAsset[];
  characters: CharacterCard[];
  worlds: Lorebook[];
  onGalleryUpdated: () => void;
}

export const AssetGallery: React.FC<AssetGalleryProps> = ({
  assets,
  characters,
  worlds,
  onGalleryUpdated,
}) => {
  const [prompt, setPrompt] = useState(
    'relaxing on a teakwood lounge by the infinity pool at golden hour sunset, warm ocean breeze'
  );
  const [selectedCharId, setSelectedCharId] = useState<string>(
    characters[characters.length - 1]?.id || characters[0]?.id || ''
  );
  const [useBackstory, setUseBackstory] = useState(true);
  const [generating, setGenerating] = useState(false);

  const selectedChar = characters.find((c) => c.id === selectedCharId);
  const boundWorld = worlds.find((w) => w.id === selectedChar?.world_id);

  const handleQuickGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim() || generating) return;
    setGenerating(true);
    try {
      if (useBackstory && selectedChar) {
        await api.generateBackstoryImage({
          custom_prompt: prompt.trim(),
          character_id: selectedChar.id,
          world_id: selectedChar.world_id,
          include_character_visuals: true,
          include_scenario_backstory: true,
          include_world_lore: true,
        });
      } else {
        await api.generateGalleryImage({ prompt: prompt.trim() });
      }
      onGalleryUpdated();
    } finally {
      setGenerating(false);
    }
  };

  const handleDeleteAsset = async (assetId: string) => {
    await api.deleteGalleryAsset(assetId);
    onGalleryUpdated();
  };

  return (
    <div className="h-full overflow-y-auto p-6 bg-[#090b10]">
      <div className="max-w-6xl mx-auto space-y-6">
        {/* Backstory & Direct Synthesis Studio Bar */}
        <form
          onSubmit={handleQuickGenerate}
          className="bg-[#111520] p-4 rounded-2xl border border-white/10 space-y-3"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-bold text-white flex items-center gap-2">
              <ImageIcon className="w-4 h-4 text-cyan-400" />
              Standalone Backstory &amp; Concept Art Studio
            </h2>
            <span className="text-xs text-slate-400">{assets.length} Rendered Assets</span>
          </div>

          <div className="flex flex-wrap items-center gap-3 text-xs bg-[#0b0e17] p-2.5 rounded-xl border border-white/10">
            <label className="flex items-center gap-2 text-cyan-300 font-semibold cursor-pointer">
              <input
                type="checkbox"
                checked={useBackstory}
                onChange={(e) => setUseBackstory(e.target.checked)}
              />
              <Layers className="w-3.5 h-3.5" />
              Fuse Roleplay Character &amp; World Backstory:
            </label>

            <select
              aria-label="Character Backstory Source"
              value={selectedCharId}
              onChange={(e) => setSelectedCharId(e.target.value)}
              disabled={!useBackstory || generating}
              className="bg-[#151a28] border border-white/15 rounded-lg px-2.5 py-1 text-xs text-white disabled:opacity-40"
            >
              {characters.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({c.title})
                </option>
              ))}
            </select>

            {useBackstory && boundWorld && (
              <span className="text-[11px] px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                World: {boundWorld.name}
              </span>
            )}
          </div>

          <div className="flex gap-2">
            <input
              type="text"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              disabled={generating}
              placeholder="Describe any standalone scene, moment, or portrait..."
              className="flex-1 bg-[#171c2b] border border-white/15 rounded-xl px-3.5 py-2 text-sm text-white"
            />
            <button
              type="submit"
              disabled={generating || !prompt.trim()}
              className="px-4 py-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold text-xs flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
            >
              <Sparkles className="w-4 h-4" />
              {generating ? 'Synthesizing...' : 'Generate Artwork'}
            </button>
          </div>
        </form>

        {generating && (
          <GenerationProgressCard
            title="Synthesizing Standalone Artwork in ComfyUI SDXL..."
            subtitle={
              useBackstory && selectedChar
                ? `Injecting ${selectedChar.name}'s physical backstory & ${
                    boundWorld?.name || 'World'
                  } lore`
                : 'Executing direct SDXL prompt pipeline'
            }
            engineLabel="ComfyUI (sd_xl_base_1.0)"
            accent="cyan"
          />
        )}

        {/* Gallery Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {assets.map((asset) => {
            const char = characters.find((c) => c.id === asset.character_id);
            return (
              <div
                key={asset.id}
                className="bg-[#111520] rounded-2xl border border-white/10 overflow-hidden flex flex-col justify-between group hover:border-amber-500/40 transition"
              >
                <div
                  className="relative bg-black/50 overflow-hidden flex items-center justify-center"
                  style={{ aspectRatio: `${asset.width || 512} / ${asset.height || 768}` }}
                >
                  <img
                    src={asset.url}
                    alt={asset.prompt}
                    width={asset.width}
                    height={asset.height}
                    className="w-full h-full object-contain group-hover:scale-105 transition duration-300"
                  />
                  {char && (
                    <span className="absolute top-2.5 left-2.5 px-2 py-0.5 rounded-lg bg-black/75 text-amber-300 border border-amber-500/30 text-[10px] font-semibold">
                      {char.name}
                    </span>
                  )}
                  <div className="opacity-0 group-hover:opacity-100 focus-within:opacity-100 absolute top-2.5 right-2.5 flex items-center gap-1.5 transition">
                    <a
                      href={asset.url}
                      download
                      className="p-2 rounded-xl bg-black/80 text-white hover:text-amber-300 border border-white/15 transition"
                      title="Download PNG"
                    >
                      <Download className="w-4 h-4" />
                    </a>
                    <button
                      type="button"
                      onClick={() => handleDeleteAsset(asset.id)}
                      aria-label="Delete image asset"
                      className="p-2 rounded-xl bg-black/80 text-rose-300 hover:bg-rose-500/30 hover:text-rose-200 border border-rose-500/30 cursor-pointer transition"
                      title="Delete Asset"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
                <div className="p-3 space-y-1.5">
                  <p className="text-xs text-slate-200 line-clamp-2 leading-relaxed">
                    {asset.prompt}
                  </p>
                  <div className="flex items-center justify-between text-[10px] text-slate-400 font-mono pt-1 border-t border-white/5">
                    <span>Seed: {asset.seed}</span>
                    <span className="truncate max-w-[140px] text-cyan-300">
                      {asset.provider}
                    </span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
