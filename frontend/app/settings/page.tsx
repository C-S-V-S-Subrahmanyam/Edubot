'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import styles from './settings.module.css';
import UploadSection from './components/UploadSection';
import ModelSection from './components/ModelSection';
import KnowledgeBase from './components/KnowledgeBase';
import WebScraper from './components/WebScraper';
import FeedbackSection from './components/FeedbackSection';
import IntegrationsSection from './components/IntegrationsSection';
import AccessSection from './components/AccessSection';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000/api';

type TabType = 'upload' | 'kb' | 'model' | 'scraper' | 'feedback' | 'integrations' | 'access';

interface ProviderSettings {
  ai_provider: string;
  available_providers: {
    [key: string]: boolean;
  };
}

interface Settings {
  id: number;
  ai_provider: string;
  updated_at: string;
}

export default function SettingsPage() {
  const { user } = useAuth();
  const router = useRouter();
  const canManageFeedback = !!user && (user.is_admin || (user.permissions || []).includes('feedback.manage'));
  const canManageIntegrations = !!user && (user.is_admin || (user.permissions || []).includes('integration.manage'));
  const canManageAccess = !!user && user.is_admin;
  
  // Check if user has upload access (not @pvpsit.ac.in)
  const hasUploadAccess = user ? !user.email.endsWith('@pvpsit.ac.in') : true;
  
  const [activeTab, setActiveTab] = useState<TabType>(hasUploadAccess ? 'upload' : 'model');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  
  const [providerSettings, setProviderSettings] = useState<ProviderSettings | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [providerDefaults, setProviderDefaults] = useState<Record<string, boolean>>({});
  
  const [formData, setFormData] = useState({
    ai_provider: 'auto',
  });
  
  const [apiKeys, setApiKeys] = useState({
    openai_key: '',
    openai_model: 'gpt-4o-mini',
    gemini_key: '',
    gemini_model: 'gemini-2.5-flash',
    ollama_url: 'http://localhost:11434',
    ollama_model: 'llama3.1:8b',
    deepseek_key: '',
    deepseek_model: 'deepseek-chat',
  });

  const loadSettings = async () => {
    try {
      setLoading(true);
      setError('');
      
      const token = localStorage.getItem('token');
      if (!token) {
        router.push('/login');
        return;
      }

      // Load provider defaults (which providers have server-side .env keys)
      const defaultsResponse = await fetch(`${API_BASE}/settings/provider/defaults`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (defaultsResponse.ok) {
        const defaultsData = await defaultsResponse.json();
        setProviderDefaults(defaultsData);

        // If a default provider is set on the server, pre-select it
        if (defaultsData.default_provider) {
          setFormData(prev => ({ ...prev, ai_provider: defaultsData.default_provider }));
        }
      }

      // Load provider settings
      const providerResponse = await fetch(`${API_BASE}/settings/provider`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (providerResponse.ok) {
        const providerData = await providerResponse.json();
        setProviderSettings(providerData);
      }

      // Load general settings
      const settingsResponse = await fetch(`${API_BASE}/settings/`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (settingsResponse.ok) {
        const settingsData = await settingsResponse.json();
        setSettings(settingsData);
        setFormData({
          ai_provider: settingsData.ai_provider,
        });
      } else if (settingsResponse.status === 403) {
        setError('Access denied. Admin privileges with @pvpsiddhartha.ac.in domain required.');
        setTimeout(() => router.push('/chat'), 2000);
      }
    } catch (err) {
      setError('Failed to load settings');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // Check if user is logged in
    if (!user) {
      router.push('/login');
      return;
    }
    
    // Load API keys from localStorage
    const savedKeys = localStorage.getItem('edubot_api_keys');
    if (savedKeys) {
      try {
        const parsedKeys = JSON.parse(savedKeys);
        
        // Migrate old model names to supported ones
        const migratedKeys = { ...parsedKeys };
        
        // Migrate OpenAI models to gpt-4o-mini
        if (parsedKeys.openai_model && parsedKeys.openai_model !== 'gpt-4o-mini') {
          migratedKeys.openai_model = 'gpt-4o-mini';
        }
        
        // Migrate Gemini models to gemini-2.5-flash
        if (parsedKeys.gemini_model && !['gemini-2.5-flash', 'gemini-flash-latest'].includes(parsedKeys.gemini_model)) {
          migratedKeys.gemini_model = 'gemini-2.5-flash';
        }
        
        // Save migrated keys back to localStorage if changes were made
        if (JSON.stringify(parsedKeys) !== JSON.stringify(migratedKeys)) {
          localStorage.setItem('edubot_api_keys', JSON.stringify(migratedKeys));
        }
        
        setApiKeys(prev => ({ ...prev, ...migratedKeys }));
      } catch (e) {
        console.error('Failed to parse saved API keys');
      }
    }
    
    loadSettings();
  }, [user, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    setSuccess('');

    try {
      const token = localStorage.getItem('token');
      if (!token) {
        router.push('/login');
        return;
      }

      const response = await fetch(`${API_BASE}/settings/`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(formData),
      });

      if (response.ok) {
        const updatedSettings = await response.json();
        setSettings(updatedSettings);
        setSuccess('User settings saved successfully!');
        
        // Reload provider settings to get updated available providers
        const providerResponse = await fetch(`${API_BASE}/settings/provider`, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });
        if (providerResponse.ok) {
          const providerData = await providerResponse.json();
          setProviderSettings(providerData);
        }
        
        // Redirect to chat page after 1 second
        setTimeout(() => {
          router.push('/chat');
        }, 1000);
      } else if (response.status === 403) {
        setError('Access denied. Admin privileges with @pvpsiddhartha.ac.in domain required.');
      } else {
        const errorData = await response.json();
        setError(errorData.detail || 'Failed to update settings');
      }
    } catch (err) {
      setError('An error occurred while saving settings');
      console.error(err);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className={styles.container}>
        <div className={styles.loading}>Loading settings...</div>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      {/* Navbar */}
      <nav className={styles.navbar}>
        <div className={styles.navBrand}>
          <span className={styles.navLogo}>⚙️</span>
          <h1 className={styles.navTitle}>Settings</h1>
        </div>
        <div className={styles.navActions}>
          <button
            type="button"
            onClick={() => router.push('/chat')}
            className={styles.backButton}
          >
            ← Back to Chat
          </button>
        </div>
      </nav>

      {/* Main Content */}
      <div className={styles.content}>
        {error && <div className={styles.error}>{error}</div>}
        {success && <div className={styles.success}>{success}</div>}

        {/* Tab Navigation */}
        <div className={styles.tabNav}>
          {hasUploadAccess && (
            <button
              type="button"
              className={`${styles.tabButton} ${activeTab === 'upload' ? styles.tabButtonActive : ''}`}
              onClick={() => setActiveTab('upload')}
            >
              <span className={styles.tabIcon}>📁</span>
              Upload Documents
            </button>
          )}
          {hasUploadAccess && (
            <button
              type="button"
              className={`${styles.tabButton} ${activeTab === 'kb' ? styles.tabButtonActive : ''}`}
              onClick={() => setActiveTab('kb')}
            >
              <span className={styles.tabIcon}>📂</span>
              Knowledge Base
            </button>
          )}
          {hasUploadAccess && (
            <button
              type="button"
              className={`${styles.tabButton} ${activeTab === 'scraper' ? styles.tabButtonActive : ''}`}
              onClick={() => setActiveTab('scraper')}
            >
              <span className={styles.tabIcon}>🌐</span>
              Web Scraper
            </button>
          )}
          <button
            type="button"
            className={`${styles.tabButton} ${activeTab === 'model' ? styles.tabButtonActive : ''}`}
            onClick={() => setActiveTab('model')}
          >
            <span className={styles.tabIcon}>🤖</span>
            AI Model
          </button>
          {canManageFeedback && (
            <button
              type="button"
              className={`${styles.tabButton} ${activeTab === 'feedback' ? styles.tabButtonActive : ''}`}
              onClick={() => setActiveTab('feedback')}
            >
              <span className={styles.tabIcon}>📊</span>
              Feedback
            </button>
          )}
          {canManageIntegrations && (
            <button
              type="button"
              className={`${styles.tabButton} ${activeTab === 'integrations' ? styles.tabButtonActive : ''}`}
              onClick={() => setActiveTab('integrations')}
            >
              <span className={styles.tabIcon}>🔌</span>
              Integrations
            </button>
          )}
          {canManageAccess && (
            <button
              type="button"
              className={`${styles.tabButton} ${activeTab === 'access' ? styles.tabButtonActive : ''}`}
              onClick={() => setActiveTab('access')}
            >
              <span className={styles.tabIcon}>🔐</span>
              Access
            </button>
          )}
        </div>

        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={styles.tabContent}>
            {activeTab === 'upload' && hasUploadAccess && <UploadSection />}
            {activeTab === 'kb' && hasUploadAccess && <KnowledgeBase />}
            {activeTab === 'scraper' && hasUploadAccess && <WebScraper />}
            {activeTab === 'model' && (
              <ModelSection
                formData={formData}
                setFormData={setFormData}
                apiKeys={apiKeys}
                setApiKeys={setApiKeys}
                providerDefaults={providerDefaults}
              />
            )}
            {activeTab === 'feedback' && canManageFeedback && <FeedbackSection />}
            {activeTab === 'integrations' && canManageIntegrations && <IntegrationsSection />}
            {activeTab === 'access' && canManageAccess && <AccessSection />}
          </div>

          {/* Last Updated Info - Only show on model tab */}
          {activeTab === 'model' && settings && (
            <div className={styles.info}>
              Last updated: {new Date(settings.updated_at).toLocaleString()}
            </div>
          )}

          {/* Action Buttons - Only show on model tab */}
          {activeTab === 'model' && (
            <div className={styles.actions}>
              <button
                type="button"
                onClick={() => router.push('/chat')}
                className={styles.cancelButton}
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={saving}
                className={styles.saveButton}
              >
                {saving ? 'Saving...' : 'Save Settings'}
              </button>
            </div>
          )}
        </form>
      </div>
    </div>
  );
}
