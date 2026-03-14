"""
Notification module — Mac alert + Telegram + Email
All credentials loaded from .env
"""

import os
import smtplib
import subprocess
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import requests

log = logging.getLogger(__name__)


def notify_mac(title: str, message: str):
    """Show a macOS notification."""
    try:
        script = f'display notification "{message}" with title "{title}" sound name "Glass"'
        subprocess.run(["osascript", "-e", script], check=True)
        log.info("Mac notification sent")
    except Exception as e:
        log.error(f"Mac notification failed: {e}")


def notify_telegram(message: str):
    """Send a Telegram message via bot."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or "your-bot-token" in token:
        log.warning("Telegram not configured — skipping")
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        resp.raise_for_status()
        log.info("Telegram message sent")
    except Exception as e:
        log.error(f"Telegram failed: {e}")


def notify_email(subject: str, body: str):
    """Send an email via SMTP."""
    from_addr = os.environ.get("EMAIL_FROM", "")
    to_addr = os.environ.get("EMAIL_TO", "")
    password = os.environ.get("EMAIL_PASSWORD", "")
    smtp_host = os.environ.get("EMAIL_SMTP", "smtp.gmail.com")
    smtp_port = int(os.environ.get("EMAIL_PORT", "587"))

    if not from_addr or "your@gmail" in from_addr:
        log.warning("Email not configured — skipping")
        return
    try:
        msg = MIMEMultipart()
        msg["From"] = from_addr
        msg["To"] = to_addr
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(from_addr, password)
            server.send_message(msg)
        log.info("Email sent")
    except Exception as e:
        log.error(f"Email failed: {e}")


def send_morning_alert():
    """Send 'time to run invHunter' reminder across all channels."""
    title = "invHunter — Market Open"
    message = "TASE is open. Time to run invHunter!\n`cd ~/Documents/repos/invHunter && source .venv/bin/activate && python tase_claude_agent.py`"
    short = "TASE is open. Time to run invHunter!"

    notify_mac(title, short)
    notify_telegram(f"*{title}*\n{message}")
    notify_email(title, message)


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    send_morning_alert()
