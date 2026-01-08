'use client';

import { useEffect, useState, useRef, useCallback } from 'react';
import { Card } from '@/components/Card';
import { Button } from '@/components/Button';
import { AgentStep, AgentStepData, ToolExecution, StepStatus } from '@/components/AgentStep';
import { gatewayApi, ChatMessage, Model, AgentEvent, StepStartEvent } from '@/lib/api';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  steps?: AgentStepData[];
}

export default function ChatPage() {
  const [models, setModels] = useState<Model[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingModels, setLoadingModels] = useState(true);
  const [useStreaming, setUseStreaming] = useState(true);
  const [currentSteps, setCurrentSteps] = useState<AgentStepData[]>([]);
  const [streamingContent, setStreamingContent] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  // Refs to track accumulated data during streaming
  const stepsRef = useRef<AgentStepData[]>([]);
  const contentRef = useRef<string>('');

  useEffect(() => {
    async function loadModels() {
      try {
        const response = await gatewayApi.getModels();
        setModels(response.data);
        if (response.data.length > 0) {
          setSelectedModel(response.data[0].id);
        }
      } catch (error) {
        console.error('Failed to load models:', error);
      } finally {
        setLoadingModels(false);
      }
    }
    loadModels();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, currentSteps, streamingContent]);

  const processStreamEvent = useCallback((event: AgentEvent) => {
    switch (event.type) {
      case 'step_start':
        setCurrentSteps((prev) => {
          const existing = prev.find((s) => s.step === event.step);
          if (existing) return prev;
          const newSteps = [
            ...prev,
            {
              step: event.step,
              maxSteps: (event as StepStartEvent).max_steps || 10,
              description: event.description || 'Processing...',
              status: 'running' as StepStatus,
              tools: [],
            },
          ];
          stepsRef.current = newSteps;
          return newSteps;
        });
        break;

      case 'tool_call':
        setCurrentSteps((prev) => {
          const newSteps = prev.map((s) =>
            s.step === event.step
              ? {
                  ...s,
                  tools: [
                    ...s.tools,
                    { tool: event.tool, args: event.args } as ToolExecution,
                  ],
                }
              : s
          );
          stepsRef.current = newSteps;
          return newSteps;
        });
        break;

      case 'tool_result':
        setCurrentSteps((prev) => {
          const newSteps = prev.map((s) =>
            s.step === event.step
              ? {
                  ...s,
                  tools: s.tools.map((t, idx) =>
                    idx === s.tools.length - 1 && t.tool === event.tool
                      ? {
                          ...t,
                          result: event.result,
                          success: event.success,
                          duration_ms: event.duration_ms,
                        }
                      : t
                  ),
                }
              : s
          );
          stepsRef.current = newSteps;
          return newSteps;
        });
        break;

      case 'step_end':
        setCurrentSteps((prev) => {
          const newSteps = prev.map((s) =>
            s.step === event.step
              ? { ...s, status: event.status as StepStatus, duration_ms: event.duration_ms }
              : s
          );
          stepsRef.current = newSteps;
          return newSteps;
        });
        break;

      case 'thinking':
        setCurrentSteps((prev) => {
          const newSteps = prev.map((s) =>
            s.step === event.step ? { ...s, thinking: event.content } : s
          );
          stepsRef.current = newSteps;
          return newSteps;
        });
        break;

      case 'error':
        setCurrentSteps((prev) => {
          const newSteps = prev.map((s) =>
            s.step === event.step ? { ...s, error: event.message, status: 'error' as StepStatus } : s
          );
          stepsRef.current = newSteps;
          return newSteps;
        });
        break;

      case 'message':
        setStreamingContent((prev) => {
          const newContent = prev + event.content;
          contentRef.current = newContent;
          return newContent;
        });
        break;

      case 'done':
        // Streaming complete
        break;
    }
  }, []);

  async function handleSendStreaming() {
    if (!input.trim() || !selectedModel || loading) return;

    const userMessage: Message = {
      role: 'user',
      content: input.trim(),
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setLoading(true);
    setCurrentSteps([]);
    setStreamingContent('');
    // Reset refs
    stepsRef.current = [];
    contentRef.current = '';

    try {
      const chatMessages: ChatMessage[] = messages
        .concat(userMessage)
        .map((m) => ({ role: m.role, content: m.content }));

      for await (const event of gatewayApi.chatStream(selectedModel, chatMessages)) {
        processStreamEvent(event);
      }

      // Use refs to get the accumulated values (not stale closure values)
      const finalSteps = stepsRef.current;
      const finalContent = contentRef.current;

      // Add assistant message with steps
      const assistantMessage: Message = {
        role: 'assistant',
        content: finalContent || 'Task completed.',
        timestamp: new Date(),
        steps: finalSteps.length > 0 ? [...finalSteps] : undefined,
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      console.error('Failed to send message:', error);
      const errorMessage: Message = {
        role: 'assistant',
        content: `Error: ${error instanceof Error ? error.message : 'Failed to get response'}`,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
      setCurrentSteps([]);
      setStreamingContent('');
      stepsRef.current = [];
      contentRef.current = '';
    }
  }

  async function handleSendNonStreaming() {
    if (!input.trim() || !selectedModel || loading) return;

    const userMessage: Message = {
      role: 'user',
      content: input.trim(),
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setLoading(true);

    try {
      const chatMessages: ChatMessage[] = messages
        .concat(userMessage)
        .map((m) => ({ role: m.role, content: m.content }));

      const response = await gatewayApi.chat(selectedModel, chatMessages);

      let content = '';
      const choice = response.choices[0];
      if (typeof choice.message.content === 'string') {
        content = choice.message.content;
      } else if (Array.isArray(choice.message.content)) {
        content = choice.message.content
          .map((c) => (typeof c === 'string' ? c : c.text))
          .join('');
      }

      const assistantMessage: Message = {
        role: 'assistant',
        content,
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      console.error('Failed to send message:', error);
      const errorMessage: Message = {
        role: 'assistant',
        content: 'Error: Failed to get response from the agent.',
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  }

  function handleSend() {
    if (useStreaming) {
      handleSendStreaming();
    } else {
      handleSendNonStreaming();
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  function clearChat() {
    setMessages([]);
    setCurrentSteps([]);
    setStreamingContent('');
  }

  if (loadingModels) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-[var(--primary)]"></div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)]">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-bold">Chat</h1>
          <p className="text-[var(--muted)] mt-1">Test your agent via Gateway API</p>
        </div>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={useStreaming}
              onChange={(e) => setUseStreaming(e.target.checked)}
              className="w-4 h-4 rounded border-[var(--border)] bg-[var(--card)]"
            />
            <span>Streaming</span>
          </label>
          <select
            value={selectedModel}
            onChange={(e) => setSelectedModel(e.target.value)}
            className="px-4 py-2 rounded-lg bg-[var(--card)] border border-[var(--border)] outline-none focus:border-[var(--primary)]"
          >
            {models.map((model) => (
              <option key={model.id} value={model.id}>
                {model.id}
              </option>
            ))}
          </select>
          <Button variant="secondary" onClick={clearChat}>
            Clear Chat
          </Button>
        </div>
      </div>

      <Card className="flex-1 flex flex-col overflow-hidden">
        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.length === 0 && currentSteps.length === 0 ? (
            <div className="flex items-center justify-center h-full text-[var(--muted)]">
              <div className="text-center">
                <p className="text-4xl mb-4">🤖</p>
                <p>Start a conversation with the agent</p>
                <p className="text-sm mt-2">Using model: {selectedModel}</p>
                {useStreaming && (
                  <p className="text-xs mt-1 text-[var(--primary)]">✨ Streaming enabled - see agent steps in real-time</p>
                )}
              </div>
            </div>
          ) : (
            <>
              {messages.map((message, index) => (
                <div key={index}>
                  {/* User message */}
                  {message.role === 'user' && (
                    <div className="flex justify-end mb-4">
                      <div className="max-w-[70%] rounded-2xl px-4 py-3 bg-[var(--primary)] text-white">
                        <p className="whitespace-pre-wrap">{message.content}</p>
                        <p className="text-xs mt-1 text-blue-200">
                          {message.timestamp.toLocaleTimeString()}
                        </p>
                      </div>
                    </div>
                  )}

                  {/* Assistant message with steps */}
                  {message.role === 'assistant' && (
                    <div className="flex justify-start mb-4">
                      <div className="max-w-[85%] space-y-3">
                        {/* Steps */}
                        {message.steps && message.steps.length > 0 && (
                          <div className="space-y-2">
                            {message.steps.map((step) => (
                              <AgentStep key={step.step} data={step} />
                            ))}
                          </div>
                        )}

                        {/* Final answer */}
                        <div className="rounded-2xl px-4 py-3 bg-[var(--background)]">
                          <p className="whitespace-pre-wrap">{message.content}</p>
                          <p className="text-xs mt-1 text-[var(--muted)]">
                            {message.timestamp.toLocaleTimeString()}
                          </p>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              ))}

              {/* Current streaming steps */}
              {loading && currentSteps.length > 0 && (
                <div className="flex justify-start mb-4">
                  <div className="max-w-[85%] space-y-2">
                    {currentSteps.map((step) => (
                      <AgentStep key={step.step} data={step} defaultExpanded />
                    ))}
                  </div>
                </div>
              )}

              {/* Streaming content preview */}
              {loading && streamingContent && (
                <div className="flex justify-start mb-4">
                  <div className="max-w-[70%] rounded-2xl px-4 py-3 bg-[var(--background)]">
                    <p className="whitespace-pre-wrap">{streamingContent}</p>
                    <div className="flex gap-1 mt-2">
                      <span className="w-2 h-2 bg-[var(--primary)] rounded-full animate-pulse"></span>
                    </div>
                  </div>
                </div>
              )}

              {/* Loading indicator (no steps yet) */}
              {loading && currentSteps.length === 0 && !streamingContent && (
                <div className="flex justify-start">
                  <div className="bg-[var(--background)] rounded-2xl px-4 py-3">
                    <div className="flex gap-1">
                      <span className="w-2 h-2 bg-[var(--muted)] rounded-full animate-bounce"></span>
                      <span className="w-2 h-2 bg-[var(--muted)] rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></span>
                      <span className="w-2 h-2 bg-[var(--muted)] rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></span>
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="border-t border-[var(--border)] p-4">
          <div className="flex gap-4">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Type your message..."
              className="flex-1 px-4 py-3 rounded-xl bg-[var(--background)] border border-[var(--border)] outline-none focus:border-[var(--primary)] resize-none"
              rows={1}
              disabled={loading}
            />
            <Button onClick={handleSend} disabled={!input.trim() || loading}>
              {loading ? '...' : 'Send'}
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
}
