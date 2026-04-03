// API types
export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  username: string;
  password: string;
  email: string;
}

export interface User {
  id: string;
  email: string;
  username: string;
  is_active: boolean;
  is_admin: boolean;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface MessageRequest {
  message: string;
  chat_id?: string | null;
}

export interface MessageResponse {
  success: boolean;
  chat_id: string;
  message: string;
}

export interface ChatMessage {
  id: string;
  chat_id: string;
  human: string;
  bot: string;
  created_at: string;
}

export interface Chat {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}
