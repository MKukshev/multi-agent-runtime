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
      system_prompt: string | null;  // DB field name
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

  async updateTemplatePrompt(templateId: string, versionId: string, systemPrompt: string): Promise<TemplateVersion> {
    const res = await fetch(`${ADMIN_API_URL}/templates/${templateId}/versions/${versionId}/prompt`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ system_prompt: systemPrompt }),
    });
    return res.json();
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

// SSE Event Types for Agent Steps
export interface StepStartEvent {
  type: 'step_start';
  step: number;
  max_steps: number;
  description: string;
  status: 'running';
  timestamp: number;
}

export interface ToolCallEvent {
  type: 'tool_call';
  step: number;
  tool: string;
  args: Record<string, unknown>;
  status: 'running';
  timestamp: number;
}

export interface ToolResultEvent {
  type: 'tool_result';
  step: number;
  tool: string;
  result: string;
  success: boolean;
  duration_ms: number | null;
  timestamp: number;
}

export interface StepEndEvent {
  type: 'step_end';
  step: number;
  status: 'completed' | 'error' | 'running';
  duration_ms: number | null;
  timestamp: number;
}

export interface ThinkingEvent {
  type: 'thinking';
  step: number;
  content: string;
  timestamp: number;
}

export interface ErrorEvent {
  type: 'error';
  step: number;
  message: string;
  timestamp: number;
}

export interface MessageEvent {
  type: 'message';
  content: string;
  session_id?: string;
}

export interface DoneEvent {
  type: 'done';
  finish_reason: string;
  session_id?: string;
}

export type AgentEvent = (
  | StepStartEvent
  | ToolCallEvent
  | ToolResultEvent
  | StepEndEvent
  | ThinkingEvent
  | ErrorEvent
  | MessageEvent
  | DoneEvent
) & { session_id?: string };

// Gateway API
export const gatewayApi = {
  async health(): Promise<{ status: string }> {
    const res = await fetch(`${GATEWAY_API_URL}/health`);
    return res.json();
  },

  async getModels(): Promise<{ data: Model[] }> {
    const res = await fetch(`${GATEWAY_API_URL}/v1/models`, {
      credentials: 'include',
    });
    return res.json();
  },

  async chat(model: string, messages: ChatMessage[], chatId?: string): Promise<ChatCompletionResponse> {
    const res = await fetch(`${GATEWAY_API_URL}/v1/chat/completions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ model, messages, stream: false, chat_id: chatId }),
    });
    return res.json();
  },

  /**
   * Stream chat completions with SSE events for agent steps
   */
  async *chatStream(
    model: string,
    messages: ChatMessage[],
    chatId?: string
  ): AsyncGenerator<AgentEvent, void, unknown> {
    const res = await fetch(`${GATEWAY_API_URL}/v1/chat/completions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ model, messages, stream: true, chat_id: chatId }),
    });
    
    // Extract session_id from response header
    let sessionId = res.headers.get('x-session-id');

    if (!res.ok) {
      throw new Error(`HTTP error! status: ${res.status}`);
    }

    const reader = res.body?.getReader();
    if (!reader) {
      throw new Error('No response body');
    }

    const decoder = new TextDecoder();
    let buffer = '';
    let currentEventType = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          // Extract session_id from SSE comment
          if (line.startsWith(': session_id=')) {
            sessionId = line.slice(13);
            continue;
          }
          // Skip other comments
          if (line.startsWith(':')) continue;
          
          if (line.startsWith('event: ')) {
            currentEventType = line.slice(7).trim();
            continue;
          }
          
          if (line.startsWith('data: ')) {
            const jsonStr = line.slice(6);
            try {
              const data = JSON.parse(jsonStr);
              
              // Use event type from SSE header if available
              switch (currentEventType) {
                case 'step_start':
                  yield {
                    type: 'step_start',
                    step: data.step,
                    description: data.description,
                    status: data.status,
                    max_steps: data.max_steps,
                    session_id: sessionId || undefined,
                  } as AgentEvent;
                  break;
                case 'tool_call':
                  yield {
                    type: 'tool_call',
                    step: data.step,
                    tool: data.tool,
                    args: data.args,
                    session_id: sessionId || undefined,
                  } as AgentEvent;
                  break;
                case 'tool_result':
                  yield {
                    type: 'tool_result',
                    step: data.step,
                    tool: data.tool,
                    result: data.result,
                    success: data.success,
                    duration_ms: data.duration_ms,
                    session_id: sessionId || undefined,
                  } as AgentEvent;
                  break;
                case 'step_end':
                  yield {
                    type: 'step_end',
                    step: data.step,
                    status: data.status,
                    duration_ms: data.duration_ms,
                    session_id: sessionId || undefined,
                  } as AgentEvent;
                  break;
                case 'thinking':
                  yield {
                    type: 'thinking',
                    step: data.step,
                    content: data.content,
                    session_id: sessionId || undefined,
                  } as AgentEvent;
                  break;
                case 'error':
                  yield {
                    type: 'error',
                    step: data.step,
                    message: data.message,
                    session_id: sessionId || undefined,
                  } as AgentEvent;
                  break;
                case 'message':
                  // OpenAI-style message chunk
                  const delta = data.choices?.[0]?.delta;
                  if (delta?.content) {
                    yield { type: 'message', content: delta.content, session_id: sessionId || undefined } as AgentEvent;
                  }
                  break;
                case 'done':
                  yield { type: 'done', finish_reason: data.finish_reason || 'stop', session_id: sessionId || undefined } as AgentEvent;
                  break;
                default:
                  // Fallback: try to determine type from data structure
                  if ('choices' in data) {
                    const delta = data.choices?.[0]?.delta;
                    if (delta?.content) {
                      yield { type: 'message', content: delta.content, session_id: sessionId || undefined } as AgentEvent;
                    }
                    if (data.finish_reason) {
                      yield { type: 'done', finish_reason: data.finish_reason, session_id: sessionId || undefined } as AgentEvent;
                    }
                  }
              }
              currentEventType = ''; // Reset after processing
            } catch {
              // Ignore parse errors for malformed JSON
            }
          }
        }
      }
    } finally {
      reader.releaseLock();
    }
  },
};

// Agent base classes available
export const AGENT_BASE_CLASSES = [
  { value: 'maruntime.core.agents.simple_agent:SimpleAgent', label: 'SimpleAgent (Basic)' },
  { value: 'maruntime.core.agents.tool_calling_agent:ToolCallingAgent', label: 'ToolCallingAgent' },
  { value: 'maruntime.core.agents.flexible_tool_calling_agent:FlexibleToolCallingAgent', label: 'FlexibleToolCallingAgent (Free-form Answer)' },
];
