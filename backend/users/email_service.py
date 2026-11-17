"""
RentBee Centralized Email Service.
Provides unified, secure, professional email delivery for all OTP verification workflows.
"""

import logging
import smtplib
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils.html import escape

logger = logging.getLogger(__name__)

# OTP Purposes
OTP_PURPOSE_SIGNUP = "signup"
OTP_PURPOSE_PASSWORD_RESET = "password_reset"
OTP_PURPOSE_EMAIL_CHANGE = "email_change"

_PURPOSE_CONFIG = {
    OTP_PURPOSE_SIGNUP: {
        "subject": "Your RentBee Email Verification Code",
        "title": "Welcome to RentBee!",
        "action_desc": "Thank you for creating an account with RentBee. Please use the verification code below to verify your email address.",
        "badge_color": "#2563eb",  # Primary blue
    },
    OTP_PURPOSE_PASSWORD_RESET: {
        "subject": "Your RentBee Password Reset Code",
        "title": "Password Reset Request",
        "action_desc": "We received a request to reset your RentBee account password. Please use the verification code below to proceed.",
        "badge_color": "#dc2626",  # Red / Security alert
    },
    OTP_PURPOSE_EMAIL_CHANGE: {
        "subject": "RentBee Email Change Verification",
        "title": "Verify Your New Email",
        "action_desc": "You requested to update your RentBee account email address. Please use the verification code below to confirm this change.",
        "badge_color": "#059669",  # Green / Update
    },
}


def _build_plain_text(otp: str, purpose_config: dict, expiry_minutes: int) -> str:
    """Builds clean, structured plain text version of the OTP email."""
    return (
        f"{purpose_config['title']}\n\n"
        f"{purpose_config['action_desc']}\n\n"
        f"Verification Code: {otp}\n\n"
        f"This code will expire in {expiry_minutes} minutes.\n\n"
        "Security Notice:\n"
        "Never share this code with anyone. RentBee employees will never ask for your verification code.\n"
        "If you did not make this request, you can safely ignore this email.\n\n"
        "— The RentBee Team\n"
        "RentBee — Smart Peer-to-Peer Rentals"
    )


