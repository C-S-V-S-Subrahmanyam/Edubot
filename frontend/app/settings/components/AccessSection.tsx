'use client';

import { useEffect, useMemo, useState } from 'react';
import styles from '../settings.module.css';
import { apiClient } from '@/lib/api';

type ManagedUser = {
  id: string;
  email: string;
  username: string;
  is_admin: boolean;
  permissions: string[];
  created_at: string;
};

export default function AccessSection() {
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [availablePermissions, setAvailablePermissions] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const [permissionCatalog, userRows] = await Promise.all([
        apiClient.getPermissionCatalog(),
        apiClient.getUsersForPermissions(100, 0),
      ]);
      setAvailablePermissions(permissionCatalog.permissions || []);
      setUsers(userRows || []);
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

  const nonAdminUsers = useMemo(() => users.filter((u) => !u.is_admin), [users]);

  const togglePermission = async (userId: string, current: string[], permission: string) => {
    const next = current.includes(permission)
      ? current.filter((p) => p !== permission)
      : [...current, permission];

    try {
      const updated = await apiClient.updateUserPermissions(userId, next);
      setUsers((prev) => prev.map((u) => (u.id === userId ? { ...u, permissions: updated.permissions } : u)));
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setError(message);
    }
  };

  if (loading) return <div className={styles.loading}>Loading access controls...</div>;

  return (
    <div className={styles.sectionContent}>
      <div className={styles.sectionIntro}>
        <h3>Access Management</h3>
        <p>Grant feature permissions to non-admin users.</p>
      </div>

      {error ? <div className={styles.error}>{error}</div> : null}

      <div className={styles.uploadedFilesList}>
        <h4>Permission Keys</h4>
        {availablePermissions.length === 0 ? (
          <p className={styles.uploadHint}>No permissions available.</p>
        ) : (
          <div className={styles.filesList}>
            {availablePermissions.map((perm) => (
              <div key={perm} className={styles.fileItem}>
                <div className={styles.fileInfo}>
                  <div className={styles.fileDetails}>
                    <p className={styles.fileName}>{perm}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className={styles.uploadedFilesList}>
        <h4>User Permissions</h4>
        {nonAdminUsers.length === 0 ? (
          <p className={styles.uploadHint}>No non-admin users found.</p>
        ) : (
          <div className={styles.filesList}>
            {nonAdminUsers.map((u) => (
              <div key={u.id} className={styles.fileItem}>
                <div className={styles.fileInfo}>
                  <div className={styles.fileDetails}>
                    <p className={styles.fileName}>{u.username}</p>
                    <p className={styles.fileSize}>{u.email}</p>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                  {availablePermissions.map((perm) => {
                    const enabled = (u.permissions || []).includes(perm);
                    return (
                      <button
                        key={`${u.id}-${perm}`}
                        type="button"
                        className={enabled ? styles.uploadButton : styles.backButton}
                        onClick={() => togglePermission(u.id, u.permissions || [], perm)}
                      >
                        {enabled ? `Revoke ${perm}` : `Grant ${perm}`}
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
