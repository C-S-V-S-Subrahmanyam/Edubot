'use client';

import { useState, FormEvent, useRef, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { apiClient } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';
import styles from '../auth.module.css';

type Step = 'form' | 'otp';

export default function RegisterPage() {
  const { loginWithToken } = useAuth();
  const [step, setStep] = useState<Step>('form');
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [otp, setOtp] = useState(['', '', '', '', '', '']);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [loading, setLoading] = useState(false);
  const [resendTimer, setResendTimer] = useState(0);
  const router = useRouter();
  const otpInputRefs = useRef<(HTMLInputElement | null)[]>([]);

  // Countdown timer for resend OTP
  useEffect(() => {
    if (resendTimer > 0) {
      const timer = setTimeout(() => setResendTimer(resendTimer - 1), 1000);
      return () => clearTimeout(timer);
    }
  }, [resendTimer]);

  const sendOTP = async () => {
    try {
      const response = await apiClient.sendOTP({ email, username, password });
      
      if (!response.success) {
        throw new Error(response.message || 'Failed to send verification code');
      }

      return true;
    } catch (err) {
      throw err;
    }
  };

  const handleFormSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess('');

    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }

    if (password.length < 6) {
      setError('Password must be at least 6 characters');
      return;
    }

    setLoading(true);

    try {
      await sendOTP();
      setStep('otp');
      setResendTimer(60); // 60 seconds cooldown
      setSuccess('Verification code sent to your email!');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send verification code');
    } finally {
      setLoading(false);
    }
  };

  const handleOTPChange = (index: number, value: string) => {
    if (!/^\d*$/.test(value)) return; // Only allow digits

    const newOtp = [...otp];
    newOtp[index] = value.slice(-1); // Only keep last digit
    setOtp(newOtp);

    // Auto-focus next input
    if (value && index < 5) {
      otpInputRefs.current[index + 1]?.focus();
    }
  };

  const handleOTPKeyDown = (index: number, e: React.KeyboardEvent) => {
    if (e.key === 'Backspace' && !otp[index] && index > 0) {
      otpInputRefs.current[index - 1]?.focus();
    }
  };

  const handleOTPPaste = (e: React.ClipboardEvent) => {
    e.preventDefault();
    const pastedData = e.clipboardData.getData('text').slice(0, 6);
    if (/^\d+$/.test(pastedData)) {
      const newOtp = pastedData.split('').concat(Array(6).fill('')).slice(0, 6);
      setOtp(newOtp);
      otpInputRefs.current[Math.min(pastedData.length, 5)]?.focus();
    }
  };

  const handleVerifyOTP = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess('');

    const otpString = otp.join('');
    if (otpString.length !== 6) {
      setError('Please enter the complete 6-digit code');
      return;
    }

    setLoading(true);

    try {
      // Verify OTP and register user via backend
      const response = await apiClient.verifyOTP({ email, otp: otpString });
      
      // Store token and user data via auth context
      const userData = { 
        email: response.user.email, 
        username: response.user.username,
        is_admin: response.user.is_admin 
      };
      loginWithToken(response.access_token, userData);
      
      // Redirect to chat
      router.push('/chat');

    } catch (err) {
      setError(err instanceof Error ? err.message : 'Verification failed');
    } finally {
      setLoading(false);
    }
  };

  const handleResendOTP = async () => {
    if (resendTimer > 0) return;
    
    setLoading(true);
    setError('');
    setSuccess('');

    try {
      await sendOTP();
      setResendTimer(60);
      setOtp(['', '', '', '', '', '']);
      setSuccess('New verification code sent!');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to resend code');
    } finally {
      setLoading(false);
    }
  };

  // OTP Verification Step
  if (step === 'otp') {
    return (
      <div className={styles.container}>
        <div className={styles.card}>
          <h1 className={styles.title}>🔐 Verify Email</h1>
          <p className={styles.subtitle}>
            Enter the 6-digit code sent to<br />
            <strong style={{ color: 'var(--text-primary)' }}>{email}</strong>
          </p>

          <form onSubmit={handleVerifyOTP} className={styles.form}>
            <div className={styles.otpContainer}>
              {otp.map((digit, index) => (
                <input
                  key={index}
                  ref={(el) => { otpInputRefs.current[index] = el; }}
                  type="text"
                  inputMode="numeric"
                  maxLength={1}
                  value={digit}
                  onChange={(e) => handleOTPChange(index, e.target.value)}
                  onKeyDown={(e) => handleOTPKeyDown(index, e)}
                  onPaste={handleOTPPaste}
                  className={styles.otpInput}
                  disabled={loading}
                  autoFocus={index === 0}
                />
              ))}
            </div>

            {error && <div className={styles.error}>{error}</div>}
            {success && <div className={styles.success}>{success}</div>}

            <button 
              type="submit" 
              className={styles.button} 
              disabled={loading || otp.join('').length !== 6}
              suppressHydrationWarning
            >
              {loading ? 'Verifying...' : 'Verify & Create Account'}
            </button>

            <div className={styles.resendContainer}>
              <p className={styles.resendText}>
                Didn&apos;t receive the code?{' '}
                {resendTimer > 0 ? (
                  <span className={styles.timerText}>Resend in {resendTimer}s</span>
                ) : (
                  <button
                    type="button"
                    onClick={handleResendOTP}
                    className={styles.resendButton}
                    disabled={loading}
                  >
                    Resend Code
                  </button>
                )}
              </p>
            </div>

            <button
              type="button"
              onClick={() => {
                setStep('form');
                setOtp(['', '', '', '', '', '']);
                setError('');
                setSuccess('');
              }}
              className={styles.backButton}
              disabled={loading}
            >
              ← Back to Registration
            </button>
          </form>
        </div>
      </div>
    );
  }

  // Registration Form Step
  return (
    <div className={styles.container}>
      <div className={styles.card}>
        <h1 className={styles.title}>🎓 Create Account</h1>
        <p className={styles.subtitle}>Join EduBot+ to get started</p>

        <form onSubmit={handleFormSubmit} className={styles.form}>
          <div className={styles.inputGroup}>
            <label htmlFor="username">Username</label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="johndoe"
              required
              disabled={loading}
              suppressHydrationWarning
            />
          </div>

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
              placeholder="At least 6 characters"
              required
              disabled={loading}
              suppressHydrationWarning
            />
          </div>

          <div className={styles.inputGroup}>
            <label htmlFor="confirmPassword">Confirm Password</label>
            <input
              id="confirmPassword"
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="Re-enter password"
              required
              disabled={loading}
              suppressHydrationWarning
            />
          </div>

          {error && <div className={styles.error}>{error}</div>}
          {success && <div className={styles.success}>{success}</div>}

          <button 
            type="submit" 
            className={styles.button} 
            disabled={loading}
            suppressHydrationWarning
          >
            {loading ? 'Sending verification code...' : 'Continue →'}
          </button>
        </form>

        <p className={styles.footer}>
          Already have an account?{' '}
          <Link href="/login" className={styles.link}>
            Sign in here
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
