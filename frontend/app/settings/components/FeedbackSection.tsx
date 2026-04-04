'use client';

import { useEffect, useState } from 'react';
import styles from '../settings.module.css';
import { apiClient } from '@/lib/api';

type FeedbackItem = {
  id: string;
  feedback_type: 'positive' | 'negative';
  user_message: string;
  bot_message: string;
  reason?: string;
  status: string;
  created_at: string;
};

type FeedbackStats = {
  total_feedback: number;
  positive_feedback: number;
  negative_feedback: number;
  pending_feedback: number;
};

export default function FeedbackSection() {
  const [stats, setStats] = useState<FeedbackStats | null>(null);
  const [items, setItems] = useState<FeedbackItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [goldenItems, setGoldenItems] = useState<Array<{
    id: string;
    source_type: string;
    original_query: string;
    golden_response: string;
    is_active: boolean;
    created_at: string;
  }>>([]);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError('');
      try {
        const [statsData, listData, goldenData] = await Promise.all([
          apiClient.getFeedbackStats(),
          apiClient.getFeedbackList(20, 0),
          apiClient.getGoldenExamples(10, 0),
        ]);
        setStats(statsData);
        setItems(listData);
        setGoldenItems(goldenData);
      } catch (e) {
        const message = e instanceof Error ? e.message : String(e);
        setError(message);
      } finally {
        setLoading(false);
      }
    };

    load();
  }, []);

  if (loading) {
    return <div className={styles.loading}>Loading feedback dashboard...</div>;
  }

  if (error) {
    return <div className={styles.error}>Failed to load feedback data: {error}</div>;
  }

  const handleStatus = async (id: string, status: 'reviewed' | 'dismissed') => {
    try {
      await apiClient.updateFeedbackStatus(id, status);
      setItems((prev) => prev.map((item) => (item.id === id ? { ...item, status } : item)));
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setError(message);
    }
  };

  const handleCreateGolden = async (item: FeedbackItem) => {
    const input = window.prompt('Enter ideal golden response:', item.bot_message);
    if (!input || !input.trim()) return;

    try {
      await apiClient.createGoldenExampleFromFeedback(item.id, input.trim());
      const refreshedGolden = await apiClient.getGoldenExamples(10, 0);
      setGoldenItems(refreshedGolden);
      setItems((prev) => prev.map((f) => (f.id === item.id ? { ...f, status: 'reviewed' } : f)));
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setError(message);
    }
  };

  const handleToggleGolden = async (id: string, current: boolean) => {
    try {
      await apiClient.updateGoldenExample(id, !current);
      setGoldenItems((prev) => prev.map((g) => (g.id === id ? { ...g, is_active: !current } : g)));
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setError(message);
    }
  };

  const handleDeleteGolden = async (id: string) => {
    const ok = window.confirm('Delete this golden example?');
    if (!ok) return;
    try {
      await apiClient.deleteGoldenExample(id);
      setGoldenItems((prev) => prev.filter((g) => g.id !== id));
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setError(message);
    }
  };

  return (
    <div className={styles.sectionContent}>
      <div className={styles.sectionIntro}>
        <h3>Feedback Dashboard</h3>
        <p>Review user feedback on assistant responses.</p>
      </div>

      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 12 }}>
          <div className={styles.uploadedFilesList}>
            <h4>Total</h4>
            <p>{stats.total_feedback}</p>
          </div>
          <div className={styles.uploadedFilesList}>
            <h4>Positive</h4>
            <p>{stats.positive_feedback}</p>
          </div>
          <div className={styles.uploadedFilesList}>
            <h4>Negative</h4>
            <p>{stats.negative_feedback}</p>
          </div>
          <div className={styles.uploadedFilesList}>
            <h4>Pending</h4>
            <p>{stats.pending_feedback}</p>
          </div>
        </div>
      )}

      <div className={styles.uploadedFilesList}>
        <h4>Recent Feedback</h4>
        {items.length === 0 ? (
          <p className={styles.uploadHint}>No feedback records yet.</p>
        ) : (
          <div className={styles.filesList}>
            {items.map((item) => (
              <div key={item.id} className={styles.fileItem}>
                <div className={styles.fileInfo}>
                  <div className={styles.fileDetails}>
                    <p className={styles.fileName}>
                      {item.feedback_type === 'positive' ? '👍 Positive' : '👎 Negative'} | {new Date(item.created_at).toLocaleString()}
                    </p>
                    <p className={styles.fileSize}>Q: {item.user_message.slice(0, 120)}</p>
                    <p className={styles.fileSize}>A: {item.bot_message.slice(0, 160)}</p>
                    <p className={styles.fileSize}>Status: {item.status}</p>
                    {item.reason ? <p className={styles.fileSize}>Reason: {item.reason}</p> : null}
                    {item.status === 'pending' ? (
                      <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
                        <button type="button" className={styles.uploadButton} onClick={() => handleStatus(item.id, 'reviewed')}>
                          Approve
                        </button>
                        <button type="button" className={styles.removeButton} onClick={() => handleStatus(item.id, 'dismissed')}>
                          Dismiss
                        </button>
                        <button type="button" className={styles.backButton} onClick={() => handleCreateGolden(item)}>
                          Create Golden
                        </button>
                      </div>
                    ) : null}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className={styles.uploadedFilesList}>
        <h4>Golden Examples</h4>
        {goldenItems.length === 0 ? (
          <p className={styles.uploadHint}>No golden examples yet.</p>
        ) : (
          <div className={styles.filesList}>
            {goldenItems.map((item) => (
              <div key={item.id} className={styles.fileItem}>
                <div className={styles.fileInfo}>
                  <div className={styles.fileDetails}>
                    <p className={styles.fileName}>
                      {item.source_type} | {new Date(item.created_at).toLocaleString()} | {item.is_active ? 'active' : 'inactive'}
                    </p>
                    <p className={styles.fileSize}>Q: {item.original_query.slice(0, 120)}</p>
                    <p className={styles.fileSize}>Golden: {item.golden_response.slice(0, 180)}</p>
                    <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
                      <button
                        type="button"
                        className={styles.uploadButton}
                        onClick={() => handleToggleGolden(item.id, item.is_active)}
                      >
                        {item.is_active ? 'Deactivate' : 'Activate'}
                      </button>
                      <button
                        type="button"
                        className={styles.removeButton}
                        onClick={() => handleDeleteGolden(item.id)}
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
