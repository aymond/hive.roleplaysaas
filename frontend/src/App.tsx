import React, { useEffect, useState, useCallback } from 'react';
import {
  MessageSquare,
  Users,
  BookOpen,
  Image as ImageIcon,
  Settings,
  Cpu,
  Sparkles,
  ShieldAlert,
  LogOut,
  Shield,
  User as UserIcon,
} from 'lucide-react';
import { api } from './api';
import type {
  AuthConfig,
  CharacterCard,
  ChatSession,
  GalleryAsset,
  Lorebook,
  SystemStatus,
  UserProfile,
} from './types';
import {
  clearAllAuthSessions,
  getAuthToken,
  getMockSession,
} from './auth/firebase';
import { RoleplayChat } from './components/RoleplayChat';
import { CharacterForge } from './components/CharacterForge';
import { WorldCodex } from './components/WorldCodex';
import { AssetGallery } from './components/AssetGallery';
import { EngineSettingsModal } from './components/EngineSettingsModal';
import { AdminModerationModal } from './components/AdminModerationModal';
import { LoginScreen } from './components/LoginScreen';

type StudioTab = 'chat' | 'characters' | 'worlds' | 'gallery';

export const App: React.FC = () => {
  const [authConfig, setAuthConfig] = useState<AuthConfig | null>(null);
  const [userProfile, setUserProfile] = useState<UserProfile | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<StudioTab>('chat');
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [characters, setCharacters] = useState<CharacterCard[]>([]);
  const [worlds, setWorlds] = useState<Lorebook[]>([]);
  const [chats, setChats] = useState<ChatSession[]>([]);
  const [activeChatId, setActiveChatId] = useState<string>('');
  const [gallery, setGallery] = useState<GalleryAsset[]>([]);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [moderationOpen, setModerationOpen] = useState(false);
  const [loading, setLoading] = useState(true);

  const handleSignOut = useCallback(() => {
    clearAllAuthSessions();
    setUserProfile(null);
    setStatus(null);
    setCharacters([]);
    setWorlds([]);
    setChats([]);
    setActiveChatId('');
    setGallery([]);
    setSettingsOpen(false);
    setModerationOpen(false);
    setAuthError(null);
  }, []);

  const bootstrapSession = useCallback(async () => {
    setLoading(true);
    setAuthError(null);
    try {
      const cfg = await api.getAuthConfig();
      setAuthConfig(cfg);

      const hasCredentials = cfg.saas_auth_enabled
        ? Boolean(getAuthToken())
        : Boolean(getMockSession());

      if (!hasCredentials) {
        setUserProfile(null);
        return;
      }

      const [me, sys, chars, wlds, chts, gal] = await Promise.all([
        api.getCurrentUser(),
        api.getSystemStatus(),
        api.listCharacters(),
        api.listWorlds(),
        api.listChats(),
        api.listGallery(),
      ]);
      setUserProfile(me);
      setStatus(sys);
      setCharacters(chars);
      setWorlds(wlds);
      setChats(chts);
      setActiveChatId(chts[0]?.id || '');
      setGallery(gal);
    } catch (err: any) {
      if (err?.status === 401) {
        clearAllAuthSessions();
        setUserProfile(null);
        setAuthError('Your session expired. Please sign in again.');
      } else {
        setAuthError(err?.message || 'Failed to authenticate session.');
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    bootstrapSession();
  }, [bootstrapSession]);

  const refreshGallery = useCallback(async () => {
    const gal = await api.listGallery();
    setGallery(gal);
  }, []);

  const refreshStatus = useCallback(async () => {
    const sys = await api.getSystemStatus();
    setStatus(sys);
  }, []);

  const handleStartChatWithChar = async (charId: string) => {
    const existing = chats.find((c) => c.character_id === charId);
    if (existing) {
      setActiveChatId(existing.id);
      setActiveTab('chat');
      return;
    }
    const char = characters.find((c) => c.id === charId);
    const created = await api.createChat({
      character_id: charId,
      world_id: char?.world_id,
      title: `Chronicle with ${char?.name || 'Character'}`,
    });
    setChats([created, ...chats]);
    setActiveChatId(created.id);
    setActiveTab('chat');
  };

  const navItems: { id: StudioTab; label: string; badge?: number; icon: React.ReactNode }[] = [
    {
      id: 'chat',
      label: 'Roleplay Chat',
      badge: chats.length,
      icon: <MessageSquare className="w-4 h-4" />,
    },
    {
      id: 'characters',
      label: 'Character Forge',
      badge: characters.length,
      icon: <Users className="w-4 h-4" />,
    },
    {
      id: 'worlds',
      label: 'World Codex',
      badge: worlds.length,
      icon: <BookOpen className="w-4 h-4" />,
    },
    {
      id: 'gallery',
      label: 'Asset Gallery',
      badge: gallery.length,
      icon: <ImageIcon className="w-4 h-4" />,
    },
  ];

  const isAdmin = userProfile?.role === 'admin';

  if (loading && !authConfig) {
    return (
      <div className="h-screen w-screen bg-[#090b10] flex items-center justify-center text-sm text-slate-400 gap-2">
        <Sparkles className="w-4 h-4 text-amber-400 animate-spin" />
        Initializing Hivemind Studio...
      </div>
    );
  }

  if (authConfig && !userProfile && !loading) {
    return (
      <LoginScreen
        authConfig={authConfig}
        initialError={authError}
        onAuthenticated={bootstrapSession}
      />
    );
  }

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-[#090b10] text-slate-100">
      {/* Compact Single-Row Top Header (< 12% viewport height per content-first-noise-reduction) */}
      <header className="h-13 px-4 border-b border-white/10 bg-[#0c0f17] flex items-center justify-between gap-4 shrink-0">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-amber-400 via-orange-500 to-violet-600 flex items-center justify-center shadow-md shadow-amber-500/20">
              <Sparkles className="w-4 h-4 text-slate-950" />
            </div>
            <div>
              <span className="font-extrabold tracking-tight text-sm text-white">HIVEMIND</span>
              <span className="hidden sm:inline-block ml-2 text-[11px] text-slate-400">
                Hivemind Cloud Roleplay Studio
              </span>
            </div>
          </div>

          {/* Primary Workspace Navigation Tabs */}
          <nav className="flex items-center gap-1" aria-label="Studio Workspaces">
            {navItems.map((item) => {
              const active = activeTab === item.id;
              const isAdmin = userProfile?.role === 'admin';

  if (loading && !authConfig) {
    return (
      <div className="h-screen w-screen bg-[#090b10] flex items-center justify-center text-sm text-slate-400 gap-2">
        <Sparkles className="w-4 h-4 text-amber-400 animate-spin" />
        Initializing Hivemind Studio...
      </div>
    );
  }

  if (authConfig && !userProfile && !loading) {
    return (
      <LoginScreen
        authConfig={authConfig}
        initialError={authError}
        onAuthenticated={bootstrapSession}
      />
    );
  }

  return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setActiveTab(item.id)}
                  className={`px-3 py-1.5 rounded-xl text-xs font-semibold flex items-center gap-2 transition cursor-pointer ${
                    active
                      ? 'bg-amber-500 text-slate-950 shadow-sm'
                      : 'text-slate-300 hover:bg-white/5 hover:text-white'
                  }`}
                >
                  {item.icon}
                  <span>{item.label}</span>
                  {item.badge !== undefined && (
                    <span
                      className={`text-[10px] px-1.5 py-0.2 rounded-full ${
                        active ? 'bg-slate-950/20 text-slate-950 font-bold' : 'bg-white/10 text-slate-300'
                      }`}
                    >
                      {item.badge}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>
        </div>

        {/* Right Profile Pill, Admin Controls & Telemetry */}
        <div className="flex items-center gap-2.5">
          {isAdmin && status && (
            <div className="hidden xl:flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-[11px] text-emerald-300">
              <Cpu className="w-3.5 h-3.5 text-emerald-400" />
              <span>
                {status.hardware.cloud_run
                  ? 'GCP Cloud Run'
                  : status.hardware.is_apple_silicon
                  ? `Apple Silicon ${status.hardware.architecture}`
                  : `${status.hardware.system} ${status.hardware.architecture}`}{' '}
                •{' '}
                {status.hardware.cuda_available
                  ? 'CUDA GPU Ready'
                  : status.hardware.mps_available
                  ? 'Metal MPS Ready'
                  : 'Cloud / CPU'}
              </span>
            </div>
          )}

          {isAdmin && (
            <>
              <button
                type="button"
                onClick={() => setModerationOpen(true)}
                className="px-3 py-1.5 rounded-xl bg-[#151a28] hover:bg-white/10 border border-white/15 text-xs font-medium text-emerald-200 flex items-center gap-1.5 cursor-pointer"
                title="Admin SFW Trigger-Word Moderation Policy"
              >
                <ShieldAlert className="w-3.5 h-3.5 text-emerald-400" />
                <span className="hidden sm:inline">SFW Guard</span>
              </button>

              <button
                type="button"
                onClick={() => setSettingsOpen(true)}
                className="px-3 py-1.5 rounded-xl bg-[#151a28] hover:bg-white/10 border border-white/15 text-xs font-medium text-slate-200 flex items-center gap-1.5 cursor-pointer"
              >
                <Settings className="w-3.5 h-3.5 text-amber-400" />
                <span className="hidden sm:inline">Inference Engines</span>
              </button>
            </>
          )}

          {userProfile && (
            <div className="flex items-center gap-2 pl-2 border-l border-white/10">
              <div
                className={`px-2.5 py-1 rounded-xl border text-[11px] font-semibold flex items-center gap-1.5 ${
                  isAdmin
                    ? 'bg-emerald-500/15 border-emerald-500/30 text-emerald-200'
                    : 'bg-amber-500/15 border-amber-500/30 text-amber-200'
                }`}
                title={`Signed in as ${userProfile.email || userProfile.uid} (${userProfile.role})`}
              >
                {isAdmin ? (
                  <Shield className="w-3.5 h-3.5 text-emerald-400" />
                ) : (
                  <UserIcon className="w-3.5 h-3.5 text-amber-400" />
                )}
                <span className="hidden md:inline max-w-[140px] truncate">
                  {userProfile.email || userProfile.uid}
                </span>
                <span className="uppercase text-[10px] opacity-80">
                  {userProfile.role}
                </span>
              </div>

              <button
                type="button"
                onClick={handleSignOut}
                className="p-1.5 rounded-xl bg-[#151a28] hover:bg-rose-500/20 border border-white/15 hover:border-rose-500/40 text-slate-300 hover:text-rose-200 cursor-pointer"
                title="Sign Out / Switch Account"
                aria-label="Sign Out"
              >
                <LogOut className="w-3.5 h-3.5" />
              </button>
            </div>
          )}
        </div>
      </header>

      {/* Active Studio Workspace */}
      <main className="flex-1 overflow-hidden relative">
        {loading ? (
          <div className="h-full w-full flex items-center justify-center text-sm text-slate-400 gap-2">
            <Sparkles className="w-4 h-4 text-amber-400 animate-spin" />
            Initializing Hivemind Studio on Apple Silicon...
          </div>
        ) : (
          <>
            {activeTab === 'chat' && (
              <RoleplayChat
                characters={characters}
                worlds={worlds}
                chats={chats}
                gallery={gallery}
                activeChatId={activeChatId}
                onSelectChat={setActiveChatId}
                onChatsUpdated={(next, newId) => {
                  setChats(next);
                  if (newId !== undefined) setActiveChatId(newId);
                }}
                onGalleryUpdated={refreshGallery}
              />
            )}

            {activeTab === 'characters' && (
              <CharacterForge
                characters={characters}
                worlds={worlds}
                onCharactersUpdated={setCharacters}
                onStartChatWithChar={handleStartChatWithChar}
                onGalleryUpdated={refreshGallery}
              />
            )}

            {activeTab === 'worlds' && (
              <WorldCodex
                worlds={worlds}
                gallery={gallery}
                onWorldsUpdated={setWorlds}
                onGalleryUpdated={refreshGallery}
              />
            )}

            {activeTab === 'gallery' && (
              <AssetGallery
                assets={gallery}
                characters={characters}
                worlds={worlds}
                onGalleryUpdated={refreshGallery}
              />
            )}
          </>
        )}
      </main>

      {/* Admin-Only Modals */}
      {isAdmin && (
        <>
          <EngineSettingsModal
            isOpen={settingsOpen}
            onClose={() => setSettingsOpen(false)}
            status={status}
            onStatusUpdated={refreshStatus}
          />

          <AdminModerationModal
            isOpen={moderationOpen}
            onClose={() => setModerationOpen(false)}
          />
        </>
      )}
    </div>
  );
};
