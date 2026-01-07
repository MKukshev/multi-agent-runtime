'use client';

import { useEffect, useState } from 'react';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Button } from '@/components/Button';
import { adminApi, Template, TemplateVersion, Tool, ToolQuota, MCPConfig, MCPServerConfig, Rule, AGENT_BASE_CLASSES } from '@/lib/api';

interface QuotaEditorProps {
  tools: Tool[];
  quotas: Record<string, ToolQuota>;
  onChange: (quotas: Record<string, ToolQuota>) => void;
}

function QuotaEditor({ tools, quotas, onChange }: QuotaEditorProps) {
  const [selectedTool, setSelectedTool] = useState<string>('');

  function updateQuota(toolName: string, field: keyof ToolQuota, value: number | null) {
    const updated = { ...quotas };
    if (!updated[toolName]) {
      updated[toolName] = { max_calls: null, timeout: 30, cooldown_seconds: null };
    }
    updated[toolName] = { ...updated[toolName], [field]: value };
    onChange(updated);
  }

  function removeQuota(toolName: string) {
    const updated = { ...quotas };
    delete updated[toolName];
    onChange(updated);
  }

  function addQuota() {
    if (!selectedTool || quotas[selectedTool]) return;
    const tool = tools.find((t) => t.name === selectedTool);
    const defaultExec = tool?.config?.execution;
    onChange({
      ...quotas,
      [selectedTool]: {
        max_calls: defaultExec?.max_calls ?? null,
        timeout: defaultExec?.timeout ?? 30,
        cooldown_seconds: defaultExec?.cooldown_seconds ?? null,
      },
    });
    setSelectedTool('');
  }

  const quotaEntries = Object.entries(quotas);
  const availableTools = tools.filter((t) => !quotas[t.name]);

  return (
    <div className="space-y-4">
      <div className="text-sm font-medium text-[var(--muted)] uppercase tracking-wider">
        Per-Tool Quotas
      </div>

      {quotaEntries.length === 0 && (
        <p className="text-sm text-[var(--muted)] italic">No custom quotas. Using tool defaults.</p>
      )}

      {quotaEntries.map(([toolName, quota]) => (
        <div key={toolName} className="p-3 rounded-lg bg-[var(--background)] border border-[var(--border)]">
          <div className="flex items-center justify-between mb-3">
            <span className="font-mono text-sm font-medium">{toolName}</span>
            <button
              onClick={() => removeQuota(toolName)}
              className="text-red-400 hover:text-red-300 text-sm"
            >
              Remove
            </button>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="text-xs text-[var(--muted)]">Max Calls</label>
              <input
                type="number"
                value={quota.max_calls ?? ''}
                onChange={(e) =>
                  updateQuota(toolName, 'max_calls', e.target.value ? parseInt(e.target.value) : null)
                }
                placeholder="∞"
                className="w-full mt-1 px-2 py-1 text-sm rounded bg-[var(--surface)] border border-[var(--border)] focus:border-[var(--primary)] outline-none"
              />
            </div>
            <div>
              <label className="text-xs text-[var(--muted)]">Timeout (s)</label>
              <input
                type="number"
                value={quota.timeout ?? ''}
                onChange={(e) =>
                  updateQuota(toolName, 'timeout', e.target.value ? parseInt(e.target.value) : null)
                }
                placeholder="30"
                className="w-full mt-1 px-2 py-1 text-sm rounded bg-[var(--surface)] border border-[var(--border)] focus:border-[var(--primary)] outline-none"
              />
            </div>
            <div>
              <label className="text-xs text-[var(--muted)]">Cooldown (s)</label>
              <input
                type="number"
                step="0.1"
                value={quota.cooldown_seconds ?? ''}
                onChange={(e) =>
                  updateQuota(
                    toolName,
                    'cooldown_seconds',
                    e.target.value ? parseFloat(e.target.value) : null
                  )
                }
                placeholder="none"
                className="w-full mt-1 px-2 py-1 text-sm rounded bg-[var(--surface)] border border-[var(--border)] focus:border-[var(--primary)] outline-none"
              />
            </div>
          </div>
        </div>
      ))}

      {availableTools.length > 0 && (
        <div className="flex gap-2 pt-2">
          <select
            value={selectedTool}
            onChange={(e) => setSelectedTool(e.target.value)}
            className="flex-1 px-3 py-2 text-sm rounded-lg bg-[var(--background)] border border-[var(--border)] focus:border-[var(--primary)] outline-none"
          >
            <option value="">Select tool to add quota...</option>
            {availableTools.map((tool) => (
              <option key={tool.id} value={tool.name}>
                {tool.name}
              </option>
            ))}
          </select>
          <Button variant="secondary" size="sm" onClick={addQuota} disabled={!selectedTool}>
            Add Quota
          </Button>
        </div>
      )}
    </div>
  );
}

