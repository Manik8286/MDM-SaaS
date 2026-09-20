"""
Transactional email — SMTP.

Set SMTP_HOST (and friends) in .env to enable. In local dev, docker-compose
runs a Mailpit catcher (smtp://mailpit:1025) with a web UI at
http://localhost:8025 — nothing is really delivered, so signup/password-reset
emails can be tested safely without a real mailbox.
"""
import asyncio
import logging
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr

from app.core.config import get_settings

log = logging.getLogger(__name__)


def _send_sync(to_email: str, subject: str, html_body: str) -> None:
    settings = get_settings()
    msg = MIMEText(html_body, "html")
    msg["Subject"] = subject
    msg["From"] = formataddr((settings.smtp_from_name, settings.smtp_from_email))
    msg["To"] = to_email

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
        if settings.smtp_use_tls:
            server.starttls()
        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password)
        server.sendmail(settings.smtp_from_email, [to_email], msg.as_string())


async def send_email(to_email: str, subject: str, html_body: str) -> None:
    """Fire-and-forget email send — logs and swallows errors so a mail outage
    never breaks the request that triggered it (signup, password reset, etc.)."""
    settings = get_settings()
    if not settings.smtp_host:
        log.warning("SMTP not configured — skipping email to %s (subject=%r)", to_email, subject)
        return
    try:
        await asyncio.to_thread(_send_sync, to_email, subject, html_body)
        log.info("Email sent to %s (subject=%r)", to_email, subject)
    except Exception as e:
        log.error("Failed to send email to %s (subject=%r): %s", to_email, subject, e)


def _wrap(title: str, body_html: str) -> str:
    """Minimal shared HTML shell so every email looks consistent."""
    return f"""<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f5f5f7;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <div style="max-width:480px;margin:40px auto;background:#ffffff;border-radius:12px;padding:32px;">
    <p style="font-size:15px;font-weight:600;color:#18181b;margin:0 0 20px;">MDM Console</p>
    <h1 style="font-size:20px;color:#18181b;margin:0 0 16px;">{title}</h1>
    <div style="font-size:14px;line-height:1.6;color:#3f3f46;">{body_html}</div>
  </div>
</body>
</html>"""


async def send_welcome_email(to_email: str, org_name: str) -> None:
    html = _wrap(
        f"Welcome to MDM Console, {org_name}!",
        "<p>Your account is set up. Once your card is confirmed you'll have a "
        "5-day free trial to enroll devices, push profiles, and try Entra SSO.</p>"
        "<p>If you didn't request this account, you can ignore this email.</p>",
    )
    await send_email(to_email, "Welcome to MDM Console", html)


async def send_password_reset_email(to_email: str, reset_url: str) -> None:
    html = _wrap(
        "Reset your password",
        f"<p>Click the link below to choose a new password. This link expires in 1 hour.</p>"
        f'<p><a href="{reset_url}" style="color:#18181b;font-weight:600;">Reset password →</a></p>'
        "<p>If you didn't request this, you can safely ignore this email — your password won't change.</p>",
    )
    await send_email(to_email, "Reset your MDM Console password", html)


async def send_trial_ending_email(to_email: str, org_name: str, days_left: int) -> None:
    html = _wrap(
        f"Your trial ends in {days_left} day{'s' if days_left != 1 else ''}",
        f"<p>Hi {org_name},</p>"
        f"<p>Your MDM Console trial ends in {days_left} day{'s' if days_left != 1 else ''}. "
        "Your card on file will be charged automatically unless you cancel before then.</p>"
        "<p>Manage your subscription any time from Settings → Plan & Billing.</p>",
    )
    await send_email(to_email, f"Your trial ends in {days_left} day{'s' if days_left != 1 else ''}", html)
