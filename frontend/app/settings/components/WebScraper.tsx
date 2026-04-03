'use client';

import { useState, useEffect, useCallback } from 'react';
import styles from '../settings.module.css';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000/api';

interface ScraperRun {
  id: string;
  started_at: string;
  finished_at: string | null;
  status: string;
  pages_attempted: number;
  pages_succeeded: number;
  pages_failed: number;
  chunks_indexed: number;
  documents_created: number;
  errors: string[];
}

export default function WebScraper() {
  const [urls, setUrls] = useState<string[]>([]);
  const [newUrl, setNewUrl] = useState('');
  const [runs, setRuns] = useState<ScraperRun[]>([]);
  const [scraping, setScraping] = useState(false);
  const [loadingConfig, setLoadingConfig] = useState(true);
  const [loadingRuns, setLoadingRuns] = useState(true);
  const [expandedRun, setExpandedRun] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<{
    show: boolean;
    success: boolean;
    message: string;
  }>({ show: false, success: false, message: '' });

  const getToken = () => localStorage.getItem('token');

  const showStatus = (success: boolean, message: string) => {
    setStatusMessage({ show: true, success, message });
    setTimeout(() => setStatusMessage({ show: false, success: false, message: '' }), 4000);
  };

  const fetchConfig = useCallback(async () => {
    try {
      const token = getToken();
      if (!token) return;
      const res = await fetch(`${API_BASE}/settings/scraper/config`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setUrls(data.urls || []);
      }
    } catch (e) {
      console.error('Failed to fetch scraper config:', e);
    } finally {
      setLoadingConfig(false);
    }
  }, []);

  const fetchRuns = useCallback(async () => {
    try {
      const token = getToken();
      if (!token) return;
      const res = await fetch(`${API_BASE}/settings/scraper/status`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        setRuns(await res.json());
      }
    } catch (e) {
      console.error('Failed to fetch scraper runs:', e);
    } finally {
      setLoadingRuns(false);
    }
  }, []);

  useEffect(() => {
    fetchConfig();
    fetchRuns();
  }, [fetchConfig, fetchRuns]);

  const addUrl = async () => {
    const url = newUrl.trim();
    if (!url || !url.startsWith('http')) {
      showStatus(false, 'Please enter a valid URL starting with http:// or https://');
      return;
    }
    try {
      const token = getToken();
      const res = await fetch(`${API_BASE}/settings/scraper/config/add`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ url }),
      });
      if (res.ok) {
        const data = await res.json();
        setUrls(data.urls);
        setNewUrl('');
        showStatus(true, 'URL added');
      } else {
        const err = await res.json();
        showStatus(false, err.detail || 'Failed to add URL');
      }
    } catch (e) {
      showStatus(false, 'Failed to add URL');
    }
  };

  const removeUrl = async (url: string) => {
    try {
      const token = getToken();
      const res = await fetch(`${API_BASE}/settings/scraper/config/remove`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ url }),
      });
      if (res.ok) {
        const data = await res.json();
        setUrls(data.urls);
        showStatus(true, 'URL removed');
      } else {
        const err = await res.json();
        showStatus(false, err.detail || 'Failed to remove URL');
      }
    } catch (e) {
      showStatus(false, 'Failed to remove URL');
    }
  };

  const triggerScrape = async () => {
    if (scraping) return;
    setScraping(true);
    try {
      const token = getToken();
      const res = await fetch(`${API_BASE}/settings/scraper/scrape`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const run: ScraperRun = await res.json();
        showStatus(true,
          `Scrape complete — ${run.pages_succeeded}/${run.pages_attempted} pages, ${run.chunks_indexed} chunks indexed`
        );
        fetchRuns();
        // Notify KnowledgeBase to refresh
        window.dispatchEvent(new Event('kb-files-updated'));
      } else {
        const err = await res.json();
        showStatus(false, err.detail || 'Scrape failed');
      }
    } catch (e) {
      showStatus(false, e instanceof Error ? e.message : 'Scrape failed');
    } finally {
      setScraping(false);
    }
  };

  const formatDate = (iso: string) =>
    new Date(iso).toLocaleString('en-US', {
      month: 'short', day: 'numeric', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed': return '✅';
      case 'failed': return '❌';
      case 'running': return '⏳';
      default: return '❓';
    }
  };

  const getDomain = (url: string) => {
    try { return new URL(url).hostname; } catch { return url; }
  };

  const getPath = (url: string) => {
    try {
      const p = new URL(url).pathname;
      return p === '/' ? '/ (home)' : p;
    } catch { return url; }
  };

  return (
    <div className={styles.scraperContainer}>
      {/* Header */}
      <div className={styles.scraperHeader}>
        <div>
          <h3>🌐 Web Scraper</h3>
          <p className={styles.scraperSubtitle}>
            Scrape official college website pages into the knowledge base
          </p>
        </div>
        <button
          className={`${styles.scraperBtn} ${styles.scraperBtnPrimary}`}
          onClick={triggerScrape}
          disabled={scraping || urls.length === 0}
        >
          {scraping ? (
            <><span className={styles.scraperSpinner} /> Scraping...</>
          ) : (
            <>🚀 Scrape Now</>
          )}
        </button>
      </div>

      {/* Status message */}
      {statusMessage.show && (
        <div className={`${styles.kbStatus} ${statusMessage.success ? styles.kbStatusSuccess : styles.kbStatusError}`}>
          {statusMessage.success ? '✓' : '✗'} {statusMessage.message}
        </div>
      )}

      {/* URL List */}
      <div className={styles.scraperSection}>
        <h4 className={styles.scraperSectionTitle}>Target URLs ({urls.length})</h4>

        {/* Add URL */}
        <div className={styles.scraperAddRow}>
          <input
            type="url"
            placeholder="https://pvpsiddhartha.ac.in/"
            value={newUrl}
            onChange={(e) => setNewUrl(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && addUrl()}
            className={styles.scraperUrlInput}
          />
          <button
            className={`${styles.scraperBtn} ${styles.scraperBtnAdd}`}
            onClick={addUrl}
            disabled={!newUrl.trim()}
          >
            + Add
          </button>
        </div>

        {/* URL table */}
        <div className={styles.scraperUrlList}>
          {loadingConfig ? (
            <div className={styles.scraperEmpty}>Loading configuration...</div>
          ) : urls.length === 0 ? (
            <div className={styles.scraperEmpty}>No URLs configured. Add some above.</div>
          ) : (
            urls.map((url, i) => (
              <div key={i} className={styles.scraperUrlRow}>
                <span className={styles.scraperUrlIndex}>{i + 1}</span>
                <div className={styles.scraperUrlInfo}>
                  <span className={styles.scraperUrlDomain}>{getDomain(url)}</span>
                  <span className={styles.scraperUrlPath}>{getPath(url)}</span>
                </div>
                <button
                  className={styles.scraperUrlRemove}
                  onClick={() => removeUrl(url)}
                  title="Remove URL"
                >
                  ✕
                </button>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Scrape History */}
      <div className={styles.scraperSection}>
        <h4 className={styles.scraperSectionTitle}>Scrape History</h4>
        <div className={styles.scraperHistory}>
          {loadingRuns ? (
            <div className={styles.scraperEmpty}>Loading history...</div>
          ) : runs.length === 0 ? (
            <div className={styles.scraperEmpty}>No scrapes yet. Click "Scrape Now" to begin.</div>
          ) : (
            runs.map((run) => {
              const isExpanded = expandedRun === run.id;
              return (
                <div key={run.id} className={styles.scraperRunCard}>
                  <div
                    className={styles.scraperRunHeader}
                    onClick={() => setExpandedRun(isExpanded ? null : run.id)}
                  >
                    <span className={styles.scraperRunStatus}>
                      {getStatusIcon(run.status)}
                    </span>
                    <div className={styles.scraperRunMeta}>
                      <span className={styles.scraperRunDate}>
                        {formatDate(run.started_at)}
                      </span>
                      <span className={styles.scraperRunStats}>
                        {run.pages_succeeded}/{run.pages_attempted} pages
                        · {run.chunks_indexed} chunks
                        · {run.documents_created} new docs
                      </span>
                    </div>
                    <span className={styles.scraperRunChevron}>
                      {isExpanded ? '▴' : '▾'}
                    </span>
                  </div>

                  {isExpanded && run.errors.length > 0 && (
                    <div className={styles.scraperRunErrors}>
                      <strong>Issues:</strong>
                      <ul>
                        {run.errors.map((err, i) => (
                          <li key={i}>{err}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
