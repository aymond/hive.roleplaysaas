import type {
  AdminUserRecord,
  AuthConfig,
  CharacterCard,
  ChatSession,
  GalleryAsset,
  InferenceConfig,
  Lorebook,
  SceneState,
  SystemStatus,
  TriggeredLoreInfo,
  UserProfile,
  WorkflowExecutionResult,
  WorkflowGraph,
} from './types';
import { getAuthToken, getMockSession } from './auth/firebase';

export function getAuthHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  const token = getAuthToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  const mock = getMockSession();
  if (mock) {
    headers['X-Mock-Uid'] = mock.uid;
  }
  return headers;
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
      ...(options?.headers || {}),
    },
  });
  if (!res.ok) {
    const errText = await res.text();
    const err = new Error(errText || `HTTP ${res.status}`) as Error & { status?: number };
    err.status = res.status;
    throw err;
  }
  return res.json() as Promise<T>;
}

export const api = {
  getAuthConfig: () => request<AuthConfig>('/api/auth/config'),
  getCurrentUser: () => request<UserProfile>('/api/auth/me'),
  deleteMyAccount: () =>
    request<{ status: string; uid: string; deleted_media_objects: number }>('/api/account', {
      method: 'DELETE',
    }),
  listAdminUsers: () => request<AdminUserRecord[]>('/api/admin/users'),
  updateAdminUser: (
    uid: string,
    patch: { role?: 'user' | 'admin'; plan?: string; disabled?: boolean; credit_balance?: number }
  ) =>
    request<AdminUserRecord>(`/api/admin/users/${encodeURIComponent(uid)}`, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    }),
  deleteAdminUser: (uid: string) =>
    request<{ status: string; uid: string }>(`/api/admin/users/${encodeURIComponent(uid)}`, {
      method: 'DELETE',
    }),
  getSystemStatus: () => request<SystemStatus>('/api/system/status'),
  updateSystemConfig: (config: InferenceConfig) =>
    request<{ status: string; config: InferenceConfig }>('/api/system/config', {
      method: 'PUT',
      body: JSON.stringify(config),
    }),

  // Characters
  listCharacters: () => request<CharacterCard[]>('/api/characters'),
  createCharacter: (card: Partial<CharacterCard>, autoGenerateAvatar = true) =>
    request<CharacterCard>(`/api/characters?auto_generate_avatar=${autoGenerateAvatar}`, {
      method: 'POST',
      body: JSON.stringify(card),
    }),
  generateCharacterProfile: (payload: {
    brief?: string;
    name?: string;
    title?: string;
    race_origins?: string;
    appearance?: string;
    world_id?: string | null;
  }) =>
    request<{
      name: string;
      title: string;
      description: string;
      personality: string;
      scenario: string;
      first_mes: string;
      mes_example: string;
      tags: string[];
      visual_prompt_tags: string;
    }>('/api/characters/generate-profile', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updateCharacter: (id: string, card: CharacterCard) =>
    request<CharacterCard>(`/api/characters/${id}`, {
      method: 'PUT',
      body: JSON.stringify(card),
    }),
  deleteCharacter: (id: string) =>
    request<{ status: string }>(`/api/characters/${id}`, { method: 'DELETE' }),
  generateCharacterAvatar: (id: string, seed?: number) =>
    request<{ character: CharacterCard; asset: GalleryAsset }>(
      `/api/characters/${id}/generate-avatar${seed !== undefined ? `?seed=${seed}` : ''}`,
      { method: 'POST' }
    ),
  importCharacterFile: async (file: File): Promise<CharacterCard> => {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch('/api/characters/import', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: form,
    });
    if (!res.ok) {
      throw new Error(await res.text());
    }
    return res.json();
  },

  // Worlds / Lorebooks
  listWorlds: () => request<Lorebook[]>('/api/worlds'),
  createWorld: (world: Partial<Lorebook>) =>
    request<Lorebook>('/api/worlds', {
      method: 'POST',
      body: JSON.stringify(world),
    }),
  updateWorld: (id: string, world: Lorebook) =>
    request<Lorebook>(`/api/worlds/${id}`, {
      method: 'PUT',
      body: JSON.stringify(world),
    }),
  deleteWorld: (id: string) =>
    request<{ status: string }>(`/api/worlds/${id}`, { method: 'DELETE' }),
  scanLorebook: (worldId: string, text: string, characterName = 'Character', userName = 'Traveler') =>
    request<{
      triggered: TriggeredLoreInfo[];
      context_block: string;
      visual_tags_block: string;
    }>(`/api/worlds/${worldId}/scan`, {
      method: 'POST',
      body: JSON.stringify({
        text,
        character_name: characterName,
        user_name: userName,
      }),
    }),
  generateLoreEntryImage: (worldId: string, entryId: string) =>
    request<{ world: Lorebook; entry: any; asset: GalleryAsset }>(
      `/api/worlds/${worldId}/entries/${entryId}/generate-image`,
      { method: 'POST' }
    ),
  generateWorldMap: (worldId: string, customPrompt?: string) =>
    request<{ world: Lorebook; asset: GalleryAsset }>(
      `/api/worlds/${worldId}/generate-map`,
      {
        method: 'POST',
        body: customPrompt?.trim() ? JSON.stringify({ custom_prompt: customPrompt.trim() }) : undefined,
      }
    ),
  pinAssetToLocation: (assetId: string, locationEntryId: string | null) =>
    request<{ asset: GalleryAsset }>(`/api/gallery/${assetId}/pin-location`, {
      method: 'POST',
      body: JSON.stringify({ location_entry_id: locationEntryId }),
    }),

  // Roleplay Chats
  listChats: () => request<ChatSession[]>('/api/chats'),
  createChat: (payload: {
    character_id: string;
    world_id?: string | null;
    title?: string;
    user_persona_name?: string;
    user_persona_desc?: string;
  }) =>
    request<ChatSession>('/api/chats', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  deleteChat: (chatId: string) =>
    request<{ status: string }>(`/api/chats/${chatId}`, { method: 'DELETE' }),
  deleteChatMessage: (chatId: string, msgId: string) =>
    request<{ session: ChatSession }>(`/api/chats/${chatId}/messages/${msgId}`, {
      method: 'DELETE',
    }),
  sendMessage: (chatId: string, content: string, illustrateScene = false) =>
    request<{
      session: ChatSession;
      provider: string;
      triggered_lore: TriggeredLoreInfo[];
      timings?: Record<string, any>;
    }>(`/api/chats/${chatId}/messages`, {
      method: 'POST',
      body: JSON.stringify({ content, illustrate_scene: illustrateScene }),
    }),
  streamMessage: async (
    chatId: string,
    content: string,
    onDelta: (delta: string) => void
  ): Promise<{ session: ChatSession; provider: string; timings?: Record<string, any> }> => {
    const resp = await fetch(`/api/chats/${chatId}/messages/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content, illustrate_scene: false }),
    });
    if (!resp.ok || !resp.body) {
      throw new Error(`Stream error: ${resp.status}`);
    }
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let finalPayload: { session: ChatSession; provider: string; timings?: Record<string, any> } | null = null;
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split('\n\n');
      buffer = parts.pop() || '';
      for (const part of parts) {
        const line = part.trim();
        if (!line.startsWith('data:')) continue;
        try {
          const evt = JSON.parse(line.slice(5).trim());
          if (evt.type === 'delta' && evt.delta) {
            onDelta(evt.delta);
          } else if (evt.type === 'done') {
            finalPayload = {
              session: evt.session,
              provider: evt.provider,
              timings: evt.timings,
            };
          }
        } catch {
          // ignore malformed SSE chunk
        }
      }
    }
    if (!finalPayload) {
      throw new Error('Stream ended without final payload');
    }
    return finalPayload;
  },
  getSystemMetrics: () =>
    request<{
      chat: { count: number; avg_ms: number | null; p50_ms: number | null; p95_ms: number | null; latest_ms: number | null };
      scene: { count: number; avg_ms: number | null; p50_ms: number | null; p95_ms: number | null; latest_ms: number | null };
      studio: { count: number; avg_ms: number | null; p50_ms: number | null; p95_ms: number | null; latest_ms: number | null };
    }>('/api/system/metrics'),
  swipeMessage: (chatId: string, msgId: string, direction: 'prev' | 'next' | 'regenerate') =>
    request<{ session: ChatSession; provider?: string }>(
      `/api/chats/${chatId}/messages/${msgId}/swipe`,
      {
        method: 'POST',
        body: JSON.stringify({ direction }),
      }
    ),
  illustrateMessage: (
    chatId: string,
    msgId: string,
    customPrompt?: string,
    reusePrompt?: boolean
  ) =>
    request<{ session: ChatSession; asset: GalleryAsset }>(
      `/api/chats/${chatId}/messages/${msgId}/illustrate`,
      {
        method: 'POST',
        body:
          customPrompt || reusePrompt
            ? JSON.stringify({
                ...(customPrompt ? { custom_prompt: customPrompt } : {}),
                ...(reusePrompt ? { reuse_prompt: true } : {}),
              })
            : undefined,
      }
    ),
  updateChatCheckpoint: (
    chatId: string,
    payload: { refresh?: boolean; custom_checkpoint?: string }
  ) =>
    request<{ session: ChatSession }>(`/api/chats/${chatId}/checkpoint`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updateChatSceneState: (chatId: string, state: SceneState) =>
    request<{ session: ChatSession }>(`/api/chats/${chatId}/scene-state`, {
      method: 'POST',
      body: JSON.stringify(state),
    }),

  // Node Workflows
  listWorkflows: () => request<WorkflowGraph[]>('/api/workflows'),
  saveWorkflow: (wf: WorkflowGraph) =>
    request<WorkflowGraph>(`/api/workflows/${wf.id}`, {
      method: 'PUT',
      body: JSON.stringify(wf),
    }),
  createWorkflow: (wf: Partial<WorkflowGraph>) =>
    request<WorkflowGraph>('/api/workflows', {
      method: 'POST',
      body: JSON.stringify(wf),
    }),
  executeWorkflow: (wf: WorkflowGraph) =>
    request<{
      execution: WorkflowExecutionResult;
      workflow: WorkflowGraph;
      new_assets: GalleryAsset[];
    }>('/api/workflows/execute', {
      method: 'POST',
      body: JSON.stringify(wf),
    }),

  // Gallery
  listGallery: () => request<GalleryAsset[]>('/api/gallery'),
  deleteGalleryAsset: (assetId: string) =>
    request<{ status: string; id: string }>(`/api/gallery/${assetId}`, {
      method: 'DELETE',
    }),
  generateGalleryImage: (payload: {
    prompt: string;
    negative_prompt?: string;
    width?: number;
    height?: number;
    steps?: number;
    cfg?: number;
    seed?: number;
  }) =>
    request<GalleryAsset>('/api/gallery/generate', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  generateBackstoryImage: (payload: {
    custom_prompt: string;
    character_id?: string | null;
    world_id?: string | null;
    chat_id?: string | null;
    include_character_visuals?: boolean;
    include_scenario_backstory?: boolean;
    include_world_lore?: boolean;
    use_llm_director?: boolean;
    render_mode?: 'hybrid_refiner' | 'single_stylized' | 'single_raw' | 'action_hybrid';
    face_detailer?: boolean;
    width?: number;
    height?: number;
    steps?: number;
    cfg?: number;
    seed?: number;
  }) =>
    request<{
      asset: GalleryAsset;
      assembled_prompt: string;
      triggered_lore: TriggeredLoreInfo[];
      image_provider: string;
      llm_provider?: string | null;
    }>('/api/backstory-image', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  // Admin SFW Moderation Policy
  getModerationPolicy: () => request<import('./types').ModerationPolicy>('/api/admin/moderation'),
  updateModerationPolicy: (policy: import('./types').ModerationPolicy) =>
    request<import('./types').ModerationPolicy>('/api/admin/moderation', {
      method: 'PUT',
      body: JSON.stringify(policy),
    }),
  testModerationPolicy: (text: string) =>
    request<{ blocked: boolean; matched_terms: string[]; sanitized_texts: string[] }>(
      '/api/admin/moderation/test',
      {
        method: 'POST',
        body: JSON.stringify({ text }),
      }
    ),
};
