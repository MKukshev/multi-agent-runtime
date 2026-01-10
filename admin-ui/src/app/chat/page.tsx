'use client';

import { useEffect, useState, useRef, useCallback } from 'react';
import { Card } from '@/components/Card';
import { Button } from '@/components/Button';
import { AgentStep, AgentStepData, ToolExecution, StepStatus } from '@/components/AgentStep';
import { ChatSidebar } from '@/components/ChatSidebar';
import { useAuth } from '@/contexts/AuthContext';
import { gatewayApi, ChatMessage, Model, AgentEvent, StepStartEvent } from '@/lib/api';

const API_URL = process.env.NEXT_PUBLIC_GATEWAY_API_URL || 'http://localhost:8000';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  steps?: AgentStepData[];
}

interface ChatSession {
  id: string;
  title: string;
  model: string | null;
}

export default function ChatPage() {
  const { user } = useAuth();
  const [models, setModels] = useState<Model[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingModels, setLoadingModels] = useState(true);
  const [useStreaming, setUseStreaming] = useState(true);
  const [currentSteps, setCurrentSteps] = useState<AgentStepData[]>([]);
  const [streamingContent, setStreamingContent] = useState('');
  const [selectedChatId, setSelectedChatId] = useState<string | null>(null);
  const [chatTitle, setChatTitle] = useState<string>('New Chat');
  const [sidebarRefresh, setSidebarRefresh] = useState(0);
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

  // Load messages when chat is selected
  useEffect(() => {
    if (selectedChatId && user) {
      loadChatMessages(selectedChatId);
    }
  }, [selectedChatId, user]);

  const loadChatMessages = async (chatId: string) => {
    try {
      const res = await fetch(`${API_URL}/v1/chats/${chatId}/messages`, {
        credentials: 'include',
      });
      if (res.ok) {
        const data = await res.json();
        
        // Group messages and steps by user request
        const loadedMessages: Message[] = [];
        let currentUserMessage: Message | null = null;
        let currentSteps: AgentStepData[] = [];
        
        for (const msg of data.data) {
          const messageType = msg.message_type || 'message';
          
          if (messageType === 'message') {
            // Regular message (user or assistant)
            if (msg.role === 'user') {
              // Save previous user message with its steps
              if (currentUserMessage) {
                loadedMessages.push(currentUserMessage);
              }
              // Start new user message
              currentUserMessage = {
                role: 'user',
                content: extractTextContent(msg.content),
                timestamp: new Date(msg.created_at),
              };
              currentSteps = [];
            } else if (msg.role === 'assistant') {
              // Save user message if exists
              if (currentUserMessage) {
                loadedMessages.push(currentUserMessage);
                currentUserMessage = null;
              }
              // Add assistant message with accumulated steps
              loadedMessages.push({
                role: 'assistant',
                content: extractTextContent(msg.content),
                timestamp: new Date(msg.created_at),
                steps: currentSteps.length > 0 ? [...currentSteps] : undefined,
              });
              currentSteps = [];
            }
          } else {
            // Agent step events
            const stepData = msg.step_data || {};
            const stepNumber = msg.step_number || 0;
            
            if (messageType === 'step_start') {
              currentSteps.push({
                step: stepNumber,
                maxSteps: stepData.max_iterations || 10,
                status: 'completed' as StepStatus,
                description: stepData.description || 'Processing...',
                tools: [],
              });
            } else if (messageType === 'tool_call') {
              // Find the step and add tool
              const step = currentSteps.find(s => s.step === stepNumber);
              if (step) {
                step.tools.push({
                  tool: stepData.tool_name || 'Unknown',
                  args: stepData.tool_args || {},
                });
              }
            } else if (messageType === 'tool_result') {
              // Find the step and update tool result
              const step = currentSteps.find(s => s.step === stepNumber);
              if (step && step.tools.length > 0) {
                const tool = step.tools.find(t => t.tool === stepData.tool_name);
                if (tool) {
                  tool.result = stepData.result;
                  tool.success = stepData.success;
                }
              }
            } else if (messageType === 'step_end') {
              const step = currentSteps.find(s => s.step === stepNumber);
              if (step) {
                step.status = (stepData.status || 'completed') as StepStatus;
              }
            } else if (messageType === 'thinking') {
              const step = currentSteps.find(s => s.step === stepNumber);
              if (step) {
                step.thinking = stepData.thought;
              }
            }
          }
        }
        
        // Don't forget last user message
        if (currentUserMessage) {
          loadedMessages.push(currentUserMessage);
        }
        
        setMessages(loadedMessages);
      }
    } catch (error) {
      console.error('Failed to load chat messages:', error);
    }
  };
  
  // Helper to extract text from content (handles various formats)
  const extractTextContent = (content: any): string => {
    if (typeof content === 'string') return content;
    if (Array.isArray(content)) {
      return content
        .map(item => (typeof item === 'string' ? item : item?.text || ''))
        .join('');
    }
    if (content?.text) return content.text;
    if (content?.content) return extractTextContent(content.content);
    return '';
  };

  const handleSelectChat = async (chatId: string) => {
    // Load chat details
    try {
      const res = await fetch(`${API_URL}/v1/chats/${chatId}`, {
        credentials: 'include',
      });
      if (res.ok) {
        const chat: ChatSession = await res.json();
        setSelectedChatId(chatId);
        setChatTitle(chat.title);
        if (chat.model) {
          setSelectedModel(chat.model);
        }
      }
    } catch (error) {
      console.error('Failed to load chat:', error);
    }
  };

  const handleNewChat = () => {
    setSelectedChatId(null);
    setMessages([]);
    setChatTitle('New Chat');
    setCurrentSteps([]);
    setStreamingContent('');
  };

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

      case 'thinking':
        setCurrentSteps((prev) => {
          const newSteps = prev.map((s) =>
            s.step === event.step
              ? { ...s, thought: event.thought }
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
              ? { ...s, status: event.status as StepStatus }
              : s
          );
          stepsRef.current = newSteps;
          return newSteps;
        });
        break;

      case 'message':
        if (event.content) {
          setStreamingContent((prev) => {
            const newContent = prev + event.content;
            contentRef.current = newContent;
            return newContent;
          });
        }
        break;

      case 'error':
        setCurrentSteps((prev) => {
          const newSteps = prev.map((s) =>
            s.step === event.step
              ? { ...s, status: 'failed' as StepStatus, error: event.error }
              : s
          );
          stepsRef.current = newSteps;
          return newSteps;
        });
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
    stepsRef.current = [];
    contentRef.current = '';

    try {
      const chatMessages: ChatMessage[] = messages
        .concat(userMessage)
        .map((m) => ({ role: m.role, content: m.content }));

      // Use chat_id if we have one
      for await (const event of gatewayApi.chatStream(selectedModel, chatMessages, selectedChatId || undefined)) {
        processStreamEvent(event);
        
        // Capture new chat_id from session header if this is a new chat
        if (!selectedChatId && event.session_id) {
          setSelectedChatId(event.session_id);
          // Auto-generate title from first message
          if (userMessage.content.length > 50) {
            setChatTitle(userMessage.content.substring(0, 50) + '...');
          } else {
            setChatTitle(userMessage.content);
          }
          // Refresh sidebar to show new chat
          setSidebarRefresh(prev => prev + 1);
        }
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

      const response = await gatewayApi.chat(selectedModel, chatMessages, selectedChatId || undefined);

      // Capture new chat_id from response if this is a new chat
      if (!selectedChatId && response.id && response.id !== selectedModel) {
        setSelectedChatId(response.id);
        if (userMessage.content.length > 50) {
          setChatTitle(userMessage.content.substring(0, 50) + '...');
        } else {
          setChatTitle(userMessage.content);
        }
        setSidebarRefresh(prev => prev + 1);
      }

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

  if (loadingModels) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-[var(--primary)]"></div>
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100vh-4rem)] -m-8">
      {/* Chat Sidebar */}
      {user && (
        <ChatSidebar
          selectedChatId={selectedChatId}
          onSelectChat={handleSelectChat}
          onNewChat={handleNewChat}
          refreshTrigger={sidebarRefresh}
        />
      )}

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col p-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-3xl font-bold">{chatTitle}</h1>
            <p className="text-[var(--muted)] mt-1">
              {selectedChatId ? 'Continue your conversation' : 'Start a new conversation'}
            </p>
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
              disabled={!!selectedChatId}
            >
              {models.map((model) => (
                <option key={model.id} value={model.id}>
                  {model.id}
                </option>
              ))}
            </select>
            {!selectedChatId && (
              <Button variant="secondary" onClick={handleNewChat}>
                Clear Chat
              </Button>
            )}
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
    </div>
  );
}
