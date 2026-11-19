import React, { useState, useRef } from 'react';
import {
  Plus,
  Save,
  Sparkles,
  Upload,
  Download,
  Trash2,
  MessageSquare,
  FileJson,
  Check,
  User,
  Wand2,
  X,
} from 'lucide-react';
import { api } from '../api';
import type { CharacterCard, Lorebook } from '../types';
import { GenerationProgressCard } from './GenerationFeedback';

interface CharacterForgeProps {
  characters: CharacterCard[];
  worlds: Lorebook[];
  onCharactersUpdated: (chars: CharacterCard[]) => void;
  onStartChatWithChar: (charId: string) => void;
  onGalleryUpdated: () => void;
}

export const CharacterForge: React.FC<CharacterForgeProps> = ({
  characters,
  worlds,
  onCharactersUpdated,
  onStartChatWithChar,
  onGalleryUpdated,
}) => {
  const [selectedId, setSelectedId] = useState<string>(characters[0]?.id || '');
  const [draft, setDraft] = useState<CharacterCard | null>(characters[0] || null);
  const [saving, setSaving] = useState(false);
  const [savedToast, setSavedToast] = useState(false);
  const [generatingAvatar, setGeneratingAvatar] = useState(false);
  const [importing, setImporting] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [newName, setNewName] = useState('');
  const [newBrief, setNewBrief] = useState('');
  const [newWorldId, setNewWorldId] = useState<string>(worlds[0]?.id || '');
  const [generatingProfile, setGeneratingProfile] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const selectCharacter = (card: CharacterCard) => {
    setIsCreating(false);
    setCreateError(null);
    setSelectedId(card.id);
    setDraft({ ...card });
  };

  const openCreateFlow = () => {
    setIsCreating(true);
    setNewName('');
    setNewBrief('');
    setNewWorldId(worlds[0]?.id || '');
    setCreateError(null);
  };

  const handleCreateBlank = async () => {
    setCreateError(null);
    const trimmedBrief = newBrief.trim();
    const resolvedName = newName.trim() || 'New Character';
    const newCard = await api.createCharacter(
      {
        name: resolvedName,
        title: 'Original Persona',
        description: trimmedBrief
          ? `{{char}} — ${trimmedBrief}`
          : '{{char}} is an original character forged in Hivemind Studio.',
        personality: '',
        scenario: '',
        first_mes: '',
        mes_example: '',
        tags: ['Original'],
        visual_prompt_tags: trimmedBrief
          ? `portrait of ${resolvedName}, ${trimmedBrief}, detailed concept art, 8k`
          : `portrait of ${resolvedName}, detailed character concept art, 8k`,
        world_id: newWorldId || null,
      },
      false
    );
    const nextList = [newCard, ...characters];
    onCharactersUpdated(nextList);
    selectCharacter(newCard);
  };

  const handleGenerateAndCreate = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!newBrief.trim() || generatingProfile) return;
    setGeneratingProfile(true);
    setCreateError(null);
    try {
      const profile = await api.generateCharacterProfile({
        brief: newBrief.trim(),
        name: newName.trim(),
        world_id: newWorldId || null,
      });
      const newCard = await api.createCharacter(
        {
          ...profile,
          world_id: newWorldId || null,
        },
        false
      );
      const nextList = [newCard, ...characters];
      onCharactersUpdated(nextList);
      selectCharacter(newCard);
    } catch (err: any) {
      setCreateError(err?.message || String(err));
    } finally {
      setGeneratingProfile(false);
    }
  };

  const handleRegenerateProfileForDraft = async () => {
    if (!draft || generatingProfile) return;
    const briefSource = (draft.description || draft.title || draft.name).trim();
    if (!briefSource) return;
    setGeneratingProfile(true);
    try {
      const profile = await api.generateCharacterProfile({
        brief: briefSource,
        name: draft.name,
        world_id: draft.world_id || null,
      });
      setDraft({
        ...draft,
        title: profile.title || draft.title,
        description: profile.description || draft.description,
        personality: profile.personality || draft.personality,
        scenario: profile.scenario || draft.scenario,
        first_mes: profile.first_mes || draft.first_mes,
        mes_example: profile.mes_example || draft.mes_example,
        tags: profile.tags?.length ? profile.tags : draft.tags,
        visual_prompt_tags: profile.visual_prompt_tags || draft.visual_prompt_tags,
      });
    } finally {
      setGeneratingProfile(false);
    }
  };

  const handleSave = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!draft) return;
    setSaving(true);
    try {
      const updated = await api.updateCharacter(draft.id, draft);
      const nextList = characters.map((c) => (c.id === updated.id ? updated : c));
      onCharactersUpdated(nextList);
      setDraft({ ...updated });
      setSavedToast(true);
      setTimeout(() => setSavedToast(false), 2000);
    } finally {
      setSaving(false);
    }
  };

  const handleGenerateAvatar = async () => {
    if (!draft || generatingAvatar) return;
    setGeneratingAvatar(true);
    try {
      await api.updateCharacter(draft.id, draft);
      const res = await api.generateCharacterAvatar(draft.id);
      const nextList = characters.map((c) => (c.id === res.character.id ? res.character : c));
      onCharactersUpdated(nextList);
      setDraft({ ...res.character });
      onGalleryUpdated();
    } finally {
      setGeneratingAvatar(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (characters.length <= 1) return;
    await api.deleteCharacter(id);
    const remaining = characters.filter((c) => c.id !== id);
    onCharactersUpdated(remaining);
    if (remaining[0]) {
      selectCharacter(remaining[0]);
    }
  };

  const handleImportFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    try {
      const imported = await api.importCharacterFile(file);
      const nextList = [imported, ...characters];
      onCharactersUpdated(nextList);
      selectCharacter(imported);
    } catch (err: any) {
      alert(`Import failed: ${err.message || err}`);
    } finally {
      setImporting(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  return (
    <div className="grid grid-cols-12 h-full overflow-hidden bg-[#090b10]">
      {/* Left Sidebar: Character Cards Deck */}
      <aside className="col-span-4 lg:col-span-3 border-r border-white/10 bg-[#0d1017] flex flex-col h-full overflow-hidden">
        <div className="p-3.5 border-b border-white/10 flex items-center justify-between gap-2">
          <div>
            <h2 className="text-sm font-bold text-white">Character Forge</h2>
            <p className="text-[11px] text-slate-400">Character V2 Cards &amp; Avatars</p>
          </div>
          <div className="flex items-center gap-1.5">
            <input
              ref={fileInputRef}
              type="file"
              accept=".png,.json"
              onChange={handleImportFile}
              className="hidden"
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={importing}
              className="px-2.5 py-1.5 rounded-lg bg-[#171c2b] hover:bg-white/10 text-slate-200 border border-white/10 text-xs flex items-center gap-1 cursor-pointer"
              title="Import Character Card V2 (PNG or JSON)"
            >
              <Upload className="w-3.5 h-3.5 text-amber-400" />
              {importing ? '...' : 'Import'}
            </button>
            <button
              type="button"
              onClick={openCreateFlow}
              className="px-2.5 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 font-semibold text-xs flex items-center gap-1 cursor-pointer"
            >
              <Plus className="w-3.5 h-3.5" />
              New
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-3 space-y-2.5">
          {characters.map((char) => {
            const isSelected = !isCreating && char.id === selectedId;
            const boundWorld = worlds.find((w) => w.id === char.world_id);
            const canDelete = characters.length > 1;
            return (
              <div
                key={char.id}
                onClick={() => selectCharacter(char)}
                className={`group p-3 rounded-2xl border transition cursor-pointer flex gap-3 items-center ${
                  isSelected
                    ? 'bg-amber-500/15 border-amber-500/50 shadow-lg shadow-amber-950/20'
                    : 'bg-[#121622]/80 border-white/10 hover:border-white/25'
                }`}
              >
                {char.avatar_url ? (
                  <img
                    src={char.avatar_url}
                    alt={char.name}
                    width={56}
                    height={56}
                    className="w-14 h-14 rounded-xl object-cover border border-white/15 shrink-0"
                  />
                ) : (
                  <div className="w-14 h-14 rounded-xl bg-[#171c2b] border border-white/10 flex items-center justify-center shrink-0 text-slate-500">
                    <User className="w-6 h-6" />
                  </div>
                )}
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-bold text-white truncate">{char.name}</div>
                  <div className="text-xs text-amber-300/90 truncate">{char.title}</div>
                  <div className="mt-1 flex items-center gap-1.5 flex-wrap">
                    {boundWorld && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 truncate max-w-[140px]">
                        {boundWorld.name}
                      </span>
                    )}
                    {char.tags.slice(0, 2).map((t) => (
                      <span
                        key={t}
                        className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-slate-300"
                      >
                        {t}
                      </span>
                    ))}
                  </div>
                </div>
                <button
                  type="button"
                  disabled={!canDelete}
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDelete(char.id);
                  }}
                  className={`p-1.5 rounded-lg border transition shrink-0 ${
                    canDelete
                      ? 'bg-rose-500/10 hover:bg-rose-500/25 text-rose-300 border-rose-500/20 opacity-80 group-hover:opacity-100 cursor-pointer'
                      : 'bg-white/5 text-slate-600 border-white/5 opacity-40 cursor-not-allowed'
                  }`}
                  title={canDelete ? `Delete ${char.name}` : 'Keep at least one character'}
                  aria-label={`Delete ${char.name}`}
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            );
          })}
        </div>
      </aside>

      {/* Main Editor & Portrait Forge */}
      <section className="col-span-8 lg:col-span-9 h-full overflow-y-auto p-6">
        {isCreating ? (
          <form onSubmit={handleGenerateAndCreate} className="max-w-3xl mx-auto space-y-6">
            <div className="flex items-center justify-between pb-4 border-b border-white/10">
              <div>
                <h1 className="text-xl font-bold text-white flex items-center gap-2">
                  <Sparkles className="w-5 h-5 text-amber-400" />
                  Forge New Character
                </h1>
                <p className="text-xs text-slate-400 mt-0.5">
                  Describe your character briefly first. You can generate backstory &amp; personality with AI, and generate a portrait later whenever you&apos;re ready.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setIsCreating(false)}
                className="p-2 rounded-xl bg-[#161b29] hover:bg-white/10 text-slate-300 border border-white/10 cursor-pointer"
                title="Cancel"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {createError && (
              <div className="p-3 rounded-xl bg-rose-500/15 border border-rose-500/30 text-xs text-rose-200">
                {createError}
              </div>
            )}

            <div className="bg-[#111520] p-6 rounded-2xl border border-white/10 space-y-5">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                    Character Name <span className="text-slate-500 font-normal">(optional)</span>
                  </label>
                  <input
                    type="text"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    placeholder="e.g. Captain Lyra Vance (leave blank for AI)"
                    className="w-full bg-[#171c2b] border border-white/15 rounded-xl px-3 py-2 text-sm text-white placeholder:text-slate-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                    Bound World Lorebook
                  </label>
                  <select
                    value={newWorldId}
                    onChange={(e) => setNewWorldId(e.target.value)}
                    className="w-full bg-[#171c2b] border border-white/15 rounded-xl px-3 py-2 text-sm text-white"
                  >
                    <option value="">— No Bound World —</option>
                    {worlds.map((w) => (
                      <option key={w.id} value={w.id}>
                        {w.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                  Brief Character Concept / Description
                </label>
                <textarea
                  rows={4}
                  value={newBrief}
                  onChange={(e) => setNewBrief(e.target.value)}
                  placeholder="Describe your character in 1–3 sentences (e.g. A retired sky-pirate navigator who now runs a floating tea shop and secretly guards an ancient star map)..."
                  className="w-full bg-[#171c2b] border border-white/15 rounded-xl p-3 text-sm text-slate-100 placeholder:text-slate-500 leading-relaxed"
                />
              </div>

              <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
                <button
                  type="button"
                  onClick={handleCreateBlank}
                  disabled={generatingProfile}
                  className="px-4 py-2 rounded-xl bg-[#171c2b] hover:bg-white/10 text-slate-200 border border-white/15 text-xs font-semibold cursor-pointer disabled:opacity-50"
                >
                  Create Blank Character (Manual)
                </button>

                <button
                  type="submit"
                  disabled={!newBrief.trim() || generatingProfile}
                  className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-amber-500 to-violet-500 hover:from-amber-400 hover:to-violet-400 text-slate-950 font-bold text-xs flex items-center gap-2 cursor-pointer shadow-lg disabled:opacity-50"
                >
                  <Wand2 className="w-4 h-4" />
                  {generatingProfile
                    ? 'Generating Backstory & Personality...'
                    : 'Generate Backstory, Personality & Greeting'}
                </button>
              </div>
            </div>
          </form>
        ) : draft ? (
          <form onSubmit={handleSave} className="max-w-5xl mx-auto space-y-6">
            {/* Top Action Header */}
            <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-white/10">
              <div>
                <h1 className="text-xl font-bold text-white flex items-center gap-2">
                  {draft.name}
                  <span className="text-xs px-2.5 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/30">
                    chara_card_v2
                  </span>
                </h1>
                <p className="text-xs text-slate-400">{draft.title}</p>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => onStartChatWithChar(draft.id)}
                  className="px-3 py-1.5 rounded-xl bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-400/30 text-emerald-200 text-xs font-semibold flex items-center gap-1.5 cursor-pointer"
                >
                  <MessageSquare className="w-3.5 h-3.5" />
                  Roleplay Chat
                </button>

                <a
                  href={`/api/characters/${draft.id}/export-png`}
                  download
                  className="px-3 py-1.5 rounded-xl bg-[#161b29] hover:bg-white/10 border border-white/15 text-slate-200 text-xs font-medium flex items-center gap-1.5"
                  title="Download PNG with embedded Character Card V2 metadata"
                >
                  <Download className="w-3.5 h-3.5 text-amber-400" />
                  Export Card PNG
                </a>

                <a
                  href={`/api/characters/${draft.id}/export-json`}
                  target="_blank"
                  rel="noreferrer"
                  className="px-3 py-1.5 rounded-xl bg-[#161b29] hover:bg-white/10 border border-white/15 text-slate-200 text-xs font-medium flex items-center gap-1.5"
                >
                  <FileJson className="w-3.5 h-3.5 text-sky-400" />
                  V2 JSON
                </a>

                <button
                  type="submit"
                  disabled={saving}
                  className="px-4 py-1.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs flex items-center gap-1.5 cursor-pointer"
                >
                  {savedToast ? <Check className="w-3.5 h-3.5" /> : <Save className="w-3.5 h-3.5" />}
                  {savedToast ? 'Saved!' : saving ? 'Saving...' : 'Save Card'}
                </button>

                {characters.length > 1 && (
                  <button
                    type="button"
                    onClick={() => handleDelete(draft.id)}
                    className="p-1.5 rounded-xl bg-rose-500/15 hover:bg-rose-500/30 text-rose-300 border border-rose-500/30 cursor-pointer"
                    title="Delete Character"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                )}
              </div>
            </div>

            {/* Portrait & Visual Prompt Studio Card */}
            {generatingAvatar && (
              <GenerationProgressCard
                title={`Synthesizing Portrait for ${draft.name}...`}
                subtitle="Running ComfyUI SDXL with character visual tags & bound world aesthetic"
                engineLabel="ComfyUI (sd_xl_base_1.0)"
                stages={[
                  'Assembling Character Visual Tags',
                  'Sampling SDXL Latents in ComfyUI',
                  'Updating Character Card Avatar',
                ]}
                accent="violet"
              />
            )}
            <div className="grid grid-cols-1 md:grid-cols-12 gap-6 bg-[#111520] p-5 rounded-2xl border border-white/10">
              <div className="md:col-span-4 flex flex-col items-center space-y-3">
                <div className="relative group w-56 h-56 rounded-2xl overflow-hidden border-2 border-amber-500/40 bg-black/40 shadow-xl flex items-center justify-center">
                  {draft.avatar_url ? (
                    <img
                      src={draft.avatar_url}
                      alt={draft.name}
                      width={224}
                      height={224}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <div className="flex flex-col items-center text-center px-4 text-slate-400">
                      <User className="w-12 h-12 mb-2 text-slate-500" />
                      <span className="text-xs font-medium text-slate-300">No portrait yet</span>
                      <span className="text-[11px] text-slate-500 mt-1">
                        Refine visual tags, then click Generate Portrait
                      </span>
                    </div>
                  )}
                </div>
                <button
                  type="button"
                  onClick={handleGenerateAvatar}
                  disabled={generatingAvatar}
                  className="w-56 py-2 px-3 rounded-xl bg-gradient-to-r from-amber-500 to-violet-500 hover:from-amber-400 hover:to-violet-400 text-slate-950 font-bold text-xs flex items-center justify-center gap-1.5 cursor-pointer shadow-md disabled:opacity-50"
                >
                  <Sparkles className="w-4 h-4" />
                  {generatingAvatar
                    ? 'Synthesizing Portrait...'
                    : draft.avatar_url
                    ? 'Generate New Portrait'
                    : 'Generate Portrait'}
                </button>
                <button
                  type="button"
                  onClick={handleRegenerateProfileForDraft}
                  disabled={generatingProfile}
                  className="w-56 py-1.5 px-3 rounded-xl bg-[#171c2b] hover:bg-white/10 text-slate-200 border border-white/15 text-xs font-medium flex items-center justify-center gap-1.5 cursor-pointer disabled:opacity-50"
                  title="Use the current Description/Name to generate Backstory, Personality, Scenario & Greeting"
                >
                  <Wand2 className="w-3.5 h-3.5 text-amber-400" />
                  {generatingProfile ? 'Generating Profile...' : 'AI Expand Backstory & Traits'}
                </button>
              </div>

              <div className="md:col-span-8 space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1">
                      Character Name
                    </label>
                    <input
                      type="text"
                      value={draft.name}
                      onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                      className="w-full bg-[#171c2b] border border-white/15 rounded-xl px-3 py-2 text-sm text-white"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1">
                      Epithet / Role Title
                    </label>
                    <input
                      type="text"
                      value={draft.title}
                      onChange={(e) => setDraft({ ...draft, title: e.target.value })}
                      className="w-full bg-[#171c2b] border border-white/15 rounded-xl px-3 py-2 text-sm text-white"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1">
                      Bound World Lorebook
                    </label>
                    <select
                      value={draft.world_id || ''}
                      onChange={(e) =>
                        setDraft({ ...draft, world_id: e.target.value || null })
                      }
                      className="w-full bg-[#171c2b] border border-white/15 rounded-xl px-3 py-2 text-sm text-white"
                    >
                      <option value="">— No Bound World —</option>
                      {worlds.map((w) => (
                        <option key={w.id} value={w.id}>
                          {w.name}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1">
                      Tags (comma-separated)
                    </label>
                    <input
                      type="text"
                      value={draft.tags.join(', ')}
                      onChange={(e) =>
                        setDraft({
                          ...draft,
                          tags: e.target.value
                            .split(',')
                            .map((t) => t.trim())
                            .filter(Boolean),
                        })
                      }
                      className="w-full bg-[#171c2b] border border-white/15 rounded-xl px-3 py-2 text-sm text-white"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-amber-300 mb-1">
                    Visual Prompt Tags (Used by Image Engine & Comfy Node Studio)
                  </label>
                  <textarea
                    rows={2}
                    value={draft.visual_prompt_tags}
                    onChange={(e) => setDraft({ ...draft, visual_prompt_tags: e.target.value })}
                    className="w-full bg-[#171c2b] border border-amber-500/30 rounded-xl px-3 py-2 text-xs text-slate-100 font-mono"
                  />
                </div>
              </div>
            </div>

            {/* Core Character Persona Fields */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="bg-[#111520] p-4 rounded-2xl border border-white/10 space-y-2">
                <label className="block text-xs font-semibold text-slate-300">
                  Description & Backstory (Supports {'{{char}}'} & {'{{user}}'})
                </label>
                <textarea
                  rows={4}
                  value={draft.description}
                  onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                  className="w-full bg-[#171c2b] border border-white/10 rounded-xl p-3 text-xs text-slate-200 leading-relaxed"
                />
              </div>

              <div className="bg-[#111520] p-4 rounded-2xl border border-white/10 space-y-2">
                <label className="block text-xs font-semibold text-slate-300">
                  Personality & Speech Traits
                </label>
                <textarea
                  rows={2}
                  value={draft.personality}
                  onChange={(e) => setDraft({ ...draft, personality: e.target.value })}
                  className="w-full bg-[#171c2b] border border-white/10 rounded-xl p-3 text-xs text-slate-200"
                />
                <label className="block text-xs font-semibold text-slate-300 pt-1">
                  Current Scenario
                </label>
                <textarea
                  rows={2}
                  value={draft.scenario}
                  onChange={(e) => setDraft({ ...draft, scenario: e.target.value })}
                  className="w-full bg-[#171c2b] border border-white/10 rounded-xl p-3 text-xs text-slate-200"
                />
              </div>
            </div>

            <div className="bg-[#111520] p-4 rounded-2xl border border-white/10 space-y-2">
              <label className="block text-xs font-semibold text-slate-300">
                First Message (Opening Greeting in Roleplay Chat)
              </label>
              <textarea
                rows={4}
                value={draft.first_mes}
                onChange={(e) => setDraft({ ...draft, first_mes: e.target.value })}
                className="w-full bg-[#171c2b] border border-white/10 rounded-xl p-3 text-xs text-slate-200 leading-relaxed"
              />
            </div>

            <details className="bg-[#111520] p-4 rounded-2xl border border-white/10">
              <summary className="text-xs font-semibold text-slate-300 cursor-pointer">
                Advanced Character V2 Fields (Example Dialogue &amp; System Prompt Override)
              </summary>
              <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs text-slate-400 mb-1">
                    Example Dialogue (mes_example)
                  </label>
                  <textarea
                    rows={4}
                    value={draft.mes_example}
                    onChange={(e) => setDraft({ ...draft, mes_example: e.target.value })}
                    className="w-full bg-[#171c2b] border border-white/10 rounded-xl p-3 text-xs text-slate-200 font-mono"
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">
                    System Prompt Override
                  </label>
                  <textarea
                    rows={4}
                    value={draft.system_prompt}
                    onChange={(e) => setDraft({ ...draft, system_prompt: e.target.value })}
                    className="w-full bg-[#171c2b] border border-white/10 rounded-xl p-3 text-xs text-slate-200 font-mono"
                  />
                </div>
              </div>
            </details>
          </form>
        ) : null}
      </section>
    </div>
  );
};
