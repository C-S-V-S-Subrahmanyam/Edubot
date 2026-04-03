'use client';

import { useState, FormEvent, useRef, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { apiClient } from '@/lib/api';
import styles from '../auth.module.css';

type Step = 'email' | 'otp' | 'reset' | 'success';

export default function ForgotPasswordPage() {
  const [step, setStep] = useState<Step>('email');
  const [email, setEmail] = useState('');
  const [otp, setOtp] = useState(['', '', '', '', '', '']);
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
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

  const sendResetOTP = async () => {
    try {
      const response = await apiClient.forgotPassword({ email });
      if (!response.success) {
        throw new Error(response.message || 'Failed to send reset code');
      }
      return true;
    } catch (err) {
      throw err;
    }
  };

  const handleEmailSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await sendResetOTP();
      setStep('otp');
      setSuccess('A reset code has been sent to your email if an account exists.');
      setResendTimer(60);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send reset code');
    } finally {
      setLoading(false);
    }
  };

  const handleOtpChange = (index: number, value: string) => {
    if (value.length > 1) {
      // Handle paste
      const digits = value.replace(/\D/g, '').slice(0, 6);
      const newOtp = [...otp];
      for (let i = 0; i < digits.length && index + i < 6; i++) {
        newOtp[index + i] = digits[i];
      }
      setOtp(newOtp);
      const nextIndex = Math.min(index + digits.length, 5);
      otpInputRefs.current[nextIndex]?.focus();
      return;
    }

    if (value && !/^\d$/.test(value)) return;

    const newOtp = [...otp];
    newOtp[index] = value;
    setOtp(newOtp);

    if (value && index < 5) {
      otpInputRefs.current[index + 1]?.focus();
    }
  };

  const handleOtpKeyDown = (index: number, e: React.KeyboardEvent) => {
    if (e.key === 'Backspace' && !otp[index] && index > 0) {
      otpInputRefs.current[index - 1]?.focus();
    }
  };

  const handleOtpSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const otpString = otp.join('');
    
    if (otpString.length !== 6) {
      setError('Please enter the complete 6-digit code');
      return;
    }

    setError('');
    setSuccess('');
    setStep('reset');
  };

  const handleResetSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');

    if (newPassword !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }

    if (newPassword.length < 6) {
      setError('Password must be at least 6 characters');
      return;
    }

    setLoading(true);

    try {
      const otpString = otp.join('');
      const response = await apiClient.resetPassword({
        email,
        otp: otpString,
        new_password: newPassword,
      });

      if (!response.success) {
        throw new Error(response.message || 'Failed to reset password');
      }

      setStep('success');
      setSuccess('Your password has been reset successfully!');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to reset password');
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    setError('');
    setLoading(true);

    try {
      await sendResetOTP();
      setOtp(['', '', '', '', '', '']);
      setResendTimer(60);
      setSuccess('A new reset code has been sent to your email.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to resend code');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={styles.container}>
      <div className={styles.card}>
        <h1 className={styles.title}>🔑 Reset Password</h1>

        {step === 'email' && (
          <>
            <p className={styles.subtitle}>Enter your email to receive a reset code</p>
            <form onSubmit={handleEmailSubmit} className={styles.form}>
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

              {error && <div className={styles.error}>{error}</div>}

              <button
                type="submit"
                className={styles.button}
                disabled={loading}
                suppressHydrationWarning
              >
                {loading ? 'Sending...' : 'Send Reset Code'}
              </button>
            </form>

            <p className={styles.footer}>
              Remember your password?{' '}
              <Link href="/login" className={styles.link}>
                Back to Login
              </Link>
            </p>
          </>
        )}

        {step === 'otp' && (
          <>
            <p className={styles.subtitle}>
              Enter the 6-digit code sent to<br />
              <strong>{email}</strong>
            </p>

            {success && <div className={styles.success}>{success}</div>}

            <form onSubmit={handleOtpSubmit} className={styles.form}>
              <div className={styles.otpContainer}>
                {otp.map((digit, index) => (
                  <input
                    key={index}
                    ref={(el) => { otpInputRefs.current[index] = el; }}
                    type="text"
                    inputMode="numeric"
                    maxLength={6}
                    value={digit}
                    onChange={(e) => handleOtpChange(index, e.target.value)}
                    onKeyDown={(e) => handleOtpKeyDown(index, e)}
                    className={styles.otpInput}
                    disabled={loading}
                    autoFocus={index === 0}
                    suppressHydrationWarning
                  />
                ))}
              </div>

              {error && <div className={styles.error}>{error}</div>}

              <button
                type="submit"
                className={styles.button}
                disabled={loading || otp.join('').length !== 6}
                suppressHydrationWarning
              >
                Verify Code
              </button>
            </form>

            <div className={styles.resendContainer}>
              {resendTimer > 0 ? (
                <p className={styles.resendText}>
                  Resend code in <span className={styles.timerText}>{resendTimer}s</span>
                </p>
              ) : (
                <button
                  onClick={handleResend}
                  className={styles.resendButton}
                  disabled={loading}
                >
                  Resend Code
                </button>
              )}
            </div>

            <button
              onClick={() => { setStep('email'); setOtp(['', '', '', '', '', '']); setError(''); setSuccess(''); }}
              className={styles.backButton}
              disabled={loading}
            >
              ← Back
            </button>
          </>
        )}

        {step === 'reset' && (
          <>
            <p className={styles.subtitle}>Enter your new password</p>

            <form onSubmit={handleResetSubmit} className={styles.form}>
              <div className={styles.inputGroup}>
                <label htmlFor="newPassword">New Password</label>
                <input
                  id="newPassword"
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="Enter new password"
                  required
                  disabled={loading}
                  minLength={6}
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
                  placeholder="Confirm new password"
                  required
                  disabled={loading}
                  minLength={6}
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
                {loading ? 'Resetting...' : 'Reset Password'}
              </button>
            </form>

            <button
              onClick={() => { setStep('otp'); setError(''); }}
              className={styles.backButton}
              disabled={loading}
            >
              ← Back
            </button>
          </>
        )}

        {step === 'success' && (
          <>
            <p className={styles.subtitle}>
              🎉 Your password has been reset successfully!
            </p>

            {success && <div className={styles.success}>{success}</div>}

            <button
              onClick={() => router.push('/login')}
              className={styles.button}
              style={{ width: '100%', marginTop: '16px' }}
            >
              Go to Login
            </button>
          </>
        )}
      </div>
    </div>
  );
}