function VersionDetails({
  version,
  tools,
  templateId,
  onPromptEdit,
}: {
  version: TemplateVersion;
  tools: Tool[];
  templateId: string;
  onPromptEdit: () => void;
}) {
  const settings = version.settings;
  const quotas = settings?.tool_policy?.quotas || {};

  return (
    <div className="space-y-6">
      {/* Base Class */}
      <div>
        <h4 className="text-sm font-semibold text-[var(--muted)] uppercase tracking-wider mb-3">
          Agent Class
        </h4>
        <div className="bg-[var(--background)] rounded-lg p-4">
          <code className="text-sm text-[var(--accent)]">
            {settings?.base_class || 'SimpleAgent (default)'}
          </code>
        </div>
      </div>

      {/* LLM Policy */}
      <div>
        <h4 className="text-sm font-semibold text-[var(--muted)] uppercase tracking-wider mb-3">
          LLM Configuration
        </h4>
        <div className="bg-[var(--background)] rounded-lg p-4 space-y-2">
          <div className="flex justify-between">
            <span className="text-[var(--muted)]">Model</span>
            <span className="font-mono text-sm">{settings?.llm_policy?.model || 'gpt-4o-mini'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-[var(--muted)]">Base URL</span>
            <span className="font-mono text-sm truncate max-w-xs">
              {settings?.llm_policy?.base_url || 'Default (OpenAI)'}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-[var(--muted)]">API Key Ref</span>
            <span className="font-mono text-sm">{settings?.llm_policy?.api_key_ref || 'OPENAI_API_KEY'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-[var(--muted)]">Temperature</span>
            <span>{settings?.llm_policy?.temperature ?? 'Default'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-[var(--muted)]">Max Tokens</span>
            <span>{settings?.llm_policy?.max_tokens ?? 'Default'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-[var(--muted)]">Streaming</span>
            <Badge variant={settings?.llm_policy?.streaming ? 'success' : 'muted'}>
              {settings?.llm_policy?.streaming ? 'Enabled' : 'Disabled'}
            </Badge>
          </div>
        </div>
      </div>

      {/* Execution Policy */}
      <div>
        <h4 className="text-sm font-semibold text-[var(--muted)] uppercase tracking-wider mb-3">
          Execution Policy
        </h4>
        <div className="bg-[var(--background)] rounded-lg p-4 grid grid-cols-2 gap-4">
          <div>
            <span className="text-[var(--muted)] text-sm">Max Iterations</span>
            <p className="font-semibold">{settings?.execution_policy?.max_iterations ?? '15'}</p>
          </div>
          <div>
            <span className="text-[var(--muted)] text-sm">Time Budget</span>
            <p className="font-semibold">
              {settings?.execution_policy?.time_budget_seconds
                ? `${settings.execution_policy.time_budget_seconds}s`
                : '∞'}
            </p>
          </div>
        </div>
      </div>

      {/* Tools */}
      <div>
        <h4 className="text-sm font-semibold text-[var(--muted)] uppercase tracking-wider mb-3">
          Assigned Tools ({version.tools?.length || 0})
        </h4>
        <div className="flex flex-wrap gap-2">
          {version.tools?.map((toolName) => {
            const quota = quotas[toolName];
            return (
              <div key={toolName} className="flex items-center gap-1">
                <Badge variant="default">{toolName}</Badge>
                {quota?.max_calls !== undefined && quota?.max_calls !== null && (
                  <span className="text-xs text-[var(--muted)]">
                    (max: {quota.max_calls})
                  </span>
                )}
              </div>
            );
          })}
          {(!version.tools || version.tools.length === 0) && (
            <span className="text-[var(--muted)] text-sm italic">No tools assigned</span>
          )}
        </div>
      </div>

      {/* Tool Quotas */}
      {Object.keys(quotas).length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-[var(--muted)] uppercase tracking-wider mb-3">
            Tool Quotas (Custom Limits)
          </h4>
          <div className="bg-[var(--background)] rounded-lg p-4 space-y-2">
            {Object.entries(quotas).map(([name, quota]) => (
              <div key={name} className="flex justify-between text-sm">
                <span className="font-mono text-[var(--accent)]">{name}</span>
                <span>
                  max: {quota.max_calls ?? '∞'}, timeout: {quota.timeout ?? 30}s
                  {quota.cooldown_seconds && `, cooldown: ${quota.cooldown_seconds}s`}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* System Prompt */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h4 className="text-sm font-semibold text-[var(--muted)] uppercase tracking-wider">
            System Prompt
          </h4>
          <Button variant="secondary" size="sm" onClick={onPromptEdit}>
            ✏️ Edit Prompt
          </Button>
        </div>
        {(settings?.prompts?.system || settings?.prompts?.system_prompt) ? (
          <div className="bg-[var(--background)] rounded-lg p-4 max-h-48 overflow-y-auto">
            <pre className="text-sm whitespace-pre-wrap font-mono text-xs">
              {settings.prompts.system || settings.prompts.system_prompt}
            </pre>
            <div className="mt-2 text-xs text-[var(--muted)]">
              {(settings.prompts.system || settings.prompts.system_prompt || '').length.toLocaleString()} characters
            </div>
          </div>
        ) : (
          <div className="bg-[var(--background)] rounded-lg p-4 text-[var(--muted)] italic">
            No custom prompt. Using default system prompt.
          </div>
        )}
      </div>

      {/* MCP Configuration */}
      <MCPSection mcp={settings?.mcp} />

      {/* Rules */}
      <RulesSection rules={settings?.rules} />
    </div>
  );
}

// MCP Section Component
function MCPSection({ mcp }: { mcp?: MCPConfig }) {
  const servers = mcp?.mcpServers || {};
  const serverEntries = Object.entries(servers);

  if (serverEntries.length === 0 && !mcp?.enabled) {
    return null;
  }

  return (
    <div>
      <h4 className="text-sm font-semibold text-[var(--muted)] uppercase tracking-wider mb-3">
        MCP Servers
        <Badge variant={mcp?.enabled !== false ? 'success' : 'muted'} className="ml-2">
          {mcp?.enabled !== false ? 'Enabled' : 'Disabled'}
        </Badge>
      </h4>
      
      {serverEntries.length === 0 ? (
        <p className="text-sm text-[var(--muted)] italic">No MCP servers configured</p>
      ) : (
        <div className="space-y-3">
          {serverEntries.map(([name, server]) => (
            <div 
              key={name} 
              className={`bg-[var(--background)] rounded-lg p-4 border-l-4 ${
                server.enabled !== false ? 'border-l-green-500' : 'border-l-gray-500'
              }`}
            >
              <div className="flex items-center justify-between mb-2">
                <span className="font-mono font-semibold text-[var(--accent)]">{name}</span>
                <Badge variant={server.enabled !== false ? 'success' : 'muted'}>
                  {server.enabled !== false ? 'Active' : 'Disabled'}
                </Badge>
              </div>
              <div className="grid grid-cols-2 gap-2 text-sm">
                {server.url && (
                  <div>
                    <span className="text-[var(--muted)]">URL: </span>
                    <span className="font-mono text-xs">{server.url}</span>
                  </div>
                )}
                {server.command && (
                  <div>
                    <span className="text-[var(--muted)]">Command: </span>
                    <span className="font-mono text-xs">{server.command}</span>
                  </div>
                )}
                {server.args && server.args.length > 0 && (
                  <div className="col-span-2">
                    <span className="text-[var(--muted)]">Args: </span>
                    <span className="font-mono text-xs">{server.args.join(' ')}</span>
                  </div>
                )}
                {server.env && Object.keys(server.env).length > 0 && (
                  <div className="col-span-2">
                    <span className="text-[var(--muted)]">Env: </span>
                    <span className="font-mono text-xs">
                      {Object.entries(server.env).map(([k, v]) => `${k}=${v}`).join(', ')}
                    </span>
                  </div>
                )}
                <div>
                  <span className="text-[var(--muted)]">Timeout: </span>
                  <span>{server.timeout || 30}s</span>
                </div>
              </div>
            </div>
          ))}
          
          {mcp?.context_limit && (
            <div className="text-sm text-[var(--muted)]">
              Context limit: {mcp.context_limit.toLocaleString()} tokens
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// Prompt Editor Modal
function PromptEditorModal({
  isOpen,
  onClose,
  templateId,
  versionId,
  currentPrompt,
  onSave,
}: {
  isOpen: boolean;
  onClose: () => void;
  templateId: string;
  versionId: string;
  currentPrompt: string;
  onSave: () => void;
}) {
  const [prompt, setPrompt] = useState(currentPrompt);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setPrompt(currentPrompt);
  }, [currentPrompt]);

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      await adminApi.updateTemplatePrompt(templateId, versionId, prompt);
      onSave();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save prompt');
    } finally {
      setSaving(false);
    }
  }

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-[var(--surface)] rounded-xl border border-[var(--border)] w-full max-w-4xl max-h-[90vh] flex flex-col">
        <div className="p-6 border-b border-[var(--border)] flex justify-between items-center">
          <h2 className="text-xl font-bold">Edit System Prompt</h2>
          <button onClick={onClose} className="text-[var(--muted)] hover:text-[var(--foreground)] text-2xl">×</button>
        </div>

        <div className="p-6 flex-1 overflow-hidden flex flex-col">
          {error && (
            <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
              {error}
            </div>
          )}
          
          <div className="text-sm text-[var(--muted)] mb-2">
            <span className="font-semibold">Placeholders:</span>{' '}
            <code className="bg-[var(--background)] px-1 rounded">{'{available_tools}'}</code>,{' '}
            <code className="bg-[var(--background)] px-1 rounded">{'{current_date}'}</code>
          </div>
          
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            className="flex-1 min-h-[400px] w-full px-4 py-3 rounded-lg bg-[var(--background)] border border-[var(--border)] focus:border-[var(--primary)] outline-none font-mono text-sm resize-none"
            placeholder="Enter system prompt..."
          />
          
          <div className="mt-2 text-xs text-[var(--muted)]">
            {prompt.length.toLocaleString()} characters
          </div>
        </div>

        <div className="p-6 border-t border-[var(--border)] flex justify-end gap-3">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? 'Saving...' : 'Save Prompt'}
          </Button>
        </div>
      </div>
    </div>
  );
}

// Rules Section Component
function RulesSection({ rules }: { rules?: Rule[] }) {
  if (!rules || rules.length === 0) {
    return null;
  }

  return (
    <div>
      <h4 className="text-sm font-semibold text-[var(--muted)] uppercase tracking-wider mb-3">
        Rules ({rules.length})
      </h4>
      <div className="space-y-3">
        {rules.map((rule, index) => (
          <div key={index} className="bg-[var(--background)] rounded-lg p-4 border border-[var(--border)]">
            <div className="flex items-center gap-2 mb-3">
              <span className="text-xs font-semibold text-[var(--muted)]">RULE #{index + 1}</span>
              <div className="flex gap-1">
                {(rule.apply_to || ['pre_retrieval', 'post_retrieval']).map((phase) => (
                  <Badge key={phase} variant="default" className="text-xs">
                    {phase}
                  </Badge>
                ))}
              </div>
            </div>

            {/* Conditions */}
            <div className="mb-3">
              <span className="text-xs font-semibold text-[var(--muted)] uppercase">When:</span>
              <div className="mt-1 flex flex-wrap gap-2">
                {rule.when?.iteration_gte != null && (
                  <code className="text-xs bg-blue-500/20 text-blue-300 px-2 py-0.5 rounded">
                    iteration ≥ {rule.when.iteration_gte}
                  </code>
                )}
                {rule.when?.searches_used_gte != null && (
                  <code className="text-xs bg-blue-500/20 text-blue-300 px-2 py-0.5 rounded">
                    searches ≥ {rule.when.searches_used_gte}
                  </code>
                )}
                {rule.when?.clarifications_used_gte != null && (
                  <code className="text-xs bg-blue-500/20 text-blue-300 px-2 py-0.5 rounded">
                    clarifications ≥ {rule.when.clarifications_used_gte}
                  </code>
                )}
                {rule.when?.state_equals && (
                  <code className="text-xs bg-purple-500/20 text-purple-300 px-2 py-0.5 rounded">
                    state = {rule.when.state_equals}
                  </code>
                )}
                {!rule.when?.iteration_gte && !rule.when?.searches_used_gte && 
                 !rule.when?.clarifications_used_gte && !rule.when?.state_equals && (
                  <span className="text-xs text-[var(--muted)] italic">Always applies</span>
                )}
              </div>
            </div>

            {/* Actions */}
            <div>
              <span className="text-xs font-semibold text-[var(--muted)] uppercase">Then:</span>
              <div className="mt-1 flex flex-wrap gap-2">
                {rule.actions?.exclude && rule.actions.exclude.length > 0 && (
                  <div className="flex items-center gap-1">
                    <span className="text-xs text-red-400">Exclude:</span>
                    {rule.actions.exclude.map((tool) => (
                      <code key={tool} className="text-xs bg-red-500/20 text-red-300 px-2 py-0.5 rounded">
                        {tool}
                      </code>
                    ))}
                  </div>
                )}
                {rule.actions?.keep_only && rule.actions.keep_only.length > 0 && (
                  <div className="flex items-center gap-1">
                    <span className="text-xs text-green-400">Keep only:</span>
                    {rule.actions.keep_only.map((tool) => (
                      <code key={tool} className="text-xs bg-green-500/20 text-green-300 px-2 py-0.5 rounded">
                        {tool}
                      </code>
                    ))}
                  </div>
                )}
                {rule.actions?.set_stage && (
                  <div className="flex items-center gap-1">
                    <span className="text-xs text-yellow-400">Set stage:</span>
                    <code className="text-xs bg-yellow-500/20 text-yellow-300 px-2 py-0.5 rounded">
                      {rule.actions.set_stage}
                    </code>
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function TemplatesPage() {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [tools, setTools] = useState<Tool[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedTemplate, setSelectedTemplate] = useState<Template | null>(null);
  const [promptEditorOpen, setPromptEditorOpen] = useState(false);

  async function loadData() {
    try {
      const [templatesData, toolsData] = await Promise.all([
        adminApi.getTemplates(),
        adminApi.getTools(true),
      ]);
      setTemplates(templatesData);
      setTools(toolsData);
      
      // Refresh selected template if it exists
      if (selectedTemplate) {
        const updated = templatesData.find(t => t.id === selectedTemplate.id);
        if (updated) setSelectedTemplate(updated);
      }
    } catch (error) {
      console.error('Failed to load data:', error);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-[var(--primary)]"></div>
      </div>
    );
  }

  const activeVersion = selectedTemplate?.versions?.find((v) => v.is_active);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Templates</h1>
          <p className="text-[var(--muted)] mt-1">Agent templates with LLM and tool configurations</p>
        </div>
        <Button onClick={() => alert('Create template coming soon!')}>+ New Template</Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Template List */}
        <div className="space-y-4">
          {templates.map((template) => {
            const version = template.versions?.find((v) => v.is_active);
            return (
              <Card
                key={template.id}
                onClick={() => setSelectedTemplate(template)}
                className={selectedTemplate?.id === template.id ? 'border-[var(--primary)]' : ''}
              >
                <div className="flex items-start justify-between mb-2">
                  <h3 className="font-semibold">{template.name}</h3>
                  <Badge variant={template.active_version_id ? 'success' : 'muted'}>
                    v{version?.version || 0}
                  </Badge>
                </div>
                <p className="text-sm text-[var(--muted)] mb-2">
                  {template.description || 'No description'}
                </p>
                {version && (
                  <div className="text-xs text-[var(--muted)]">
                    <span className="font-mono">{version.settings?.llm_policy?.model || 'gpt-4o-mini'}</span>
                    <span className="mx-2">•</span>
                    <span>{version.tools?.length || 0} tools</span>
                  </div>
                )}
              </Card>
            );
          })}

          {templates.length === 0 && (
            <Card className="text-center py-8">
              <p className="text-[var(--muted)]">No templates found</p>
            </Card>
          )}
        </div>

        {/* Template Details */}
        <div className="lg:col-span-2">
          {selectedTemplate && activeVersion ? (
            <Card>
              <div className="flex items-center justify-between mb-6">
                <div>
                  <h2 className="text-2xl font-bold">{selectedTemplate.name}</h2>
                  <p className="text-[var(--muted)]">{selectedTemplate.description}</p>
                </div>
                <Button variant="secondary" onClick={() => alert('Edit coming soon!')}>
                  Edit Version
                </Button>
              </div>

              <VersionDetails 
                version={activeVersion} 
                tools={tools} 
                templateId={selectedTemplate.id}
                onPromptEdit={() => setPromptEditorOpen(true)}
              />
            </Card>
          ) : selectedTemplate ? (
            <Card className="flex flex-col items-center justify-center h-full min-h-[400px]">
              <p className="text-[var(--muted)] mb-4">No active version for this template</p>
              <Button onClick={() => alert('Create version coming soon!')}>Create Version</Button>
            </Card>
          ) : (
            <Card className="flex items-center justify-center h-full min-h-[400px]">
              <p className="text-[var(--muted)]">Select a template to view details</p>
            </Card>
          )}
        </div>
      </div>

      {/* Prompt Editor Modal */}
      {selectedTemplate && activeVersion && (
        <PromptEditorModal
          isOpen={promptEditorOpen}
          onClose={() => setPromptEditorOpen(false)}
          templateId={selectedTemplate.id}
          versionId={activeVersion.id}
          currentPrompt={activeVersion.settings?.prompts?.system || activeVersion.settings?.prompts?.system_prompt || ''}
          onSave={loadData}
        />
      )}
    </div>
  );
}
