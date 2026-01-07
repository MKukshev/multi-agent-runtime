const ADMIN_API_URL = process.env.NEXT_PUBLIC_ADMIN_API_URL || 'http://localhost:8001';
const GATEWAY_API_URL = process.env.NEXT_PUBLIC_GATEWAY_API_URL || 'http://localhost:8000';

// Types
export interface ToolExecutionConfig {
  max_calls: number | null;
  timeout: number;
  cooldown_seconds: number | null;
  rate_limit_per_minute: number | null;
}

export interface Tool {
  id: string;
  name: string;
  description: string | null;
  python_entrypoint: string | null;
  config: {
    api_key_ref?: string;
    api_base_url?: string;
    execution?: ToolExecutionConfig;
    [key: string]: unknown;
  };
  category: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export const TOOL_CATEGORIES = [
  { value: 'research', label: 'Research', icon: '🔍', color: 'blue' },
  { value: 'memory', label: 'Memory', icon: '💾', color: 'purple' },
  { value: 'utility', label: 'Utility', icon: '🔧', color: 'slate' },
] as const;

export interface ToolQuota {
  max_calls: number | null;
  timeout: number | null;
  cooldown_seconds: number | null;
}

// MCP Configuration
export interface MCPServerConfig {
  url: string | null;
  command: string | null;
  args: string[];
  env: Record<string, string>;
  timeout: number;
  enabled: boolean;
}

export interface MCPConfig {
  mcpServers: Record<string, MCPServerConfig>;
  context_limit: number;
  enabled: boolean;
}

// Rules Engine
export interface RuleCondition {
  iteration_gte: number | string | null;
  searches_used_gte: number | string | null;
  clarifications_used_gte: number | string | null;
  state_equals: string | null;
}

export interface RuleAction {
  exclude: string[];
  keep_only: string[] | null;
  set_stage: string | null;
}

export interface Rule {
  apply_to: string[];
  when: RuleCondition;
  actions: RuleAction;
}

export interface TemplateVersion {
  id: string;
  template_id: string;
  version: number;
  settings: {
    base_class: string;
    llm_policy: {
      base_url: string | null;
      api_key_ref: string | null;
      model: string;
      temperature: number | null;
      max_tokens: number | null;
      streaming: boolean;
    };
    prompts: {
      system: string | null;
      initial_user: string | null;
      clarification: string | null;
    };
    execution_policy: {
      max_iterations: number | null;
      time_budget_seconds: number | null;
    };
    tool_policy: {
      required_tools: string[];
      allowlist: string[];
      denylist: string[];
      max_tools_in_prompt: number | null;
      selection_strategy: string | null;
      quotas: Record<string, ToolQuota>;
    };
    mcp: MCPConfig;
    rules: Rule[];
  };
  prompt: string | null;
  tools: string[];
  is_active: boolean;
  created_at: string;
}

export interface Template {
  id: string;
  name: string;
  description: string | null;
  active_version_id: string | null;
  versions: TemplateVersion[];
  created_at: string;
  updated_at: string;
}

export interface Session {
  id: string;
  template_version_id: string;
  instance_id: string | null;
  instance_name: string | null;
  state: string;
  context: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface AgentInstance {
  id: string;
  name: string;
  display_name: string | null;
  description: string | null;
  template_id: string;
  template_version_id: string;
  current_session_id: string | null;
  status: 'OFFLINE' | 'STARTING' | 'IDLE' | 'BUSY' | 'ERROR' | 'STOPPING';
  is_enabled: boolean;
  auto_start: boolean;
  priority: number;
  config_overrides: Record<string, unknown>;
  total_sessions: number;
  total_messages: number;
  total_tool_calls: number;
  error_count: number;
  last_error: string | null;
  last_error_at: string | null;
  last_heartbeat: string | null;
  started_at: string | null;
  stopped_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AgentInstanceCreate {
  name: string;
  display_name?: string;
  description?: string;
  template_version_id: string;
  is_enabled?: boolean;
  auto_start?: boolean;
  priority?: number;
  config_overrides?: Record<string, unknown>;
}

export interface AgentInstanceUpdate {
  name?: string;
  display_name?: string;
  description?: string;
  template_version_id?: string;
  is_enabled?: boolean;
  auto_start?: boolean;
  priority?: number;
  config_overrides?: Record<string, unknown>;
}

export interface SystemPrompt {
  id: string;
  name: string;
  description: string | null;
  content: string;
  placeholders: string[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface SystemPromptDefaults {
  system: string;
  initial_user: string;
  clarification: string;
}

export interface Model {
  id: string;
  object: string;
  created: number | null;
  owned_by: string;
  version_id: string | null;
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

export interface ChatCompletionResponse {
  id: string;
  object: string;
  model: string;
  choices: Array<{
    index: number;
    message: {
      role: string;
      content: string | Array<{ type: string; text: string }>;
    };
    finish_reason: string;
  }>;
}

// Admin API
export const adminApi = {
  // Health
  async health(): Promise<{ status: string }> {
    const res = await fetch(`${ADMIN_API_URL}/health`);
    return res.json();
  },

  // Tools
  async getTools(activeOnly?: boolean): Promise<Tool[]> {
    const params = activeOnly !== undefined ? `?active_only=${activeOnly}` : '';
    const res = await fetch(`${ADMIN_API_URL}/tools${params}`);
    return res.json();
  },

  async getTool(id: string): Promise<Tool> {
    const res = await fetch(`${ADMIN_API_URL}/tools/${id}`);
    return res.json();
  },

  async createTool(data: Partial<Tool>): Promise<Tool> {
    const res = await fetch(`${ADMIN_API_URL}/tools`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return res.json();
  },

  async updateTool(id: string, data: Partial<Tool>): Promise<Tool> {
    const res = await fetch(`${ADMIN_API_URL}/tools/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return res.json();
  },

  // Templates
  async getTemplates(): Promise<Template[]> {
    const res = await fetch(`${ADMIN_API_URL}/templates`);
    return res.json();
  },

  async getTemplate(id: string): Promise<Template> {
    const res = await fetch(`${ADMIN_API_URL}/templates/${id}`);
    return res.json();
  },

  async createTemplate(data: { name: string; description?: string }): Promise<Template> {
    const res = await fetch(`${ADMIN_API_URL}/templates`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return res.json();
  },

  async createTemplateVersion(
    templateId: string,
    data: {
      settings: TemplateVersion['settings'];
      tools: string[];
      prompt?: string;
      activate?: boolean;
    }
  ): Promise<TemplateVersion> {
    const res = await fetch(`${ADMIN_API_URL}/templates/${templateId}/versions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return res.json();
  },

  async activateVersion(templateId: string, versionId: string): Promise<void> {
    await fetch(`${ADMIN_API_URL}/templates/${templateId}/versions/${versionId}/activate`, {
      method: 'POST',
    });
  },

  // Sessions
  async getSessions(filters?: {
    template_version_id?: string;
    instance_id?: string;
    state?: string;
  }): Promise<Session[]> {
    const params = new URLSearchParams();
    if (filters?.template_version_id) params.append('template_version_id', filters.template_version_id);
    if (filters?.instance_id) params.append('instance_id', filters.instance_id);
    if (filters?.state) params.append('state', filters.state);
    const query = params.toString() ? `?${params.toString()}` : '';
    const res = await fetch(`${ADMIN_API_URL}/sessions${query}`);
    return res.json();
  },

  async getSession(id: string): Promise<Session> {
    const res = await fetch(`${ADMIN_API_URL}/sessions/${id}`);
    return res.json();
  },

  // Instances
  async getInstances(filters?: {
    template_id?: string;
    status?: string;
    is_enabled?: boolean;
  }): Promise<AgentInstance[]> {
    const params = new URLSearchParams();
    if (filters?.template_id) params.append('template_id', filters.template_id);
    if (filters?.status) params.append('status_filter', filters.status);
    if (filters?.is_enabled !== undefined) params.append('is_enabled', String(filters.is_enabled));
    const query = params.toString() ? `?${params.toString()}` : '';
    const res = await fetch(`${ADMIN_API_URL}/instances${query}`);
    return res.json();
  },

  async getInstance(id: string): Promise<AgentInstance> {
    const res = await fetch(`${ADMIN_API_URL}/instances/${id}`);
    return res.json();
  },

  async createInstance(data: AgentInstanceCreate): Promise<AgentInstance> {
    const res = await fetch(`${ADMIN_API_URL}/instances`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return res.json();
  },

  async updateInstance(id: string, data: AgentInstanceUpdate): Promise<AgentInstance> {
    const res = await fetch(`${ADMIN_API_URL}/instances/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return res.json();
  },

  async deleteInstance(id: string): Promise<void> {
    await fetch(`${ADMIN_API_URL}/instances/${id}`, { method: 'DELETE' });
  },

  async startInstance(id: string): Promise<AgentInstance> {
    const res = await fetch(`${ADMIN_API_URL}/instances/${id}/start`, { method: 'POST' });
    return res.json();
  },

  async stopInstance(id: string): Promise<AgentInstance> {
    const res = await fetch(`${ADMIN_API_URL}/instances/${id}/stop`, { method: 'POST' });
    return res.json();
  },

  // System Prompts
  async getPrompts(activeOnly?: boolean): Promise<SystemPrompt[]> {
    const params = activeOnly !== undefined ? `?active_only=${activeOnly}` : '';
    const res = await fetch(`${ADMIN_API_URL}/prompts${params}`);
    return res.json();
  },

  async getPrompt(id: string): Promise<SystemPrompt> {
    const res = await fetch(`${ADMIN_API_URL}/prompts/${id}`);
    return res.json();
  },

  async getPromptDefaults(): Promise<SystemPromptDefaults> {
    const res = await fetch(`${ADMIN_API_URL}/prompts/defaults`);
    return res.json();
  },

  async updatePrompt(id: string, data: Partial<SystemPrompt>): Promise<SystemPrompt> {
    const res = await fetch(`${ADMIN_API_URL}/prompts/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return res.json();
  },

  async resetPrompt(id: string): Promise<SystemPrompt> {
    const res = await fetch(`${ADMIN_API_URL}/prompts/${id}/reset`, {
      method: 'POST',
    });
    return res.json();
  },
};

// Gateway API
export const gatewayApi = {
  async health(): Promise<{ status: string }> {
    const res = await fetch(`${GATEWAY_API_URL}/health`);
    return res.json();
  },

  async getModels(): Promise<{ data: Model[] }> {
    const res = await fetch(`${GATEWAY_API_URL}/v1/models`);
    return res.json();
  },

  async chat(model: string, messages: ChatMessage[]): Promise<ChatCompletionResponse> {
    const res = await fetch(`${GATEWAY_API_URL}/v1/chat/completions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model, messages, stream: false }),
    });
    return res.json();
  },
};

// Agent base classes available
export const AGENT_BASE_CLASSES = [
  { value: 'maruntime.core.agents.simple_agent:SimpleAgent', label: 'SimpleAgent (Basic)' },
  { value: 'maruntime.core.agents.sgr_agent:SGRAgent', label: 'SGRAgent (Research)' },
  { value: 'maruntime.core.agents.tool_calling_agent:ToolCallingAgent', label: 'ToolCallingAgent' },
];
