import React, { useState } from 'react';
import {
  Plus,
  Save,
  Sparkles,
  Search,
  BookOpen,
  Trash2,
  MapPin,
  Shield,
  Wand,
  Scroll,
  Gem,
  Users,
  Check,
} from 'lucide-react';
import { api } from '../api';
import type { Lorebook, LoreCategory, LoreEntry, TriggeredLoreInfo } from '../types';

interface WorldCodexProps {
  worlds: Lorebook[];
  onWorldsUpdated: (worlds: Lorebook[]) => void;
  onGalleryUpdated: () => void;
}

const CATEGORY_META: Record<LoreCategory, { label: string; color: string; icon: React.ReactNode }> = {
  location: { label: 'Location', color: 'text-emerald-300 bg-emerald-500/15 border-emerald-500/30', icon: <MapPin className="w-3.5 h-3.5" /> },
  faction: { label: 'Faction', color: 'text-amber-300 bg-amber-500/15 border-amber-500/30', icon: <Shield className="w-3.5 h-3.5" /> },
  magic_tech: { label: 'Magic / Tech', color: 'text-violet-300 bg-violet-500/15 border-violet-500/30', icon: <Wand className="w-3.5 h-3.5" /> },
  artifact: { label: 'Artifact', color: 'text-cyan-300 bg-cyan-500/15 border-cyan-500/30', icon: <Gem className="w-3.5 h-3.5" /> },
  history: { label: 'History', color: 'text-rose-300 bg-rose-500/15 border-rose-500/30', icon: <Scroll className="w-3.5 h-3.5" /> },
  relationship: { label: 'Relationship', color: 'text-pink-300 bg-pink-500/15 border-pink-500/30', icon: <Users className="w-3.5 h-3.5" /> },
  rule: { label: 'World Rule', color: 'text-slate-300 bg-white/10 border-white/20', icon: <BookOpen className="w-3.5 h-3.5" /> },
};

