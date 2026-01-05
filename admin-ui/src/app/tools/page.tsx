'use client';

import { useEffect, useState } from 'react';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Button } from '@/components/Button';
import { adminApi, Tool } from '@/lib/api';

interface ToolFormData {
  name: string;
  description: string;
  python_entrypoint: string;
  config: Record<string, unknown>;
  is_active: boolean;
}

function ConfigEditor({
  config,
  onChange,
}: {
  config: Record<string, unknown>;
  onChange: (config: Record<string, unknown>) => void;
}) {
  const [entries, setEntries] = useState<Array<{ key: string; value: string }>>(
    Object.entries(config).map(([key, value]) => ({
      key,
      value: typeof value === 'string' ? value : JSON.stringify(value),
    }))
  );
  const [newKey, setNewKey] = useState('');
  const [newValue, setNewValue] = useState('');

  function updateConfig(newEntries: Array<{ key: string; value: string }>) {
    const result: Record<string, unknown> = {};
    for (const entry of newEntries) {
      if (entry.key.trim()) {
        // Try to parse as JSON, otherwise use as string
        try {
          result[entry.key] = JSON.parse(entry.value);
        } catch {
          result[entry.key] = entry.value;
        }
      }
    }
    onChange(result);
  }

  function handleEntryChange(index: number, field: 'key' | 'value', val: string) {
    const updated = [...entries];
    updated[index][field] = val;
    setEntries(updated);
    updateConfig(updated);
  }

  function handleRemove(index: number) {
    const updated = entries.filter((_, i) => i !== index);
    setEntries(updated);
    updateConfig(updated);
  }

  function handleAdd() {
    if (!newKey.trim()) return;
    const updated = [...entries, { key: newKey, value: newValue }];
    setEntries(updated);
    setNewKey('');
    setNewValue('');
    updateConfig(updated);
  }

  return (
    <div className="space-y-3">
      <label className="block text-sm text-[var(--muted)]">
        Configuration (key-value pairs)
      </label>

      {entries.map((entry, i) => (
        <div key={i} className="flex gap-2 items-center">
          <input
            type="text"
            value={entry.key}
            onChange={(e) => handleEntryChange(i, 'key', e.target.value)}
            className="flex-1 px-3 py-2 text-sm rounded-lg bg-[var(--background)] border border-[var(--border)] focus:border-[var(--primary)] outline-none font-mono"
            placeholder="key"
          />
          <span className="text-[var(--muted)]">=</span>
          <input
            type="text"
            value={entry.value}
            onChange={(e) => handleEntryChange(i, 'value', e.target.value)}
            className="flex-[2] px-3 py-2 text-sm rounded-lg bg-[var(--background)] border border-[var(--border)] focus:border-[var(--primary)] outline-none font-mono"
            placeholder="value"
          />
          <button
            onClick={() => handleRemove(i)}
            className="p-2 text-red-400 hover:text-red-300 hover:bg-red-400/10 rounded-lg transition-colors"
            title="Remove"
          >
            ×
          </button>
        </div>
      ))}

      <div className="flex gap-2 items-center pt-2 border-t border-[var(--border)]">
        <input
          type="text"
          value={newKey}
          onChange={(e) => setNewKey(e.target.value)}
          className="flex-1 px-3 py-2 text-sm rounded-lg bg-[var(--background)] border border-[var(--border)] focus:border-[var(--primary)] outline-none font-mono"
          placeholder="new_key"
          onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
        />
        <span className="text-[var(--muted)]">=</span>
        <input
          type="text"
          value={newValue}
          onChange={(e) => setNewValue(e.target.value)}
          className="flex-[2] px-3 py-2 text-sm rounded-lg bg-[var(--background)] border border-[var(--border)] focus:border-[var(--primary)] outline-none font-mono"
          placeholder="value"
          onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
        />
        <Button variant="secondary" size="sm" onClick={handleAdd} disabled={!newKey.trim()}>
          Add
        </Button>
      </div>

      <p className="text-xs text-[var(--muted)]">
        💡 Use <code className="bg-[var(--surface)] px-1 rounded">api_key_ref</code> to reference environment variables (e.g., <code className="bg-[var(--surface)] px-1 rounded">TAVILY_API_KEY</code>)
      </p>
    </div>
  );
}

function ConfigDisplay({ config }: { config: Record<string, unknown> }) {
  const entries = Object.entries(config);

  if (entries.length === 0) {
    return <span className="text-[var(--muted)] text-xs italic">No config</span>;
  }

  return (
    <div className="space-y-1">
      {entries.map(([key, value]) => (
        <div key={key} className="flex gap-2 text-xs font-mono">
          <span className="text-[var(--accent)]">{key}:</span>
          <span className="text-[var(--foreground)]">
            {typeof value === 'string' ? value : JSON.stringify(value)}
          </span>
        </div>
      ))}
    </div>
  );
}

