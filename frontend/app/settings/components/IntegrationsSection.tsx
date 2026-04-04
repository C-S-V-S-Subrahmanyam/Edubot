'use client';

import { useEffect, useState } from 'react';
import styles from '../settings.module.css';
import { apiClient } from '@/lib/api';

type Integration = {
  id: string;
  service_name: string;
  auth_type: string;
  config: Record<string, unknown>;
  is_active: boolean;
  last_sync_status?: string;
  last_sync_error?: string;
  last_synced_at?: string;
  created_at: string;
};

export default function IntegrationsSection() {
  const [rows, setRows] = useState<Integration[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [serviceName, setServiceName] = useState('');
  const [authType, setAuthType] = useState('api_key');
  const [baseUrl, setBaseUrl] = useState('');

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await apiClient.getIntegrations(50, 0);
      setRows(data);
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleCreate = async () => {
    if (!serviceName.trim()) return;
    try {
      await apiClient.createIntegration({
        service_name: serviceName.trim(),
        auth_type: authType,
        config: baseUrl ? { base_url: baseUrl } : {},
        is_active: true,
      });
      setServiceName('');
      setBaseUrl('');
      await load();
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setError(message);
    }
  };

  const handleToggle = async (id: string, active: boolean) => {
    try {
      await apiClient.updateIntegration(id, { is_active: !active });
      setRows((prev) => prev.map((r) => (r.id === id ? { ...r, is_active: !active } : r)));
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setError(message);
    }
  };

  const handleDelete = async (id: string) => {
    if (!window.confirm('Delete this integration?')) return;
    try {
      await apiClient.deleteIntegration(id);
      setRows((prev) => prev.filter((r) => r.id !== id));
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setError(message);
    }
  };

  const handleTest = async (url: string | undefined) => {
    if (!url) return;
    try {
      const result = await apiClient.testIntegrationConnection(url);
      alert(result.success ? `Success (${result.status_code ?? 'n/a'})` : `Failed: ${result.message}`);
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setError(message);
    }
  };

  if (loading) return <div className={styles.loading}>Loading integrations...</div>;

  return (
    <div className={styles.sectionContent}>
      <div className={styles.sectionIntro}>
        <h3>Integrations</h3>
        <p>Configure external service connectors.</p>
      </div>

      {error ? <div className={styles.error}>{error}</div> : null}

      <div className={styles.uploadedFilesList}>
        <h4>Add Integration</h4>
        <div className={styles.filesList}>
          <input className={styles.input} value={serviceName} onChange={(e) => setServiceName(e.target.value)} placeholder="Service name" />
          <select className={styles.select} value={authType} onChange={(e) => setAuthType(e.target.value)}>
            <option value="api_key">API Key</option>
            <option value="oauth">OAuth</option>
            <option value="basic">Basic</option>
          </select>
          <input className={styles.input} value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="Base URL (optional)" />
          <button type="button" className={styles.uploadButton} onClick={handleCreate}>Create</button>
        </div>
      </div>

      <div className={styles.uploadedFilesList}>
        <h4>Configured Integrations</h4>
        {rows.length === 0 ? (
          <p className={styles.uploadHint}>No integrations configured.</p>
        ) : (
          <div className={styles.filesList}>
            {rows.map((row) => {
              const cfgBase = typeof row.config?.base_url === 'string' ? (row.config.base_url as string) : '';
              return (
                <div key={row.id} className={styles.fileItem}>
                  <div className={styles.fileInfo}>
                    <div className={styles.fileDetails}>
                      <p className={styles.fileName}>{row.service_name} ({row.auth_type})</p>
                      <p className={styles.fileSize}>Status: {row.is_active ? 'active' : 'inactive'}</p>
                      {cfgBase ? <p className={styles.fileSize}>Base URL: {cfgBase}</p> : null}
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    {cfgBase ? (
                      <button type="button" className={styles.backButton} onClick={() => handleTest(cfgBase)}>
                        Test
                      </button>
                    ) : null}
                    <button type="button" className={styles.uploadButton} onClick={() => handleToggle(row.id, row.is_active)}>
                      {row.is_active ? 'Deactivate' : 'Activate'}
                    </button>
                    <button type="button" className={styles.removeButton} onClick={() => handleDelete(row.id)}>
                      Delete
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
