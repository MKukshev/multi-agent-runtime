'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Button } from '@/components/Button';
import { adminApi, Session, AgentInstance } from '@/lib/api';

export default function SessionsPage() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [instances, setInstances] = useState<AgentInstance[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedSession, setSelectedSession] = useState<Session | null>(null);

  // Filters
  const [filterInstance, setFilterInstance] = useState<string>('');
  const [filterState, setFilterState] = useState<string>('');

  const loadData = async () => {
    try {
      setLoading(true);
      const [sessionsData, instancesData] = await Promise.all([
        adminApi.getSessions({
          instance_id: filterInstance || undefined,
          state: filterState || undefined,
        }),
        adminApi.getInstances(),
      ]);
      setSessions(sessionsData);
      setInstances(instancesData);
    } catch (error) {
      console.error('Failed to load data:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [filterInstance, filterState]);

  function getStateVariant(state: string): 'success' | 'default' | 'danger' | 'warning' | 'muted' {
    switch (state) {
      case 'COMPLETED':
        return 'success';
      case 'ACTIVE':
        return 'default';
      case 'FAILED':
        return 'danger';
      case 'WAITING':
        return 'warning';
      default:
        return 'muted';
    }
  }

  const getInstanceName = (instanceId: string | null) => {
    if (!instanceId) return null;
    const instance = instances.find((i) => i.id === instanceId);
    return instance?.name || instanceId.slice(0, 8) + '...';
  };

  if (loading && sessions.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-[var(--primary)]"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-3xl font-bold">Sessions</h1>
          <p className="text-[var(--muted)] mt-1">View agent execution sessions</p>
        </div>
        <Button variant="secondary" onClick={loadData}>
          ↻ Refresh
        </Button>
      </div>

      {/* Filters */}
      <Card className="p-4">
        <div className="flex flex-wrap gap-4 items-end">
          <div>
            <label className="block text-sm text-slate-400 mb-1">Filter by Instance</label>
            <select
              value={filterInstance}
              onChange={(e) => setFilterInstance(e.target.value)}
              className="bg-slate-800 border border-slate-700 rounded px-3 py-2 text-white focus:border-cyan-500 focus:outline-none min-w-[200px]"
            >
              <option value="">All Instances</option>
              {instances.map((instance) => (
                <option key={instance.id} value={instance.id}>
                  {instance.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm text-slate-400 mb-1">Filter by State</label>
            <select
              value={filterState}
              onChange={(e) => setFilterState(e.target.value)}
              className="bg-slate-800 border border-slate-700 rounded px-3 py-2 text-white focus:border-cyan-500 focus:outline-none min-w-[150px]"
            >
              <option value="">All States</option>
              <option value="ACTIVE">Active</option>
              <option value="WAITING">Waiting</option>
              <option value="COMPLETED">Completed</option>
              <option value="FAILED">Failed</option>
            </select>
          </div>
          {(filterInstance || filterState) && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setFilterInstance('');
                setFilterState('');
              }}
            >
              Clear Filters
            </Button>
          )}
        </div>
      </Card>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="p-4 text-center">
          <div className="text-3xl font-bold text-white">{sessions.length}</div>
          <div className="text-slate-400 text-sm">Total Sessions</div>
        </Card>
        <Card className="p-4 text-center">
          <div className="text-3xl font-bold text-blue-400">
            {sessions.filter((s) => s.state === 'ACTIVE').length}
          </div>
          <div className="text-slate-400 text-sm">Active</div>
        </Card>
        <Card className="p-4 text-center">
          <div className="text-3xl font-bold text-yellow-400">
            {sessions.filter((s) => s.state === 'WAITING').length}
          </div>
          <div className="text-slate-400 text-sm">Waiting</div>
        </Card>
        <Card className="p-4 text-center">
          <div className="text-3xl font-bold text-green-400">
            {sessions.filter((s) => s.state === 'COMPLETED').length}
          </div>
          <div className="text-slate-400 text-sm">Completed</div>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Session List */}
        <div className="space-y-4">
          {sessions.length === 0 ? (
            <Card className="text-center py-12">
              <p className="text-[var(--muted)]">No sessions found</p>
              {(filterInstance || filterState) && (
                <p className="text-sm text-slate-500 mt-2">Try adjusting your filters</p>
              )}
            </Card>
          ) : (
            sessions.map((session) => (
              <Card
                key={session.id}
                onClick={() => setSelectedSession(session)}
                className={selectedSession?.id === session.id ? 'border-[var(--primary)]' : ''}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="font-mono text-sm">{session.id.slice(0, 12)}...</span>
                  <Badge variant={getStateVariant(session.state)}>{session.state}</Badge>
                </div>

                {/* Instance info */}
                {session.instance_id && (
                  <div className="mb-2 flex items-center gap-2">
                    <span className="text-xs text-slate-500">Instance:</span>
                    <Link
                      href="/instances"
                      className="text-sm text-cyan-400 hover:text-cyan-300 font-mono"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {session.instance_name || getInstanceName(session.instance_id)}
                    </Link>
                  </div>
                )}

                <div className="text-sm text-[var(--muted)]">
                  <p>Created: {new Date(session.created_at).toLocaleString()}</p>
                  <p>Updated: {new Date(session.updated_at).toLocaleString()}</p>
                </div>
              </Card>
            ))
          )}
        </div>

        {/* Session Details */}
        <div>
          {selectedSession ? (
            <Card>
              <h2 className="text-xl font-bold mb-4">Session Details</h2>

              <div className="space-y-4">
                <div>
                  <label className="text-sm text-[var(--muted)]">Session ID</label>
                  <p className="font-mono text-sm break-all">{selectedSession.id}</p>
                </div>

                <div>
                  <label className="text-sm text-[var(--muted)]">State</label>
                  <div className="mt-1">
                    <Badge variant={getStateVariant(selectedSession.state)}>
                      {selectedSession.state}
                    </Badge>
                  </div>
                </div>

                {/* Instance info in details */}
                <div>
                  <label className="text-sm text-[var(--muted)]">Instance</label>
                  {selectedSession.instance_id ? (
                    <div className="mt-1">
                      <Link
                        href="/instances"
                        className="text-cyan-400 hover:text-cyan-300 font-mono text-sm"
                      >
                        {selectedSession.instance_name || getInstanceName(selectedSession.instance_id)}
                      </Link>
                      <p className="font-mono text-xs text-slate-500 mt-1">
                        {selectedSession.instance_id}
                      </p>
                    </div>
                  ) : (
                    <p className="text-slate-500 text-sm">Not assigned to an instance</p>
                  )}
                </div>

                <div>
                  <label className="text-sm text-[var(--muted)]">Template Version ID</label>
                  <p className="font-mono text-sm break-all">{selectedSession.template_version_id}</p>
                </div>

                <div>
                  <label className="text-sm text-[var(--muted)]">Created</label>
                  <p>{new Date(selectedSession.created_at).toLocaleString()}</p>
                </div>

                <div>
                  <label className="text-sm text-[var(--muted)]">Last Updated</label>
                  <p>{new Date(selectedSession.updated_at).toLocaleString()}</p>
                </div>

                <div>
                  <label className="text-sm text-[var(--muted)]">Context</label>
                  <pre className="mt-2 p-4 bg-[var(--background)] rounded-lg text-sm overflow-auto max-h-64">
                    {JSON.stringify(selectedSession.context, null, 2)}
                  </pre>
                </div>
              </div>
            </Card>
          ) : (
            <Card className="flex items-center justify-center h-full min-h-[400px]">
              <p className="text-[var(--muted)]">Select a session to view details</p>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
