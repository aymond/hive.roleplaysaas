import type {
  CharacterCard,
  ChatSession,
  GalleryAsset,
  InferenceConfig,
  Lorebook,
  SystemStatus,
  TriggeredLoreInfo,
  WorkflowExecutionResult,
  WorkflowGraph,
} from './types';

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...(options?.headers || {}),
    },
    ...options,
  });
  if (!res.ok) {
    const errText = await res.text();
    throw new Error(errText || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  getSystemStatus: () => request<SystemStatus>('/api/system/status'),
  updateSystemConfig: (config: InferenceConfig) =>
    request<{ status: string; config: InferenceConfig }>('/api/system/config', {
      method: 'PUT',
      body: JSON.stringify(config),
    }),

  // Characters
  listCharacters: () => request<CharacterCard[]>('/api/characters'),
  createCharacter: (card: Partial<CharacterCard>) =>
    request<CharacterCard>('/api/characters', {
      method: 'POST',
      body: JSON.stringify(card),
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
  sendMessage: (chatId: string, content: string, illustrateScene = false) =>
    request<{
      session: ChatSession;
      provider: string;
      triggered_lore: TriggeredLoreInfo[];
    }>(`/api/chats/${chatId}/messages`, {
      method: 'POST',
      body: JSON.stringify({ content, illustrate_scene: illustrateScene }),
    }),
  swipeMessage: (chatId: string, msgId: string, direction: 'prev' | 'next' | 'regenerate') =>
    request<{ session: ChatSession; provider?: string }>(
      `/api/chats/${chatId}/messages/${msgId}/swipe`,
      {
        method: 'POST',
        body: JSON.stringify({ direction }),
      }
    ),
  illustrateMessage: (chatId: string, msgId: string, customPrompt?: string) =>
    request<{ session: ChatSession; asset: GalleryAsset }>(
      `/api/chats/${chatId}/messages/${msgId}/illustrate`,
      {
        method: 'POST',
        body: customPrompt ? JSON.stringify({ custom_prompt: customPrompt }) : undefined,
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
    render_mode?: 'hybrid_refiner' | 'single_stylized' | 'single_raw';
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
};
