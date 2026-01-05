'use client';

import { useEffect, useState } from 'react';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Button } from '@/components/Button';
import { adminApi, SystemPrompt, SystemPromptDefaults } from '@/lib/api';

interface EditingPrompt {
  id: string;
  content: string;
  name: string;
  description: string;
}

export default function PromptsPage() {
  const [prompts, setPrompts] = useState<SystemPrompt[]>([]);
  const [defaults, setDefaults] = useState<SystemPromptDefaults | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<EditingPrompt | null>(null);
  const [saving, setSaving] = useState(false);
  const [showDiff, setShowDiff] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    try {
      setLoading(true);
      const [promptsData, defaultsData] = await Promise.all([
        adminApi.getPrompts(),
        adminApi.getPromptDefaults(),
      ]);
      // Ensure prompts is always an array
      setPrompts(Array.isArray(promptsData) ? promptsData : []);
      setDefaults(defaultsData);
      setError(null);
    } catch (err) {
      setError('Failed to load prompts');
      console.error(err);
      setPrompts([]); // Reset to empty array on error
    } finally {
      setLoading(false);
    }
  }

  function startEditing(prompt: SystemPrompt) {
    setEditing({
      id: prompt.id,
      content: prompt.content,
      name: prompt.name,
      description: prompt.description || '',
    });
    setShowDiff(null);
  }

  function cancelEditing() {
    setEditing(null);
  }

  async function savePrompt() {
    if (!editing) return;

    try {
      setSaving(true);
      await adminApi.updatePrompt(editing.id, {
        content: editing.content,
        name: editing.name,
        description: editing.description || null,
      });
      await loadData();
      setEditing(null);
    } catch (err) {
      setError('Failed to save prompt');
      console.error(err);
    } finally {
      setSaving(false);
    }
  }

  async function resetToDefault(promptId: string) {
    if (!confirm('Are you sure you want to reset this prompt to its default?')) {
      return;
    }

    try {
      setSaving(true);
      await adminApi.resetPrompt(promptId);
      await loadData();
      setEditing(null);
    } catch (err) {
      setError('Failed to reset prompt');
      console.error(err);
    } finally {
      setSaving(false);
    }
  }

  function getDefaultContent(promptId: string): string {
    if (!defaults) return '';
    switch (promptId) {
      case 'system':
        return defaults.system;
      case 'initial_user':
        return defaults.initial_user;
      case 'clarification':
        return defaults.clarification;
      default:
        return '';
    }
  }

  function isModified(prompt: SystemPrompt): boolean {
    const defaultContent = getDefaultContent(prompt.id);
    return prompt.content !== defaultContent;
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-slate-400">Loading prompts...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-900/20 border border-red-500 rounded-lg p-4">
        <p className="text-red-400">{error}</p>
        <Button onClick={loadData} className="mt-2">
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-white">System Prompts</h1>
          <p className="text-slate-400 mt-1">
            Configure default prompts used by all agents. Template-specific prompts override these.
          </p>
        </div>
        <Button onClick={loadData} variant="secondary">
          Refresh
        </Button>
      </div>

      {/* Info box about placeholders */}
      <Card className="bg-slate-800/50 border-slate-700">
        <div className="p-4">
          <h3 className="text-sm font-semibold text-white mb-2">Available Placeholders</h3>
          <div className="flex flex-wrap gap-2">
            <code className="text-xs bg-slate-900 text-emerald-400 px-2 py-1 rounded">
              {'{current_date}'}
            </code>
            <code className="text-xs bg-slate-900 text-emerald-400 px-2 py-1 rounded">
              {'{available_tools}'}
            </code>
            <code className="text-xs bg-slate-900 text-emerald-400 px-2 py-1 rounded">
              {'{task}'}
            </code>
            <code className="text-xs bg-slate-900 text-emerald-400 px-2 py-1 rounded">
              {'{clarifications}'}
            </code>
          </div>
        </div>
      </Card>

      {/* Prompts list */}
      <div className="space-y-4">
        {prompts.map((prompt) => (
          <Card key={prompt.id} className="overflow-hidden">
            <div className="p-4 border-b border-slate-700 bg-slate-800/50">
              <div className="flex justify-between items-start">
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-lg font-semibold text-white">{prompt.name}</h2>
                    <code className="text-xs bg-slate-900 text-slate-400 px-2 py-0.5 rounded">
                      {prompt.id}
                    </code>
                    {isModified(prompt) && (
                      <Badge variant="warning">Modified</Badge>
                    )}
                    {!prompt.is_active && (
                      <Badge variant="error">Inactive</Badge>
                    )}
                  </div>
                  {prompt.description && (
                    <p className="text-slate-400 text-sm mt-1">{prompt.description}</p>
                  )}
                </div>
                <div className="flex gap-2">
                  {isModified(prompt) && (
                    <>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => setShowDiff(showDiff === prompt.id ? null : prompt.id)}
                      >
                        {showDiff === prompt.id ? 'Hide Diff' : 'Show Diff'}
                      </Button>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => resetToDefault(prompt.id)}
                        disabled={saving}
                      >
                        Reset
                      </Button>
                    </>
                  )}
                  <Button
                    size="sm"
                    onClick={() => startEditing(prompt)}
                  >
                    Edit
                  </Button>
                </div>
              </div>
              {prompt.placeholders.length > 0 && (
                <div className="mt-2 flex gap-1">
                  <span className="text-xs text-slate-500">Placeholders:</span>
                  {prompt.placeholders.map((ph) => (
                    <code
                      key={ph}
                      className="text-xs bg-slate-900 text-emerald-400 px-1.5 py-0.5 rounded"
                    >
                      {`{${ph}}`}
                    </code>
                  ))}
                </div>
              )}
            </div>

            {/* Show diff if requested */}
            {showDiff === prompt.id && (
              <div className="p-4 bg-slate-900/50 border-b border-slate-700">
                <h3 className="text-sm font-semibold text-white mb-2">Default Content</h3>
                <pre className="text-xs text-slate-400 whitespace-pre-wrap overflow-auto max-h-64 bg-slate-950 p-3 rounded">
                  {getDefaultContent(prompt.id)}
                </pre>
              </div>
            )}

            {/* Content preview */}
            <div className="p-4">
              <pre className="text-sm text-slate-300 whitespace-pre-wrap overflow-auto max-h-48 bg-slate-900/50 p-3 rounded font-mono">
                {prompt.content}
              </pre>
              <div className="mt-2 text-xs text-slate-500">
                Last updated: {new Date(prompt.updated_at).toLocaleString()}
              </div>
            </div>
          </Card>
        ))}
      </div>

      {/* Edit Modal */}
      {editing && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <div className="bg-slate-800 rounded-lg w-full max-w-4xl max-h-[90vh] overflow-hidden flex flex-col">
            <div className="p-4 border-b border-slate-700 flex justify-between items-center">
              <h2 className="text-lg font-semibold text-white">
                Edit: {editing.name}
              </h2>
              <button
                onClick={cancelEditing}
                className="text-slate-400 hover:text-white text-2xl"
              >
                ×
              </button>
            </div>
            <div className="p-4 overflow-auto flex-1 space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">
                  Name
                </label>
                <input
                  type="text"
                  value={editing.name}
                  onChange={(e) =>
                    setEditing({ ...editing, name: e.target.value })
                  }
                  className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-2 text-white"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">
                  Description
                </label>
                <input
                  type="text"
                  value={editing.description}
                  onChange={(e) =>
                    setEditing({ ...editing, description: e.target.value })
                  }
                  className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-2 text-white"
                  placeholder="Optional description"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">
                  Content
                </label>
                <textarea
                  value={editing.content}
                  onChange={(e) =>
                    setEditing({ ...editing, content: e.target.value })
                  }
                  className="w-full h-96 bg-slate-900 border border-slate-700 rounded px-3 py-2 text-white font-mono text-sm resize-none"
                  spellCheck={false}
                />
              </div>
            </div>
            <div className="p-4 border-t border-slate-700 flex justify-between">
              <Button
                variant="secondary"
                onClick={() => {
                  const defaultContent = getDefaultContent(editing.id);
                  if (defaultContent) {
                    setEditing({ ...editing, content: defaultContent });
                  }
                }}
              >
                Load Default
              </Button>
              <div className="flex gap-2">
                <Button variant="secondary" onClick={cancelEditing}>
                  Cancel
                </Button>
                <Button onClick={savePrompt} disabled={saving}>
                  {saving ? 'Saving...' : 'Save'}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

