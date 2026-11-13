import React, { useState, useRef, useEffect } from 'react';
import {
  Send,
  Sparkles,
  Image as ImageIcon,
  ChevronLeft,
  ChevronRight,
  Plus,
  Trash2,
  BookOpen,
  UserCheck,
  Wand2,
  MessageSquare,
  Camera,
  Download,
  Layers,
  Loader2,
  Pin,
  PinOff,
  RefreshCw,
} from 'lucide-react';
import { api } from '../api';
import type {
  CharacterCard,
  ChatSession,
  GalleryAsset,
  Lorebook,
  SceneState,
  TriggeredLoreInfo,
} from '../types';
import { GenerationProgressCard, useElapsedTimer } from './GenerationFeedback';

interface RoleplayChatProps {
  characters: CharacterCard[];
  worlds: Lorebook[];
  chats: ChatSession[];
  gallery: GalleryAsset[];
  activeChatId: string;
  onSelectChat: (id: string) => void;
  onChatsUpdated: (chats: ChatSession[], newActiveId?: string) => void;
  onGalleryUpdated: () => void;
  onOpenWorkflowWithChar: (charId: string, worldId?: string | null) => void;
}

function renderFormattedRoleplayText(text: string) {
  const paragraphs = text.split(/\n\n+/);
  return paragraphs.map((para, pIdx) => {
    const tokens = para.split(/(\*[^*]+\*|"[^"]+")/g);
    return (
      <p key={pIdx} className="leading-relaxed mb-2.5 last:mb-0">
        {tokens.map((tok, tIdx) => {
          if (tok.startsWith('*') && tok.endsWith('*') && tok.length > 2) {
            return (
              <em key={tIdx} className="text-amber-300/90 italic font-serif">
                {tok.slice(1, -1)}
              </em>
            );
          }
          if (tok.startsWith('"') && tok.endsWith('"') && tok.length > 2) {
            return (
              <span key={tIdx} className="text-white font-medium">
                {tok}
              </span>
            );
          }
          return <span key={tIdx} className="text-slate-200">{tok}</span>;
        })}
      </p>
    );
  });
}

export const RoleplayChat: React.FC<RoleplayChatProps> = ({
  characters,
  worlds,
  chats,
  gallery,
  activeChatId,
  onSelectChat,
  onChatsUpdated,
  onGalleryUpdated,
  onOpenWorkflowWithChar,
}) => {
  const [inputMessage, setInputMessage] = useState('');
  const [autoIllustrate, setAutoIllustrate] = useState(false);
  const [sending, setSending] = useState(false);
  const [pendingUserText, setPendingUserText] = useState<string | null>(null);
  const [illustratingMsgId, setIllustratingMsgId] = useState<string | null>(null);
  const [editedScenePrompts, setEditedScenePrompts] = useState<Record<string, string>>({});
  const [checkpointOpen, setCheckpointOpen] = useState(false);
  const [checkpointDraft, setCheckpointDraft] = useState<string>('');
  const [updatingCheckpoint, setUpdatingCheckpoint] = useState(false);
  const [swipingMsgId, setSwipingMsgId] = useState<string | null>(null);
  const [lastProvider, setLastProvider] = useState<string>('Ollama / ComfyUI Hybrid');
  const [newChatCharId, setNewChatCharId] = useState<string>(characters[0]?.id || '');

  // Right sidebar collapsible & tab: 'backstory_studio' | 'lore_inspector' | 'scene_state'
  const [rightPanelOpen, setRightPanelOpen] = useState(true);
  const [rightTab, setRightTab] = useState<
    'backstory_studio' | 'lore_inspector' | 'scene_state'
  >('backstory_studio');
  const [visibleSnapshotCount, setVisibleSnapshotCount] = useState(6);
  const [savingSceneState, setSavingSceneState] = useState(false);
  const [sceneStateDraft, setSceneStateDraft] = useState<SceneState>({
    location: '',
    time_and_lighting: '',
    weather: '',
    atmosphere: '',
    attire: '',
    hairstyle: '',
    makeup: '',
    skin_and_condition: '',
    pose_and_action: '',
    pinned_fields: [],
  });

  // Backstory Standalone Image Generator state
  const [backstoryPrompt, setBackstoryPrompt] = useState(
    'relaxing by the candlelit infinity pool overlooking the turquoise lagoon at sunset, warm golden hour breeze'
  );
  const [includeCharVisuals, setIncludeCharVisuals] = useState(true);
  const [includeScenario, setIncludeScenario] = useState(true);
  const [includeWorldLore, setIncludeWorldLore] = useState(true);
  const [useLlmDirector, setUseLlmDirector] = useState(true);
  const [renderMode, setRenderMode] = useState<
    'hybrid_refiner' | 'single_stylized' | 'single_raw'
  >('single_stylized');
  const [faceDetailer, setFaceDetailer] = useState(true);
  const [aspectRatio, setAspectRatio] = useState<
    '768x1024' | '512x768' | '768x768' | '1024x768' | '512x512' | '768x512'
  >('768x1024');
  const [generatingBackstoryImg, setGeneratingBackstoryImg] = useState(false);
  const [lastBackstoryPromptUsed, setLastBackstoryPromptUsed] = useState<string | null>(null);

  const sendElapsed = useElapsedTimer(sending);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const activeSession = chats.find((c) => c.id === activeChatId) || chats[0];
  const activeCharacter = characters.find((c) => c.id === activeSession?.character_id);
  const activeWorld = worlds.find((w) => w.id === activeSession?.world_id);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [activeSession?.messages.length, sending, illustratingMsgId]);

  useEffect(() => {
    setVisibleSnapshotCount(6);
    setSceneStateDraft({
      location: activeSession?.scene_state?.location || '',
      time_and_lighting: activeSession?.scene_state?.time_and_lighting || '',
      weather: activeSession?.scene_state?.weather || '',
      atmosphere: activeSession?.scene_state?.atmosphere || '',
      attire: activeSession?.scene_state?.attire || '',
      hairstyle: activeSession?.scene_state?.hairstyle || '',
      makeup: activeSession?.scene_state?.makeup || '',
      skin_and_condition: activeSession?.scene_state?.skin_and_condition || '',
      pose_and_action: activeSession?.scene_state?.pose_and_action || '',
      pinned_fields: activeSession?.scene_state?.pinned_fields || [],
    });
  }, [activeSession?.id, activeSession?.scene_state]);

  const latestTriggeredLore: TriggeredLoreInfo[] = React.useMemo(() => {
    if (!activeSession) return [];
    for (let i = activeSession.messages.length - 1; i >= 0; i--) {
      const m = activeSession.messages[i];
      if (m.triggered_lore && m.triggered_lore.length > 0) {
        return m.triggered_lore;
      }
    }
    return [];
  }, [activeSession]);

  // Filter gallery assets related to the active character or world
  const characterBackstoryAssets = React.useMemo(() => {
    if (!activeCharacter) return gallery.slice(0, 6);
    const matching = gallery.filter(
      (g) =>
        g.character_id === activeCharacter.id ||
        (activeWorld && g.world_id === activeWorld.id)
    );
    return matching.length > 0 ? matching : gallery.slice(0, 6);
  }, [gallery, activeCharacter, activeWorld]);

  const handleCreateNewChat = async (charId: string) => {
    const targetChar = characters.find((c) => c.id === charId) || characters[0];
    if (!targetChar) return;
    const created = await api.createChat({
      character_id: targetChar.id,
      world_id: targetChar.world_id,
      title: `Chronicle with ${targetChar.name}`,
    });
    const updated = [created, ...chats];
    onChatsUpdated(updated, created.id);
  };

  const handleDeleteChat = async (chatId: string) => {
    await api.deleteChat(chatId);
    const remaining = chats.filter((c) => c.id !== chatId);
    onChatsUpdated(remaining, remaining[0]?.id || '');
  };

  const handleSend = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!inputMessage.trim() || !activeSession || sending) return;

    const text = inputMessage.trim();
    setInputMessage('');
    setPendingUserText(text);
    setSending(true);
    const shouldAutoIllustrate = autoIllustrate;
    let newAssistantMsgId: string | null = null;
    try {
      // Always fetch the text reply first without blocking on image generation
      const res = await api.sendMessage(activeSession.id, text, false);
      setLastProvider(res.provider);
      const nextChats = chats.map((c) => (c.id === res.session.id ? res.session : c));
      onChatsUpdated(nextChats);
      if (shouldAutoIllustrate) {
        const lastAssistant = [...res.session.messages]
          .reverse()
          .find((m) => m.role === 'assistant');
        newAssistantMsgId = lastAssistant?.id || null;
      }
    } finally {
      setSending(false);
      setPendingUserText(null);
    }

    if (newAssistantMsgId) {
      // Run image generation asynchronously so the user can read the reply immediately
      void handleIllustrateTurn(newAssistantMsgId);
    }
  };

  const handleSwipe = async (msgId: string, direction: 'prev' | 'next' | 'regenerate') => {
    if (!activeSession || swipingMsgId) return;
    setSwipingMsgId(msgId);
    try {
      const res = await api.swipeMessage(activeSession.id, msgId, direction);
      if (res.provider) setLastProvider(res.provider);
      const nextChats = chats.map((c) => (c.id === res.session.id ? res.session : c));
      onChatsUpdated(nextChats);
    } finally {
      setSwipingMsgId(null);
    }
  };

  const handleIllustrateTurn = async (msgId: string, customPrompt?: string) => {
    if (!activeSession || illustratingMsgId) return;
    setIllustratingMsgId(msgId);
    try {
      const res = await api.illustrateMessage(activeSession.id, msgId, customPrompt);
      const nextChats = chats.map((c) => (c.id === res.session.id ? res.session : c));
      onChatsUpdated(nextChats);
      if (customPrompt) {
        setEditedScenePrompts((prev) => {
          const next = { ...prev };
          delete next[msgId];
          return next;
        });
      }
      onGalleryUpdated();
    } finally {
      setIllustratingMsgId(null);
    }
  };

  const handleGenerateBackstoryImage = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!backstoryPrompt.trim() || generatingBackstoryImg) return;

    const [w, h] = aspectRatio.split('x').map(Number);
    setGeneratingBackstoryImg(true);
    try {
      const res = await api.generateBackstoryImage({
        custom_prompt: backstoryPrompt.trim(),
        character_id: activeCharacter?.id || null,
        world_id: activeWorld?.id || activeCharacter?.world_id || null,
        chat_id: activeSession?.id || null,
        include_character_visuals: includeCharVisuals,
        include_scenario_backstory: includeScenario,
        include_world_lore: includeWorldLore,
        use_llm_director: useLlmDirector,
        render_mode: renderMode,
        face_detailer: faceDetailer,
        width: w,
        height: h,
      });
      setLastBackstoryPromptUsed(res.assembled_prompt);
      onGalleryUpdated();
    } finally {
      setGeneratingBackstoryImg(false);
    }
  };

  const handleDeleteSnapshot = async (assetId: string) => {
    await api.deleteGalleryAsset(assetId);
    onGalleryUpdated();
  };

  const handleRefreshCheckpoint = async () => {
    if (!activeSession || updatingCheckpoint) return;
    setUpdatingCheckpoint(true);
    try {
      const res = await api.updateChatCheckpoint(activeSession.id, { refresh: true });
      const nextChats = chats.map((c) => (c.id === res.session.id ? res.session : c));
      onChatsUpdated(nextChats);
      setCheckpointDraft(res.session.situation_checkpoint || '');
    } finally {
      setUpdatingCheckpoint(false);
    }
  };

  const handleSaveCheckpoint = async () => {
    if (!activeSession || updatingCheckpoint) return;
    setUpdatingCheckpoint(true);
    try {
      const res = await api.updateChatCheckpoint(activeSession.id, {
        refresh: false,
        custom_checkpoint: checkpointDraft,
      });
      const nextChats = chats.map((c) => (c.id === res.session.id ? res.session : c));
      onChatsUpdated(nextChats);
    } finally {
      setUpdatingCheckpoint(false);
    }
  };

  const handleSaveSceneState = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!activeSession || savingSceneState) return;
    setSavingSceneState(true);
    try {
      const res = await api.updateChatSceneState(activeSession.id, sceneStateDraft);
      const nextChats = chats.map((c) => (c.id === res.session.id ? res.session : c));
      onChatsUpdated(nextChats);
    } finally {
      setSavingSceneState(false);
    }
  };

  const handleTogglePinField = async (field: string) => {
    if (!activeSession || savingSceneState) return;
    const currentPinned = sceneStateDraft.pinned_fields || [];
    const nextPinned = currentPinned.includes(field)
      ? currentPinned.filter((f) => f !== field)
      : [...currentPinned, field];
    const nextDraft: SceneState = { ...sceneStateDraft, pinned_fields: nextPinned };
    setSceneStateDraft(nextDraft);
    setSavingSceneState(true);
    try {
      const res = await api.updateChatSceneState(activeSession.id, nextDraft);
      const nextChats = chats.map((c) => (c.id === res.session.id ? res.session : c));
      onChatsUpdated(nextChats);
    } finally {
      setSavingSceneState(false);
    }
  };

  const quickBackstoryIdeas = [
    'Walking barefoot along the sunlit shoreline in the ocean breeze',
    'Sipping a tropical cocktail at the candlelit beach cabana at dusk',
    'Close-up golden hour portrait smiling by the turquoise infinity pool',
    'Stargazing on the private teakwood deck over the calm lagoon',
  ];

  return (
    <div className="grid grid-cols-12 h-full overflow-hidden bg-[#090b10]">
      {/* Left Column: Sessions & Quick Character Launcher */}
      <aside className="col-span-3 lg:col-span-2 border-r border-white/10 bg-[#0d1017] flex flex-col h-full overflow-hidden">
        <div className="p-3 border-b border-white/10 space-y-2">
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            Start New Roleplay
          </div>
          <div className="flex gap-1.5">
            <select
              aria-label="Select character for new chat"
              value={newChatCharId}
              onChange={(e) => setNewChatCharId(e.target.value)}
              className="flex-1 min-w-0 bg-[#151a26] border border-white/10 rounded-lg px-2 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-amber-400"
            >
              {characters.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => handleCreateNewChat(newChatCharId || characters[0]?.id)}
              className="px-2.5 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 font-semibold text-xs flex items-center gap-1 cursor-pointer shrink-0"
              title="Create Roleplay Session"
            >
              <Plus className="w-3.5 h-3.5" />
              New
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
          {chats.map((chat) => {
            const char = characters.find((c) => c.id === chat.character_id);
            const isSelected = chat.id === activeSession?.id;
            return (
              <div
                key={chat.id}
                onClick={() => onSelectChat(chat.id)}
                className={`group flex items-center gap-2.5 p-2 rounded-xl cursor-pointer transition border ${
                  isSelected
                    ? 'bg-amber-500/15 border-amber-500/40 text-amber-200'
                    : 'bg-[#121621]/60 border-transparent hover:border-white/10 text-slate-300'
                }`}
              >
                {char?.avatar_url ? (
                  <img
                    src={char.avatar_url}
                    alt={char.name}
                    width={36}
                    height={36}
                    className="w-9 h-9 rounded-lg object-cover border border-white/15 shrink-0"
                  />
                ) : (
                  <div className="w-9 h-9 rounded-lg bg-violet-500/20 flex items-center justify-center text-xs font-bold">
                    {char?.name?.slice(0, 2) || 'RP'}
                  </div>
                )}
                <div className="min-w-0 flex-1">
                  <div className="text-xs font-semibold truncate">{chat.title}</div>
                  <div className="text-[11px] text-slate-400 truncate">
                    {char?.name} • {chat.messages.length} turns
                  </div>
                </div>
                {chats.length > 1 && (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDeleteChat(chat.id);
                    }}
                    className="opacity-0 group-hover:opacity-100 p-1 text-slate-400 hover:text-rose-400 transition"
                    title="Delete session"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </aside>

      {/* Center Column: Interactive Tavern Chat Stream */}
      <section
        className={`col-span-9 ${
          rightPanelOpen ? 'lg:col-span-6' : 'lg:col-span-10'
        } flex flex-col h-full overflow-hidden bg-[#090b10]`}
      >
        {activeSession && activeCharacter ? (
          <>
            {/* Compact Chat Context Header */}
            <div className="px-4 py-2.5 border-b border-white/10 bg-[#0d1018]/90 flex items-center justify-between gap-4">
              <div className="flex items-center gap-3 min-w-0">
                <img
                  src={activeCharacter.avatar_url}
                  alt={activeCharacter.name}
                  width={40}
                  height={40}
                  className="w-10 h-10 rounded-xl object-cover border border-amber-400/40 shrink-0"
                />
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <h2 className="text-sm font-bold text-white truncate">
                      {activeCharacter.name}
                    </h2>
                    <span className="text-[11px] px-2 py-0.5 rounded-full bg-violet-500/20 text-violet-300 border border-violet-500/30 truncate">
                      {activeCharacter.title}
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 truncate">
                    World Codex:{' '}
                    <span className="text-emerald-300 font-medium">
                      {activeWorld ? activeWorld.name : 'Unbound Realm'}
                    </span>
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2 shrink-0">
                <button
                  type="button"
                  onClick={() => {
                    const nextOpen = !checkpointOpen;
                    setCheckpointOpen(nextOpen);
                    if (nextOpen) {
                      setCheckpointDraft(activeSession.situation_checkpoint || '');
                    }
                  }}
                  className={`px-3 py-1.5 rounded-lg border text-xs font-medium flex items-center gap-1.5 cursor-pointer transition ${
                    checkpointOpen || activeSession.situation_checkpoint
                      ? 'bg-emerald-500/15 hover:bg-emerald-500/25 border-emerald-400/30 text-emerald-200'
                      : 'bg-white/5 hover:bg-white/10 border-white/15 text-slate-300'
                  }`}
                  title="Distilled backstory & situation checkpoint"
                >
                  <Sparkles className="w-3.5 h-3.5" />
                  Checkpoint
                </button>
                <button
                  type="button"
                  onClick={() => onOpenWorkflowWithChar(activeCharacter.id, activeWorld?.id)}
                  className="px-3 py-1.5 rounded-lg bg-violet-500/20 hover:bg-violet-500/30 border border-violet-400/30 text-violet-200 text-xs font-medium flex items-center gap-1.5 cursor-pointer transition"
                >
                  <Wand2 className="w-3.5 h-3.5" />
                  Open in Node Studio
                </button>
                <button
                  type="button"
                  onClick={() => setRightPanelOpen((prev) => !prev)}
                  className="hidden lg:flex px-2.5 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 border border-white/15 text-slate-200 text-xs font-medium items-center gap-1 cursor-pointer transition"
                  title={rightPanelOpen ? 'Collapse Studio & State Panel' : 'Expand Studio & State Panel'}
                >
                  {rightPanelOpen ? (
                    <>
                      <ChevronRight className="w-3.5 h-3.5" />
                      Hide Panel
                    </>
                  ) : (
                    <>
                      <ChevronLeft className="w-3.5 h-3.5" />
                      Studio / State
                    </>
                  )}
                </button>
              </div>
            </div>

            {checkpointOpen && (
              <div className="px-4 py-2.5 border-b border-white/10 bg-[#0d111b] space-y-2 shrink-0">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-emerald-300">
                    Situation Checkpoint (Distilled Backstory &amp; Roleplay State)
                  </span>
                  <div className="flex items-center gap-1.5">
                    <button
                      type="button"
                      onClick={handleRefreshCheckpoint}
                      disabled={updatingCheckpoint}
                      className="px-2.5 py-1 rounded-md bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-400/30 text-emerald-200 text-[11px] font-medium flex items-center gap-1 cursor-pointer disabled:opacity-50"
                    >
                      {updatingCheckpoint ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : (
                        <RefreshCw className="w-3 h-3" />
                      )}
                      Distill Now
                    </button>
                    <button
                      type="button"
                      onClick={handleSaveCheckpoint}
                      disabled={updatingCheckpoint}
                      className="px-2.5 py-1 rounded-md bg-white/10 hover:bg-white/15 border border-white/15 text-slate-200 text-[11px] font-medium cursor-pointer disabled:opacity-50"
                    >
                      Save
                    </button>
                  </div>
                </div>
                <textarea
                  rows={3}
                  value={checkpointDraft}
                  onChange={(e) => setCheckpointDraft(e.target.value)}
                  placeholder="No checkpoint distilled yet. Click 'Distill Now' to summarize the backstory and roleplay so far, or write your own situation state..."
                  className="w-full rounded-lg bg-[#090c14] border border-white/10 px-2.5 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-400 resize-y"
                />
              </div>
            )}

            {/* Messages Scroll Area */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {activeSession.messages.map((msg) => {
                const isAssistant = msg.role === 'assistant';
                const swipeCount = msg.swipes?.length || 1;
                const currentSwipe = (msg.active_swipe ?? 0) + 1;
                const isIllustratingThis = illustratingMsgId === msg.id;
                const isSwipingThis = swipingMsgId === msg.id;

                return (
                  <div
                    key={msg.id}
                    className={`flex gap-3.5 ${
                      isAssistant ? 'items-start' : 'items-start flex-row-reverse'
                    }`}
                  >
                    {isAssistant ? (
                      <img
                        src={activeCharacter.avatar_url}
                        alt={activeCharacter.name}
                        width={42}
                        height={42}
                        className="w-10.5 h-10.5 rounded-xl object-cover border border-amber-500/30 shrink-0 mt-0.5"
                      />
                    ) : (
                      <div className="w-10 h-10 rounded-xl bg-sky-500/20 border border-sky-400/30 flex items-center justify-center text-xs font-bold text-sky-200 shrink-0 mt-0.5">
                        {msg.sender_name.slice(0, 2).toUpperCase()}
                      </div>
                    )}

                    <div
                      className={`max-w-2xl w-full rounded-2xl p-4 border ${
                        isAssistant
                          ? 'bg-[#121622] border-white/10 text-slate-100'
                          : 'bg-sky-950/40 border-sky-500/30 text-slate-100'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-4 mb-1.5">
                        <span
                          className={`text-xs font-bold ${
                            isAssistant ? 'text-amber-300' : 'text-sky-300'
                          }`}
                        >
                          {msg.sender_name}
                        </span>

                        {msg.triggered_lore && msg.triggered_lore.length > 0 && (
                          <div className="flex items-center gap-1 flex-wrap">
                            {msg.triggered_lore.map((tl) => (
                              <span
                                key={tl.entry_id}
                                className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 flex items-center gap-1"
                                title={`Triggered by: ${tl.matched_keys.join(', ')}`}
                              >
                                <BookOpen className="w-2.5 h-2.5" />
                                {tl.title}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>

                      <div className="text-sm">{renderFormattedRoleplayText(msg.content)}</div>

                      {/* Live Swipe Generation Progress Card */}
                      {isSwipingThis && (
                        <div className="mt-3">
                          <GenerationProgressCard
                            title={`Generating alternate reply for ${activeCharacter.name}...`}
                            subtitle="Sampling new narrative branch with active Lorebook context"
                            engineLabel="Ollama (hermes3:8b)"
                            compact
                            accent="amber"
                          />
                        </div>
                      )}

                      {/* Live Scene Illustration Progress Card */}
                      {isIllustratingThis && (
                        <div className="mt-3">
                          <GenerationProgressCard
                            title="Synthesizing Contextual Scene Illustration in ComfyUI SDXL..."
                            subtitle={`Distilling chat action & ${
                              activeCharacter.name
                            }'s scenario into SDXL visual keywords via Hermes 3`}
                            engineLabel="Hermes 3 Keyword Distiller + ComfyUI SDXL"
                            stages={[
                              'Distilling Scenario & Action to SDXL Keywords',
                              'Sampling SDXL Latents in ComfyUI',
                              'Decoding Keyframe Image',
                            ]}
                            accent="cyan"
                          />
                        </div>
                      )}

                      {/* Inline Generated Scene Artwork */}
                      {msg.image_url && !isIllustratingThis && (() => {
                        const matchedAsset = gallery.find((g) => g.url === msg.image_url);
                        const imgW = matchedAsset?.width || 512;
                        const imgH = matchedAsset?.height || 768;
                        return (
                          <div className="mt-3 rounded-xl overflow-hidden border border-white/15 bg-black/60">
                            <img
                              src={msg.image_url}
                              alt={msg.image_prompt || 'Scene keyframe'}
                              width={imgW}
                              height={imgH}
                              style={{ aspectRatio: `${imgW} / ${imgH}` }}
                              className="w-full h-auto max-h-[680px] object-contain mx-auto block"
                            />
                            {msg.image_prompt && (() => {
                              const draftPrompt =
                                editedScenePrompts[msg.id] ?? msg.image_prompt;
                              const isDirty =
                                editedScenePrompts[msg.id] !== undefined &&
                                editedScenePrompts[msg.id] !== msg.image_prompt;
                              return (
                                <details className="bg-[#0b0e16] border-t border-white/10 text-[11px] text-slate-300">
                                  <summary className="px-3 py-2 cursor-pointer select-none flex items-center justify-between text-amber-300 font-semibold hover:bg-white/5 transition">
                                    <span>View / Edit Scene Prompt</span>
                                    {isDirty && (
                                      <span className="text-[10px] text-cyan-300 font-normal">
                                        (Edited — ready to resubmit)
                                      </span>
                                    )}
                                  </summary>
                                  <div className="px-3 pb-3 pt-1 space-y-2 border-t border-white/5">
                                    <textarea
                                      rows={3}
                                      value={draftPrompt}
                                      onChange={(e) =>
                                        setEditedScenePrompts((prev) => ({
                                          ...prev,
                                          [msg.id]: e.target.value,
                                        }))
                                      }
                                      disabled={isIllustratingThis}
                                      className="w-full bg-[#121724] border border-white/15 rounded-lg p-2 text-[11px] font-mono text-slate-200 leading-relaxed focus:outline-none focus:border-amber-400"
                                    />
                                    <div className="flex items-center justify-end gap-2">
                                      {isDirty && (
                                        <button
                                          type="button"
                                          onClick={() =>
                                            setEditedScenePrompts((prev) => {
                                              const next = { ...prev };
                                              delete next[msg.id];
                                              return next;
                                            })
                                          }
                                          className="px-2.5 py-1 rounded-lg bg-white/5 hover:bg-white/10 text-[11px] text-slate-300 cursor-pointer"
                                        >
                                          Reset
                                        </button>
                                      )}
                                      <button
                                        type="button"
                                        disabled={isIllustratingThis || !draftPrompt.trim()}
                                        onClick={() =>
                                          handleIllustrateTurn(msg.id, draftPrompt.trim())
                                        }
                                        className="px-3 py-1 rounded-lg bg-amber-500 hover:bg-amber-400 disabled:opacity-50 text-slate-950 font-bold text-[11px] cursor-pointer transition"
                                      >
                                        Regenerate with Edited Prompt
                                      </button>
                                    </div>
                                  </div>
                                </details>
                              );
                            })()}
                          </div>
                        );
                      })()}

                      {/* Message Action Bar: Swipes & Scene Illustration */}
                      <div className="mt-3 pt-2 border-t border-white/5 flex items-center justify-between gap-2 text-xs text-slate-400">
                        <button
                          type="button"
                          onClick={() => handleIllustrateTurn(msg.id)}
                          disabled={isIllustratingThis}
                          className="px-2.5 py-1 rounded-lg bg-white/5 hover:bg-amber-500/20 hover:text-amber-200 border border-white/10 flex items-center gap-1.5 text-[11px] cursor-pointer transition disabled:opacity-50"
                        >
                          <ImageIcon className="w-3.5 h-3.5 text-amber-400" />
                          {isIllustratingThis
                            ? 'Rendering Scene in ComfyUI...'
                            : msg.image_url
                            ? 'Re-Illustrate Scene'
                            : 'Illustrate Scene'}
                        </button>

                        {isAssistant && (
                          <div className="flex items-center gap-1">
                            <button
                              type="button"
                              onClick={() => handleSwipe(msg.id, 'prev')}
                              disabled={currentSwipe <= 1 || isSwipingThis}
                              className="p-1 rounded hover:bg-white/10 disabled:opacity-30 cursor-pointer"
                              title="Previous swipe"
                            >
                              <ChevronLeft className="w-3.5 h-3.5" />
                            </button>
                            <span className="text-[11px] font-mono px-1">
                              {isSwipingThis ? '...' : `${currentSwipe}/${swipeCount}`}
                            </span>
                            <button
                              type="button"
                              onClick={() => handleSwipe(msg.id, 'next')}
                              disabled={isSwipingThis}
                              className="p-1 rounded hover:bg-white/10 disabled:opacity-30 cursor-pointer"
                              title="Generate / Next swipe variation"
                            >
                              <ChevronRight className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}

              {/* Optimistic User Turn + Live Character Generation Card when Sending */}
              {sending && (
                <>
                  {pendingUserText && (
                    <div className="flex gap-3.5 items-start flex-row-reverse">
                      <div className="w-10 h-10 rounded-xl bg-sky-500/20 border border-sky-400/30 flex items-center justify-center text-xs font-bold text-sky-200 shrink-0 mt-0.5">
                        {activeSession.user_persona_name.slice(0, 2).toUpperCase()}
                      </div>
                      <div className="max-w-2xl rounded-2xl p-4 border bg-sky-950/40 border-sky-500/30 text-slate-100">
                        <div className="text-xs font-bold text-sky-300 mb-1">
                          {activeSession.user_persona_name}
                        </div>
                        <div className="text-sm">{pendingUserText}</div>
                      </div>
                    </div>
                  )}

                  <div className="flex gap-3.5 items-start">
                    <img
                      src={activeCharacter.avatar_url}
                      alt={activeCharacter.name}
                      width={42}
                      height={42}
                      className="w-10.5 h-10.5 rounded-xl object-cover border-2 border-amber-400 animate-pulse shrink-0 mt-0.5"
                    />
                    <div className="max-w-2xl w-full">
                      <GenerationProgressCard
                        title={
                          autoIllustrate
                            ? `${activeCharacter.name} is replying & rendering scene keyframe...`
                            : `${activeCharacter.name} is composing a roleplay response...`
                        }
                        subtitle={`Scanning ${
                          activeWorld?.name || 'World'
                        } lorebook & running local inference`}
                        engineLabel={
                          autoIllustrate ? 'Hermes 3 + ComfyUI SDXL' : 'Ollama (hermes3:8b)'
                        }
                        stages={
                          autoIllustrate
                            ? [
                                'Scanning World Lore Triggers',
                                `Generating ${activeCharacter.name}'s Reply`,
                                'Rendering SDXL Scene in ComfyUI',
                              ]
                            : [
                                'Scanning World Lore Triggers',
                                `Generating ${activeCharacter.name}'s Reply`,
                                'Formatting Dialogue & Actions',
                              ]
                        }
                        accent="amber"
                      />
                    </div>
                  </div>
                </>
              )}

              <div ref={messagesEndRef} />
            </div>

            {/* Composer Bar */}
            <form
              onSubmit={handleSend}
              className="p-3 border-t border-white/10 bg-[#0d1017] space-y-2"
            >
              <div className="flex items-center justify-between text-xs text-slate-400 px-1">
                <label className="flex items-center gap-2 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={autoIllustrate}
                    onChange={(e) => setAutoIllustrate(e.target.checked)}
                    className="rounded border-white/20 bg-slate-900 text-amber-500 focus:ring-amber-500"
                  />
                  <span className="text-[11px] text-slate-300 flex items-center gap-1">
                    <Sparkles className="w-3 h-3 text-amber-400" />
                    Auto-generate inline scene illustration with reply
                  </span>
                </label>
                <span className="text-[11px] text-slate-400 font-mono">
                  Engine: {lastProvider}
                </span>
              </div>

              <div className="flex gap-2">
                <input
                  type="text"
                  value={inputMessage}
                  onChange={(e) => setInputMessage(e.target.value)}
                  disabled={sending}
                  placeholder={`Write your action or dialogue to ${activeCharacter.name}...`}
                  className="flex-1 bg-[#141926] border border-white/15 rounded-xl px-3.5 py-2.5 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-amber-400 disabled:opacity-60"
                />
                <button
                  type="submit"
                  disabled={sending || !inputMessage.trim()}
                  className="px-4 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 disabled:bg-amber-500/30 disabled:text-amber-200 text-slate-950 font-semibold text-sm flex items-center gap-2 cursor-pointer transition shrink-0"
                >
                  {sending ? (
                    <>
                      <progress
                        aria-label="Sending roleplay message"
                        className="loading-spinner"
                        style={{ '--size': '16px', '--thickness': '2px' } as React.CSSProperties}
                      />
                      <span>Generating ({sendElapsed}s)</span>
                    </>
                  ) : (
                    <>
                      <Send className="w-4 h-4" />
                      <span>Send</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center text-slate-400 text-sm">
            Select or create a Roleplay Session to begin.
          </div>
        )}
      </section>

      {/* Right Column: Collapsible Backstory Studio, Persona & Lore, and Scene State */}
      {rightPanelOpen && (
        <aside className="hidden lg:flex lg:col-span-4 border-l border-white/10 bg-[#0d1017] flex-col h-full overflow-hidden">
          {/* Sub-Navigation Toggle inside Right Drawer */}
          <div className="p-2.5 border-b border-white/10 bg-[#0a0d14] grid grid-cols-3 gap-1.5">
            <button
              type="button"
              onClick={() => setRightTab('backstory_studio')}
              className={`py-1.5 px-2 rounded-xl text-[11px] font-bold flex items-center justify-center gap-1 cursor-pointer transition ${
                rightTab === 'backstory_studio'
                  ? 'bg-cyan-500 text-slate-950 shadow-sm'
                  : 'bg-[#141926] text-slate-300 hover:text-white'
              }`}
            >
              <Camera className="w-3.5 h-3.5 shrink-0" />
              Studio
            </button>
            <button
              type="button"
              onClick={() => setRightTab('scene_state')}
              className={`py-1.5 px-2 rounded-xl text-[11px] font-bold flex items-center justify-center gap-1 cursor-pointer transition ${
                rightTab === 'scene_state'
                  ? 'bg-amber-500 text-slate-950 shadow-sm'
                  : 'bg-[#141926] text-slate-300 hover:text-white'
              }`}
            >
              <Layers className="w-3.5 h-3.5 shrink-0" />
              Scene State
            </button>
            <button
              type="button"
              onClick={() => setRightTab('lore_inspector')}
              className={`py-1.5 px-2 rounded-xl text-[11px] font-bold flex items-center justify-center gap-1 cursor-pointer transition ${
                rightTab === 'lore_inspector'
                  ? 'bg-emerald-500 text-slate-950 shadow-sm'
                  : 'bg-[#141926] text-slate-300 hover:text-white'
              }`}
            >
              <BookOpen className="w-3.5 h-3.5 shrink-0" />
              Lore ({latestTriggeredLore.length})
            </button>
          </div>

          {rightTab === 'backstory_studio' ? (
            <div
              className="flex-1 overflow-y-auto p-4 space-y-4"
              onScroll={(e) => {
                const el = e.currentTarget;
                if (
                  el.scrollHeight - el.scrollTop - el.clientHeight < 140 &&
                  visibleSnapshotCount < characterBackstoryAssets.length
                ) {
                  setVisibleSnapshotCount((prev) =>
                    Math.min(characterBackstoryAssets.length, prev + 6)
                  );
                }
              }}
            >
            {/* Backstory Studio Header & Form */}
            <form
              onSubmit={handleGenerateBackstoryImage}
              className="p-3.5 rounded-2xl bg-[#121724] border border-cyan-500/30 space-y-3"
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h3 className="text-xs font-bold text-cyan-300 flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5" />
                    Standalone Backstory Image Synthesizer
                  </h3>
                  <p className="text-[11px] text-slate-400 mt-0.5 leading-relaxed">
                    Generate specific scenes, poses, or moments using{' '}
                    <strong className="text-slate-200">
                      {activeCharacter?.name || 'Character'}
                    </strong>
                    &apos;s physical description &amp;{' '}
                    <strong className="text-emerald-300">
                      {activeWorld?.name || 'World'}
                    </strong>{' '}
                    backstory without adding to the chat conversation.
                  </p>
                </div>
              </div>

              <div>
                <label className="block text-[11px] font-semibold text-slate-300 mb-1">
                  Specific Scene, Pose, Outfit, or Moment
                </label>
                <textarea
                  rows={2}
                  value={backstoryPrompt}
                  onChange={(e) => setBackstoryPrompt(e.target.value)}
                  disabled={generatingBackstoryImg}
                  placeholder="Describe the exact image you want to generate from this roleplay's backstory..."
                  className="w-full bg-[#0b0e17] border border-white/15 rounded-xl p-2.5 text-xs text-white placeholder:text-slate-500 focus:outline-none focus:border-cyan-400"
                />
              </div>

              {/* Quick Scene Idea Chips */}
              <div className="space-y-1">
                <div className="text-[10px] uppercase tracking-wider text-slate-400">
                  Quick Backstory Scene Presets:
                </div>
                <div className="flex flex-wrap gap-1">
                  {quickBackstoryIdeas.map((idea) => (
                    <button
                      key={idea}
                      type="button"
                      onClick={() => setBackstoryPrompt(idea)}
                      className="text-[10px] px-2 py-1 rounded-lg bg-[#181f30] hover:bg-cyan-500/20 text-slate-300 hover:text-cyan-200 border border-white/10 cursor-pointer transition text-left truncate max-w-full"
                    >
                      + {idea}
                    </button>
                  ))}
                </div>
              </div>

              {/* Backstory Context Fusion Checkboxes */}
              <div className="p-2.5 rounded-xl bg-[#0b0e17] border border-white/10 space-y-1.5">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-cyan-300 flex items-center gap-1">
                  <Layers className="w-3 h-3" />
                  Injected Backstory Layers
                </div>

                <label className="flex items-center gap-2 text-[11px] text-slate-200 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={includeCharVisuals}
                    onChange={(e) => setIncludeCharVisuals(e.target.checked)}
                  />
                  <span>
                    Character Physical Traits ({activeCharacter?.name || 'Persona'})
                  </span>
                </label>

                <label className="flex items-center gap-2 text-[11px] text-slate-200 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={includeScenario}
                    onChange={(e) => setIncludeScenario(e.target.checked)}
                  />
                  <span>Roleplay Scenario &amp; Backstory Context</span>
                </label>

                <label className="flex items-center gap-2 text-[11px] text-slate-200 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={includeWorldLore}
                    onChange={(e) => setIncludeWorldLore(e.target.checked)}
                  />
                  <span>
                    World Codex Aesthetic &amp; Lore ({activeWorld?.name || 'None'})
                  </span>
                </label>

                <label className="flex items-center gap-2 text-[11px] text-amber-200 cursor-pointer pt-0.5 border-t border-white/5">
                  <input
                    type="checkbox"
                    checked={useLlmDirector}
                    onChange={(e) => setUseLlmDirector(e.target.checked)}
                  />
                  <span>Distill Scenario &amp; Scene into SDXL Keywords via Ollama (hermes3:8b)</span>
                </label>

                <label className="flex items-center gap-2 text-[11px] text-emerald-300 cursor-pointer pt-0.5 border-t border-white/5">
                  <input
                    type="checkbox"
                    checked={faceDetailer}
                    onChange={(e) => setFaceDetailer(e.target.checked)}
                  />
                  <span>
                    ✨ Automatic Face Detailer Pass (MediaPipe 768×768 Face Crop &amp; Refine)
                  </span>
                </label>

                <div className="pt-1.5 border-t border-white/5">
                  <label className="block text-[10px] font-semibold uppercase tracking-wider text-amber-300 mb-1">
                    Artistic Render Pipeline (Experiment Mode)
                  </label>
                  <select
                    aria-label="Backstory Artistic Render Mode"
                    value={renderMode}
                    onChange={(e) =>
                      setRenderMode(
                        e.target.value as 'hybrid_refiner' | 'single_stylized' | 'single_raw'
                      )
                    }
                    disabled={generatingBackstoryImg}
                    className="w-full bg-[#141926] border border-amber-500/30 rounded-lg px-2 py-1.5 text-[11px] text-amber-100"
                  >
                    <option value="single_stylized">
                      Option 1 (Recommended): Single Checkpoint + Painterly Golden-Hour Style
                    </option>
                    <option value="hybrid_refiner">
                      Option 2: 2-Stage Img2Img Hybrid (Pony Pose → SDXL Golden-Hour Refiner)
                    </option>
                    <option value="single_raw">
                      Option 3: Single Checkpoint + Raw Unfiltered Photo Style
                    </option>
                  </select>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <select
                  aria-label="Backstory Image Aspect Ratio"
                  value={aspectRatio}
                  onChange={(e) =>
                    setAspectRatio(
                      e.target.value as
                        | '768x1024'
                        | '512x768'
                        | '768x768'
                        | '1024x768'
                        | '512x512'
                        | '768x512'
                    )
                  }
                  disabled={generatingBackstoryImg}
                  className="bg-[#0b0e17] border border-white/15 rounded-xl px-2.5 py-2 text-xs text-slate-200"
                >
                  <option value="768x1024">768×1024 HD Portrait</option>
                  <option value="512x768">512×768 Fast Portrait</option>
                  <option value="768x768">768×768 HD Square</option>
                  <option value="1024x768">1024×768 HD Cinema</option>
                  <option value="512x512">512×512 Fast Square</option>
                  <option value="768x512">768×512 Fast Cinema</option>
                </select>

                <button
                  type="submit"
                  disabled={generatingBackstoryImg || !backstoryPrompt.trim()}
                  className="flex-1 py-2 px-3 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-500 hover:from-cyan-400 hover:to-blue-400 disabled:opacity-50 text-slate-950 font-bold text-xs flex items-center justify-center gap-1.5 cursor-pointer shadow-md"
                >
                  <Camera className="w-4 h-4" />
                  {generatingBackstoryImg
                    ? 'Synthesizing in ComfyUI...'
                    : 'Generate Backstory Image'}
                </button>
              </div>
            </form>

            {/* Live Progress Card while Generating Standalone Backstory Image */}
            {generatingBackstoryImg && (
              <GenerationProgressCard
                title="Rendering Standalone Backstory Artwork..."
                subtitle={`Fusing ${activeCharacter?.name || 'Character'}'s physical traits + ${
                  activeWorld?.name || 'World'
                } lore`}
                engineLabel="ComfyUI (sd_xl_base_1.0)"
                stages={[
                  'Assembling Persona & World Backstory',
                  'Running ComfyUI SDXL Diffusion',
                  'Saving to Backstory Gallery',
                ]}
                accent="cyan"
              />
            )}

            {/* Assembled Backstory Prompt Readout */}
            {lastBackstoryPromptUsed && !generatingBackstoryImg && (
              <details className="p-2.5 rounded-xl bg-[#111520] border border-white/10 text-[11px] text-slate-300">
                <summary className="cursor-pointer font-semibold text-cyan-300">
                  View Last Assembled Backstory Prompt
                </summary>
                <p className="mt-1.5 font-mono text-[10px] text-slate-400 leading-relaxed">
                  {lastBackstoryPromptUsed}
                </p>
              </details>
            )}

            {/* Backstory Snapshots Gallery Strip */}
            <div className="space-y-2.5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Roleplay Backstory Snapshots ({Math.min(visibleSnapshotCount, characterBackstoryAssets.length)} / {characterBackstoryAssets.length})
                </span>
              </div>

              <div className="grid grid-cols-2 gap-2.5">
                {characterBackstoryAssets.slice(0, visibleSnapshotCount).map((asset) => (
                  <div
                    key={asset.id}
                    className="group rounded-xl overflow-hidden bg-[#121622] border border-white/10 hover:border-cyan-400/50 transition flex flex-col justify-between"
                  >
                    <div
                      className="relative bg-black flex items-center justify-center overflow-hidden"
                      style={{
                        aspectRatio: `${asset.width || 512} / ${asset.height || 768}`,
                      }}
                    >
                      <img
                        src={asset.url}
                        alt={asset.prompt}
                        width={asset.width || 512}
                        height={asset.height || 768}
                        className="w-full h-full object-contain"
                      />
                      <div className="absolute top-2 right-2 flex items-center gap-1 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition">
                        <a
                          href={asset.url}
                          download
                          className="p-1.5 rounded-lg bg-black/80 text-white hover:text-cyan-300 border border-white/15 transition"
                          title="Download PNG"
                        >
                          <Download className="w-3.5 h-3.5" />
                        </a>
                        <button
                          type="button"
                          onClick={() => handleDeleteSnapshot(asset.id)}
                          aria-label="Delete snapshot"
                          className="p-1.5 rounded-lg bg-black/80 text-rose-300 hover:bg-rose-500/30 hover:text-rose-200 border border-rose-500/30 cursor-pointer transition"
                          title="Delete snapshot"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                    <div className="p-2 flex items-center justify-between gap-1.5">
                      <p className="text-[10px] text-slate-300 line-clamp-2 leading-snug flex-1">
                        {asset.prompt}
                      </p>
                      <button
                        type="button"
                        onClick={() => handleDeleteSnapshot(asset.id)}
                        aria-label="Delete snapshot from backstory"
                        className="p-1 rounded text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 cursor-pointer shrink-0 transition"
                        title="Delete snapshot"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>

              {visibleSnapshotCount < characterBackstoryAssets.length && (
                <button
                  type="button"
                  onClick={() =>
                    setVisibleSnapshotCount((prev) =>
                      Math.min(characterBackstoryAssets.length, prev + 6)
                    )
                  }
                  className="w-full py-2 rounded-xl bg-[#141926] hover:bg-[#1a2234] border border-white/10 text-xs font-semibold text-cyan-300 cursor-pointer transition"
                >
                  Load More Snapshots ({characterBackstoryAssets.length - visibleSnapshotCount} remaining)
                </button>
              )}
            </div>
          </div>
        ) : rightTab === 'scene_state' ? (
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            <form onSubmit={handleSaveSceneState} className="space-y-3">
              <div className="flex items-center justify-between gap-2">
                <h3 className="text-xs font-bold text-amber-300 flex items-center gap-1.5">
                  <Layers className="w-3.5 h-3.5" />
                  Live Tracked Scene State
                </h3>
                <button
                  type="submit"
                  disabled={savingSceneState || !activeSession}
                  className="px-3 py-1 rounded-lg bg-amber-500 hover:bg-amber-400 disabled:opacity-50 text-slate-950 font-bold text-[11px] cursor-pointer transition"
                >
                  {savingSceneState ? 'Saving...' : 'Save State'}
                </button>
              </div>
              <p className="text-[11px] text-slate-400">
                Updated automatically each turn and fed into both roleplay replies and image prompts. Edit any field below to override.
              </p>
              {(
                [
                  ['section', 'World & Scenario (Stable)'],
                  ['location', 'Location', 'e.g. Solana Cove beach, candlelit cabana'],
                  ['time_and_lighting', 'Time & Lighting', 'e.g. golden hour sunset, moonlit night'],
                  ['weather', 'Weather', 'e.g. clear warm breeze, tropical rainstorm'],
                  ['atmosphere', 'Atmosphere', 'e.g. tranquil resort dusk, intimate secrecy'],
                  ['section', 'Character Visuals (Turn-by-Turn)'],
                  ['attire', 'Attire / State of Undress', 'e.g. string bikini, completely nude, silk dress'],
                  ['hairstyle', 'Hairstyle', 'e.g. wet slicked-back hair, loose tousled hair'],
                  ['makeup', 'Makeup', 'e.g. natural bare-faced, smoky evening makeup'],
                  ['skin_and_condition', 'Skin & Condition', 'e.g. wet glistening skin, sun-kissed dry skin'],
                  ['pose_and_action', 'Pose & Action', 'e.g. walking away along shoreline'],
                ] as const
              ).map((entry, idx) => {
                if (entry[0] === 'section') {
                  return (
                    <div
                      key={`sec_${idx}`}
                      className="pt-2 pb-0.5 text-[10px] font-bold uppercase tracking-wider text-slate-400 border-b border-white/10"
                    >
                      {entry[1]}
                    </div>
                  );
                }
                const [field, label, placeholder] = entry;
                const isPinned = (sceneStateDraft.pinned_fields || []).includes(field);
                return (
                  <div
                    key={field}
                    className={`space-y-1 p-2 rounded-xl border transition ${
                      isPinned
                        ? 'bg-amber-500/10 border-amber-400/40'
                        : 'bg-transparent border-transparent'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <label className="block text-[11px] font-semibold text-slate-300">
                        {label}
                      </label>
                      <button
                        type="button"
                        onClick={() => handleTogglePinField(field)}
                        disabled={savingSceneState || !activeSession}
                        className={`px-2 py-0.5 rounded-md text-[10px] font-semibold flex items-center gap-1 cursor-pointer transition ${
                          isPinned
                            ? 'bg-amber-500/25 text-amber-200 border border-amber-400/40'
                            : 'bg-white/5 hover:bg-white/10 text-slate-400 hover:text-slate-200 border border-white/10'
                        }`}
                        title={
                          isPinned
                            ? 'Pinned across turns (auto-updates only if explicitly changed in chat). Click to unpin.'
                            : 'Pin this field to keep it across future turns unless explicitly changed.'
                        }
                      >
                        {isPinned ? (
                          <>
                            <Pin className="w-3 h-3" />
                            Pinned
                          </>
                        ) : (
                          <>
                            <PinOff className="w-3 h-3" />
                            Pin
                          </>
                        )}
                      </button>
                    </div>
                    <input
                      type="text"
                      value={sceneStateDraft[field]}
                      onChange={(e) =>
                        setSceneStateDraft((prev) => ({ ...prev, [field]: e.target.value }))
                      }
                      placeholder={placeholder}
                      className="w-full rounded-lg bg-[#090c14] border border-white/15 px-2.5 py-1.5 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-amber-400"
                    />
                  </div>
                );
              })}
            </form>
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto p-4 space-y-5">
            {activeCharacter && (
              <div className="space-y-3">
                <div className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                  <UserCheck className="w-3.5 h-3.5 text-amber-400" />
                  Active Persona Card
                </div>
                <div className="p-3 rounded-xl bg-[#131824] border border-white/10 space-y-2">
                  <div className="flex items-center gap-3">
                    <img
                      src={activeCharacter.avatar_url}
                      alt={activeCharacter.name}
                      width={56}
                      height={56}
                      className="w-14 h-14 rounded-xl object-cover border border-amber-400/30"
                    />
                    <div>
                      <div className="text-sm font-bold text-white">{activeCharacter.name}</div>
                      <div className="text-xs text-amber-300/90">{activeCharacter.title}</div>
                    </div>
                  </div>
                  <p className="text-xs text-slate-300 leading-relaxed">
                    {activeCharacter.personality}
                  </p>
                  <details className="text-xs text-slate-400 pt-1">
                    <summary className="cursor-pointer text-slate-300 font-medium">
                      Scenario &amp; Visual Tags
                    </summary>
                    <div className="mt-2 space-y-1.5 text-[11px]">
                      <div>
                        <strong className="text-slate-200">Scenario:</strong>{' '}
                        {activeCharacter.scenario}
                      </div>
                      <div>
                        <strong className="text-slate-200">Visual Prompt Tags:</strong>{' '}
                        {activeCharacter.visual_prompt_tags}
                      </div>
                    </div>
                  </details>
                </div>
              </div>
            )}

            {/* Triggered Lorebook Inspector */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                  <BookOpen className="w-3.5 h-3.5 text-emerald-400" />
                  Triggered World Info
                </span>
                <span className="text-[11px] px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                  {latestTriggeredLore.length} Active
                </span>
              </div>

              {latestTriggeredLore.length > 0 ? (
                <div className="space-y-2.5">
                  {latestTriggeredLore.map((item) => (
                    <div
                      key={item.entry_id}
                      className="p-3 rounded-xl bg-emerald-950/20 border border-emerald-500/30 space-y-1.5"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-emerald-200">
                          {item.title}
                        </span>
                        <span className="text-[10px] uppercase px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300">
                          {item.category}
                        </span>
                      </div>
                      <div className="text-[11px] text-emerald-400/90">
                        Matched keys: {item.matched_keys.join(', ')}
                      </div>
                      <p className="text-xs text-slate-300 leading-relaxed">{item.snippet}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="p-3 rounded-xl bg-[#131824] border border-white/10 text-xs text-slate-400">
                  Mention world keywords in chat to automatically inject Lorebook entries into
                  the LLM and Scene Renderer.
                </div>
              )}
            </div>

            {/* All Available Keywords in Bound World */}
            {activeWorld && (
              <div className="space-y-2">
                <div className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                  <MessageSquare className="w-3.5 h-3.5 text-violet-400" />
                  World Keyword Triggers ({activeWorld.name})
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {activeWorld.entries.flatMap((e) =>
                    e.keys.map((k) => (
                      <button
                        key={`${e.id}_${k}`}
                        type="button"
                        onClick={() =>
                          setInputMessage((prev) =>
                            prev ? `${prev} ${k}` : `Tell me about the ${k}.`
                          )
                        }
                        className="text-[11px] px-2 py-1 rounded-lg bg-[#151a28] hover:bg-violet-500/20 text-slate-300 hover:text-violet-200 border border-white/10 cursor-pointer transition"
                        title={`Click to insert "${k}" (${e.title})`}
                      >
                        #{k}
                      </button>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>
        )}
        </aside>
      )}
    </div>
  );
};
