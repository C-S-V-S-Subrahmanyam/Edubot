'use client';

import { useState, useEffect, useCallback } from 'react';
import styles from '../settings.module.css';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000/api';

interface UploadedFile {
  id?: string;
  filename: string;
  category: string;
  size: number;
  modified?: number;
  upload_date?: string;
  expiry_date?: string | null;
  is_expired?: boolean;
}

export default function KnowledgeBase() {
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [deletingFile, setDeletingFile] = useState<string | null>(null);
  const [editingExpiry, setEditingExpiry] = useState<string | null>(null);
  const [expiryInput, setExpiryInput] = useState('');
  const [savingExpiry, setSavingExpiry] = useState<string | null>(null);
  const [expandedFile, setExpandedFile] = useState<string | null>(null);
  const [fileContents, setFileContents] = useState<Record<string, { content: string; truncated: boolean }>>({});
  const [loadingContent, setLoadingContent] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<{
    show: boolean;
    success: boolean;
    message: string;
  }>({ show: false, success: false, message: '' });

  const fetchFiles = useCallback(async () => {
    try {
      const token = localStorage.getItem('token');
      if (!token) return;

      const response = await fetch(`${API_BASE}/settings/files`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });

      if (response.ok) {
        const data = await response.json();
        const sorted = (data.files || []).sort(
          (a: UploadedFile, b: UploadedFile) => {
            // Sort expired first, then by upload_date descending
            if (a.is_expired && !b.is_expired) return -1;
            if (!a.is_expired && b.is_expired) return 1;
            const aTime = a.upload_date ? new Date(a.upload_date).getTime() : (a.modified || 0) * 1000;
            const bTime = b.upload_date ? new Date(b.upload_date).getTime() : (b.modified || 0) * 1000;
            return bTime - aTime;
          }
        );
        setFiles(sorted);
      }
    } catch (error) {
      console.error('Failed to fetch files:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchFiles();
  }, [fetchFiles]);

  useEffect(() => {
    const handler = () => fetchFiles();
    window.addEventListener('kb-files-updated', handler);
    return () => window.removeEventListener('kb-files-updated', handler);
  }, [fetchFiles]);

  const deleteFile = async (category: string, filename: string) => {
    const key = `${category}/${filename}`;
    if (!confirm(`Delete "${filename}" from ${category}?`)) return;

    setDeletingFile(key);
    try {
      const token = localStorage.getItem('token');
      if (!token) throw new Error('Not authenticated');

      const response = await fetch(
        `${API_BASE}/settings/files/${encodeURIComponent(category)}/${encodeURIComponent(filename)}`,
        {
          method: 'DELETE',
          headers: { 'Authorization': `Bearer ${token}` },
        }
      );

      if (response.ok) {
        showStatus(true, `Deleted "${filename}"`);
        fetchFiles();
      } else {
        const error = await response.json();
        showStatus(false, error.detail || 'Delete failed');
      }
    } catch (error) {
      showStatus(false, error instanceof Error ? error.message : 'Delete failed');
    } finally {
      setDeletingFile(null);
    }
  };

  const handleSetExpiry = (file: UploadedFile) => {
    const fileKey = file.id || `${file.category}/${file.filename}`;
    if (editingExpiry === fileKey) {
      setEditingExpiry(null);
      return;
    }
    setEditingExpiry(fileKey);
    if (file.expiry_date) {
      setExpiryInput(file.expiry_date.split('T')[0]);
    } else {
      setExpiryInput('');
    }
  };

  const saveExpiry = async (file: UploadedFile) => {
    if (!file.id) {
      showStatus(false, 'Cannot set expiry on legacy files without DB record');
      return;
    }
    const fileKey = file.id;
    setSavingExpiry(fileKey);

    try {
      const token = localStorage.getItem('token');
      if (!token) throw new Error('Not authenticated');

      const payload = expiryInput
        ? { expiry_date: new Date(expiryInput + 'T23:59:59Z').toISOString() }
        : { expiry_date: null };

      const response = await fetch(`${API_BASE}/settings/files/${file.id}/expiry`, {
        method: 'PATCH',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });

      if (response.ok) {
        showStatus(true, expiryInput
          ? `Expiry set to ${expiryInput} for "${file.filename}"`
          : `Expiry removed for "${file.filename}"`
        );
        setEditingExpiry(null);
        fetchFiles();
      } else {
        const error = await response.json();
        showStatus(false, error.detail || 'Failed to update expiry');
      }
    } catch (error) {
      showStatus(false, error instanceof Error ? error.message : 'Failed to update expiry');
    } finally {
      setSavingExpiry(null);
    }
  };

  const removeExpiry = async (file: UploadedFile) => {
    if (!file.id) return;
    setSavingExpiry(file.id);
    try {
      const token = localStorage.getItem('token');
      if (!token) throw new Error('Not authenticated');

      const response = await fetch(`${API_BASE}/settings/files/${file.id}/expiry`, {
        method: 'PATCH',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ expiry_date: null }),
      });

      if (response.ok) {
        showStatus(true, `Expiry removed for "${file.filename}"`);
        setEditingExpiry(null);
        fetchFiles();
      } else {
        const error = await response.json();
        showStatus(false, error.detail || 'Failed to remove expiry');
      }
    } catch (error) {
      showStatus(false, error instanceof Error ? error.message : 'Failed');
    } finally {
      setSavingExpiry(null);
    }
  };

  const toggleFileContent = async (file: UploadedFile) => {
    const key = `${file.category}/${file.filename}`;
    if (expandedFile === key) {
      setExpandedFile(null);
      return;
    }
    setExpandedFile(key);

    // Already fetched
    if (fileContents[key]) return;

    setLoadingContent(key);
    try {
      const token = localStorage.getItem('token');
      if (!token) return;

      const response = await fetch(
        `${API_BASE}/settings/files/${encodeURIComponent(file.category)}/${encodeURIComponent(file.filename)}/content`,
        { headers: { 'Authorization': `Bearer ${token}` } }
      );

      if (response.ok) {
        const data = await response.json();
        setFileContents(prev => ({ ...prev, [key]: data }));
      } else {
        setFileContents(prev => ({ ...prev, [key]: { content: 'Failed to load content.', truncated: false } }));
      }
    } catch {
      setFileContents(prev => ({ ...prev, [key]: { content: 'Failed to load content.', truncated: false } }));
    } finally {
      setLoadingContent(null);
    }
  };

  const showStatus = (success: boolean, message: string) => {
    setStatusMessage({ show: true, success, message });
    setTimeout(() => setStatusMessage({ show: false, success: false, message: '' }), 3000);
  };

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
  };

  const formatDate = (timestamp: number | undefined, isoDate?: string) => {
    if (isoDate) {
      return new Date(isoDate).toLocaleDateString('en-US', {
        month: 'short', day: 'numeric', year: 'numeric',
      });
    }
    if (timestamp) {
      return new Date(timestamp * 1000).toLocaleDateString('en-US', {
        month: 'short', day: 'numeric', year: 'numeric',
      });
    }
    return '—';
  };

  const getExpiryLabel = (file: UploadedFile) => {
    if (!file.expiry_date) return null;
    const exp = new Date(file.expiry_date);
    const now = new Date();
    const diff = exp.getTime() - now.getTime();
    const days = Math.ceil(diff / (1000 * 60 * 60 * 24));

    if (days < 0) return { text: `Expired ${Math.abs(days)}d ago`, status: 'expired' as const };
    if (days <= 7) return { text: `Expires in ${days}d`, status: 'expiring-soon' as const };
    if (days <= 30) return { text: `Expires in ${days}d`, status: 'expiring' as const };
    return { text: `Expires ${exp.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}`, status: 'active' as const };
  };

  const getCategoryIcon = (category: string) => {
    switch (category) {
      case 'Academic': return '📅';
      case 'Administrative': return '🏛️';
      case 'Educational': return '📖';
      default: return '📄';
    }
  };

  const getCategoryColor = (category: string) => {
    switch (category) {
      case 'Academic': return styles.categoryAcademic;
      case 'Administrative': return styles.categoryAdministrative;
      case 'Educational': return styles.categoryEducational;
      default: return '';
    }
  };

  const filteredFiles = files.filter(f =>
    f.filename.toLowerCase().includes(searchQuery.toLowerCase()) ||
    f.category.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const expiredCount = files.filter(f => f.is_expired).length;

  return (
    <div className={styles.kbContainer}>
      <div className={styles.kbHeader}>
        <h3>📂 Knowledge Base</h3>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span className={styles.kbCount}>{files.length} file{files.length !== 1 ? 's' : ''}</span>
          {expiredCount > 0 && (
            <span className={styles.kbExpiredBadge}>
              ⚠️ {expiredCount} expired
            </span>
          )}
        </div>
      </div>

      {/* Search Bar */}
      <div className={styles.kbSearchWrapper}>
        <span className={styles.kbSearchIcon}>🔍</span>
        <input
          type="text"
          placeholder="Search files..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className={styles.kbSearchInput}
        />
        {searchQuery && (
          <button
            type="button"
            className={styles.kbSearchClear}
            onClick={() => setSearchQuery('')}
          >
            ✕
          </button>
        )}
      </div>

      {/* Status Message */}
      {statusMessage.show && (
        <div className={`${styles.kbStatus} ${statusMessage.success ? styles.kbStatusSuccess : styles.kbStatusError}`}>
          {statusMessage.success ? '✓' : '✗'} {statusMessage.message}
        </div>
      )}

      {/* File List */}
      <div className={styles.kbFileList}>
        {loading ? (
          <div className={styles.kbEmpty}>Loading files...</div>
        ) : filteredFiles.length === 0 ? (
          <div className={styles.kbEmpty}>
            {searchQuery ? `No files matching "${searchQuery}"` : 'No files uploaded yet'}
          </div>
        ) : (
          filteredFiles.map((file, index) => {
            const key = `${file.category}/${file.filename}`;
            const fileKey = file.id || key;
            const expiryLabel = getExpiryLabel(file);
            const isEditing = editingExpiry === fileKey;

            return (
              <div
                key={file.id || index}
                className={`${styles.kbFileCard} ${file.is_expired ? styles.kbFileExpired : ''}`}
              >
                <div
                  className={styles.kbFileItem}
                  onClick={() => toggleFileContent(file)}
                  style={{ cursor: 'pointer' }}
                >
                  <div className={styles.kbFileIcon}>
                    {getCategoryIcon(file.category)}
                  </div>
                  <div className={styles.kbFileDetails}>
                    <p className={styles.kbFileName} title={file.filename}>
                      {file.filename}
                    </p>
                    <div className={styles.kbFileMeta}>
                      <span className={`${styles.kbCategoryBadge} ${getCategoryColor(file.category)}`}>
                        {file.category}
                      </span>
                      <span className={styles.kbFileSizeDot}>·</span>
                      <span>{formatFileSize(file.size)}</span>
                      <span className={styles.kbFileSizeDot}>·</span>
                      <span>{formatDate(file.modified, file.upload_date)}</span>
                      {expiryLabel && (
                        <>
                          <span className={styles.kbFileSizeDot}>·</span>
                          <span className={`${styles.kbExpiryTag} ${styles[`kbExpiry_${expiryLabel.status}`]}`}>
                            ⏰ {expiryLabel.text}
                          </span>
                        </>
                      )}
                    </div>

                    {/* Inline Expiry Editor */}
                    {isEditing && (
                      <div className={styles.kbExpiryEditor} onClick={(e) => e.stopPropagation()}>
                        <input
                          type="date"
                          value={expiryInput}
                          onChange={(e) => setExpiryInput(e.target.value)}
                          className={styles.kbExpiryInput}
                          min={new Date().toISOString().split('T')[0]}
                        />
                        <button
                          onClick={() => saveExpiry(file)}
                          disabled={savingExpiry === fileKey}
                          className={styles.kbExpirySave}
                          title="Save expiry"
                        >
                          {savingExpiry === fileKey ? '⏳' : '✓'}
                        </button>
                        {file.expiry_date && (
                          <button
                            onClick={() => removeExpiry(file)}
                            disabled={savingExpiry === fileKey}
                            className={styles.kbExpiryRemove}
                            title="Remove expiry"
                          >
                            ✕
                          </button>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Expiry toggle button */}
                  {file.id && (
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); handleSetExpiry(file); }}
                      className={`${styles.kbExpiryBtn} ${isEditing ? styles.kbExpiryBtnActive : ''}`}
                      title={isEditing ? 'Close expiry editor' : 'Set expiry date'}
                    >
                      ⏰
                    </button>
                  )}

                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); deleteFile(file.category, file.filename); }}
                    className={styles.kbDeleteBtn}
                    title="Delete file"
                    disabled={deletingFile === key}
                  >
                    {deletingFile === key ? '⏳' : '🗑️'}
                  </button>

                  <span className={styles.kbChevron}>
                    {expandedFile === key ? '▴' : '▾'}
                  </span>
                </div>

                {/* Expanded File Content */}
                {expandedFile === key && (
                  <div className={styles.kbFileContent}>
                    {loadingContent === key ? (
                      <div className={styles.kbContentLoading}>Loading content...</div>
                    ) : fileContents[key] ? (
                      <>
                        <pre className={styles.kbContentPre}>{fileContents[key].content}</pre>
                        {fileContents[key].truncated && (
                          <div className={styles.kbContentTruncated}>
                            ⚠️ Content truncated (file too large to display in full)
                          </div>
                        )}
                      </>
                    ) : (
                      <div className={styles.kbContentLoading}>No content available.</div>
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Summary footer */}
      {files.length > 0 && (
        <div className={styles.kbFooter}>
          {filteredFiles.length !== files.length && (
            <span>Showing {filteredFiles.length} of {files.length}</span>
          )}
        </div>
      )}
    </div>
  );
}
