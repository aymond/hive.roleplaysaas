import React, { useState, useCallback, useMemo, useEffect } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Handle,
  Position,
  addEdge,
  useNodesState,
  useEdgesState,
  type Connection,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react';
import {
  Play,
  Plus,
  Save,
  Sparkles,
  User,
  BookOpen,
  FileText,
  Cpu,
  Image as ImageIcon,
  Eye,
  Check,
  Clock,
  UserCheck,
} from 'lucide-react';
import { api } from '../api';
import type {
  CharacterCard,
  Lorebook,
  NodeExecutionTrace,
  StudioNodeType,
  WorkflowGraph,
} from '../types';

interface NodeStudioProps {
  workflows: WorkflowGraph[];
  characters: CharacterCard[];
  worlds: Lorebook[];
  onWorkflowsUpdated: (wfs: WorkflowGraph[]) => void;
  onCharactersUpdated: (chars: CharacterCard[]) => void;
  onGalleryUpdated: () => void;
}

interface StudioNodeContextType {
  characters: CharacterCard[];
  worlds: Lorebook[];
  traces: Record<string, NodeExecutionTrace>;
  updateNodeData: (nodeId: string, patch: Record<string, any>) => void;
  applyImageToCharacter: (charId: string, imageUrl: string) => void;
}

const StudioNodeContext = React.createContext<StudioNodeContextType>({
  characters: [],
  worlds: [],
  traces: {},
  updateNodeData: () => {},
  applyImageToCharacter: () => {},
});

function TraceBadge({ nodeId }: { nodeId: string }) {
  const { traces } = React.useContext(StudioNodeContext);
  const trace = traces[nodeId];
  if (!trace) return null;
  return (
    <span
      className={`text-[10px] font-mono px-1.5 py-0.5 rounded flex items-center gap-1 ${
        trace.status === 'completed'
          ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
          : 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
      }`}
    >
      <Clock className="w-2.5 h-2.5" />
      {trace.duration_ms}ms
    </span>
  );
}

const CharacterSourceNode: React.FC<NodeProps> = ({ id, data }) => {
  const { characters, updateNodeData } = React.useContext(StudioNodeContext);
  const selectedChar =
    characters.find((c) => c.id === data.character_id) || characters[0];

  return (
    <div className="w-72 rounded-xl bg-[#131724] border-2 border-violet-500/60 shadow-xl text-xs overflow-hidden">
      <div className="px-3 py-2 bg-violet-950/60 border-b border-violet-500/30 flex items-center justify-between">
        <span className="font-bold text-violet-200 flex items-center gap-1.5">
          <User className="w-3.5 h-3.5 text-violet-400" />
          {String(data.label || 'Character Card Source')}
        </span>
        <TraceBadge nodeId={id} />
      </div>
      <div className="p-3 space-y-2.5">
        <div>
          <label className="block text-[10px] uppercase text-slate-400 mb-1">
            Character Card
          </label>
          <select
            value={String(data.character_id || selectedChar?.id || '')}
            onChange={(e) => updateNodeData(id, { character_id: e.target.value })}
            className="w-full bg-[#0b0e17] border border-white/15 rounded-lg px-2 py-1.5 text-xs text-white"
          >
            {characters.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} ({c.title})
              </option>
            ))}
          </select>
        </div>
        {selectedChar && (
          <div className="flex items-center gap-2.5 p-2 rounded-lg bg-black/30 border border-white/5">
            <img
              src={selectedChar.avatar_url}
              alt={selectedChar.name}
              width={40}
              height={40}
              className="w-10 h-10 rounded-lg object-cover border border-violet-400/40 shrink-0"
            />
            <div className="min-w-0 flex-1">
              <div className="font-semibold text-white truncate">{selectedChar.name}</div>
              <div className="text-[10px] text-slate-400 line-clamp-2">
                {selectedChar.visual_prompt_tags}
              </div>
            </div>
          </div>
        )}
      </div>
      <div className="px-3 py-1.5 bg-black/40 border-t border-white/5 flex justify-end text-[10px] text-violet-300 font-mono relative">
        <span>visual_tags ●</span>
        <Handle
          type="source"
          position={Position.Right}
          id="visual_tags"
          style={{ background: '#a855f7' }}
        />
      </div>
    </div>
  );
};

