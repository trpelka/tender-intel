import json
import os
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape
from pathlib import Path

C = {"HIGH": "#c0392b", "MEDIUM": "#e67e22", "LOW": "#7f8c8d"}
BG = {"HIGH": "#fdf2f2", "MEDIUM": "#fef9f0", "LOW": "#f8f9fa"}


def _impact(notice):
    impact = str(notice.get("impact") or "LOW").upper()
    return impact if impact in C else "LOW"


def _safe_url(value):
    value = str(value or "").strip()
    if value.startswith(("http://", "https://")):
        return escape(value, quote=True)
    return "#"


def _format_value(notice):
    raw = notice.get("estimated_value")
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if raw in (None, ""):
        return "—"
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return "—"
    if value <= 0:
        return "—"
    currency = escape(str(notice.get("currency") or "EUR"))
    return f"{value:,.0f} {currency}"


def _cpv_codes(notice):
    codes = notice.get("cpv_codes", [])
    if isinstance(codes, str):
        try:
            codes = json.loads(codes)
        except (TypeError, ValueError):
            codes = [codes] if codes else []
    if not isinstance(codes, list):
        codes = []
    return [escape(str(code)) for code in codes[:2]]


def _block(notice, index):
    impact = _impact(notice)
    color = C[impact]
    background = BG[impact]
    title = escape(str(notice.get("title") or "No title")[:120])
    url = _safe_url(notice.get("url"))
    country = escape(str(notice.get("buyer_country") or ""))
    summary = notice.get("summary_en") or notice.get("description", "")
    summary = escape(str(summary or "")[:280])
    summary_pl = escape(str(notice.get("summary_pl") or ""))
    deadline = escape(str(notice.get("deadline") or "—"))
    cpv = ", ".join(_cpv_codes(notice)) or "—"

    polish = (
        f"<p style='margin:0 0 6px;color:#666;font-size:13px;font-style:italic;'>{summary_pl}</p>"
        if summary_pl
        else ""
    )

    return f"""
<div style="margin-bottom:18px;border-left:4px solid {color};background:{background};
            padding:14px;border-radius:4px;">
  <span style="background:{color};color:white;font-size:11px;padding:2px 7px;
               border-radius:3px;font-weight:bold;">{impact}</span>
  <span style="color:#999;font-size:12px;float:right;">#{index} · {country}</span>
  <h3 style="margin:10px 0 6px;font-size:15px;">
    <a href="{url}" style="color:#2c3e50;text-decoration:none;">
      {title}
    </a>
  </h3>
  <p style="margin:0 0 8px;color:#444;font-size:14px;line-height:1.5;">
    {summary}
  </p>
  {polish}
  <span style="font-size:13px;color:#555;">
    <b>Value:</b> {_format_value(notice)} &nbsp;·&nbsp;
    <b>Deadline:</b> {deadline} &nbsp;·&nbsp;
    <b>CPV:</b> {cpv}
  </span>
  <br><a href="{url}" style="font-size:13px;color:#2980b9;">→ Full tender</a>
</div>"""


def generate(client_name, notices, period_from, period_to, client_email=""):
    now = datetime.now(timezone.utc).strftime("%d %b %Y")
    name = escape(str(client_name))
    start = escape(str(period_from))
    end = escape(str(period_to))
    hi = [n for n in notices if _impact(n) == "HIGH"]
    me = [n for n in notices if _impact(n) == "MEDIUM"]
    lo = [n for n in notices if _impact(n) == "LOW"]

    def section(label, items, first_index):
        if not items:
            return ""
        blocks = "".join(_block(n, first_index + i) for i, n in enumerate(items))
        return (
            f"<h2 style='margin:28px 0 10px;font-size:15px;text-transform:uppercase;"
            f"letter-spacing:1px;color:#7f8c8d;border-bottom:1px solid #eee;padding-bottom:5px;'>"
            f"{label} ({len(items)})</h2>{blocks}"
        )

    empty_note = (
        '<p style="color:#aaa;text-align:center;font-size:13px;">No relevant tenders this week.</p>'
        if not notices
        else ""
    )

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Tender Intelligence — {name}</title></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
max-width:680px;margin:0 auto;padding:20px;color:#2c3e50;background:#fff;">
<div style="background:#2c3e50;color:white;padding:22px;border-radius:6px;margin-bottom:26px;">
  <div style="font-size:11px;text-transform:uppercase;letter-spacing:2px;opacity:.7;">Tender Intelligence</div>
  <h1 style="margin:4px 0;font-size:20px;">Weekly Digest</h1>
  <div style="opacity:.8;font-size:13px;">{name} · {start} – {end}</div>
</div>
<div style="background:#eaf4fb;border-radius:6px;padding:14px;margin-bottom:22px;font-size:14px;color:#2471a3;">
  <b>{len(notices)} relevant tenders</b> this week —
  <span style="color:{C['HIGH']}">{len(hi)} high</span>,
  <span style="color:{C['MEDIUM']}">{len(me)} medium</span>,
  {len(lo)} low priority.
</div>
{section('High Priority', hi, 1)}
{section('Medium Priority', me, len(hi) + 1)}
{section('Low Priority', lo, len(hi) + len(me) + 1)}
{empty_note}
<div style="margin-top:36px;padding-top:16px;border-top:1px solid #eee;
font-size:12px;color:#aaa;text-align:center;">Generated {now} · Tender Intelligence</div>
</body></html>"""


def save(html, path):
    Path(path).write_text(html, encoding="utf-8")
    print(f"Digest saved: {path}")


def send_email(html, to_email, subject):
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "465"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    if not smtp_user:
        print("SMTP not configured — skipping email")
        return False
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = to_email
    msg.attach(MIMEText(html, "html", "utf-8"))
    try:
        with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, to_email, msg.as_string())
        print(f"Email sent → {to_email}")
        return True
    except Exception as exc:  # noqa: BLE001 - SMTP failures must not kill the digest
        print(f"Email error: {exc}")
        return False
