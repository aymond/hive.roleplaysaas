import React, { useEffect, useState } from 'react';
import { Clock, Cpu, CheckCircle2 } from 'lucide-react';

export function useElapsedTimer(isActive: boolean): string {
  const [elapsedMs, setElapsedMs] = useState(0);

  useEffect(() => {
    if (!isActive) {
      setElapsedMs(0);
      return;
    }
    const start = performance.now();
    const interval = window.setInterval(() => {
      setElapsedMs(performance.now() - start);
    }, 100);
    return () => window.clearInterval(interval);
  }, [isActive]);

  return (elapsedMs / 1000).toFixed(1);
}

interface GenerationProgressCardProps {
  title: string;
  subtitle?: string;
  engineLabel?: string;
  stages?: string[];
  compact?: boolean;
  accent?: 'amber' | 'cyan' | 'violet' | 'emerald';
}

export const GenerationProgressCard: React.FC<GenerationProgressCardProps> = ({
  title,
  subtitle,
  engineLabel = 'Cloud / Local Inference',
  stages = [
    'Injecting Character & World Backstory',
    'Executing Model Inference',
    'Decoding & Rendering Output',
  ],
  compact = false,
  accent = 'amber',
}) => {
  const elapsedSec = useElapsedTimer(true);
  const numericSec = parseFloat(elapsedSec);
  const activeStageIndex = numericSec < 1.2 ? 0 : numericSec < 12.0 ? 1 : 2;

  const borderMap = {
    amber: 'border-amber-500/40 bg-amber-950/20',
    cyan: 'border-cyan-500/40 bg-cyan-950/20',
    violet: 'border-violet-500/40 bg-violet-950/20',
    emerald: 'border-emerald-500/40 bg-emerald-950/20',
  };

  return (
    <div
      role="status"
      aria-live="polite"
      className={`rounded-2xl border ${borderMap[accent]} p-3.5 space-y-2.5 shadow-lg transition-all`}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <progress aria-label={title} className="loading-spinner shrink-0" />
          <div className="min-w-0">
            <div className="text-xs font-bold text-white truncate">{title}</div>
            {subtitle && (
              <div className="text-[11px] text-slate-300 truncate">{subtitle}</div>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <span className="hidden sm:inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-white/10 text-slate-200 border border-white/10 font-mono">
            <Cpu className="w-3 h-3 text-amber-400" />
            {engineLabel}
          </span>
          <span className="inline-flex items-center gap-1 text-xs font-mono font-bold px-2 py-0.5 rounded-lg bg-black/50 text-amber-300 border border-amber-500/30">
            <Clock className="w-3 h-3" />
            {elapsedSec}s
          </span>
        </div>
      </div>

      <progress aria-label={`${title} progress`} className="studio-progress block" />

      {!compact && stages.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-1.5 pt-0.5">
          {stages.map((stage, idx) => {
            const isDone = idx < activeStageIndex;
            const isCurrent = idx === activeStageIndex;
            return (
              <div
                key={stage}
                className={`text-[10px] px-2 py-1 rounded-lg border flex items-center gap-1.5 truncate ${
                  isCurrent
                    ? 'bg-amber-500/20 border-amber-400/50 text-amber-200 font-semibold'
                    : isDone
                    ? 'bg-emerald-500/10 border-emerald-500/25 text-emerald-300'
                    : 'bg-black/20 border-white/5 text-slate-500'
                }`}
              >
                <CheckCircle2
                  className={`w-3 h-3 shrink-0 ${
                    isDone
                      ? 'text-emerald-400'
                      : isCurrent
                      ? 'text-amber-400 animate-pulse'
                      : 'text-slate-600'
                  }`}
                />
                <span className="truncate">{stage}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
