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
  Menu,
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
import { AdminPage } from './components/AdminPage';

type StudioTab = 'chat' | 'characters' | 'worlds' | 'gallery' | 'admin';

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
  const [adminMenuOpen, setAdminMenuOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [loading, setLoading] = useState(true);

  const handleSignOut = useCallback(() => {
    clearAllAuthSessions();
    setUserProfile(null);
    setActiveTab('chat');
    setStatus(null);
    setCharacters([]);
    setWorlds([]);
    setChats([]);
    setActiveChatId('');
    setGallery([]);
    setSettingsOpen(false);
    setModerationOpen(false);
    setAdminMenuOpen(false);
    setUserMenuOpen(false);
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
      <div className="h-[100dvh] w-full bg-[#090b10] flex items-center justify-center text-sm text-slate-400 gap-2">
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
    <div className="flex flex-col h-[100dvh] w-full overflow-hidden bg-[#090b10] text-slate-100">
      {/* Compact Single-Row Top Header */}
      <header className="h-13 px-3 sm:px-4 border-b border-white/10 bg-[#0c0f17] flex items-center justify-between gap-3 shrink-0">
        <div className="flex items-center gap-4 lg:gap-6 min-w-0">
          <div className="flex items-center gap-2.5 shrink-0">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-amber-400 via-orange-500 to-violet-600 flex items-center justify-center shadow-md shadow-amber-500/20">
              <Sparkles className="w-4 h-4 text-slate-950" />
            </div>
            <div className="flex items-baseline gap-1.5 whitespace-nowrap">
              <span className="font-extrabold tracking-tight text-sm text-white">HIVEMIND</span>
              <span className="hidden sm:inline-block text-xs font-medium text-slate-300">
                Roleplay Studio
              </span>
            </div>
          </div>

          {/* Primary Workspace Navigation Tabs (Desktop & Tablet) */}
          <nav className="hidden md:flex items-center gap-1" aria-label="Studio Workspaces">
            {navItems.map((item) => {
              const active = activeTab === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setActiveTab(item.id)}
                  className={`px-3 py-1.5 rounded-xl text-xs font-semibold whitespace-nowrap flex items-center gap-2 transition cursor-pointer ${
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

        {/* Right Profile Pill, Admin Hamburger Menu & Telemetry */}
        <div className="flex items-center gap-2 shrink-0">
          {isAdmin && status && (
            <div className="hidden xl:flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-[11px] text-emerald-300 whitespace-nowrap">
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
            <div className="relative">
              <button
                type="button"
                onClick={() => setAdminMenuOpen((prev) => !prev)}
                className={`px-2.5 py-1.5 rounded-xl border text-xs font-semibold flex items-center gap-1.5 cursor-pointer transition ${
                  adminMenuOpen || activeTab === 'admin'
                    ? 'bg-emerald-500/20 border-emerald-500/40 text-emerald-200'
                    : 'bg-[#151a28] hover:bg-white/10 border-white/15 text-slate-200'
                }`}
                title="Admin Menu (User Management, SFW Guard, Inference Engines)"
                aria-expanded={adminMenuOpen}
                aria-haspopup="menu"
              >
                <Menu className="w-4 h-4 text-emerald-400" />
                <span className="hidden sm:inline">Admin</span>
              </button>

              {adminMenuOpen && (
                <>
                  <div
                    className="fixed inset-0 z-40"
                    onClick={() => setAdminMenuOpen(false)}
                  />
                  <div
                    role="menu"
                    className="absolute right-0 mt-2 w-56 rounded-2xl bg-[#111520] border border-white/15 shadow-2xl py-1.5 z-50"
                  >
                    <button
                      type="button"
                      role="menuitem"
                      onClick={() => {
                        setActiveTab('admin');
                        setAdminMenuOpen(false);
                      }}
                      className={`w-full px-3.5 py-2.5 text-left text-xs font-semibold flex items-center gap-2.5 hover:bg-white/10 cursor-pointer ${
                        activeTab === 'admin' ? 'text-emerald-300 bg-emerald-500/10' : 'text-slate-200'
                      }`}
                    >
                      <Shield className="w-4 h-4 text-emerald-400" />
                      Admin &amp; Users
                    </button>

                    <button
                      type="button"
                      role="menuitem"
                      onClick={() => {
                        setModerationOpen(true);
                        setAdminMenuOpen(false);
                      }}
                      className="w-full px-3.5 py-2.5 text-left text-xs font-semibold text-slate-200 flex items-center gap-2.5 hover:bg-white/10 cursor-pointer"
                    >
                      <ShieldAlert className="w-4 h-4 text-emerald-400" />
                      SFW Guard
                    </button>

                    <button
                      type="button"
                      role="menuitem"
                      onClick={() => {
                        setSettingsOpen(true);
                        setAdminMenuOpen(false);
                      }}
                      className="w-full px-3.5 py-2.5 text-left text-xs font-semibold text-slate-200 flex items-center gap-2.5 hover:bg-white/10 cursor-pointer"
                    >
                      <Settings className="w-4 h-4 text-amber-400" />
                      Inference Engines
                    </button>
                  </div>
                </>
              )}
            </div>
          )}

          {userProfile && (
            <div className="relative pl-1.5 border-l border-white/10">
              <button
                type="button"
                onClick={() => {
                  setUserMenuOpen((prev) => !prev);
                  setAdminMenuOpen(false);
                }}
                className={`p-2 rounded-xl border transition cursor-pointer flex items-center justify-center ${
                  userMenuOpen
                    ? 'bg-amber-500/20 border-amber-500/40 text-amber-200'
                    : isAdmin
                    ? 'bg-emerald-500/15 hover:bg-emerald-500/25 border-emerald-500/30 text-emerald-200'
                    : 'bg-[#151a28] hover:bg-white/10 border-white/15 text-slate-200'
                }`}
                title={userProfile.email || userProfile.uid}
                aria-label="Account menu"
                aria-expanded={userMenuOpen}
                aria-haspopup="menu"
              >
                <UserIcon className="w-4 h-4" />
              </button>

              {userMenuOpen && (
                <>
                  <div
                    className="fixed inset-0 z-40"
                    onClick={() => setUserMenuOpen(false)}
                  />
                  <div
                    role="menu"
                    className="absolute right-0 mt-2 w-60 rounded-2xl bg-[#111520] border border-white/15 shadow-2xl py-2 z-50"
                  >
                    <div className="px-3.5 py-2 border-b border-white/10">
                      <div className="text-xs font-semibold text-white truncate">
                        {userProfile.email || userProfile.uid}
                      </div>
                      <div className="mt-1 flex items-center gap-1.5 text-[10px] uppercase tracking-wider">
                        <span
                          className={`px-1.5 py-0.5 rounded font-bold ${
                            isAdmin
                              ? 'bg-emerald-500/20 text-emerald-300'
                              : 'bg-amber-500/20 text-amber-300'
                          }`}
                        >
                          {userProfile.role}
                        </span>
                        <span className="text-slate-400">{userProfile.plan}</span>
                      </div>
                    </div>

                    <button
                      type="button"
                      role="menuitem"
                      onClick={handleSignOut}
                      className="w-full px-3.5 py-2.5 text-left text-xs font-semibold text-rose-200 flex items-center gap-2.5 hover:bg-rose-500/15 cursor-pointer"
                    >
                      <LogOut className="w-4 h-4 text-rose-400" />
                      Log Out
                    </button>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </header>

      {/* Active Studio Workspace */}
      <main className="flex-1 overflow-hidden relative">
        {loading ? (
          <div className="h-full w-full flex flex-col items-center justify-center px-6 text-center gap-3">
            <div className="flex items-center gap-2 text-sm font-medium text-slate-200">
              <Sparkles className="w-4 h-4 text-amber-400 animate-spin" />
              Loading your workspace...
            </div>
            <p className="text-xs text-slate-400 max-w-md">
              {[
                'Tip: Bind a World Lorebook to a character so matching keywords automatically enrich your scenes.',
                'Tip: Pin Scene State fields like attire or location to preserve visual continuity across turns.',
                'Tip: Use Character Forge to generate a lore-grounded backstory first, then craft a portrait whenever you are ready.',
              ][Math.floor(Date.now() / 5000) % 3]}
            </p>
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

            {activeTab === 'admin' && isAdmin && userProfile && (
              <AdminPage
                currentUser={userProfile}
                onOpenEngineSettings={() => setSettingsOpen(true)}
                onOpenModeration={() => setModerationOpen(true)}
              />
            )}
          </>
        )}
      </main>

      {/* Mobile Bottom Navigation Bar */}
      <nav
        className="md:hidden border-t border-white/10 bg-[#0c0f17] px-2 pt-1.5 pb-[max(0.375rem,env(safe-area-inset-bottom))] flex items-center justify-around shrink-0"
        aria-label="Mobile Workspaces"
      >
        {navItems.map((item) => {
          const active = activeTab === item.id;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => setActiveTab(item.id)}
              className={`min-h-[44px] min-w-[48px] px-2 py-1 rounded-xl flex flex-col items-center justify-center gap-0.5 text-[10px] font-semibold transition cursor-pointer ${
                active ? 'text-amber-400 bg-amber-500/10' : 'text-slate-400 hover:text-white'
              }`}
            >
              {item.icon}
              <span className="truncate max-w-[64px]">{item.label.split(' ')[0]}</span>
            </button>
          );
        })}
      </nav>

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
