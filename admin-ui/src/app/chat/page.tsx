'use client';

import { useEffect, useState, useRef } from 'react';
import { Card } from '@/components/Card';
import { Button } from '@/components/Button';
import { gatewayApi, ChatMessage, Model } from '@/lib/api';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

export default function ChatPage() {
  const [models, setModels] = useState<Model[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingModels, setLoadingModels] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);

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
  }, [messages]);

  async function handleSend() {
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

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  function clearChat() {
    setMessages([]);
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
          {messages.length === 0 ? (
            <div className="flex items-center justify-center h-full text-[var(--muted)]">
              <div className="text-center">
                <p className="text-4xl mb-4">🤖</p>
                <p>Start a conversation with the agent</p>
                <p className="text-sm mt-2">Using model: {selectedModel}</p>
              </div>
            </div>
          ) : (
            messages.map((message, index) => (
              <div
                key={index}
                className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[70%] rounded-2xl px-4 py-3 ${
                    message.role === 'user'
                      ? 'bg-[var(--primary)] text-white'
                      : 'bg-[var(--background)]'
                  }`}
                >
                  <p className="whitespace-pre-wrap">{message.content}</p>
                  <p
                    className={`text-xs mt-1 ${
                      message.role === 'user' ? 'text-blue-200' : 'text-[var(--muted)]'
                    }`}
                  >
                    {message.timestamp.toLocaleTimeString()}
                  </p>
                </div>
              </div>
            ))
          )}
          {loading && (
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

