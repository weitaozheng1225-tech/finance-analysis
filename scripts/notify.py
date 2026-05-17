"""Send email + webhook alerts when stress conditions warrant.

Daily (default) and weekly modes attach the matching PDF report.

Env (all optional — only configured channels fire):
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_FROM, EMAIL_TO
  SMTP_SSL=1                # force SSL even on non-465 ports
  WEBHOOK_URL               # Slack / Discord / generic JSON POST
  ALERT_MIN_BAND            # watch | warn (default) | crisis
  ALWAYS_SEND               # 1 → bypass band check (weekly always sends)

CLI:
  python scripts/notify.py            # daily — only send if band warrants
  python scripts/notify.py weekly     # weekly — always send (subject to channel config)
"""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import smtplib
import sys
from email.message import EmailMessage
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "data" / "latest_snapshot.json"
WEEKLY_SNAPSHOT = ROOT / "data" / "weekly_snapshot.json"
DAILY_PDF = ROOT / "reports" / "daily" / "latest.pdf"
WEEKLY_PDF = ROOT / "reports" / "weekly" / "latest.pdf"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
log = logging.getLogger("notify")

BAND_RANK = {"ok": 0, "watch": 1, "warn": 2, "crisis": 3}


def _should_alert(snap: dict) -> bool:
    if os.getenv("ALWAYS_SEND", "").lower() in {"1", "true", "yes"}:
        return True
    min_band = os.getenv("ALERT_MIN_BAND", "warn").lower()
    threshold = BAND_RANK.get(min_band, 2)
    band = snap.get("stress_band") or snap.get("today_band") or "ok"
    if BAND_RANK.get(band, 0) >= threshold:
        return True
    # Also alert if any individual indicator is at crisis threshold
    if any(i.get("threshold_state") == "crisis" for i in snap.get("indicators", [])):
        return True
    return False


def _subject(snap: dict, mode: str) -> str:
    stress = snap.get("composite_stress") or snap.get("today_stress") or 0
    band = (snap.get("stress_band") or snap.get("today_band") or "ok").upper()
    n_anom = len(snap.get("anomalies", []))
    date_str = snap.get("as_of", "")
    tag = "WEEKLY" if mode == "weekly" else "DAILY"
    return f"[BOND-MONITOR · {tag}] {date_str} stress={stress}/12 band={band} anomalies={n_anom}"


def _summary_body(snap: dict, mode: str, pdf_path: Path | None) -> str:
    """Plain-text email body — short summary; the PDF is the deliverable."""
    band = (snap.get("stress_band") or snap.get("today_band") or "ok").upper()
    stress = snap.get("composite_stress") or snap.get("today_stress") or 0
    lines = [
        f"Bond Crisis Monitor — {mode.title()} Report",
        f"As of: {snap.get('as_of', '')}",
        f"Composite stress: {stress}/12  ({band})",
        "",
    ]
    if snap.get("anomalies"):
        lines.append("Active anomalies:")
        for a in snap["anomalies"][:10]:
            lines.append(f"  • {a}")
        if len(snap["anomalies"]) > 10:
            lines.append(f"  … and {len(snap['anomalies']) - 10} more")
    else:
        lines.append("No anomalies or threshold breaches detected.")
    lines.append("")
    if pdf_path and pdf_path.exists():
        lines.append(f"See attached PDF for the full report ({pdf_path.stat().st_size // 1024} KB).")
    lines.append("")
    lines.append("Full archive: https://github.com/weitaozheng1225-tech/finance-analysis")
    return "\n".join(lines)


def _send_email(snap: dict, mode: str, pdf_path: Path | None) -> None:
    host = os.getenv("SMTP_HOST")
    if not host:
        log.info("Email: SMTP_HOST not set, skipping")
        return
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    pw = os.getenv("SMTP_PASS")
    sender = os.getenv("EMAIL_FROM", user)
    recipient = os.getenv("EMAIL_TO")
    if not all([user, pw, sender, recipient]):
        log.warning("Email: missing one of SMTP_USER/SMTP_PASS/EMAIL_FROM/EMAIL_TO")
        return

    msg = EmailMessage()
    msg["Subject"] = _subject(snap, mode)
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(_summary_body(snap, mode, pdf_path))

    if pdf_path and pdf_path.exists():
        with open(pdf_path, "rb") as f:
            data = f.read()
        ctype, _ = mimetypes.guess_type(str(pdf_path)) or ("application/pdf", None)
        maintype, subtype = (ctype or "application/pdf").split("/", 1)
        msg.add_attachment(
            data, maintype=maintype, subtype=subtype, filename=pdf_path.name
        )
        log.info("Email: attaching %s (%d KB)", pdf_path.name, len(data) // 1024)
    else:
        log.warning("Email: PDF %s not found — sending text-only", pdf_path)

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
        log.info("Email sent to %s via %s:%d (%s)",
                 recipient, host, port, "SSL" if use_ssl else "STARTTLS")
    except Exception as e:
        log.error("Email send failed: %s", e)


def _send_webhook(snap: dict, mode: str, pdf_path: Path | None) -> None:
    url = os.getenv("WEBHOOK_URL")
    if not url:
        return
    body = _summary_body(snap, mode, pdf_path)
    payload = {
        "text": _subject(snap, mode),
        "content": _subject(snap, mode),  # Discord compatibility
        "attachments": [{"title": f"{mode.title()} report", "text": body[:3500]}],
        "snapshot": {
            "as_of": snap.get("as_of"),
            "stress": snap.get("composite_stress") or snap.get("today_stress"),
            "band": snap.get("stress_band") or snap.get("today_band"),
            "anomalies": snap.get("anomalies", []),
        },
    }
    try:
        r = requests.post(url, json=payload, timeout=20)
        r.raise_for_status()
        log.info("Webhook OK: %s", r.status_code)
    except Exception as e:
        log.error("Webhook failed: %s", e)


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "daily"
    if mode == "weekly":
        snap_path = WEEKLY_SNAPSHOT
        pdf_path = WEEKLY_PDF
        os.environ.setdefault("ALWAYS_SEND", "1")  # weekly always sends
    else:
        snap_path = SNAPSHOT
        pdf_path = DAILY_PDF

    if not snap_path.exists():
        log.error("%s not found — run analyze.py (or weekly_report.py) first", snap_path.name)
        return 1
    snap = json.loads(snap_path.read_text())

    if not _should_alert(snap):
        log.info("No alert: band=%s below threshold", snap.get("stress_band"))
        return 0
    _send_email(snap, mode, pdf_path)
    _send_webhook(snap, mode, pdf_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
