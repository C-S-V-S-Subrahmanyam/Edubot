import smtplib
import hmac
import random
import string
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
import os
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# OTP storage backed by PostgreSQL (serverless-safe)
# ---------------------------------------------------------------------------

def _get_sync_session():
    """Create a sync SQLAlchemy session for OTP operations."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.config import DATABASE_URL_SYNC
    import ssl as _ssl

    # Ensure the URL uses the psycopg (v3) dialect, not psycopg2
    url = DATABASE_URL_SYNC
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql+psycopg2://"):
        url = url.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)

    connect_args = {}
    if os.getenv("DATABASE_SSL", "true").lower() != "false":
        ssl_context = _ssl.create_default_context()
        connect_args["sslmode"] = "require"

    eng = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
    Session = sessionmaker(bind=eng)
    return Session()


def _store_otp_db(email: str, otp: str, purpose: str,
                  username: str = None, hashed_password: str = None) -> None:
    """Store OTP in PostgreSQL, replacing any existing one for the same email+purpose."""
    from app.db.models import OTPToken
    from sqlalchemy import and_

    session = _get_sync_session()
    try:
        # Delete any existing OTP for this email+purpose
        session.query(OTPToken).filter(
            and_(OTPToken.email == email, OTPToken.purpose == purpose)
        ).delete()

        token = OTPToken(
            email=email,
            otp=otp,
            purpose=purpose,
            username=username,
            hashed_password=hashed_password,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
        session.add(token)
        session.commit()
    finally:
        session.close()


def _verify_otp_db(email: str, otp: str, purpose: str) -> Optional[dict]:
    """Verify OTP from PostgreSQL. Returns stored data if valid, else None."""
    from app.db.models import OTPToken
    from sqlalchemy import and_

    session = _get_sync_session()
    try:
        record = session.query(OTPToken).filter(
            and_(OTPToken.email == email, OTPToken.purpose == purpose)
        ).first()

        if not record:
            return None

        if datetime.now(timezone.utc) > record.expires_at:
            session.delete(record)
            session.commit()
            return None

        if not hmac.compare_digest(record.otp, otp):
            return None

        data = {
            "username": record.username,
            "hashed_password": record.hashed_password,
        }
        session.delete(record)  # OTP is single-use
        session.commit()
        return data
    finally:
        session.close()


def generate_otp() -> str:
    """Generate a 6-digit OTP."""
    return ''.join(random.choices(string.digits, k=6))


def get_otp_email_template(otp: str, username: str) -> str:
    """Generate professional OTP email HTML template."""
    current_year = datetime.now().year
    return f'''
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Verify Your Email - EduBot+</title>
</head>
<body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f7fa;">
  <table role="presentation" style="width: 100%; border-collapse: collapse;">
    <tr>
      <td align="center" style="padding: 40px 0;">
        <table role="presentation" style="width: 600px; border-collapse: collapse; background-color: #ffffff; border-radius: 16px; box-shadow: 0 4px 24px rgba(0, 0, 0, 0.1);">
          <!-- Header -->
          <tr>
            <td style="padding: 40px 40px 20px 40px; text-align: center; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 16px 16px 0 0;">
              <h1 style="margin: 0; font-size: 32px; color: #ffffff; font-weight: 700;">🎓 EduBot+</h1>
              <p style="margin: 8px 0 0 0; font-size: 14px; color: rgba(255, 255, 255, 0.9);">Your Intelligent Academic Assistant</p>
            </td>
          </tr>
          
          <!-- Body -->
          <tr>
            <td style="padding: 40px;">
              <h2 style="margin: 0 0 16px 0; font-size: 24px; color: #1a1a2e; font-weight: 600;">Verify Your Email Address</h2>
              <p style="margin: 0 0 24px 0; font-size: 16px; color: #4a5568; line-height: 1.6;">
                Hello <strong>{username}</strong>,
              </p>
              <p style="margin: 0 0 24px 0; font-size: 16px; color: #4a5568; line-height: 1.6;">
                Thank you for registering with EduBot+! To complete your account setup, please use the verification code below:
              </p>
              
              <!-- OTP Box -->
              <div style="background: linear-gradient(135deg, #667eea15 0%, #764ba215 100%); border: 2px dashed #667eea; border-radius: 12px; padding: 24px; text-align: center; margin: 32px 0;">
                <p style="margin: 0 0 8px 0; font-size: 14px; color: #4a5568; text-transform: uppercase; letter-spacing: 1px;">Your Verification Code</p>
                <p style="margin: 0; font-size: 42px; font-weight: 700; letter-spacing: 12px; color: #667eea; font-family: 'Courier New', monospace;">{otp}</p>
              </div>
              
              <p style="margin: 0 0 16px 0; font-size: 14px; color: #718096; line-height: 1.6;">
                ⏱️ This code will expire in <strong>10 minutes</strong> for security purposes.
              </p>
              
              <div style="background-color: #fff8e6; border-left: 4px solid #f6ad55; padding: 16px; border-radius: 0 8px 8px 0; margin: 24px 0;">
                <p style="margin: 0; font-size: 14px; color: #744210;">
                  <strong>🔒 Security Notice:</strong> If you didn't request this code, please ignore this email. Never share this code with anyone.
                </p>
              </div>
            </td>
          </tr>
          
          <!-- Footer -->
          <tr>
            <td style="padding: 24px 40px; background-color: #f8fafc; border-radius: 0 0 16px 16px; text-align: center;">
              <p style="margin: 0 0 8px 0; font-size: 14px; color: #718096;">
                Need help? Contact us at <a href="mailto:22501a0557@pvpsit.ac.in" style="color: #667eea; text-decoration: none;">22501a0557@pvpsit.ac.in</a>
              </p>
              <p style="margin: 0; font-size: 12px; color: #a0aec0;">
                © {current_year} EduBot+. All rights reserved.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
'''


def get_welcome_email_template(username: str, email: str) -> str:
    """Generate professional welcome email HTML template."""
    current_year = datetime.now().year
    app_url = os.getenv("APP_URL", "http://localhost:3000")
    return f'''
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Welcome to EduBot+</title>
</head>
<body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f7fa;">
  <table role="presentation" style="width: 100%; border-collapse: collapse;">
    <tr>
      <td align="center" style="padding: 40px 0;">
        <table role="presentation" style="width: 600px; border-collapse: collapse; background-color: #ffffff; border-radius: 16px; box-shadow: 0 4px 24px rgba(0, 0, 0, 0.1);">
          <!-- Header -->
          <tr>
            <td style="padding: 40px 40px 20px 40px; text-align: center; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 16px 16px 0 0;">
              <h1 style="margin: 0; font-size: 32px; color: #ffffff; font-weight: 700;">🎉 Welcome to EduBot+!</h1>
              <p style="margin: 8px 0 0 0; font-size: 14px; color: rgba(255, 255, 255, 0.9);">Your account has been successfully created</p>
            </td>
          </tr>
          
          <!-- Body -->
          <tr>
            <td style="padding: 40px;">
              <p style="margin: 0 0 24px 0; font-size: 18px; color: #1a1a2e; line-height: 1.6;">
                Hello <strong>{username}</strong>! 👋
              </p>
              <p style="margin: 0 0 24px 0; font-size: 16px; color: #4a5568; line-height: 1.6;">
                Congratulations! Your EduBot+ account is now active and ready to use. We're thrilled to have you on board!
              </p>
              
              <!-- Account Info Box -->
              <div style="background: linear-gradient(135deg, #48bb7815 0%, #38a16915 100%); border: 1px solid #48bb78; border-radius: 12px; padding: 24px; margin: 24px 0;">
                <h3 style="margin: 0 0 16px 0; font-size: 16px; color: #276749;">📋 Your Account Details</h3>
                <table style="width: 100%; border-collapse: collapse;">
                  <tr>
                    <td style="padding: 8px 0; font-size: 14px; color: #718096;">Username:</td>
                    <td style="padding: 8px 0; font-size: 14px; color: #1a1a2e; font-weight: 600;">{username}</td>
                  </tr>
                  <tr>
                    <td style="padding: 8px 0; font-size: 14px; color: #718096;">Email:</td>
                    <td style="padding: 8px 0; font-size: 14px; color: #1a1a2e; font-weight: 600;">{email}</td>
                  </tr>
                  <tr>
                    <td style="padding: 8px 0; font-size: 14px; color: #718096;">Account Status:</td>
                    <td style="padding: 8px 0; font-size: 14px; color: #48bb78; font-weight: 600;">✓ Verified & Active</td>
                  </tr>
                </table>
              </div>
              
              <!-- Features -->
              <h3 style="margin: 32px 0 16px 0; font-size: 18px; color: #1a1a2e;">🚀 Get Started with EduBot+</h3>
              
              <table style="width: 100%; border-collapse: collapse;">
                <tr>
                  <td style="padding: 12px; vertical-align: top; width: 50%;">
                    <div style="background-color: #f8fafc; border-radius: 8px; padding: 16px; height: 100%;">
                      <p style="margin: 0 0 8px 0; font-size: 24px;">💬</p>
                      <p style="margin: 0 0 4px 0; font-size: 14px; font-weight: 600; color: #1a1a2e;">Smart Conversations</p>
                      <p style="margin: 0; font-size: 12px; color: #718096;">Get instant answers to your academic queries</p>
                    </div>
                  </td>
                  <td style="padding: 12px; vertical-align: top; width: 50%;">
                    <div style="background-color: #f8fafc; border-radius: 8px; padding: 16px; height: 100%;">
                      <p style="margin: 0 0 8px 0; font-size: 24px;">📚</p>
                      <p style="margin: 0 0 4px 0; font-size: 14px; font-weight: 600; color: #1a1a2e;">Knowledge Base</p>
                      <p style="margin: 0; font-size: 12px; color: #718096;">Access comprehensive academic resources</p>
                    </div>
                  </td>
                </tr>
                <tr>
                  <td style="padding: 12px; vertical-align: top; width: 50%;">
                    <div style="background-color: #f8fafc; border-radius: 8px; padding: 16px; height: 100%;">
                      <p style="margin: 0 0 8px 0; font-size: 24px;">🎯</p>
                      <p style="margin: 0 0 4px 0; font-size: 14px; font-weight: 600; color: #1a1a2e;">Personalized Help</p>
                      <p style="margin: 0; font-size: 12px; color: #718096;">Tailored responses for your needs</p>
                    </div>
                  </td>
                  <td style="padding: 12px; vertical-align: top; width: 50%;">
                    <div style="background-color: #f8fafc; border-radius: 8px; padding: 16px; height: 100%;">
                      <p style="margin: 0 0 8px 0; font-size: 24px;">⚡</p>
                      <p style="margin: 0 0 4px 0; font-size: 14px; font-weight: 600; color: #1a1a2e;">Instant Responses</p>
                      <p style="margin: 0; font-size: 12px; color: #718096;">Get answers in seconds, anytime</p>
                    </div>
                  </td>
                </tr>
              </table>
              
              <!-- CTA Button -->
              <div style="text-align: center; margin: 32px 0;">
                <a href="{app_url}/chat" 
                   style="display: inline-block; padding: 16px 32px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: #ffffff; text-decoration: none; border-radius: 8px; font-size: 16px; font-weight: 600; box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);">
                  Start Chatting Now →
                </a>
              </div>
            </td>
          </tr>
          
          <!-- Footer -->
          <tr>
            <td style="padding: 24px 40px; background-color: #f8fafc; border-radius: 0 0 16px 16px; text-align: center;">
              <p style="margin: 0 0 8px 0; font-size: 14px; color: #718096;">
                Need assistance? We're here to help at <a href="mailto:22501a0557@pvpsit.ac.in" style="color: #667eea; text-decoration: none;">22501a0557@pvpsit.ac.in</a>
              </p>
              <p style="margin: 0; font-size: 12px; color: #a0aec0;">
                © {current_year} EduBot+. All rights reserved.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
'''


def send_email(to_email: str, subject: str, html_content: str) -> bool:
    """Send an email using SMTP."""
    try:
        email_user = os.getenv("EMAIL_USER")
        email_pass = os.getenv("EMAIL_PASS")
        
        if not email_user or not email_pass:
            print("Email credentials not configured")
            return False
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"EduBot+ <{email_user}>"
        msg['To'] = to_email
        
        html_part = MIMEText(html_content, 'html')
        msg.attach(html_part)
        
        # Connect to Gmail SMTP
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(email_user, email_pass)
            server.sendmail(email_user, to_email, msg.as_string())
        
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False


def store_otp(email: str, otp: str, username: str, hashed_password: str) -> None:
    """Store registration OTP in PostgreSQL."""
    _store_otp_db(email, otp, purpose="registration",
                  username=username, hashed_password=hashed_password)


def verify_otp(email: str, otp: str) -> Optional[dict]:
    """Verify registration OTP. Returns stored data if valid."""
    return _verify_otp_db(email, otp, purpose="registration")


def send_otp_email(email: str, username: str, hashed_password: str) -> bool:
    """Generate, store and send OTP email."""
    otp = generate_otp()
    store_otp(email, otp, username, hashed_password)
    
    html_content = get_otp_email_template(otp, username)
    return send_email(email, "🔐 Verify Your Email - EduBot+", html_content)


def send_welcome_email(email: str, username: str) -> bool:
    """Send welcome email after successful registration."""
    html_content = get_welcome_email_template(username, email)
    return send_email(email, "🎉 Welcome to EduBot+ - Account Created Successfully!", html_content)


def get_password_reset_email_template(otp: str, username: str) -> str:
    """Generate professional password reset OTP email HTML template."""
    current_year = datetime.now().year
    return f'''
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Reset Your Password - EduBot+</title>
</head>
<body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f7fa;">
  <table role="presentation" style="width: 100%; border-collapse: collapse;">
    <tr>
      <td align="center" style="padding: 40px 0;">
        <table role="presentation" style="width: 600px; border-collapse: collapse; background-color: #ffffff; border-radius: 16px; box-shadow: 0 4px 24px rgba(0, 0, 0, 0.1);">
          <!-- Header -->
          <tr>
            <td style="padding: 40px 40px 20px 40px; text-align: center; background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%); border-radius: 16px 16px 0 0;">
              <h1 style="margin: 0; font-size: 32px; color: #ffffff; font-weight: 700;">🔑 EduBot+</h1>
              <p style="margin: 8px 0 0 0; font-size: 14px; color: rgba(255, 255, 255, 0.9);">Password Reset Request</p>
            </td>
          </tr>
          
          <!-- Body -->
          <tr>
            <td style="padding: 40px;">
              <h2 style="margin: 0 0 16px 0; font-size: 24px; color: #1a1a2e; font-weight: 600;">Reset Your Password</h2>
              <p style="margin: 0 0 24px 0; font-size: 16px; color: #4a5568; line-height: 1.6;">
                Hello <strong>{username}</strong>,
              </p>
              <p style="margin: 0 0 24px 0; font-size: 16px; color: #4a5568; line-height: 1.6;">
                We received a request to reset your password. Use the verification code below to proceed:
              </p>
              
              <!-- OTP Box -->
              <div style="background: linear-gradient(135deg, #e74c3c15 0%, #c0392b15 100%); border: 2px dashed #e74c3c; border-radius: 12px; padding: 24px; text-align: center; margin: 32px 0;">
                <p style="margin: 0 0 8px 0; font-size: 14px; color: #4a5568; text-transform: uppercase; letter-spacing: 1px;">Your Reset Code</p>
                <p style="margin: 0; font-size: 42px; font-weight: 700; letter-spacing: 12px; color: #e74c3c; font-family: 'Courier New', monospace;">{otp}</p>
              </div>
              
              <p style="margin: 0 0 16px 0; font-size: 14px; color: #718096; line-height: 1.6;">
                ⏱️ This code will expire in <strong>10 minutes</strong> for security purposes.
              </p>
              
              <div style="background-color: #fff8e6; border-left: 4px solid #f6ad55; padding: 16px; border-radius: 0 8px 8px 0; margin: 24px 0;">
                <p style="margin: 0; font-size: 14px; color: #744210;">
                  <strong>🔒 Security Notice:</strong> If you didn't request a password reset, please ignore this email. Your password will remain unchanged.
                </p>
              </div>
            </td>
          </tr>
          
          <!-- Footer -->
          <tr>
            <td style="padding: 24px 40px; background-color: #f8fafc; border-radius: 0 0 16px 16px; text-align: center;">
              <p style="margin: 0 0 8px 0; font-size: 14px; color: #718096;">
                Need help? Contact us at <a href="mailto:22501a0557@pvpsit.ac.in" style="color: #e74c3c; text-decoration: none;">22501a0557@pvpsit.ac.in</a>
              </p>
              <p style="margin: 0; font-size: 12px; color: #a0aec0;">
                © {current_year} EduBot+. All rights reserved.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
'''


def store_password_reset_otp(email: str, otp: str) -> None:
    """Store password reset OTP in PostgreSQL."""
    _store_otp_db(email, otp, purpose="password_reset")


def verify_password_reset_otp(email: str, otp: str) -> bool:
    """Verify password reset OTP. Returns True if valid."""
    result = _verify_otp_db(email, otp, purpose="password_reset")
    return result is not None


def send_password_reset_otp_email(email: str, username: str) -> bool:
    """Generate, store and send password reset OTP email."""
    otp = generate_otp()
    store_password_reset_otp(email, otp)
    
    html_content = get_password_reset_email_template(otp, username)
    return send_email(email, "🔑 Reset Your Password - EduBot+", html_content)