const LoreInjectorNode: React.FC<NodeProps> = ({ id, data }) => {
  const { worlds, traces, updateNodeData } = React.useContext(StudioNodeContext);
  const trace = traces[id];

  return (
    <div className="w-72 rounded-xl bg-[#131724] border-2 border-emerald-500/60 shadow-xl text-xs overflow-hidden">
      <div className="px-3 py-2 bg-emerald-950/60 border-b border-emerald-500/30 flex items-center justify-between">
        <span className="font-bold text-emerald-200 flex items-center gap-1.5">
          <BookOpen className="w-3.5 h-3.5 text-emerald-400" />
          {String(data.label || 'World Lore Scanner')}
        </span>
        <TraceBadge nodeId={id} />
      </div>
      <div className="p-3 space-y-2.5">
        <div>
          <label className="block text-[10px] uppercase text-slate-400 mb-1">
            World Lorebook
          </label>
          <select
            value={String(data.world_id || worlds[0]?.id || '')}
            onChange={(e) => updateNodeData(id, { world_id: e.target.value })}
            className="w-full bg-[#0b0e17] border border-white/15 rounded-lg px-2 py-1.5 text-xs text-white"
          >
            {worlds.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-[10px] uppercase text-slate-400 mb-1">
            Trigger Keywords Query
          </label>
          <input
            type="text"
            value={String(data.query_text || '')}
            onChange={(e) => updateNodeData(id, { query_text: e.target.value })}
            placeholder="e.g. spire, pendulum, sector 9"
            className="w-full bg-[#0b0e17] border border-white/15 rounded-lg px-2 py-1.5 text-xs text-emerald-200 font-mono"
          />
        </div>
        {trace?.outputs?.triggered_titles && (
          <div className="text-[10px] text-emerald-300 bg-emerald-950/40 px-2 py-1 rounded border border-emerald-500/20">
            Matched: {(trace.outputs.triggered_titles as string[]).join(', ') || 'Default Entry'}
          </div>
        )}
      </div>
      <div className="px-3 py-1.5 bg-black/40 border-t border-white/5 flex justify-end text-[10px] text-emerald-300 font-mono relative">
        <span>lore_visuals ●</span>
        <Handle
          type="source"
          position={Position.Right}
          id="lore_visuals"
          style={{ background: '#10b981' }}
        />
      </div>
    </div>
  );
};

const PromptTemplateNode: React.FC<NodeProps> = ({ id, data }) => {
  const { updateNodeData } = React.useContext(StudioNodeContext);

  return (
    <div className="w-80 rounded-xl bg-[#131724] border-2 border-amber-500/60 shadow-xl text-xs overflow-hidden">
      <div className="px-3 py-2 bg-amber-950/60 border-b border-amber-500/30 flex items-center justify-between">
        <span className="font-bold text-amber-200 flex items-center gap-1.5">
          <FileText className="w-3.5 h-3.5 text-amber-400" />
          {String(data.label || 'Prompt Combiner')}
        </span>
        <TraceBadge nodeId={id} />
      </div>

      <div className="p-3 space-y-2.5 relative">
        <div className="flex justify-between text-[10px] font-mono text-slate-400 pb-1 border-b border-white/5">
          <div className="space-y-1">
            <div className="relative pl-2 text-violet-300">
              <Handle
                type="target"
                position={Position.Left}
                id="char"
                style={{ top: '6px', background: '#a855f7' }}
              />
              ● char
            </div>
            <div className="relative pl-2 text-emerald-300">
              <Handle
                type="target"
                position={Position.Left}
                id="lore"
                style={{ top: '26px', background: '#10b981' }}
              />
              ● lore
            </div>
          </div>
          <div className="relative pr-2 text-amber-300">
            prompt ●
            <Handle
              type="source"
              position={Position.Right}
              id="prompt"
              style={{ top: '14px', background: '#f59e0b' }}
            />
          </div>
        </div>

        <div>
          <label className="block text-[10px] uppercase text-slate-400 mb-1">
            Template ({'{{char}}'}, {'{{lore}}'}, {'{{style}}'})
          </label>
          <textarea
            rows={2}
            value={String(data.template || '{{char}}, {{lore}}, {{style}}')}
            onChange={(e) => updateNodeData(id, { template: e.target.value })}
            className="w-full bg-[#0b0e17] border border-white/15 rounded-lg p-2 text-xs text-amber-100 font-mono"
          />
        </div>
        <div>
          <label className="block text-[10px] uppercase text-slate-400 mb-1">
            Style Modifiers
          </label>
          <input
            type="text"
            value={String(data.style || '')}
            onChange={(e) => updateNodeData(id, { style: e.target.value })}
            className="w-full bg-[#0b0e17] border border-white/15 rounded-lg px-2 py-1 text-xs text-slate-200 font-mono"
          />
        </div>
      </div>
    </div>
  );
};

const LLMGeneratorNode: React.FC<NodeProps> = ({ id, data }) => {
  const { traces, updateNodeData } = React.useContext(StudioNodeContext);
  const trace = traces[id];

  return (
    <div className="w-80 rounded-xl bg-[#131724] border-2 border-pink-500/60 shadow-xl text-xs overflow-hidden">
      <div className="px-3 py-2 bg-pink-950/60 border-b border-pink-500/30 flex items-center justify-between">
        <span className="font-bold text-pink-200 flex items-center gap-1.5">
          <Cpu className="w-3.5 h-3.5 text-pink-400" />
          {String(data.label || 'LLM Prompt & Lore Director')}
        </span>
        <TraceBadge nodeId={id} />
      </div>

      <div className="p-3 space-y-2.5">
        <div className="flex justify-between text-[10px] font-mono text-slate-400 pb-1 border-b border-white/5">
          <span className="relative pl-2 text-amber-300">
            <Handle
              type="target"
              position={Position.Left}
              id="prompt"
              style={{ background: '#f59e0b' }}
            />
            ● prompt_in
          </span>
          <span className="relative pr-2 text-pink-300">
            expanded_prompt ●
            <Handle
              type="source"
              position={Position.Right}
              id="prompt"
              style={{ background: '#ec4899' }}
            />
          </span>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="block text-[10px] uppercase text-slate-400 mb-1">Mode</label>
            <select
              value={String(data.mode || 'visual_prompt')}
              onChange={(e) => updateNodeData(id, { mode: e.target.value })}
              className="w-full bg-[#0b0e17] border border-white/15 rounded-lg px-2 py-1 text-xs text-white"
            >
              <option value="visual_prompt">Visual Art Director</option>
              <option value="lore_expand">World Lore Expander</option>
            </select>
          </div>
          <div>
            <label className="block text-[10px] uppercase text-slate-400 mb-1">
              Director Note
            </label>
            <input
              type="text"
              value={String(data.user_prompt || '')}
              onChange={(e) => updateNodeData(id, { user_prompt: e.target.value })}
              placeholder="Extra direction..."
              className="w-full bg-[#0b0e17] border border-white/15 rounded-lg px-2 py-1 text-xs text-white"
            />
          </div>
        </div>

        {trace?.outputs?.text && (
          <div className="p-2 rounded-lg bg-black/40 border border-pink-500/20 text-[10px] text-slate-300 font-mono line-clamp-3">
            {String(trace.outputs.text)}
          </div>
        )}
      </div>
    </div>
  );
};

const ImageGeneratorNode: React.FC<NodeProps> = ({ id, data }) => {
  const { traces, updateNodeData } = React.useContext(StudioNodeContext);
  const trace = traces[id];

  return (
    <div className="w-80 rounded-xl bg-[#131724] border-2 border-cyan-500/60 shadow-xl text-xs overflow-hidden">
      <div className="px-3 py-2 bg-cyan-950/60 border-b border-cyan-500/30 flex items-center justify-between">
        <span className="font-bold text-cyan-200 flex items-center gap-1.5">
          <ImageIcon className="w-3.5 h-3.5 text-cyan-400" />
          {String(data.label || 'Apple Silicon Image Synthesizer')}
        </span>
        <TraceBadge nodeId={id} />
      </div>

      <div className="p-3 space-y-2.5">
        <div className="flex justify-between text-[10px] font-mono text-slate-400 pb-1 border-b border-white/5">
          <span className="relative pl-2 text-amber-300">
            <Handle
              type="target"
              position={Position.Left}
              id="prompt"
              style={{ background: '#f59e0b' }}
            />
            ● positive_prompt
          </span>
          <span className="relative pr-2 text-cyan-300">
            IMAGE ●
            <Handle
              type="source"
              position={Position.Right}
              id="image_url"
              style={{ background: '#06b6d4' }}
            />
          </span>
        </div>

        <div className="grid grid-cols-3 gap-2">
          <div>
            <label className="block text-[10px] text-slate-400">Size</label>
            <select
              value={`${data.width || 512}x${data.height || 512}`}
              onChange={(e) => {
                const [w, h] = e.target.value.split('x').map(Number);
                updateNodeData(id, { width: w, height: h });
              }}
              className="w-full bg-[#0b0e17] border border-white/15 rounded-lg px-1.5 py-1 text-xs text-white"
            >
              <option value="512x512">512×512</option>
              <option value="768x512">768×512</option>
              <option value="512x768">512×768</option>
            </select>
          </div>
          <div>
            <label className="block text-[10px] text-slate-400">Steps</label>
            <input
              type="number"
              value={Number(data.steps ?? 20)}
              onChange={(e) => updateNodeData(id, { steps: Number(e.target.value) })}
              className="w-full bg-[#0b0e17] border border-white/15 rounded-lg px-2 py-1 text-xs text-white"
            />
          </div>
          <div>
            <label className="block text-[10px] text-slate-400">Seed</label>
            <input
              type="number"
              value={Number(data.seed ?? 777)}
              onChange={(e) => updateNodeData(id, { seed: Number(e.target.value) })}
              className="w-full bg-[#0b0e17] border border-white/15 rounded-lg px-2 py-1 text-xs text-cyan-300 font-mono"
            />
          </div>
        </div>

        <div>
          <label className="block text-[10px] text-slate-400 mb-1">Negative Prompt</label>
          <input
            type="text"
            value={String(data.negative_prompt || 'blurry, low quality, deformed')}
            onChange={(e) => updateNodeData(id, { negative_prompt: e.target.value })}
            className="w-full bg-[#0b0e17] border border-white/15 rounded-lg px-2 py-1 text-[11px] text-slate-300 font-mono"
          />
        </div>

        {trace?.outputs?.provider && (
          <div className="text-[10px] text-cyan-300 truncate">
            Engine: {String(trace.outputs.provider)}
          </div>
        )}
      </div>
    </div>
  );
};

const ImagePreviewNode: React.FC<NodeProps> = ({ id, data }) => {
  const { characters, traces, applyImageToCharacter } =
    React.useContext(StudioNodeContext);
  const trace = traces[id];
  const imgUrl = String(trace?.outputs?.image_url || data.image_url || '');
  const targetCharId = String(
    trace?.outputs?.apply_to_character_id ||
      data.apply_to_character_id ||
      characters[0]?.id ||
      ''
  );

  return (
    <div className="w-72 rounded-xl bg-[#131724] border-2 border-emerald-400/60 shadow-xl text-xs overflow-hidden">
      <div className="px-3 py-2 bg-slate-900 border-b border-white/10 flex items-center justify-between">
        <span className="font-bold text-white flex items-center gap-1.5">
          <Eye className="w-3.5 h-3.5 text-emerald-400" />
          {String(data.label || 'Preview & Asset Output')}
        </span>
        <TraceBadge nodeId={id} />
      </div>

      <div className="p-3 space-y-2.5">
        <div className="relative pl-2 text-[10px] font-mono text-cyan-300">
          <Handle
            type="target"
            position={Position.Left}
            id="image"
            style={{ background: '#06b6d4' }}
          />
          ● IMAGE_IN
        </div>

        {imgUrl ? (
          <div className="rounded-lg overflow-hidden border border-white/15 bg-black">
            <img
              src={imgUrl}
              alt="Workflow Rendered Output"
              width={256}
              height={256}
              className="w-full h-56 object-cover"
            />
          </div>
        ) : (
          <div className="h-48 rounded-lg bg-black/40 border border-dashed border-white/15 flex items-center justify-center text-slate-400">
            Click "Queue Prompt" to render
          </div>
        )}

        {imgUrl && targetCharId && (
          <button
            type="button"
            onClick={() => applyImageToCharacter(targetCharId, imgUrl)}
            className="w-full py-1.5 px-2.5 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 border border-amber-400/40 text-amber-200 font-semibold flex items-center justify-center gap-1.5 cursor-pointer transition"
          >
            <UserCheck className="w-3.5 h-3.5" />
            Apply as Character Avatar
          </button>
        )}
      </div>
    </div>
  );
};

const NODE_TYPES = {
  character_source: CharacterSourceNode,
  lore_injector: LoreInjectorNode,
  prompt_template: PromptTemplateNode,
  llm_generator: LLMGeneratorNode,
  image_generator: ImageGeneratorNode,
  image_preview: ImagePreviewNode,
};

export const NodeStudio: React.FC<NodeStudioProps> = ({
  workflows,
  characters,
  worlds,
  onWorkflowsUpdated,
  onCharactersUpdated,
  onGalleryUpdated,
}) => {
  const [activeWfId, setActiveWfId] = useState<string>(workflows[0]?.id || '');
  const activeWorkflow = workflows.find((w) => w.id === activeWfId) || workflows[0];

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>(
    (activeWorkflow?.nodes as Node[]) || []
  );
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(
    (activeWorkflow?.edges as Edge[]) || []
  );
  const [traces, setTraces] = useState<Record<string, NodeExecutionTrace>>({});
  const [executing, setExecuting] = useState(false);
  const [totalDurationMs, setTotalDurationMs] = useState<number | null>(null);
  const [savedToast, setSavedToast] = useState(false);

  useEffect(() => {
    if (activeWorkflow) {
      setNodes(activeWorkflow.nodes as Node[]);
      setEdges(
        activeWorkflow.edges.map((e) => ({
          ...e,
          animated: true,
          style: { stroke: '#f59e0b', strokeWidth: 2 },
        })) as Edge[]
      );
      setTraces({});
      setTotalDurationMs(null);
    }
  }, [activeWfId]);

  const onConnect = useCallback(
    (connection: Connection) =>
      setEdges((eds) =>
        addEdge(
          {
            ...connection,
            animated: true,
            style: { stroke: '#f59e0b', strokeWidth: 2 },
          },
          eds
        )
      ),
    [setEdges]
  );

  const updateNodeData = useCallback(
    (nodeId: string, patch: Record<string, any>) => {
      setNodes((nds) =>
        nds.map((n) => (n.id === nodeId ? { ...n, data: { ...n.data, ...patch } } : n))
      );
    },
    [setNodes]
  );

  const applyImageToCharacter = useCallback(
    async (charId: string, imageUrl: string) => {
      const target = characters.find((c) => c.id === charId);
      if (!target) return;
      const updated = await api.updateCharacter(target.id, {
        ...target,
        avatar_url: imageUrl,
      });
      onCharactersUpdated(characters.map((c) => (c.id === updated.id ? updated : c)));
      setSavedToast(true);
      setTimeout(() => setSavedToast(false), 2000);
    },
    [characters, onCharactersUpdated]
  );

  const buildCurrentGraphPayload = (): WorkflowGraph => {
    return {
      ...(activeWorkflow || {
        id: 'wf_custom',
        name: 'Custom Pipeline',
        description: '',
        category: 'Custom',
      }),
      nodes: nodes.map((n) => ({
        id: n.id,
        type: n.type as StudioNodeType,
        position: n.position,
        data: n.data,
      })),
      edges: edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        sourceHandle: e.sourceHandle,
        targetHandle: e.targetHandle,
      })),
    };
  };

  const handleQueuePrompt = async () => {
    if (executing) return;
    setExecuting(true);
    try {
      const payload = buildCurrentGraphPayload();
      const res = await api.executeWorkflow(payload);
      setTraces(res.execution.node_traces);
      setTotalDurationMs(res.execution.total_duration_ms);
      setNodes(res.workflow.nodes as Node[]);
      onWorkflowsUpdated(
        workflows.map((w) => (w.id === res.workflow.id ? res.workflow : w))
      );
      onGalleryUpdated();
    } finally {
      setExecuting(false);
    }
  };

  const handleSaveGraph = async () => {
    const payload = buildCurrentGraphPayload();
    const saved = await api.saveWorkflow(payload);
    onWorkflowsUpdated(workflows.map((w) => (w.id === saved.id ? saved : w)));
    setSavedToast(true);
    setTimeout(() => setSavedToast(false), 2000);
  };

  const handleAddNode = (type: StudioNodeType) => {
    const id = `node_${type}_${Date.now().toString().slice(-4)}`;
    const defaults: Record<StudioNodeType, Record<string, any>> = {
      character_source: {
        label: 'Character Card Loader',
        character_id: characters[0]?.id || '',
      },
      lore_injector: {
        label: 'World Lorebook Scanner',
        world_id: worlds[0]?.id || '',
        query_text: 'spire pendulum',
      },
      prompt_template: {
        label: 'Prompt Combiner',
        template: '{{char}}, {{lore}}, {{style}}',
        style: 'cinematic lighting, 8k concept art',
      },
      llm_generator: {
        label: 'LLM Visual Director',
        mode: 'visual_prompt',
        user_prompt: 'Emphasize dramatic atmosphere and intricate details',
      },
      image_generator: {
        label: 'Apple Silicon Image Synthesizer',
        width: 512,
        height: 512,
        steps: 20,
        cfg: 7.0,
        seed: Math.floor(Math.random() * 9000) + 100,
      },
      image_preview: {
        label: 'Asset Output Preview',
        image_url: '',
      },
    };

    const newNode: Node = {
      id,
      type,
      position: {
        x: 180 + (nodes.length % 4) * 220,
        y: 120 + (nodes.length % 3) * 90,
      },
      data: defaults[type],
    };
    setNodes((nds) => [...nds, newNode]);
  };

  const contextValue = useMemo(
    () => ({
      characters,
      worlds,
      traces,
      updateNodeData,
      applyImageToCharacter,
    }),
    [characters, worlds, traces, updateNodeData, applyImageToCharacter]
  );

  return (
    <StudioNodeContext.Provider value={contextValue}>
      <div className="flex flex-col h-full w-full bg-[#080a0f] overflow-hidden">
        {/* ComfyUI-Style Top Control Ribbon */}
        <div className="px-4 py-2.5 border-b border-white/10 bg-[#0d1018] flex flex-wrap items-center justify-between gap-3 z-10">
          <div className="flex items-center gap-3">
            <select
              aria-label="Select Node Workflow Pipeline"
              value={activeWfId}
              onChange={(e) => setActiveWfId(e.target.value)}
              className="bg-[#151a28] border border-white/15 rounded-xl px-3 py-1.5 text-xs font-bold text-white"
            >
              {workflows.map((wf) => (
                <option key={wf.id} value={wf.id}>
                  Pipeline: {wf.name}
                </option>
              ))}
            </select>

            {/* Quick Add Node Buttons */}
            <div className="hidden xl:flex items-center gap-1.5 border-l border-white/10 pl-3">
              <span className="text-[11px] text-slate-400 mr-1">Add Node:</span>
              <button
                type="button"
                onClick={() => handleAddNode('character_source')}
                className="px-2 py-1 rounded-lg bg-violet-500/15 hover:bg-violet-500/25 border border-violet-500/30 text-violet-200 text-[11px] flex items-center gap-1 cursor-pointer"
              >
                <Plus className="w-3 h-3" /> Character
              </button>
              <button
                type="button"
                onClick={() => handleAddNode('lore_injector')}
                className="px-2 py-1 rounded-lg bg-emerald-500/15 hover:bg-emerald-500/25 border border-emerald-500/30 text-emerald-200 text-[11px] flex items-center gap-1 cursor-pointer"
              >
                <Plus className="w-3 h-3" /> Lorebook
              </button>
              <button
                type="button"
                onClick={() => handleAddNode('prompt_template')}
                className="px-2 py-1 rounded-lg bg-amber-500/15 hover:bg-amber-500/25 border border-amber-500/30 text-amber-200 text-[11px] flex items-center gap-1 cursor-pointer"
              >
                <Plus className="w-3 h-3" /> Prompt
              </button>
              <button
                type="button"
                onClick={() => handleAddNode('llm_generator')}
                className="px-2 py-1 rounded-lg bg-pink-500/15 hover:bg-pink-500/25 border border-pink-500/30 text-pink-200 text-[11px] flex items-center gap-1 cursor-pointer"
              >
                <Plus className="w-3 h-3" /> LLM Director
              </button>
              <button
                type="button"
                onClick={() => handleAddNode('image_generator')}
                className="px-2 py-1 rounded-lg bg-cyan-500/15 hover:bg-cyan-500/25 border border-cyan-500/30 text-cyan-200 text-[11px] flex items-center gap-1 cursor-pointer"
              >
                <Plus className="w-3 h-3" /> Image Synth
              </button>
              <button
                type="button"
                onClick={() => handleAddNode('image_preview')}
                className="px-2 py-1 rounded-lg bg-white/10 hover:bg-white/15 border border-white/20 text-slate-200 text-[11px] flex items-center gap-1 cursor-pointer"
              >
                <Plus className="w-3 h-3" /> Preview
              </button>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {totalDurationMs !== null && (
              <span className="text-xs px-2.5 py-1 rounded-lg bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 font-mono">
                DAG Executed in {totalDurationMs}ms
              </span>
            )}

            <button
              type="button"
              onClick={handleSaveGraph}
              className="px-3 py-1.5 rounded-xl bg-[#171c2b] hover:bg-white/10 border border-white/15 text-slate-200 text-xs font-medium flex items-center gap-1.5 cursor-pointer"
            >
              {savedToast ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Save className="w-3.5 h-3.5" />}
              {savedToast ? 'Saved' : 'Save Graph'}
            </button>

            <button
              type="button"
              onClick={handleQueuePrompt}
              disabled={executing}
              className="px-4 py-1.5 rounded-xl bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-400 hover:to-orange-400 text-slate-950 font-bold text-xs flex items-center gap-1.5 cursor-pointer shadow-lg shadow-amber-500/20 disabled:opacity-50"
            >
              {executing ? (
                <>
                  <Sparkles className="w-4 h-4 animate-spin" />
                  Executing Graph...
                </>
              ) : (
                <>
                  <Play className="w-4 h-4 fill-current" />
                  Queue Prompt
                </>
              )}
            </button>
          </div>
        </div>

        {/* Interactive Node Graph Canvas */}
        <div className="flex-1 w-full h-full relative">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            nodeTypes={NODE_TYPES}
            fitView
            colorMode="dark"
          >
            <Background color="#262d40" gap={22} size={1.5} />
            <Controls />
            <MiniMap
              nodeColor={(n) => {
                switch (n.type) {
                  case 'character_source':
                    return '#a855f7';
                  case 'lore_injector':
                    return '#10b981';
                  case 'prompt_template':
                    return '#f59e0b';
                  case 'llm_generator':
                    return '#ec4899';
                  case 'image_generator':
                    return '#06b6d4';
                  default:
                    return '#94a3b8';
                }
              }}
            />
          </ReactFlow>
        </div>
      </div>
    </StudioNodeContext.Provider>
  );
};
