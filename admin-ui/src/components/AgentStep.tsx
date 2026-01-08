'use client';

import { useState } from 'react';

export type StepStatus = 'running' | 'completed' | 'error';

export interface ToolExecution {
  tool: string;
  args: Record<string, unknown>;
  result?: string;
  success?: boolean;
  duration_ms?: number | null;
}

export interface AgentStepData {
  step: number;
  maxSteps: number;
  description: string;
  status: StepStatus;
  tools: ToolExecution[];
  thinking?: string;
  error?: string;
  duration_ms?: number | null;
}

interface AgentStepProps {
  data: AgentStepData;
  defaultExpanded?: boolean;
}

const StatusIcon = ({ status }: { status: StepStatus }) => {
  switch (status) {
    case 'running':
      return (
        <div className="w-5 h-5 border-2 border-[var(--primary)] border-t-transparent rounded-full animate-spin" />
      );
    case 'completed':
      return (
        <div className="w-5 h-5 rounded-full bg-green-500/20 flex items-center justify-center">
          <svg className="w-3 h-3 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
          </svg>
        </div>
      );
    case 'error':
      return (
        <div className="w-5 h-5 rounded-full bg-red-500/20 flex items-center justify-center">
          <svg className="w-3 h-3 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </div>
      );
  }
};

const ToolIcon = ({ tool }: { tool: string }) => {
  const toolLower = tool.toLowerCase();
  if (toolLower.includes('search') || toolLower.includes('web')) return '🔍';
  if (toolLower.includes('reasoning') || toolLower.includes('think')) return '🧠';
  if (toolLower.includes('extract') || toolLower.includes('page')) return '📄';
  if (toolLower.includes('memory') || toolLower.includes('read')) return '💾';
  if (toolLower.includes('write') || toolLower.includes('save')) return '✏️';
  if (toolLower.includes('final') || toolLower.includes('answer')) return '✅';
  if (toolLower.includes('clarif')) return '❓';
  return '🔧';
};

const formatDuration = (ms: number | null | undefined): string => {
  if (ms === null || ms === undefined) return '';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
};

const formatArgs = (args: Record<string, unknown>): string => {
  try {
    const str = JSON.stringify(args, null, 2);
    return str.length > 500 ? str.slice(0, 500) + '...' : str;
  } catch {
    return String(args);
  }
};

export function AgentStep({ data, defaultExpanded = false }: AgentStepProps) {
  const [expanded, setExpanded] = useState(defaultExpanded || data.status === 'running');

  const hasContent = data.tools.length > 0 || data.thinking || data.error;

  return (
    <div className="border border-[var(--border)] rounded-lg overflow-hidden bg-[var(--card)]">
      {/* Header - Always visible */}
      <button
        onClick={() => hasContent && setExpanded(!expanded)}
        disabled={!hasContent}
        className={`w-full flex items-center gap-3 px-4 py-3 text-left transition-colors ${
          hasContent ? 'hover:bg-[var(--background)] cursor-pointer' : 'cursor-default'
        }`}
      >
        <StatusIcon status={data.status} />
        
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium text-sm">
              Step {data.step}/{data.maxSteps}
            </span>
            {data.tools.length > 0 && (
              <span className="text-xs text-[var(--muted)]">
                {data.tools.map(t => t.tool).join(' → ')}
              </span>
            )}
          </div>
          {data.description && (
            <p className="text-xs text-[var(--muted)] truncate">{data.description}</p>
          )}
        </div>

        {data.duration_ms && (
          <span className="text-xs text-[var(--muted)]">
            {formatDuration(data.duration_ms)}
          </span>
        )}

        {hasContent && (
          <svg
            className={`w-4 h-4 text-[var(--muted)] transition-transform ${expanded ? 'rotate-180' : ''}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        )}
      </button>

      {/* Content - Expandable */}
      {expanded && hasContent && (
        <div className="border-t border-[var(--border)] bg-[var(--background)]">
          {/* Tools */}
          {data.tools.map((tool, idx) => (
            <div key={idx} className="px-4 py-3 border-b border-[var(--border)] last:border-b-0">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-lg">{ToolIcon({ tool: tool.tool })}</span>
                <span className="font-mono text-sm font-medium">{tool.tool}</span>
                {tool.success !== undefined && (
                  <span className={`text-xs px-1.5 py-0.5 rounded ${
                    tool.success 
                      ? 'bg-green-500/20 text-green-400' 
                      : 'bg-red-500/20 text-red-400'
                  }`}>
                    {tool.success ? 'success' : 'failed'}
                  </span>
                )}
                {tool.duration_ms && (
                  <span className="text-xs text-[var(--muted)]">
                    {formatDuration(tool.duration_ms)}
                  </span>
                )}
              </div>

              {/* Args */}
              {Object.keys(tool.args).length > 0 && (
                <details className="mb-2">
                  <summary className="text-xs text-[var(--muted)] cursor-pointer hover:text-[var(--foreground)]">
                    Arguments
                  </summary>
                  <pre className="mt-1 p-2 bg-[var(--card)] rounded text-xs overflow-x-auto font-mono">
                    {formatArgs(tool.args)}
                  </pre>
                </details>
              )}

              {/* Result */}
              {tool.result && (
                <details open={tool.tool.toLowerCase().includes('final')}>
                  <summary className="text-xs text-[var(--muted)] cursor-pointer hover:text-[var(--foreground)]">
                    Result
                  </summary>
                  <div className="mt-1 p-2 bg-[var(--card)] rounded text-sm max-h-60 overflow-y-auto">
                    <pre className="whitespace-pre-wrap break-words font-mono text-xs">
                      {tool.result}
                    </pre>
                  </div>
                </details>
              )}
            </div>
          ))}

          {/* Thinking */}
          {data.thinking && (
            <div className="px-4 py-3 border-b border-[var(--border)] last:border-b-0">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-lg">💭</span>
                <span className="font-mono text-sm font-medium">Thinking</span>
              </div>
              <p className="text-sm text-[var(--muted)]">{data.thinking}</p>
            </div>
          )}

          {/* Error */}
          {data.error && (
            <div className="px-4 py-3 bg-red-500/10">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-lg">❌</span>
                <span className="font-medium text-red-400">Error</span>
              </div>
              <p className="text-sm text-red-300">{data.error}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default AgentStep;
