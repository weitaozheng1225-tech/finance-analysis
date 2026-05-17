"""Send email + webhook alerts when stress band is warn/crisis or anomalies exist.

Env (all optional — only configured channels fire):
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_FROM, EMAIL_TO
  WEBHOOK_URL  (Slack/Discord/Feishu/generic JSON POST)
  ALERT_MIN_BAND  (one of: watch | warn | crisis, default: warn)
"""

from __future__ import annotations

import json
import logging
import os
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "data" / "latest_snapshot.json"
LATEST_REPORT = ROOT / "reports" / "daily" / "latest.md"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
log = logging.getLogger("notify")

BAND_RANK = {"ok": 0, "watch": 1, "warn": 2, "crisis": 3}


def _should_alert(snap: dict) -> bool:
    min_band = os.getenv("ALERT_MIN_BAND", "warn").lower()
    threshold = BAND_RANK.get(min_band, 2)
    if BAND_RANK.get(snap["stress_band"], 0) >= threshold:
        return True
    # Also alert if any indicator is at "crisis" individually
    if any(i["threshold_state"] == "crisis" for i in snap["indicators"]):
        return True
    return False


def _subject(snap: dict) -> str:
    return (
        f"[BOND-MONITOR] {snap['as_of']} stress={snap['composite_stress']}/12 "
        f"band={snap['stress_band'].upper()} anomalies={len(snap['anomalies'])}"
    )


def _send_email(snap: dict, body_md: str) -> None:
    host = os.getenv("SMTP_HOST")
    if not host:
        return
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    pw = os.getenv("SMTP_PASS")
    sender = os.getenv("EMAIL_FROM", user)
    recipient = os.getenv("EMAIL_TO")
    if not all([user, pw, sender, recipient]):
        log.warning("Email: missing one of SMTP_USER/SMTP_PASS/EMAIL_FROM/EMAIL_TO")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = _subject(snap)
    msg["From"] = sender
    msg["To"] = recipient
    msg.attach(MIMEText(body_md, "plain", "utf-8"))
    # Crude html rendering: monospace + line breaks
    html = "<pre style='font-family: monospace'>" + body_md.replace("<", "&lt;") + "</pre>"
    msg.attach(MIMEText(html, "html", "utf-8"))

    use_ssl = port == 465 or os.getenv("SMTP_SSL", "").lower() in {"1", "true", "yes"}
    try:
        if use_ssl:
            smtp = smtplib.SMTP_SSL(host, port, timeout=30)
        else:
            smtp = smtplib.SMTP(host, port, timeout=30)
            smtp.starttls()
        with smtp:
            smtp.login(user, pw)
            smtp.sendmail(sender, [r.strip() for r in recipient.split(",")], msg.as_string())
        log.info("Email sent to %s via %s:%d (%s)", recipient, host, port, "SSL" if use_ssl else "STARTTLS")
    except Exception as e:
        log.error("Email send failed: %s", e)


def _send_webhook(snap: dict, body_md: str) -> None:
    url = os.getenv("WEBHOOK_URL")
    if not url:
        return
    payload = {
        "text": _subject(snap),
        "content": _subject(snap),  # Discord compatibility
        "attachments": [
            {
                "title": "Daily report",
                "text": body_md[:3500],
            }
        ],
        "snapshot": {
            "as_of": snap["as_of"],
            "composite_stress": snap["composite_stress"],
            "stress_band": snap["stress_band"],
            "anomalies": snap["anomalies"],
        },
    }
    try:
        r = requests.post(url, json=payload, timeout=20)
        r.raise_for_status()
        log.info("Webhook OK: %s", r.status_code)
    except Exception as e:
        log.error("Webhook failed: %s", e)


def main() -> int:
    snap = json.loads(SNAPSHOT.read_text())
    if not _should_alert(snap):
        log.info("No alert: band=%s below threshold", snap["stress_band"])
        return 0
    body = LATEST_REPORT.read_text() if LATEST_REPORT.exists() else json.dumps(snap, indent=2)
    _send_email(snap, body)
    _send_webhook(snap, body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
