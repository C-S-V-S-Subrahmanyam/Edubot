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

  async submitFeedback(data: {
    chat_id?: string | null;
    feedback_type: 'positive' | 'negative';
    user_message: string;
    bot_message: string;
    reason?: string;
  }): Promise<{ id: string; feedback_type: string; status: string }> {
    return this.request<{ id: string; feedback_type: string; status: string }>('/feedback/', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async getFeedbackStats(): Promise<{
    total_feedback: number;
    positive_feedback: number;
    negative_feedback: number;
    pending_feedback: number;
  }> {
    return this.request('/feedback/stats');
  }

  async getFeedbackList(limit = 50, offset = 0): Promise<Array<{
    id: string;
    feedback_type: 'positive' | 'negative';
    user_message: string;
    bot_message: string;
    reason?: string;
    status: string;
    created_at: string;
  }>> {
    return this.request(`/feedback/?limit=${limit}&offset=${offset}`);
  }

  async updateFeedbackStatus(
    feedbackId: string,
    status: 'pending' | 'reviewed' | 'dismissed',
  ): Promise<{ id: string; status: string }> {
    return this.request(`/feedback/${feedbackId}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    });
  }

  async createGoldenExampleFromFeedback(
    feedbackId: string,
    goldenResponse: string,
  ): Promise<{ id: string; source_type: string; golden_response: string }> {
    return this.request(`/feedback/${feedbackId}/golden-example`, {
      method: 'POST',
      body: JSON.stringify({ golden_response: goldenResponse }),
    });
  }

  async getGoldenExamples(limit = 50, offset = 0): Promise<Array<{
    id: string;
    source_type: string;
    original_query: string;
    original_response: string;
    golden_response: string;
    is_active: boolean;
    created_at: string;
  }>> {
    return this.request(`/feedback/golden-examples?limit=${limit}&offset=${offset}`);
  }

  async updateGoldenExample(
    goldenId: string,
    isActive: boolean,
  ): Promise<{ id: string; is_active: boolean }> {
    return this.request(`/feedback/golden-examples/${goldenId}`, {
      method: 'PATCH',
      body: JSON.stringify({ is_active: isActive }),
    });
  }

  async deleteGoldenExample(goldenId: string): Promise<{ success: boolean; message: string }> {
    return this.request(`/feedback/golden-examples/${goldenId}`, {
      method: 'DELETE',
    });
  }

  async getIntegrations(limit = 50, offset = 0): Promise<Array<{
    id: string;
    service_name: string;
    auth_type: string;
    config: Record<string, unknown>;
    is_active: boolean;
    last_sync_status?: string;
    last_sync_error?: string;
    last_synced_at?: string;
    created_at: string;
  }>> {
    return this.request(`/integrations/?limit=${limit}&offset=${offset}`);
  }

  async createIntegration(data: {
    service_name: string;
    auth_type: string;
    config: Record<string, unknown>;
    is_active?: boolean;
  }): Promise<{ id: string; service_name: string }> {
    return this.request('/integrations/', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateIntegration(
    integrationId: string,
    data: Partial<{
      service_name: string;
      auth_type: string;
      config: Record<string, unknown>;
      is_active: boolean;
    }>,
  ): Promise<{ id: string; is_active: boolean }> {
    return this.request(`/integrations/${integrationId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  async deleteIntegration(integrationId: string): Promise<{ success: boolean; message: string }> {
    return this.request(`/integrations/${integrationId}`, {
      method: 'DELETE',
    });
  }

  async testIntegrationConnection(baseUrl: string): Promise<{ success: boolean; status_code?: number; message: string; details?: string }> {
    return this.request('/integrations/test-connection', {
      method: 'POST',
      body: JSON.stringify({ base_url: baseUrl }),
    });
  }

  async runIntegrationSync(integrationId: string): Promise<{
    success: boolean;
    log: {
      id: string;
      status: string;
      http_status?: number;
      message?: string;
      started_at: string;
      finished_at?: string;
    };
  }> {
    return this.request(`/integrations/${integrationId}/sync`, {
      method: 'POST',
    });
  }

  async getIntegrationSyncHistory(integrationId: string, limit = 20, offset = 0): Promise<Array<{
    id: string;
    integration_id: string;
    status: string;
    http_status?: number;
    message?: string;
    started_at: string;
    finished_at?: string;
    triggered_by?: string;
    created_at: string;
  }>> {
    return this.request(`/integrations/${integrationId}/sync-history?limit=${limit}&offset=${offset}`);
  }

  async getPermissionCatalog(): Promise<{ permissions: string[] }> {
    return this.request('/settings/permissions/catalog');
  }

  async getUsersForPermissions(limit = 100, offset = 0): Promise<Array<{
    id: string;
    email: string;
    username: string;
    is_admin: boolean;
    permissions: string[];
    created_at: string;
  }>> {
    return this.request(`/settings/users?limit=${limit}&offset=${offset}`);
  }

  async updateUserPermissions(userId: string, permissions: string[]): Promise<{
    id: string;
    permissions: string[];
  }> {
    return this.request(`/settings/users/${userId}/permissions`, {
      method: 'PATCH',
      body: JSON.stringify({ permissions }),
    });
  }
}

export const apiClient = new ApiClient();
