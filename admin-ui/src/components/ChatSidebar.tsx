'use client';

import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';

const API_URL = process.env.NEXT_PUBLIC_GATEWAY_API_URL || 'http://localhost:8000';

interface ChatSession {
  id: string;
  title: string;
  model: string | null;
  state: string;
  created_at: string;
  updated_at: string;
}

interface ChatSidebarProps {
  selectedChatId: string | null;
  onSelectChat: (chatId: string) => void;
  onNewChat: () => void;
  refreshTrigger?: number;  // Increment to trigger refresh
}

export function ChatSidebar({ selectedChatId, onSelectChat, onNewChat, refreshTrigger }: ChatSidebarProps) {
  const { user } = useAuth();
  const [chats, setChats] = useState<ChatSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');

  useEffect(() => {
    if (user) {
      loadChats();
    }
  }, [user, refreshTrigger]);

  const loadChats = async () => {
    try {
      const res = await fetch(`${API_URL}/v1/chats`, {
        credentials: 'include',
      });
      if (res.ok) {
        const data = await res.json();
        setChats(data.data);
      }
    } catch (error) {
      console.error('Failed to load chats:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (chatId: string) => {
    if (!confirm('Delete this chat?')) return;
    
    try {
      const res = await fetch(`${API_URL}/v1/chats/${chatId}`, {
        method: 'DELETE',
        credentials: 'include',
      });
      if (res.ok) {
        setChats(chats.filter(c => c.id !== chatId));
        if (selectedChatId === chatId) {
          onNewChat();
        }
      }
    } catch (error) {
      console.error('Failed to delete chat:', error);
    }
  };

  const startEdit = (chat: ChatSession) => {
    setEditingId(chat.id);
    setEditTitle(chat.title);
  };

  const saveEdit = async () => {
    if (!editingId || !editTitle.trim()) return;
    
    try {
      const res = await fetch(`${API_URL}/v1/chats/${editingId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ title: editTitle }),
      });
      if (res.ok) {
        setChats(chats.map(c => 
          c.id === editingId ? { ...c, title: editTitle } : c
        ));
      }
    } catch (error) {
      console.error('Failed to update chat:', error);
    } finally {
      setEditingId(null);
    }
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    
    if (days === 0) return 'Today';
    if (days === 1) return 'Yesterday';
    if (days < 7) return `${days} days ago`;
    return date.toLocaleDateString();
  };

  if (!user) {
    return null;
  }

  return (
    <div className="w-64 bg-slate-900/50 border-r border-slate-700/50 flex flex-col h-full">
      {/* Header */}
      <div className="p-4 border-b border-slate-700/50">
        <button
          onClick={onNewChat}
          className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors font-medium"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          New Chat
        </button>
      </div>

      {/* Chat List */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin h-6 w-6 border-2 border-blue-500 border-t-transparent rounded-full" />
          </div>
        ) : chats.length === 0 ? (
          <div className="text-center py-8 text-slate-500 text-sm">
            No chats yet.<br />Start a new conversation!
          </div>
        ) : (
          chats.map((chat) => (
            <div
              key={chat.id}
              className={`group relative rounded-lg transition-colors ${
                selectedChatId === chat.id
                  ? 'bg-slate-700/50'
                  : 'hover:bg-slate-800/50'
              }`}
            >
              {editingId === chat.id ? (
                <div className="p-2">
                  <input
                    type="text"
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    onBlur={saveEdit}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') saveEdit();
                      if (e.key === 'Escape') setEditingId(null);
                    }}
                    className="w-full px-2 py-1 bg-slate-800 border border-slate-600 rounded text-white text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
                    autoFocus
                  />
                </div>
              ) : (
                <button
                  onClick={() => onSelectChat(chat.id)}
                  className="w-full text-left p-3"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0">
                      <p className="text-white text-sm font-medium truncate">
                        {chat.title}
                      </p>
                      <p className="text-slate-500 text-xs mt-0.5">
                        {chat.model || 'Unknown model'} • {formatDate(chat.updated_at)}
                      </p>
                    </div>
                  </div>
                </button>
              )}
              
              {/* Actions */}
              {editingId !== chat.id && (
                <div className="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity flex gap-1">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      startEdit(chat);
                    }}
                    className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-700 rounded transition-colors"
                    title="Rename"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                    </svg>
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDelete(chat.id);
                    }}
                    className="p-1.5 text-slate-400 hover:text-red-400 hover:bg-slate-700 rounded transition-colors"
                    title="Delete"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