def _build_html_email(otp: str, purpose_config: dict, expiry_minutes: int) -> str:
    """Builds a responsive, beautifully styled HTML email template."""
    title = escape(purpose_config["title"])
    action_desc = escape(purpose_config["action_desc"])
    badge_color = purpose_config.get("badge_color", "#2563eb")
    safe_otp = escape(otp)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      background-color: #f8fafc;
      margin: 0;
      padding: 0;
      color: #1e293b;
      line-height: 1.6;
    }}
    .container {{
      max-width: 580px;
      margin: 40px auto;
      background: #ffffff;
      border-radius: 12px;
      overflow: hidden;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -2px rgba(0, 0, 0, 0.05);
      border: 1px solid #e2e8f0;
    }}
    .header {{
      background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
      padding: 28px 32px;
      text-align: center;
    }}
    .logo-text {{
      font-size: 24px;
      font-weight: 800;
      color: #ffffff;
      letter-spacing: -0.5px;
      margin: 0;
    }}
    .logo-accent {{
      color: #f59e0b;
    }}
    .content {{
      padding: 36px 32px;
    }}
    .title {{
      font-size: 20px;
      font-weight: 700;
      color: #0f172a;
      margin-top: 0;
      margin-bottom: 12px;
    }}
    .description {{
      font-size: 15px;
      color: #475569;
      margin-bottom: 24px;
    }}
    .otp-box {{
      background-color: #f1f5f9;
      border: 1px dashed {badge_color};
      border-radius: 10px;
      padding: 24px;
      text-align: center;
      margin: 28px 0;
    }}
    .otp-code {{
      font-family: 'Courier New', Courier, monospace;
      font-size: 34px;
      font-weight: 800;
      letter-spacing: 8px;
      color: {badge_color};
      margin: 0;
    }}
    .expiry-note {{
      font-size: 13px;
      color: #64748b;
      margin-top: 10px;
      margin-bottom: 0;
      font-weight: 500;
    }}
    .security-notice {{
      background-color: #fef2f2;
      border-left: 4px solid #ef4444;
      padding: 12px 16px;
      border-radius: 0 6px 6px 0;
      font-size: 13px;
      color: #991b1b;
      margin-top: 24px;
    }}
    .footer {{
      background-color: #f8fafc;
      padding: 24px 32px;
      text-align: center;
      border-top: 1px solid #e2e8f0;
      font-size: 12px;
      color: #94a3b8;
    }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1 class="logo-text">Rent<span class="logo-accent">Bee</span></h1>
    </div>
    <div class="content">
      <h2 class="title">{title}</h2>
      <p class="description">{action_desc}</p>
      
      <div class="otp-box">
        <div class="otp-code">{safe_otp}</div>
        <p class="expiry-note">Valid for <strong>{expiry_minutes} minutes</strong></p>
      </div>

      <div class="security-notice">
        <strong>Security tip:</strong> Never share this code with anyone. RentBee will never call, text, or email you asking for this verification code.
      </div>
    </div>
    <div class="footer">
      <p style="margin: 0 0 6px 0;">This is an automated system notification from RentBee.</p>
      <p style="margin: 0;">&copy; RentBee — Peer-to-Peer Rental Community. All rights reserved.</p>
    </div>
  </div>
</body>
</html>
"""


def send_rentbee_otp_email(to_email: str, otp: str, purpose: str, expiry_minutes: int = 10) -> bool:
    """
    Centralized email delivery function for OTP verification codes.
    
    Args:
        to_email: Target recipient email address.
        otp: 6-digit plain text OTP code.
        purpose: 'signup', 'password_reset', or 'email_change'.
        expiry_minutes: Expiration window in minutes (defaults to 10).
        
    Returns:
        bool: True if the email was successfully sent.
        
    Raises:
        Exception: If SMTP connection, authentication, or transmission fails.
                   The error is logged safely without leaking the OTP value.
    """
    purpose_config = _PURPOSE_CONFIG.get(purpose, _PURPOSE_CONFIG[OTP_PURPOSE_SIGNUP])
    subject = purpose_config["subject"]
    
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or "RentBee <noreply@rentbee.com>"
    
    backend_name = getattr(settings, "EMAIL_BACKEND", "")
    is_smtp_backend = "smtp" in backend_name.lower()
    host_user = getattr(settings, "EMAIL_HOST_USER", "")
    host_password = getattr(settings, "EMAIL_HOST_PASSWORD", "")

    # When using real SMTP, fail safely and immediately if credentials are missing
    if is_smtp_backend and (not host_user or not host_password):
        error_msg = "SMTP delivery failed: Email credentials (EMAIL_HOST_USER / EMAIL_HOST_PASSWORD) are not configured."
        logger.error("Failed to send %s OTP email to %s: %s", purpose, to_email, error_msg)
        raise smtplib.SMTPException(error_msg)

    plain_text_message = _build_plain_text(otp, purpose_config, expiry_minutes)
    html_content = _build_html_email(otp, purpose_config, expiry_minutes)

    msg = EmailMultiAlternatives(
        subject=subject,
        body=plain_text_message,
        from_email=from_email,
        to=[to_email],
    )
    msg.attach_alternative(html_content, "text/html")

    try:
        sent_count = msg.send(fail_silently=False)
        if sent_count != 1:
            raise smtplib.SMTPException(
                f"SMTP transmission failed: expected 1 delivered email, but got {sent_count}."
            )
        logger.info("Successfully delivered %s OTP email to %s via SMTP", purpose, to_email)
        return True
    except Exception as exc:
        # Never log or expose the OTP in logs or exceptions
        logger.error(
            "Failed to send %s OTP email to %s: %s (%s)",
            purpose,
            to_email,
            type(exc).__name__,
            str(exc),
        )
        raise exc

