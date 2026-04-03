'use client';

import { useState, FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAuth } from '@/lib/auth-context';
import styles from '../auth.module.css';

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const router = useRouter();

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await login(email, password);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={styles.container}>
      <div className={styles.card}>
        <h1 className={styles.title}>🎓 EduBot+ Login</h1>
        <p className={styles.subtitle}>Welcome back! Sign in to continue</p>

        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={styles.inputGroup}>
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="your.email@university.edu"
              required
              disabled={loading}
              suppressHydrationWarning
            />
          </div>

          <div className={styles.inputGroup}>
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter your password"
              required
              disabled={loading}
              suppressHydrationWarning
            />
          </div>

          {error && <div className={styles.error}>{error}</div>}

          <button 
            type="submit" 
            className={styles.button} 
            disabled={loading}
            suppressHydrationWarning
          >
            {loading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>

        <p className={styles.footer} style={{ marginTop: '12px' }}>
          <Link href="/forgot-password" className={styles.link}>
            Forgot Password?
          </Link>
        </p>

        <p className={styles.footer}>
          Don't have an account?{' '}
          <Link href="/register" className={styles.link}>
            Register here
          </Link>
        </p>
        
        <p className={styles.footer} style={{ marginTop: '12px', paddingTop: '12px', borderTop: '1px solid var(--border-light)' }}>
          Or{' '}
          <Link href="/chat" className={styles.link}>
            Go to Chat
          </Link>
          {' '}without signing in
        </p>
      </div>
    </div>
  );
}
