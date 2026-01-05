'use client';

import { useEffect, useState } from 'react';
import { Card, StatCard } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { adminApi, gatewayApi, Tool, Template, Session } from '@/lib/api';

export default function Dashboard() {
  const [tools, setTools] = useState<Tool[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [adminHealth, setAdminHealth] = useState<boolean>(false);
  const [gatewayHealth, setGatewayHealth] = useState<boolean>(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadData() {
      try {
        const [toolsData, templatesData, sessionsData] = await Promise.all([
          adminApi.getTools(),
          adminApi.getTemplates(),
          adminApi.getSessions(),
        ]);
        setTools(toolsData);
        setTemplates(templatesData);
        setSessions(sessionsData);

        const adminHealthRes = await adminApi.health();
        setAdminHealth(adminHealthRes.status === 'ok');

        const gatewayHealthRes = await gatewayApi.health();
        setGatewayHealth(gatewayHealthRes.status === 'ok');
      } catch (error) {
        console.error('Failed to load data:', error);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-[var(--primary)]"></div>
      </div>
    );
  }

  const activeTools = tools.filter((t) => t.is_active).length;
  const completedSessions = sessions.filter((s) => s.state === 'COMPLETED').length;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold">Dashboard</h1>
        <p className="text-[var(--muted)] mt-1">Overview of your agent runtime</p>
      </div>

      {/* Health Status */}
      <div className="flex gap-4">
        <div className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--card)] border border-[var(--border)]">
          <span className={`w-2.5 h-2.5 rounded-full ${adminHealth ? 'bg-[var(--success)]' : 'bg-[var(--danger)]'}`}></span>
          <span className="text-sm">Admin API</span>
        </div>
        <div className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--card)] border border-[var(--border)]">
          <span className={`w-2.5 h-2.5 rounded-full ${gatewayHealth ? 'bg-[var(--success)]' : 'bg-[var(--danger)]'}`}></span>
          <span className="text-sm">Gateway API</span>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard title="Total Tools" value={tools.length} icon="🔧" />
        <StatCard title="Active Tools" value={activeTools} icon="✅" />
        <StatCard title="Templates" value={templates.length} icon="📋" />
        <StatCard title="Sessions" value={sessions.length} icon="💬" />
      </div>

      {/* Recent Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <h3 className="text-lg font-semibold mb-4">Active Templates</h3>
          <div className="space-y-3">
            {templates.length === 0 ? (
              <p className="text-[var(--muted)] text-sm">No templates found</p>
            ) : (
              templates.map((template) => (
                <div
                  key={template.id}
                  className="flex items-center justify-between p-3 rounded-lg bg-[var(--background)]"
                >
                  <div>
                    <p className="font-medium">{template.name}</p>
                    <p className="text-xs text-[var(--muted)]">{template.description}</p>
                  </div>
                  <Badge variant={template.active_version_id ? 'success' : 'muted'}>
                    {template.active_version_id ? 'Active' : 'No version'}
                  </Badge>
                </div>
              ))
            )}
          </div>
        </Card>

        <Card>
          <h3 className="text-lg font-semibold mb-4">Recent Sessions</h3>
          <div className="space-y-3">
            {sessions.length === 0 ? (
              <p className="text-[var(--muted)] text-sm">No sessions found</p>
            ) : (
              sessions.slice(0, 5).map((session) => (
                <div
                  key={session.id}
                  className="flex items-center justify-between p-3 rounded-lg bg-[var(--background)]"
                >
                  <div>
                    <p className="font-mono text-sm">{session.id.slice(0, 8)}...</p>
                    <p className="text-xs text-[var(--muted)]">
                      {new Date(session.created_at).toLocaleString()}
                    </p>
                  </div>
                  <Badge
                    variant={
                      session.state === 'COMPLETED'
                        ? 'success'
                        : session.state === 'ACTIVE'
                        ? 'default'
                        : session.state === 'FAILED'
                        ? 'danger'
                        : 'warning'
                    }
                  >
                    {session.state}
                  </Badge>
                </div>
              ))
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
