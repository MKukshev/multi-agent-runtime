'use client';

import { useEffect, useState } from 'react';
import { adminApi, AgentInstance, AgentInstanceCreate, Template } from '@/lib/api';
import Card from '@/components/Card';
import Badge from '@/components/Badge';
import Button from '@/components/Button';

type InstanceStatus = AgentInstance['status'];

const STATUS_COLORS: Record<InstanceStatus, 'green' | 'yellow' | 'red' | 'blue' | 'gray'> = {
  OFFLINE: 'gray',
  STARTING: 'blue',
  IDLE: 'green',
  BUSY: 'yellow',
  ERROR: 'red',
  STOPPING: 'blue',
};

const STATUS_LABELS: Record<InstanceStatus, string> = {
  OFFLINE: 'Offline',
  STARTING: 'Starting...',
  IDLE: 'Idle (Ready)',
  BUSY: 'Busy',
  ERROR: 'Error',
  STOPPING: 'Stopping...',
};

export default function InstancesPage() {
  const [instances, setInstances] = useState<AgentInstance[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [selectedInstance, setSelectedInstance] = useState<AgentInstance | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [instancesData, templatesData] = await Promise.all([
        adminApi.getInstances(),
        adminApi.getTemplates(),
      ]);
      setInstances(instancesData);
      setTemplates(templatesData);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    // Poll for updates every 5 seconds
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleStart = async (id: string) => {
    setActionLoading(id);
    try {
      await adminApi.startInstance(id);
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start instance');
    } finally {
      setActionLoading(null);
    }
  };

  const handleStop = async (id: string) => {
    setActionLoading(id);
    try {
      await adminApi.stopInstance(id);
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to stop instance');
    } finally {
      setActionLoading(null);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Are you sure you want to delete this instance?')) return;
    setActionLoading(id);
    try {
      await adminApi.deleteInstance(id);
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete instance');
    } finally {
      setActionLoading(null);
    }
  };

  const handleToggleEnabled = async (instance: AgentInstance) => {
    setActionLoading(instance.id);
    try {
      await adminApi.updateInstance(instance.id, { is_enabled: !instance.is_enabled });
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update instance');
    } finally {
      setActionLoading(null);
    }
  };

  const getTemplateName = (templateId: string) => {
    const template = templates.find((t) => t.id === templateId);
    return template?.name || templateId.slice(0, 8) + '...';
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleString();
  };

  if (loading && instances.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-cyan-400"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-white tracking-tight">Agent Instances</h1>
          <p className="text-slate-400 mt-1">
            Named worker slots that process sessions sequentially
          </p>
        </div>
        <Button onClick={() => setShowCreateModal(true)}>
          <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          Create Instance
        </Button>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 text-red-400">
          {error}
          <button onClick={() => setError(null)} className="ml-4 text-red-300 hover:text-red-100">
            ✕
          </button>
        </div>
      )}

      {/* Stats Summary */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="p-4 text-center">
          <div className="text-3xl font-bold text-white">{instances.length}</div>
          <div className="text-slate-400 text-sm">Total Instances</div>
        </Card>
        <Card className="p-4 text-center">
          <div className="text-3xl font-bold text-green-400">
            {instances.filter((i) => i.status === 'IDLE').length}
          </div>
          <div className="text-slate-400 text-sm">Idle (Ready)</div>
        </Card>
        <Card className="p-4 text-center">
          <div className="text-3xl font-bold text-yellow-400">
            {instances.filter((i) => i.status === 'BUSY').length}
          </div>
          <div className="text-slate-400 text-sm">Busy</div>
        </Card>
        <Card className="p-4 text-center">
          <div className="text-3xl font-bold text-red-400">
            {instances.filter((i) => i.status === 'ERROR').length}
          </div>
          <div className="text-slate-400 text-sm">Errors</div>
        </Card>
      </div>

      {/* Instances Grid */}
      {instances.length === 0 ? (
        <Card className="p-12 text-center">
          <div className="text-slate-400 mb-4">
            <svg className="w-16 h-16 mx-auto mb-4 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M5 12h14M12 5v14" />
            </svg>
            No agent instances yet
          </div>
          <p className="text-slate-500 mb-4">
            Create your first instance to start processing sessions
          </p>
          <Button onClick={() => setShowCreateModal(true)}>Create Instance</Button>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {instances.map((instance) => (
            <Card key={instance.id} className="overflow-hidden">
              {/* Header */}
              <div className="p-4 border-b border-slate-700 bg-slate-800/50">
                <div className="flex justify-between items-start">
                  <div className="flex-1 min-w-0">
                    <h3 className="text-lg font-semibold text-white truncate">
                      {instance.display_name || instance.name}
                    </h3>
                    <p className="text-sm text-slate-400 truncate font-mono">
                      {instance.name}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 ml-2">
                    <Badge color={STATUS_COLORS[instance.status]}>
                      {STATUS_LABELS[instance.status]}
                    </Badge>
                  </div>
                </div>
              </div>

              {/* Body */}
              <div className="p-4 space-y-3">
                {instance.description && (
                  <p className="text-sm text-slate-400">{instance.description}</p>
                )}

                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div>
                    <span className="text-slate-500">Template:</span>
                    <span className="text-slate-300 ml-2">{getTemplateName(instance.template_id)}</span>
                  </div>
                  <div>
                    <span className="text-slate-500">Priority:</span>
                    <span className="text-slate-300 ml-2">{instance.priority}</span>
                  </div>
                </div>

                {/* Stats */}
                <div className="grid grid-cols-3 gap-2 text-center text-xs">
                  <div className="bg-slate-800 rounded p-2">
                    <div className="text-white font-semibold">{instance.total_sessions}</div>
                    <div className="text-slate-500">Sessions</div>
                  </div>
                  <div className="bg-slate-800 rounded p-2">
                    <div className="text-white font-semibold">{instance.total_messages}</div>
                    <div className="text-slate-500">Messages</div>
                  </div>
                  <div className="bg-slate-800 rounded p-2">
                    <div className="text-white font-semibold">{instance.total_tool_calls}</div>
                    <div className="text-slate-500">Tool Calls</div>
                  </div>
                </div>

                {/* Error info */}
                {instance.last_error && (
                  <div className="bg-red-500/10 border border-red-500/30 rounded p-2 text-xs">
                    <div className="text-red-400 font-medium">
                      {instance.error_count} error{instance.error_count !== 1 ? 's' : ''}
                    </div>
                    <div className="text-red-300 truncate">{instance.last_error}</div>
                    {instance.last_error_at && (
                      <div className="text-red-400/60 mt-1">
                        Last: {formatDate(instance.last_error_at)}
                      </div>
                    )}
                  </div>
                )}

                {/* Flags */}
                <div className="flex gap-2 text-xs">
                  <button
                    onClick={() => handleToggleEnabled(instance)}
                    disabled={actionLoading === instance.id}
                    className={`px-2 py-1 rounded transition ${
                      instance.is_enabled
                        ? 'bg-green-500/20 text-green-400 hover:bg-green-500/30'
                        : 'bg-slate-700 text-slate-400 hover:bg-slate-600'
                    }`}
                  >
                    {instance.is_enabled ? '✓ Enabled' : '○ Disabled'}
                  </button>
                  {instance.auto_start && (
                    <span className="px-2 py-1 rounded bg-blue-500/20 text-blue-400">
                      Auto-start
                    </span>
                  )}
                </div>

                {/* Timestamps */}
                <div className="text-xs text-slate-500 space-y-1">
                  {instance.started_at && (
                    <div>Started: {formatDate(instance.started_at)}</div>
                  )}
                  {instance.last_heartbeat && (
                    <div>Last heartbeat: {formatDate(instance.last_heartbeat)}</div>
                  )}
                </div>
              </div>

              {/* Actions */}
              <div className="p-4 border-t border-slate-700 bg-slate-800/30 flex gap-2 flex-wrap">
                {(instance.status === 'OFFLINE' || instance.status === 'ERROR') && (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => handleStart(instance.id)}
                    disabled={actionLoading === instance.id}
                  >
                    {actionLoading === instance.id ? 'Starting...' : '▶ Start'}
                  </Button>
                )}
                {(instance.status === 'IDLE' || instance.status === 'BUSY') && (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => handleStop(instance.id)}
                    disabled={actionLoading === instance.id}
                  >
                    {actionLoading === instance.id ? 'Stopping...' : '⏹ Stop'}
                  </Button>
                )}
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setSelectedInstance(instance)}
                >
                  Edit
                </Button>
                <Button
                  variant="danger"
                  size="sm"
                  onClick={() => handleDelete(instance.id)}
                  disabled={actionLoading === instance.id || instance.status === 'BUSY'}
                >
                  Delete
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Create Modal */}
      {showCreateModal && (
        <CreateInstanceModal
          templates={templates}
          onClose={() => setShowCreateModal(false)}
          onCreated={() => {
            setShowCreateModal(false);
            fetchData();
          }}
        />
      )}

      {/* Edit Modal */}
      {selectedInstance && (
        <EditInstanceModal
          instance={selectedInstance}
          templates={templates}
          onClose={() => setSelectedInstance(null)}
          onUpdated={() => {
            setSelectedInstance(null);
            fetchData();
          }}
        />
      )}
    </div>
  );
}

// Create Modal Component
function CreateInstanceModal({
  templates,
  onClose,
  onCreated,
}: {
  templates: Template[];
  onClose: () => void;
  onCreated: () => void;
}) {
  const [formData, setFormData] = useState<AgentInstanceCreate>({
    name: '',
    display_name: '',
    description: '',
    template_version_id: '',
    is_enabled: true,
    auto_start: false,
    priority: 0,
  });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name || !formData.template_version_id) {
      setError('Name and template version are required');
      return;
    }

    setLoading(true);
    try {
      await adminApi.createInstance(formData);
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create instance');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <Card className="w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="p-4 border-b border-slate-700">
          <h2 className="text-xl font-semibold text-white">Create Agent Instance</h2>
        </div>
        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          {error && (
            <div className="bg-red-500/10 border border-red-500/30 rounded p-3 text-red-400 text-sm">
              {error}
            </div>
          )}

          <div>
            <label className="block text-sm text-slate-400 mb-1">Name (unique identifier) *</label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 text-white focus:border-cyan-500 focus:outline-none"
              placeholder="research-agent-1"
              required
            />
          </div>

          <div>
            <label className="block text-sm text-slate-400 mb-1">Display Name</label>
            <input
              type="text"
              value={formData.display_name || ''}
              onChange={(e) => setFormData({ ...formData, display_name: e.target.value })}
              className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 text-white focus:border-cyan-500 focus:outline-none"
              placeholder="Research Agent #1"
            />
          </div>

          <div>
            <label className="block text-sm text-slate-400 mb-1">Description</label>
            <textarea
              value={formData.description || ''}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 text-white focus:border-cyan-500 focus:outline-none"
              rows={2}
              placeholder="Primary research agent for user queries"
            />
          </div>

          <div>
            <label className="block text-sm text-slate-400 mb-1">Template Version *</label>
            <select
              value={formData.template_version_id}
              onChange={(e) => setFormData({ ...formData, template_version_id: e.target.value })}
              className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 text-white focus:border-cyan-500 focus:outline-none"
              required
            >
              <option value="">Select a template version...</option>
              {templates.map((template) =>
                template.versions.map((version) => (
                  <option key={version.id} value={version.id}>
                    {template.name} v{version.version}
                    {version.is_active ? ' (active)' : ''}
                  </option>
                ))
              )}
            </select>
          </div>

          <div>
            <label className="block text-sm text-slate-400 mb-1">Priority</label>
            <input
              type="number"
              value={formData.priority}
              onChange={(e) => setFormData({ ...formData, priority: parseInt(e.target.value) || 0 })}
              className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 text-white focus:border-cyan-500 focus:outline-none"
            />
            <p className="text-xs text-slate-500 mt-1">Higher priority instances are selected first</p>
          </div>

          <div className="flex gap-4">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={formData.is_enabled}
                onChange={(e) => setFormData({ ...formData, is_enabled: e.target.checked })}
                className="rounded bg-slate-800 border-slate-700 text-cyan-500 focus:ring-cyan-500"
              />
              <span className="text-slate-300">Enabled</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={formData.auto_start}
                onChange={(e) => setFormData({ ...formData, auto_start: e.target.checked })}
                className="rounded bg-slate-800 border-slate-700 text-cyan-500 focus:ring-cyan-500"
              />
              <span className="text-slate-300">Auto-start</span>
            </label>
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t border-slate-700">
            <Button type="button" variant="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={loading}>
              {loading ? 'Creating...' : 'Create Instance'}
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}

// Edit Modal Component
function EditInstanceModal({
  instance,
  templates,
  onClose,
  onUpdated,
}: {
  instance: AgentInstance;
  templates: Template[];
  onClose: () => void;
  onUpdated: () => void;
}) {
  const [formData, setFormData] = useState({
    name: instance.name,
    display_name: instance.display_name || '',
    description: instance.description || '',
    template_version_id: instance.template_version_id,
    is_enabled: instance.is_enabled,
    auto_start: instance.auto_start,
    priority: instance.priority,
  });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await adminApi.updateInstance(instance.id, formData);
      onUpdated();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update instance');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <Card className="w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="p-4 border-b border-slate-700">
          <h2 className="text-xl font-semibold text-white">Edit Instance: {instance.name}</h2>
        </div>
        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          {error && (
            <div className="bg-red-500/10 border border-red-500/30 rounded p-3 text-red-400 text-sm">
              {error}
            </div>
          )}

          <div>
            <label className="block text-sm text-slate-400 mb-1">Name (unique identifier)</label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 text-white focus:border-cyan-500 focus:outline-none"
              required
            />
          </div>

          <div>
            <label className="block text-sm text-slate-400 mb-1">Display Name</label>
            <input
              type="text"
              value={formData.display_name}
              onChange={(e) => setFormData({ ...formData, display_name: e.target.value })}
              className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 text-white focus:border-cyan-500 focus:outline-none"
            />
          </div>

          <div>
            <label className="block text-sm text-slate-400 mb-1">Description</label>
            <textarea
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 text-white focus:border-cyan-500 focus:outline-none"
              rows={2}
            />
          </div>

          <div>
            <label className="block text-sm text-slate-400 mb-1">Template Version</label>
            <select
              value={formData.template_version_id}
              onChange={(e) => setFormData({ ...formData, template_version_id: e.target.value })}
              className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 text-white focus:border-cyan-500 focus:outline-none"
            >
              {templates.map((template) =>
                template.versions.map((version) => (
                  <option key={version.id} value={version.id}>
                    {template.name} v{version.version}
                    {version.is_active ? ' (active)' : ''}
                  </option>
                ))
              )}
            </select>
          </div>

          <div>
            <label className="block text-sm text-slate-400 mb-1">Priority</label>
            <input
              type="number"
              value={formData.priority}
              onChange={(e) => setFormData({ ...formData, priority: parseInt(e.target.value) || 0 })}
              className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 text-white focus:border-cyan-500 focus:outline-none"
            />
          </div>

          <div className="flex gap-4">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={formData.is_enabled}
                onChange={(e) => setFormData({ ...formData, is_enabled: e.target.checked })}
                className="rounded bg-slate-800 border-slate-700 text-cyan-500 focus:ring-cyan-500"
              />
              <span className="text-slate-300">Enabled</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={formData.auto_start}
                onChange={(e) => setFormData({ ...formData, auto_start: e.target.checked })}
                className="rounded bg-slate-800 border-slate-700 text-cyan-500 focus:ring-cyan-500"
              />
              <span className="text-slate-300">Auto-start</span>
            </label>
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t border-slate-700">
            <Button type="button" variant="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={loading}>
              {loading ? 'Saving...' : 'Save Changes'}
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}