export const WorldCodex: React.FC<WorldCodexProps> = ({
  worlds,
  onWorldsUpdated,
  onGalleryUpdated,
}) => {
  const [selectedWorldId, setSelectedWorldId] = useState<string>(worlds[0]?.id || '');
  const [draftWorld, setDraftWorld] = useState<Lorebook | null>(worlds[0] || null);
  const [saving, setSaving] = useState(false);
  const [savedToast, setSavedToast] = useState(false);
  const [renderingEntryId, setRenderingEntryId] = useState<string | null>(null);

  // Lore Scanner Testbench state
  const [scanInput, setScanInput] = useState(
    'We ascend the Spire of Echoes to confront the Order of the Glass Hourglass with the pendulum.'
  );
  const [scanResult, setScanResult] = useState<{
    triggered: TriggeredLoreInfo[];
    context_block: string;
    visual_tags_block: string;
  } | null>(null);

  const selectWorld = (w: Lorebook) => {
    setSelectedWorldId(w.id);
    setDraftWorld(JSON.parse(JSON.stringify(w)));
    setScanResult(null);
  };

  const handleCreateWorld = async () => {
    const created = await api.createWorld({
      name: 'New Mythic Realm',
      subtitle: 'Custom Lorebook & World Codex',
      description: 'A richly detailed world with interconnected factions, locations, and visual prompts.',
      aesthetic_style: 'epic fantasy concept art, volumetric lighting, intricate architecture, 8k',
      entries: [
        {
          id: `lore_${Date.now()}`,
          title: 'The Nexus Sanctum',
          keys: ['nexus', 'sanctum', 'temple'],
          secondary_keys: [],
          category: 'location',
          content: 'At the heart of the realm stands the Nexus Sanctum, where leyline currents converge.',
          visual_description: 'ancient floating sanctuary surrounded by glowing crystalline monoliths',
          image_url: '',
          constant: true,
          enabled: true,
          priority: 80,
        },
      ],
    });
    const next = [created, ...worlds];
    onWorldsUpdated(next);
    selectWorld(created);
  };

  const handleSaveWorld = async () => {
    if (!draftWorld) return;
    setSaving(true);
    try {
      const updated = await api.updateWorld(draftWorld.id, draftWorld);
      const next = worlds.map((w) => (w.id === updated.id ? updated : w));
      onWorldsUpdated(next);
      setDraftWorld(JSON.parse(JSON.stringify(updated)));
      setSavedToast(true);
      setTimeout(() => setSavedToast(false), 2000);
    } finally {
      setSaving(false);
    }
  };

  const handleAddEntry = () => {
    if (!draftWorld) return;
    const newEntry: LoreEntry = {
      id: `lore_${Date.now()}`,
      title: 'New Codex Entry',
      keys: ['keyword1', 'keyword2'],
      secondary_keys: [],
      category: 'location',
      content: 'Describe how this location, faction, or artifact shapes the world when triggered...',
      visual_description: 'dramatic concept art, atmospheric lighting, detailed architecture',
      image_url: '',
      constant: false,
      enabled: true,
      priority: 60,
    };
    setDraftWorld({
      ...draftWorld,
      entries: [newEntry, ...draftWorld.entries],
    });
  };

  const handleUpdateEntry = (entryId: string, patch: Partial<LoreEntry>) => {
    if (!draftWorld) return;
    setDraftWorld({
      ...draftWorld,
      entries: draftWorld.entries.map((e) => (e.id === entryId ? { ...e, ...patch } : e)),
    });
  };

  const handleDeleteEntry = (entryId: string) => {
    if (!draftWorld) return;
    setDraftWorld({
      ...draftWorld,
      entries: draftWorld.entries.filter((e) => e.id !== entryId),
    });
  };

  const handleGenerateEntryArt = async (entryId: string) => {
    if (!draftWorld || renderingEntryId) return;
    setRenderingEntryId(entryId);
    try {
      await api.updateWorld(draftWorld.id, draftWorld);
      const res = await api.generateLoreEntryImage(draftWorld.id, entryId);
      const next = worlds.map((w) => (w.id === res.world.id ? res.world : w));
      onWorldsUpdated(next);
      setDraftWorld(JSON.parse(JSON.stringify(res.world)));
      onGalleryUpdated();
    } finally {
      setRenderingEntryId(null);
    }
  };

  const handleRunScanner = async () => {
    if (!draftWorld) return;
    await api.updateWorld(draftWorld.id, draftWorld);
    const res = await api.scanLorebook(draftWorld.id, scanInput, 'Lyra Vance', 'Traveler');
    setScanResult(res);
  };

  return (
    <div className="grid grid-cols-12 h-full overflow-hidden bg-[#090b10]">
      {/* Left Sidebar: World Lorebooks */}
      <aside className="col-span-4 lg:col-span-3 border-r border-white/10 bg-[#0d1017] flex flex-col h-full overflow-hidden">
        <div className="p-3.5 border-b border-white/10 flex items-center justify-between">
          <div>
            <h2 className="text-sm font-bold text-white">World Codex</h2>
            <p className="text-[11px] text-slate-400">Keyword-Triggered Lorebooks</p>
          </div>
          <button
            type="button"
            onClick={handleCreateWorld}
            className="px-2.5 py-1.5 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-xs flex items-center gap-1 cursor-pointer"
          >
            <Plus className="w-3.5 h-3.5" />
            New World
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-3 space-y-2.5">
          {worlds.map((w) => {
            const isSelected = w.id === selectedWorldId;
            return (
              <div
                key={w.id}
                onClick={() => selectWorld(w)}
                className={`p-3.5 rounded-2xl border cursor-pointer transition space-y-1.5 ${
                  isSelected
                    ? 'bg-emerald-500/15 border-emerald-500/50 text-white'
                    : 'bg-[#121622]/80 border-white/10 hover:border-white/25 text-slate-200'
                }`}
              >
                <div className="text-sm font-bold">{w.name}</div>
                <div className="text-xs text-emerald-300/90">{w.subtitle}</div>
                <p className="text-[11px] text-slate-400 line-clamp-2">{w.description}</p>
                <div className="pt-1 flex items-center gap-2 text-[11px] text-slate-400">
                  <span className="px-2 py-0.5 rounded bg-white/5 text-slate-300">
                    {w.entries.length} Lore Entries
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </aside>

      {/* Center/Right: World Metadata, Scanner Testbench & Lore Entries */}
      <section className="col-span-8 lg:col-span-9 h-full overflow-y-auto p-6">
        {draftWorld ? (
          <div className="max-w-5xl mx-auto space-y-6">
            {/* World Header */}
            <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-white/10">
              <div>
                <h1 className="text-xl font-bold text-white">{draftWorld.name}</h1>
                <p className="text-xs text-emerald-300">{draftWorld.subtitle}</p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleAddEntry}
                  className="px-3 py-1.5 rounded-xl bg-white/10 hover:bg-white/15 border border-white/15 text-white text-xs font-semibold flex items-center gap-1.5 cursor-pointer"
                >
                  <Plus className="w-3.5 h-3.5 text-emerald-400" />
                  Add Lore Entry
                </button>
                <button
                  type="button"
                  onClick={handleSaveWorld}
                  disabled={saving}
                  className="px-4 py-1.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold text-xs flex items-center gap-1.5 cursor-pointer"
                >
                  {savedToast ? <Check className="w-3.5 h-3.5" /> : <Save className="w-3.5 h-3.5" />}
                  {savedToast ? 'Saved!' : saving ? 'Saving...' : 'Save World Codex'}
                </button>
              </div>
            </div>

            {/* World Global Settings */}
            <div className="bg-[#111520] p-4 rounded-2xl border border-white/10 grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">
                    World Name
                  </label>
                  <input
                    type="text"
                    value={draftWorld.name}
                    onChange={(e) => setDraftWorld({ ...draftWorld, name: e.target.value })}
                    className="w-full bg-[#171c2b] border border-white/15 rounded-xl px-3 py-1.5 text-sm text-white"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-emerald-300 mb-1">
                    Global Aesthetic Style (Injected into Image Pipelines)
                  </label>
                  <input
                    type="text"
                    value={draftWorld.aesthetic_style}
                    onChange={(e) =>
                      setDraftWorld({ ...draftWorld, aesthetic_style: e.target.value })
                    }
                    className="w-full bg-[#171c2b] border border-emerald-500/30 rounded-xl px-3 py-1.5 text-xs text-slate-100 font-mono"
                  />
                </div>
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  World Overview
                </label>
                <textarea
                  rows={4}
                  value={draftWorld.description}
                  onChange={(e) => setDraftWorld({ ...draftWorld, description: e.target.value })}
                  className="w-full bg-[#171c2b] border border-white/15 rounded-xl p-2.5 text-xs text-slate-200 leading-relaxed"
                />
              </div>
            </div>

            {/* Live Lore Scanner Testbench */}
            <div className="bg-[#111722] p-4 rounded-2xl border border-emerald-500/30 space-y-3">
              <div className="flex items-center justify-between">
                <div className="text-xs font-bold text-emerald-300 flex items-center gap-1.5">
                  <Search className="w-3.5 h-3.5" />
                  Live Lorebook Keyword Scanner Testbench
                </div>
                <span className="text-[11px] text-slate-400">
                  Simulate how chat messages or node inputs trigger World Info
                </span>
              </div>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={scanInput}
                  onChange={(e) => setScanInput(e.target.value)}
                  className="flex-1 bg-[#171d2c] border border-white/15 rounded-xl px-3 py-2 text-xs text-white"
                  placeholder="Type sample dialogue or action to test keyword triggers..."
                />
                <button
                  type="button"
                  onClick={handleRunScanner}
                  className="px-4 py-2 rounded-xl bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-400/40 text-emerald-200 text-xs font-semibold cursor-pointer"
                >
                  Test Triggers
                </button>
              </div>
              {scanResult && (
                <div className="p-3 rounded-xl bg-[#0b0e16] border border-white/10 space-y-2 text-xs">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-slate-400 font-semibold">Matched Entries:</span>
                    {scanResult.triggered.map((t) => (
                      <span
                        key={t.entry_id}
                        className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                      >
                        {t.title} ({t.matched_keys.join(', ')})
                      </span>
                    ))}
                  </div>
                  <div className="text-[11px] text-amber-300/90 font-mono">
                    <strong>Assembled Visual Prompt:</strong> {scanResult.visual_tags_block}
                  </div>
                </div>
              )}
            </div>

            {/* Lore Entries List */}
            <div className="space-y-4">
              {draftWorld.entries.map((entry) => {
                const catMeta = CATEGORY_META[entry.category] || CATEGORY_META.location;
                return (
                  <div
                    key={entry.id}
                    className="bg-[#111520] p-4 rounded-2xl border border-white/10 grid grid-cols-1 md:grid-cols-12 gap-4"
                  >
                    {/* Entry Concept Art Column */}
                    <div className="md:col-span-3 flex flex-col items-center justify-between space-y-2">
                      {entry.image_url ? (
                        <img
                          src={entry.image_url}
                          alt={entry.title}
                          width={180}
                          height={180}
                          className="w-full h-36 rounded-xl object-cover border border-white/15"
                        />
                      ) : (
                        <div className="w-full h-36 rounded-xl bg-[#171c2b] border border-dashed border-white/15 flex flex-col items-center justify-center text-xs text-slate-400 p-3 text-center">
                          No Concept Art Rendered Yet
                        </div>
                      )}
                      <button
                        type="button"
                        onClick={() => handleGenerateEntryArt(entry.id)}
                        disabled={renderingEntryId === entry.id}
                        className="w-full py-1.5 px-2.5 rounded-xl bg-amber-500/20 hover:bg-amber-500/30 border border-amber-400/30 text-amber-200 text-xs font-semibold flex items-center justify-center gap-1.5 cursor-pointer disabled:opacity-50"
                      >
                        <Sparkles className="w-3.5 h-3.5" />
                        {renderingEntryId === entry.id ? 'Rendering...' : 'Render Concept Art'}
                      </button>
                    </div>

                    {/* Entry Fields Column */}
                    <div className="md:col-span-9 space-y-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex items-center gap-2 flex-1 min-w-[200px]">
                          <span
                            className={`text-xs px-2.5 py-1 rounded-lg border flex items-center gap-1 font-semibold ${catMeta.color}`}
                          >
                            {catMeta.icon}
                            {catMeta.label}
                          </span>
                          <input
                            type="text"
                            value={entry.title}
                            onChange={(e) =>
                              handleUpdateEntry(entry.id, { title: e.target.value })
                            }
                            className="flex-1 bg-[#171c2b] border border-white/15 rounded-xl px-3 py-1.5 text-sm font-bold text-white"
                          />
                        </div>

                        <div className="flex items-center gap-3">
                          <select
                            aria-label="Entry Category"
                            value={entry.category}
                            onChange={(e) =>
                              handleUpdateEntry(entry.id, {
                                category: e.target.value as LoreCategory,
                              })
                            }
                            className="bg-[#171c2b] border border-white/15 rounded-lg px-2 py-1 text-xs text-slate-200"
                          >
                            <option value="location">Location</option>
                            <option value="faction">Faction</option>
                            <option value="magic_tech">Magic / Tech</option>
                            <option value="artifact">Artifact</option>
                            <option value="history">History</option>
                            <option value="relationship">Relationship</option>
                            <option value="rule">World Rule</option>
                          </select>

                          <label className="flex items-center gap-1.5 text-xs text-slate-300 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={entry.constant}
                              onChange={(e) =>
                                handleUpdateEntry(entry.id, { constant: e.target.checked })
                              }
                            />
                            Constant
                          </label>

                          <button
                            type="button"
                            onClick={() => handleDeleteEntry(entry.id)}
                            className="p-1.5 text-slate-400 hover:text-rose-400 cursor-pointer"
                            title="Delete Entry"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </div>

                      <div className="grid grid-cols-1 sm:grid-cols-12 gap-3">
                        <div className="sm:col-span-9">
                          <label className="block text-[11px] text-slate-400 mb-1">
                            Trigger Keywords (comma-separated)
                          </label>
                          <input
                            type="text"
                            value={entry.keys.join(', ')}
                            onChange={(e) =>
                              handleUpdateEntry(entry.id, {
                                keys: e.target.value
                                  .split(',')
                                  .map((k) => k.trim())
                                  .filter(Boolean),
                              })
                            }
                            className="w-full bg-[#171c2b] border border-white/15 rounded-xl px-3 py-1.5 text-xs text-emerald-300 font-mono"
                          />
                        </div>
                        <div className="sm:col-span-3">
                          <label className="block text-[11px] text-slate-400 mb-1">
                            Priority (0-100)
                          </label>
                          <input
                            type="number"
                            value={entry.priority}
                            onChange={(e) =>
                              handleUpdateEntry(entry.id, {
                                priority: Number(e.target.value) || 50,
                              })
                            }
                            className="w-full bg-[#171c2b] border border-white/15 rounded-xl px-3 py-1.5 text-xs text-white"
                          />
                        </div>
                      </div>

                      <div>
                        <label className="block text-[11px] text-slate-400 mb-1">
                          Lore Content (Injected into LLM Prompt when triggered)
                        </label>
                        <textarea
                          rows={2}
                          value={entry.content}
                          onChange={(e) =>
                            handleUpdateEntry(entry.id, { content: e.target.value })
                          }
                          className="w-full bg-[#171c2b] border border-white/10 rounded-xl p-2.5 text-xs text-slate-200"
                        />
                      </div>

                      <div>
                        <label className="block text-[11px] text-amber-300/90 mb-1">
                          Visual Prompt Descriptor (Injected into Image Nodes & Scene Renderer)
                        </label>
                        <input
                          type="text"
                          value={entry.visual_description}
                          onChange={(e) =>
                            handleUpdateEntry(entry.id, { visual_description: e.target.value })
                          }
                          className="w-full bg-[#171c2b] border border-amber-500/25 rounded-xl px-3 py-1.5 text-xs text-slate-200 font-mono"
                        />
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ) : null}
      </section>
    </div>
  );
};
