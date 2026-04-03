'use client';

import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { useRouter } from 'next/navigation';
import { apiClient } from './api';

interface AuthContextType {
  user: { email: string; username: string; is_admin: boolean } | null;
  login: (email: string, password: string) => Promise<void>;
  loginWithToken: (token: string, user: { email: string; username: string; is_admin: boolean }) => void;
  logout: () => void;
  loading: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<{ email: string; username: string; is_admin: boolean } | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    const token = apiClient.getToken();
    const userData = localStorage.getItem('user');
    
    if (token && userData) {
      try {
        setUser(JSON.parse(userData));
      } catch {
        localStorage.removeItem('user');
        localStorage.removeItem('token');
        apiClient.setToken(null);
        setUser(null);
      }
    }
    setLoading(false);
  }, []);

  const login = async (email: string, password: string) => {
    const response = await apiClient.login({ email, password });
    apiClient.setToken(response.access_token);
    const userData = { 
      email: response.user.email, 
      username: response.user.username,
      is_admin: response.user.is_admin 
    };
    localStorage.setItem('user', JSON.stringify(userData));
    setUser(userData);
    router.push('/chat');
  };

  const logout = () => {
    apiClient.setToken(null);
    localStorage.removeItem('user');
    localStorage.removeItem('edubot_api_keys');
    setUser(null);
    router.push('/chat');
  };

  const loginWithToken = (token: string, userData: { email: string; username: string; is_admin: boolean }) => {
    apiClient.setToken(token);
    localStorage.setItem('user', JSON.stringify(userData));
    setUser(userData);
  };

  return (
    <AuthContext.Provider value={{ user, login, loginWithToken, logout, loading }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