function ToolModal({
  tool,
  onClose,
  onSave,
}: {
  tool: Tool | null;
  onClose: () => void;
  onSave: () => void;
}) {
  const isEdit = !!tool;
  const [formData, setFormData] = useState<ToolFormData>({
    name: tool?.name || '',
    description: tool?.description || '',
    python_entrypoint: tool?.python_entrypoint || '',
    config: tool?.config || {},
    is_active: tool?.is_active ?? true,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    if (!formData.name.trim()) {
      setError('Name is required');
      return;
    }

    setSaving(true);
    setError(null);

    try {
      if (isEdit && tool) {
        await adminApi.updateTool(tool.id, {
          name: formData.name,
          description: formData.description || null,
          python_entrypoint: formData.python_entrypoint || null,
          config: formData.config,
          is_active: formData.is_active,
        });
      } else {
        await adminApi.createTool({
          name: formData.name,
          description: formData.description || null,
          python_entrypoint: formData.python_entrypoint || null,
          config: formData.config,
          is_active: formData.is_active,
        });
      }
      onSave();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save tool');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-[var(--surface)] rounded-xl border border-[var(--border)] w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <div className="p-6 border-b border-[var(--border)]">
          <h2 className="text-xl font-bold">{isEdit ? 'Edit Tool' : 'Create New Tool'}</h2>
        </div>

        <div className="p-6 space-y-5">
          {error && (
            <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
              {error}
            </div>
          )}

          <div>
            <label className="block text-sm text-[var(--muted)] mb-1">Name *</label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="w-full px-4 py-2 rounded-lg bg-[var(--background)] border border-[var(--border)] focus:border-[var(--primary)] outline-none font-mono"
              placeholder="my_tool_name"
            />
          </div>

          <div>
            <label className="block text-sm text-[var(--muted)] mb-1">Description</label>
            <textarea
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              className="w-full px-4 py-2 rounded-lg bg-[var(--background)] border border-[var(--border)] focus:border-[var(--primary)] outline-none resize-none"
              rows={3}
              placeholder="What does this tool do?"
            />
          </div>

          <div>
            <label className="block text-sm text-[var(--muted)] mb-1">Python Entrypoint</label>
            <input
              type="text"
              value={formData.python_entrypoint}
              onChange={(e) => setFormData({ ...formData, python_entrypoint: e.target.value })}
              className="w-full px-4 py-2 rounded-lg bg-[var(--background)] border border-[var(--border)] focus:border-[var(--primary)] outline-none font-mono text-sm"
              placeholder="maruntime.core.tools.my_tool:MyTool"
            />
            <p className="text-xs text-[var(--muted)] mt-1">
              Format: <code className="bg-[var(--surface)] px-1 rounded">module.path:ClassName</code>
            </p>
          </div>

          <ConfigEditor
            config={formData.config}
            onChange={(config) => setFormData({ ...formData, config })}
          />

          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={formData.is_active}
                onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                className="w-4 h-4 rounded border-[var(--border)] bg-[var(--background)] text-[var(--primary)] focus:ring-[var(--primary)]"
              />
              <span className="text-sm">Active</span>
            </label>
          </div>
        </div>

        <div className="p-6 border-t border-[var(--border)] flex justify-end gap-3">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? 'Saving...' : isEdit ? 'Save Changes' : 'Create Tool'}
          </Button>
        </div>
      </div>
    </div>
  );
}

export default function ToolsPage() {
  const [tools, setTools] = useState<Tool[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalTool, setModalTool] = useState<Tool | null | 'new'>(null);
  const [expandedConfig, setExpandedConfig] = useState<string | null>(null);

  async function loadTools() {
    try {
      const data = await adminApi.getTools();
      setTools(data);
    } catch (error) {
      console.error('Failed to load tools:', error);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadTools();
  }, []);

  async function toggleActive(tool: Tool) {
    try {
      await adminApi.updateTool(tool.id, { is_active: !tool.is_active });
      loadTools();
    } catch (error) {
      console.error('Failed to update tool:', error);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-[var(--primary)]"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Tools</h1>
          <p className="text-[var(--muted)] mt-1">Manage available tools for agents</p>
        </div>
        <Button onClick={() => setModalTool('new')}>+ Add Tool</Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {tools.map((tool) => (
          <Card key={tool.id} className="flex flex-col">
            <div className="flex items-start justify-between mb-3">
              <div className="flex-1 min-w-0">
                <h3 className="font-semibold text-lg truncate">{tool.name}</h3>
                {tool.python_entrypoint && (
                  <p className="text-xs font-mono text-[var(--accent)] truncate mt-0.5">
                    {tool.python_entrypoint}
                  </p>
                )}
              </div>
              <Badge variant={tool.is_active ? 'success' : 'muted'} className="ml-2 shrink-0">
                {tool.is_active ? 'Active' : 'Inactive'}
              </Badge>
            </div>

            <p className="text-[var(--muted)] text-sm mb-4 line-clamp-2">
              {tool.description || 'No description'}
            </p>

            {/* Config Section */}
            <div className="mb-4 p-3 rounded-lg bg-[var(--background)] border border-[var(--border)]">
              <div
                className="flex items-center justify-between cursor-pointer"
                onClick={() => setExpandedConfig(expandedConfig === tool.id ? null : tool.id)}
              >
                <span className="text-xs font-medium text-[var(--muted)] uppercase tracking-wide">
                  Configuration
                </span>
                <span className="text-[var(--muted)] text-xs">
                  {Object.keys(tool.config).length} params
                  <span className="ml-1">{expandedConfig === tool.id ? '▼' : '▶'}</span>
                </span>
              </div>

              {expandedConfig === tool.id && (
                <div className="mt-3 pt-3 border-t border-[var(--border)]">
                  <ConfigDisplay config={tool.config} />
                </div>
              )}
            </div>

            <div className="flex gap-2 mt-auto">
              <Button variant="secondary" size="sm" onClick={() => setModalTool(tool)}>
                Edit
              </Button>
              <Button variant="secondary" size="sm" onClick={() => toggleActive(tool)}>
                {tool.is_active ? 'Disable' : 'Enable'}
              </Button>
            </div>
          </Card>
        ))}
      </div>

      {tools.length === 0 && (
        <Card className="text-center py-12">
          <p className="text-[var(--muted)]">No tools found. Create your first tool!</p>
        </Card>
      )}

      {/* Modal for create/edit */}
      {modalTool && (
        <ToolModal
          tool={modalTool === 'new' ? null : modalTool}
          onClose={() => setModalTool(null)}
          onSave={loadTools}
        />
      )}
    </div>
  );
}
