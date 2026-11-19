export interface CharacterCard {
  id: string;
  name: string;
  title: string;
  description: string;
  personality: string;
  scenario: string;
  first_mes: string;
  mes_example: string;
  system_prompt: string;
  post_history_instructions: string;
  creator_notes: string;
  tags: string[];
  visual_prompt_tags: string;
  negative_prompt_tags: string;
  avatar_url: string;
  world_id: string | null;
  default_workflow_id: string | null;
  created_at?: string;
  updated_at?: string;
}

export type LoreCategory =
  | 'location'
  | 'faction'
  | 'magic_tech'
  | 'history'
  | 'artifact'
  | 'relationship'
  | 'rule';

export interface LoreEntry {
  id: string;
  title: string;
  keys: string[];
  secondary_keys: string[];
  category: LoreCategory;
  content: string;
  visual_description: string;
  image_url: string;
  map_x?: number | null;
  map_y?: number | null;
  constant: boolean;
  enabled: boolean;
  priority: number;
}

export interface Lorebook {
  id: string;
  name: string;
  subtitle: string;
  description: string;
  aesthetic_style: string;
  map_image_url?: string;
  map_prompt?: string;
  entries: LoreEntry[];
  created_at?: string;
  updated_at?: string;
}

export interface TriggeredLoreInfo {
  entry_id: string;
  title: string;
  category: string;
  matched_keys: string[];
  snippet: string;
  visual_description: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  sender_name: string;
  content: string;
  swipes: string[];
  active_swipe: number;
  image_url: string | null;
  image_prompt: string | null;
  image_seed?: number | null;
  image_metadata_url?: string | null;
  triggered_lore: TriggeredLoreInfo[];
  timings?: {
    reply_ms?: number;
    render_ms?: number;
    prompt_ms?: number;
    scene_state_ms?: number;
    total_ms?: number;
  } | null;
  created_at?: string;
}

export interface SceneState {
  location: string;
  time_and_lighting: string;
  weather: string;
  atmosphere: string;
  attire: string;
  hairstyle: string;
  makeup: string;
  skin_and_condition: string;
  pose_and_action: string;
  pinned_fields?: string[];
}

export interface ChatSession {
  id: string;
  title: string;
  character_id: string;
  world_id: string | null;
  user_persona_name: string;
  user_persona_desc: string;
  messages: ChatMessage[];
  situation_checkpoint?: string;
  checkpoint_msg_count?: number;
  scene_state?: SceneState;
  created_at?: string;
  updated_at?: string;
}

export type StudioNodeType =
  | 'character_source'
  | 'lore_injector'
  | 'prompt_template'
  | 'llm_generator'
  | 'image_generator'
  | 'image_preview';

export interface WorkflowNode {
  id: string;
  type: StudioNodeType;
  position: { x: number; y: number };
  data: Record<string, any>;
}

export interface WorkflowEdge {
  id: string;
  source: string;
  target: string;
  sourceHandle?: string | null;
  targetHandle?: string | null;
}

export interface WorkflowGraph {
  id: string;
  name: string;
  description: string;
  category: string;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  created_at?: string;
  updated_at?: string;
}

export interface NodeExecutionTrace {
  node_id: string;
  node_type: StudioNodeType;
  status: 'completed' | 'error';
  duration_ms: number;
  outputs: Record<string, any>;
  error?: string | null;
}

export interface WorkflowExecutionResult {
  workflow_id: string;
  status: 'completed' | 'error';
  total_duration_ms: number;
  node_traces: Record<string, NodeExecutionTrace>;
  generated_images: string[];
  final_text: string;
}

export interface ImagePipelineProfile {
  provider:
    | 'inherit'
    | 'auto'
    | 'mps_diffusers'
    | 'comfyui'
    | 'vertex_imagen'
    | 'runpod_serverless'
    | 'procedural_art';
  checkpoint: string;
  vertex_model: string;
  render_mode: string;
  face_detailer: boolean | null;
  steps: number | null;
  cfg: number | null;
}

export interface InferenceConfig {
  log_level?: 'INFO' | 'DEBUG';
  llm_provider: 'auto' | 'vertex_ai' | 'ollama' | 'openai_compat' | 'builtin_synth';
  sfw_mode?: boolean;
  ollama_base_url: string;
  ollama_model: string;
  openai_base_url: string;
  openai_api_key: string;
  openai_model: string;
  vertex_gemini_model?: string;
  temperature: number;
  max_tokens: number;

  image_provider:
    | 'auto'
    | 'mps_diffusers'
    | 'comfyui'
    | 'vertex_imagen'
    | 'runpod_serverless'
    | 'procedural_art';
  vertex_project_id?: string;
  vertex_location?: string;
  vertex_imagen_model?: string;
  runpod_endpoint_id?: string;
  runpod_api_key?: string;
  mps_model_id: string;
  mps_use_fp16: boolean;
  mps_attention_slicing: boolean;
  comfyui_base_url: string;
  comfyui_checkpoint: string;
  comfyui_render_mode?: 'hybrid_refiner' | 'single_stylized' | 'single_raw' | 'action_hybrid';
  comfyui_refiner_checkpoint?: string;
  comfyui_landscape_checkpoint?: string;
  comfyui_refiner_switch?: number;
  comfyui_face_detailer_enabled?: boolean;
  comfyui_face_detailer_model?: string;
  comfyui_face_detailer_denoise?: number;
  comfyui_face_detailer_scale?: number;
  comfyui_sampler?: string;
  comfyui_scheduler?: string;
  default_width: number;
  default_height: number;
  default_steps: number;
  default_cfg: number;
  use_specialist_image_models?: boolean;
  portrait_profile?: ImagePipelineProfile;
  scene_profile?: ImagePipelineProfile;
  scenery_profile?: ImagePipelineProfile;
  workflow_profile?: ImagePipelineProfile;
  scene_prompt_template?: string;
  studio_prompt_template?: string;
  portrait_prompt_template?: string;
  location_prompt_template?: string;
  world_map_prompt_template?: string;
}

export interface ModerationPolicy {
  enabled: boolean;
  mode: 'block' | 'redact';
  trigger_words: string[];
  regex_patterns: string[];
  updated_by: string;
  updated_at: string;
}

export interface SystemStatus {
  hardware: {
    architecture: string;
    system: string;
    processor: string;
    is_apple_silicon: boolean;
    cloud_run?: boolean;
    torch_available: boolean;
    torch_version: string;
    mps_available: boolean;
    cuda_available?: boolean;
    cuda_device?: string;
    mps_loaded_models: string[];
  };
  providers: {
    ollama: { online: boolean; models: string[] };
    openai_compat: { online: boolean; models: string[] };
    comfyui: { online: boolean; checkpoints?: string[]; stats: Record<string, any> };
  };
  config: InferenceConfig;
  counts: {
    characters: number;
    worlds: number;
    chats: number;
    workflows: number;
    gallery: number;
  };
}

export interface GalleryAsset {
  id: string;
  url: string;
  prompt: string;
  negative_prompt: string;
  provider: string;
  width: number;
  height: number;
  seed: number;
  metadata_url?: string | null;
  character_id?: string | null;
  world_id?: string | null;
  location_entry_id?: string | null;
  workflow_id?: string | null;
  duration_ms?: number | null;
  created_at: string;
}

export interface AuthConfig {
  saas_auth_enabled: boolean;
  firebase_api_key: string;
  firebase_auth_domain: string;
  firebase_project_id: string;
}

export interface UserProfile {
  uid: string;
  email: string;
  role: 'user' | 'admin';
  plan: string;
  saas_auth_enabled: boolean;
}
