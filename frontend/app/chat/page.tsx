'use client';

import { useState, useEffect, useRef, FormEvent, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import ReactMarkdown from 'react-markdown';
import { apiClient } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';
import styles from './chat.module.css';
import { Chat } from '@/lib/types';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  status?: string;   // tool-use status (e.g. "Searching...")
  streaming?: boolean; // true while still receiving tokens
  feedbackSent?: boolean;
}

type FeedbackType = 'positive' | 'negative';

type FeedbackDraft = {
  assistantIndex: number;
  feedbackType: FeedbackType;
  reason: string;
};

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [chatId, setChatId] = useState<string | null>(null);
  const [chats, setChats] = useState<Chat[]>([]);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [editingChatId, setEditingChatId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [chatsLoading, setChatsLoading] = useState(false);
  const [feedbackReasonCatalog, setFeedbackReasonCatalog] = useState<Record<FeedbackType, string[]>>({
    positive: [],
    negative: [],
  });
  const [feedbackDraft, setFeedbackDraft] = useState<FeedbackDraft | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const editInputRef = useRef<HTMLInputElement>(null);
  const { user, logout } = useAuth();
  const router = useRouter();

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Load chats list when user is authenticated
  const loadChats = useCallback(async () => {
    if (!user) return;
    setChatsLoading(true);
    try {
      const chatList = await apiClient.getChats();
      setChats(chatList);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      if (message.includes('401') || message.includes('403')) {
        logout();
        return;
      }
      console.warn('Failed to load chats:', message);
      setChats([]);
    } finally {
      setChatsLoading(false);
    }
  }, [user, logout]);

  useEffect(() => {
    loadChats();
  }, [loadChats]);

  useEffect(() => {
    if (!user) return;
    const loadFeedbackTaxonomy = async () => {
      try {
        const taxonomy = await apiClient.getFeedbackTaxonomy();
        setFeedbackReasonCatalog(taxonomy.reasons);
      } catch {
        // Non-blocking; feedback can still be sent without reason selection.
      }
    };
    loadFeedbackTaxonomy();
  }, [user]);

  // Focus edit input when editing
  useEffect(() => {
    if (editingChatId) {
      editInputRef.current?.focus();
    }
  }, [editingChatId]);

  const loadChatMessages = async (selectedChatId: string) => {
    if (!user) return;
    try {
      const data = await apiClient.getChatMessages(selectedChatId);
      const loadedMessages: Message[] = [];
      for (const msg of data.messages) {
        loadedMessages.push({ role: 'user', content: msg.human });
        loadedMessages.push({ role: 'assistant', content: msg.bot });
      }
      setMessages(loadedMessages);
      setChatId(selectedChatId);
    } catch (err) {
      console.error('Failed to load chat messages:', err);
    }
  };

  const handleNewChat = () => {
    setMessages([]);
    setChatId(null);
  };

  const handleLogout = () => {
    logout();
  };

  const handleLogin = () => {
    router.push('/login');
  };

  const handleClear = () => {
    setMessages([]);
    setChatId(null);
  };

  const handleSettings = () => {
    router.push('/settings');
  };

  const handleFeedbackSelection = (assistantIndex: number, feedbackType: FeedbackType) => {
    const defaultReasons = feedbackReasonCatalog[feedbackType] || [];
    setFeedbackDraft({
      assistantIndex,
      feedbackType,
      reason: defaultReasons[0] || '',
    });
  };

  const submitFeedbackDraft = async () => {
    if (!feedbackDraft || !user || !chatId) return;

    const assistantIndex = feedbackDraft.assistantIndex;
    if (!user || !chatId) return;
    if (assistantIndex <= 0 || messages[assistantIndex].role !== 'assistant') return;

    const userMessage = messages[assistantIndex - 1];
    const assistantMessage = messages[assistantIndex];
    if (userMessage.role !== 'user') return;

    try {
      await apiClient.submitFeedback({
        chat_id: chatId,
        feedback_type: feedbackDraft.feedbackType,
        user_message: userMessage.content,
        bot_message: assistantMessage.content,
        reason: feedbackDraft.reason || undefined,
      });

      setMessages(prev => {
        const updated = [...prev];
        updated[assistantIndex] = { ...updated[assistantIndex], feedbackSent: true };
        return updated;
      });
      setFeedbackDraft(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      console.warn('Failed to submit feedback:', message);
    }
  };

  const handleRename = async (targetChatId: string) => {
    if (!editTitle.trim()) {
      setEditingChatId(null);
      return;
    }
    try {
      await apiClient.renameChat(targetChatId, editTitle.trim());
      setChats(prev =>
        prev.map(c => (c.id === targetChatId ? { ...c, title: editTitle.trim() } : c))
      );
    } catch (err) {
      console.error('Failed to rename chat:', err);
    }
    setEditingChatId(null);
  };

  const handleArchive = async (targetChatId: string) => {
    try {
      await apiClient.archiveChat(targetChatId);
      setChats(prev => prev.filter(c => c.id !== targetChatId));
      if (chatId === targetChatId) {
        handleNewChat();
      }
    } catch (err) {
      console.error('Failed to archive chat:', err);
    }
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userMessage = input.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    setLoading(true);

    // Authenticated users → try streaming; unauthenticated → non-streaming
    if (user) {
      // Add a placeholder assistant message that tokens will stream into
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: '', streaming: true },
      ]);

      try {
        await apiClient.streamMessage(
          { message: userMessage, chat_id: chatId },
          {
            onToken(token) {
              setMessages(prev => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                if (last.role === 'assistant') {
                  updated[updated.length - 1] = {
                    ...last,
                    content: last.content + token,
                  };
                }
                return updated;
              });
            },
            onStatus(status) {
              setMessages(prev => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                if (last.role === 'assistant') {
                  updated[updated.length - 1] = { ...last, status };
                }
                return updated;
              });
            },
            onComplete(newChatId) {
              setChatId(newChatId);
              // Mark streaming done
              setMessages(prev => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                if (last.role === 'assistant') {
                  updated[updated.length - 1] = {
                    ...last,
                    streaming: false,
                    status: undefined,
                  };
                }
                return updated;
              });
              loadChats();
            },
            onError(errMsg) {
              setMessages(prev => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                const cleaned = (errMsg || '').trim();
                const displayError = cleaned || 'Something went wrong while processing your message. Please try again.';
                if (last.role === 'assistant') {
                  updated[updated.length - 1] = {
                    ...last,
                    content: last.content || displayError,
                    streaming: false,
                    status: undefined,
                  };
                }
                return updated;
              });
            },
          },
        );
      } catch (err) {
        // Streaming failed — fall back to non-streaming
        setMessages(prev => prev.filter(m => !(m.role === 'assistant' && m.streaming)));
        try {
          const response = await apiClient.sendAuthMessage({
            message: userMessage,
            chat_id: chatId,
          });
          if (response.success) {
            setChatId(response.chat_id);
            setMessages(prev => [
              ...prev,
              { role: 'assistant', content: response.message },
            ]);
            loadChats();
          } else {
            setMessages(prev => [
              ...prev,
              { role: 'assistant', content: 'Sorry, I was unable to process your request. Please try again.' },
            ]);
          }
        } catch (fallbackErr) {
          const errText = fallbackErr instanceof Error ? fallbackErr.message : 'Failed to send message';
          setMessages(prev => [
            ...prev,
            {
              role: 'assistant',
              content: errText,
            },
          ]);
        }
      } finally {
        setLoading(false);
      }
    } else {
      // Unauthenticated — non-streaming
      try {
        const response = await apiClient.sendMessage({
          message: userMessage,
          chat_id: chatId,
        });
        if (response.success) {
          setChatId(response.chat_id);
          setMessages(prev => [
            ...prev,
            { role: 'assistant', content: response.message },
          ]);
        } else {
          setMessages(prev => [
            ...prev,
            { role: 'assistant', content: 'Sorry, I was unable to process your request. Please try again.' },
          ]);
        }
      } catch (err) {
        const errText = err instanceof Error ? err.message : 'Failed to send message';
        setMessages(prev => [
          ...prev,
          {
            role: 'assistant',
            content: errText,
          },
        ]);
      } finally {
        setLoading(false);
      }
    }
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffDays === 0) return 'Today';
    if (diffDays === 1) return 'Yesterday';
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
  };

  return (
    <div className={styles.container}>
      {/* Sidebar - only for authenticated users */}
      {user && (
        <aside className={`${styles.sidebar} ${sidebarOpen ? styles.sidebarOpen : styles.sidebarClosed}`}>
          <div className={styles.sidebarHeader}>
            <button onClick={handleNewChat} className={styles.newChatBtn}>
              + New Chat
            </button>
          </div>
          <div className={styles.chatList}>
            {chatsLoading ? (
              <p className={styles.sidebarEmpty}>Loading...</p>
            ) : chats.length === 0 ? (
              <p className={styles.sidebarEmpty}>No conversations yet</p>
            ) : (
              chats.map(chat => (
                <div
                  key={chat.id}
                  className={`${styles.chatItem} ${chatId === chat.id ? styles.chatItemActive : ''}`}
                  onClick={() => loadChatMessages(chat.id)}
                >
                  {editingChatId === chat.id ? (
                    <input
                      ref={editInputRef}
                      className={styles.editInput}
                      value={editTitle}
                      onChange={e => setEditTitle(e.target.value)}
                      onBlur={() => handleRename(chat.id)}
                      onKeyDown={e => {
                        if (e.key === 'Enter') handleRename(chat.id);
                        if (e.key === 'Escape') setEditingChatId(null);
                      }}
                      onClick={e => e.stopPropagation()}
                    />
                  ) : (
                    <>
                      <div className={styles.chatItemContent}>
                        <span className={styles.chatItemTitle}>{chat.title}</span>
                        <span className={styles.chatItemDate}>{formatDate(chat.updated_at)}</span>
                      </div>
                      <div className={styles.chatItemActions}>
                        <button
                          className={styles.chatActionBtn}
                          title="Rename"
                          onClick={e => {
                            e.stopPropagation();
                            setEditingChatId(chat.id);
                            setEditTitle(chat.title);
                          }}
                        >
                          ✏️
                        </button>
                        <button
                          className={styles.chatActionBtn}
                          title="Delete"
                          onClick={e => {
                            e.stopPropagation();
                            handleArchive(chat.id);
                          }}
                        >
                          🗑️
                        </button>
                      </div>
                    </>
                  )}
                </div>
              ))
            )}
          </div>
        </aside>
      )}

      {/* Main content */}
      <div className={styles.mainWrapper}>
        <header className={styles.header}>
          <div className={styles.headerLeft}>
            {user && (
              <button
                onClick={() => setSidebarOpen(prev => !prev)}
                className={styles.toggleSidebarBtn}
                title={sidebarOpen ? 'Close sidebar' : 'Open sidebar'}
              >
                {sidebarOpen ? '◀' : '▶'}
              </button>
            )}
            <div>
              <h1>🎓 EduBot+</h1>
              <span className={styles.username}>Welcome, {user ? user.username : 'Guest'}</span>
            </div>
          </div>
          <div className={styles.headerButtons}>
            <button onClick={handleClear} className={styles.clearBtn}>
              Clear
            </button>
            {user && (
              <button onClick={handleSettings} className={styles.settingsBtn}>
                ⚙️ Settings
              </button>
            )}
            {user ? (
              <button onClick={handleLogout} className={styles.logoutBtn}>
                Logout
              </button>
            ) : (
              <button onClick={handleLogin} className={styles.logoutBtn}>
                Login
              </button>
            )}
          </div>
        </header>

        <main className={styles.main}>
          <div className={styles.messages}>
            {messages.length === 0 && (
              <div className={styles.welcome}>
                <h2>Welcome to EduBot+! 👋</h2>
                <p>Ask me anything about the university:</p>
                <ul>
                  <li>What are the B.Tech fee structures for convenor and management quota?</li>
                  <li>When is Ugadi holiday in 2026?</li>
                  <li>What departments are available at PVPSIT?</li>
                  <li>When do IV B.Tech second semester classes start?</li>
                </ul>
              </div>
            )}

            {messages.map((msg, idx) => (
              <div
                key={idx}
                className={`${styles.message} ${
                  msg.role === 'user' ? styles.userMessage : styles.assistantMessage
                }`}
              >
                <div className={styles.messageContent}>
                  {msg.role === 'assistant' ? (
                    <>
                      {msg.status && (
                        <div className={styles.streamStatus}>
                          🔍 {msg.status}
                        </div>
                      )}
                      <ReactMarkdown>{msg.content}</ReactMarkdown>
                      {msg.streaming && <span className={styles.streamCursor}>▊</span>}
                      {user && !msg.streaming && msg.content && (
                        <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
                          <button
                            type="button"
                            onClick={() => handleFeedbackSelection(idx, 'positive')}
                            disabled={!!msg.feedbackSent}
                            className={styles.chatActionBtn}
                            title="Helpful"
                          >
                            👍
                          </button>
                          <button
                            type="button"
                            onClick={() => handleFeedbackSelection(idx, 'negative')}
                            disabled={!!msg.feedbackSent}
                            className={styles.chatActionBtn}
                            title="Not helpful"
                          >
                            👎
                          </button>
                        </div>
                      )}
                      {feedbackDraft && feedbackDraft.assistantIndex === idx && (
                        <div style={{ marginTop: 10, display: 'grid', gap: 8 }}>
                          <label style={{ fontSize: 12, opacity: 0.85 }}>
                            Feedback reason
                          </label>
                          <select
                            value={feedbackDraft.reason}
                            onChange={(e) => setFeedbackDraft({ ...feedbackDraft, reason: e.target.value })}
                            style={{
                              borderRadius: 10,
                              padding: '8px 10px',
                              border: '1px solid rgba(255,255,255,0.25)',
                              background: 'rgba(255,255,255,0.08)',
                              color: '#fff',
                            }}
                          >
                            {(feedbackReasonCatalog[feedbackDraft.feedbackType] || []).map((reason) => (
                              <option key={reason} value={reason}>
                                {reason}
                              </option>
                            ))}
                            <option value="Other: Custom feedback">Other: Custom feedback</option>
                          </select>
                          <div style={{ display: 'flex', gap: 8 }}>
                            <button type="button" className={styles.uploadButton} onClick={submitFeedbackDraft}>
                              Submit feedback
                            </button>
                            <button type="button" className={styles.removeButton} onClick={() => setFeedbackDraft(null)}>
                              Cancel
                            </button>
                          </div>
                        </div>
                      )}
                    </>
                  ) : (
                    msg.content
                  )}
                </div>
              </div>
            ))}

            {loading && !messages.some(m => m.streaming) && (
              <div className={`${styles.message} ${styles.assistantMessage}`}>
                <div className={styles.messageContent}>
                  <span className={styles.typing}>Thinking...</span>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          <form onSubmit={handleSubmit} className={styles.inputForm}>
            <textarea
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSubmit(e);
                }
              }}
              placeholder="Type your message... (Press Enter to send, Shift+Enter for new line)"
              disabled={loading}
              rows={3}
            />
            <button type="submit" disabled={loading || !input.trim()}>
              {loading ? 'Sending...' : 'Send'}
            </button>
          </form>
        </main>
      </div>
    </div>
  );
}
