import { AuthResponse, LoginRequest, RegisterRequest, MessageRequest, MessageResponse, Chat, ChatMessage } from './types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000/api';

class ApiClient {
  private token: string | null = null;

  constructor() {
    if (typeof window !== 'undefined') {
      this.token = localStorage.getItem('token');
    }
  }

  setToken(token: string | null) {
    this.token = token;
    if (typeof window !== 'undefined') {
      if (token) {
        localStorage.setItem('token', token);
      } else {
        localStorage.removeItem('token');
      }
    }
  }

  getToken() {
    return this.token;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string>),
    };

    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    // Add user's API keys from localStorage to headers (only if authenticated)
    if (typeof window !== 'undefined' && this.token) {
      const savedKeys = localStorage.getItem('edubot_api_keys');
      if (savedKeys) {
        try {
          const apiKeys = JSON.parse(savedKeys);
          if (apiKeys.openai_key) {
            headers['X-OpenAI-Key'] = apiKeys.openai_key;
          }
          if (apiKeys.openai_model) {
            headers['X-OpenAI-Model'] = apiKeys.openai_model;
          }
          if (apiKeys.gemini_key) {
            headers['X-Gemini-Key'] = apiKeys.gemini_key;
          }
          if (apiKeys.gemini_model) {
            headers['X-Gemini-Model'] = apiKeys.gemini_model;
          }
          if (apiKeys.ollama_url) {
            headers['X-Ollama-Url'] = apiKeys.ollama_url;
          }
          if (apiKeys.ollama_model) {
            headers['X-Ollama-Model'] = apiKeys.ollama_model;
          }
          if (apiKeys.deepseek_key) {
            headers['X-DeepSeek-Key'] = apiKeys.deepseek_key;
          }
          if (apiKeys.deepseek_model) {
            headers['X-DeepSeek-Model'] = apiKeys.deepseek_model;
          }
        } catch (e) {
          console.error('Failed to parse API keys from localStorage');
        }
      }
    }

    const response = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers,
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`API Error: ${response.status} - ${error}`);
    }

    return response.json();
  }

  async register(data: RegisterRequest): Promise<AuthResponse> {
    return this.request<AuthResponse>('/auth/register', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async sendOTP(data: { email: string; username: string; password: string }): Promise<{ success: boolean; message: string }> {
    return this.request<{ success: boolean; message: string }>('/auth/send-otp', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async verifyOTP(data: { email: string; otp: string }): Promise<AuthResponse> {
    return this.request<AuthResponse>('/auth/verify-otp', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async login(data: LoginRequest): Promise<AuthResponse> {
    return this.request<AuthResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async forgotPassword(data: { email: string }): Promise<{ success: boolean; message: string }> {
    return this.request<{ success: boolean; message: string }>('/auth/forgot-password', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async resetPassword(data: { email: string; otp: string; new_password: string }): Promise<{ success: boolean; message: string }> {
    return this.request<{ success: boolean; message: string }>('/auth/reset-password', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async sendMessage(data: MessageRequest): Promise<MessageResponse> {
    return this.request<MessageResponse>('/chat/message', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async sendAuthMessage(data: MessageRequest): Promise<MessageResponse> {
    return this.request<MessageResponse>('/chat/prompt', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  /**
   * Build request headers including auth token and user API keys.
   * Shared by both the JSON helper and the streaming helper.
   */
  private getHeaders(): Record<string, string> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }
    if (typeof window !== 'undefined' && this.token) {
      const savedKeys = localStorage.getItem('edubot_api_keys');
      if (savedKeys) {
        try {
          const apiKeys = JSON.parse(savedKeys);
          if (apiKeys.openai_key)   headers['X-OpenAI-Key']   = apiKeys.openai_key;
          if (apiKeys.openai_model)  headers['X-OpenAI-Model']  = apiKeys.openai_model;
          if (apiKeys.gemini_key)    headers['X-Gemini-Key']    = apiKeys.gemini_key;
          if (apiKeys.gemini_model)  headers['X-Gemini-Model']  = apiKeys.gemini_model;
          if (apiKeys.ollama_url)    headers['X-Ollama-Url']    = apiKeys.ollama_url;
          if (apiKeys.ollama_model)  headers['X-Ollama-Model']  = apiKeys.ollama_model;
          if (apiKeys.deepseek_key)  headers['X-DeepSeek-Key']  = apiKeys.deepseek_key;
          if (apiKeys.deepseek_model) headers['X-DeepSeek-Model'] = apiKeys.deepseek_model;
        } catch { /* ignore */ }
      }
    }
    return headers;
  }

  /**
   * Stream a message via SSE from `/chat/prompt/stream`.
   *
   * Calls `onToken` for each content chunk (real-time text),
   * `onStatus` for tool-use status updates (e.g. "Searching ..."),
   * and `onComplete` with the `chat_id` when the stream finishes.
   *
   * Returns a Promise that resolves when the stream ends.
   */
  async streamMessage(
    data: MessageRequest,
    callbacks: {
      onToken: (token: string) => void;
      onStatus?: (status: string) => void;
      onComplete: (chatId: string) => void;
      onError?: (error: string) => void;
    },
  ): Promise<void> {
    const headers = this.getHeaders();

    const response = await fetch(`${API_BASE}/chat/prompt/stream`, {
      method: 'POST',
      headers,
      body: JSON.stringify(data),
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`Stream error ${response.status}: ${text}`);
    }

    const reader = response.body?.getReader();
    if (!reader) throw new Error('ReadableStream not supported');

    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const event = JSON.parse(line.slice(6));
          switch (event.type) {
            case 'content':
              callbacks.onToken(event.data);
              break;
            case 'status':
              callbacks.onStatus?.(event.data);
              break;
            case 'complete':
              callbacks.onComplete(event.chat_id);
              break;
            case 'error':
              callbacks.onError?.(event.data);
              break;
          }
        } catch { /* skip unparseable lines */ }
      }
    }
  }

  async getChats(): Promise<Chat[]> {
    return this.request<Chat[]>('/chat/');
  }

  async getChatMessages(chatId: string): Promise<{ id: string; title: string; updated_at: string; messages: ChatMessage[] }> {
    return this.request<{ id: string; title: string; updated_at: string; messages: ChatMessage[] }>(`/chat/messages/${chatId}`);
  }

  async renameChat(chatId: string, title: string): Promise<{ success: boolean; message: string }> {
    return this.request<{ success: boolean; message: string }>(`/chat/rename/${chatId}`, {
      method: 'PUT',
      body: JSON.stringify({ title }),
    });
  }

  async archiveChat(chatId: string): Promise<{ success: boolean; message: string }> {
    return this.request<{ success: boolean; message: string }>(`/chat/archive/${chatId}`, {
      method: 'DELETE',
    });
  }
}

export const apiClient = new ApiClient();
