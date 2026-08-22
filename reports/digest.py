from datetime import datetime
from pathlib import Path
import smtplib, os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

C = {"HIGH":"#c0392b","MEDIUM":"#e67e22","LOW":"#7f8c8d"}
BG= {"HIGH":"#fdf2f2","MEDIUM":"#fef9f0","LOW":"#f8f9fa"}

def _block(n, idx):
    imp = n.get("impact","MEDIUM"); c = C[imp]; bg = BG[imp]
    val = n.get("estimated_value")
    val_s = f"{val:,.0f} {n.get('currency','EUR')}" if val else "—"
    import json
    cpvs = n.get("cpv_codes",[])
    if isinstance(cpvs, str):
        try: cpvs = json.loads(cpvs)
        except: cpvs = []
    return f"""
<div style="margin-bottom:18px;border-left:4px solid {c};background:{bg};
            padding:14px;border-radius:4px;">
  <span style="background:{c};color:white;font-size:11px;padding:2px 7px;
               border-radius:3px;font-weight:bold;">{imp}</span>
  <span style="color:#999;font-size:12px;float:right;">#{idx} · {n.get('buyer_country','')}</span>
  <h3 style="margin:10px 0 6px;font-size:15px;">
    <a href="{n.get('url','#')}" style="color:#2c3e50;text-decoration:none;">
      {n.get('title','No title')[:120]}
    </a>
  </h3>
  <p style="margin:0 0 8px;color:#444;font-size:14px;line-height:1.5;">
    {n.get('summary_en') or n.get('description','')[:280]}
  </p>
  {"<p style='margin:0 0 6px;color:#666;font-size:13px;font-style:italic;'>" + n.get('summary_pl','') + "</p>" if n.get('summary_pl') else ''}
  <span style="font-size:13px;color:#555;">
    <b>Value:</b> {val_s} &nbsp;·&nbsp;
    <b>Deadline:</b> {n.get('deadline','—')} &nbsp;·&nbsp;
    <b>CPV:</b> {', '.join(str(c) for c in cpvs[:2]) or '—'}
  </span>
  <br><a href="{n.get('url','#')}" style="font-size:13px;color:#2980b9;">→ Full tender</a>
</div>"""

def generate(client_name, notices, period_from, period_to, client_email=""):
    now = datetime.utcnow().strftime("%d %b %Y")
    hi = [n for n in notices if n.get("impact")=="HIGH"]
    me = [n for n in notices if n.get("impact")=="MEDIUM"]
    lo = [n for n in notices if n.get("impact")=="LOW"]

    def sec(label, items, start):
        if not items: return ""
        blocks = "".join(_block(n, start+i) for i,n in enumerate(items))
        return f"<h2 style='margin:28px 0 10px;font-size:15px;text-transform:uppercase;letter-spacing:1px;color:#7f8c8d;border-bottom:1px solid #eee;padding-bottom:5px;'>{label} ({len(items)})</h2>{blocks}"

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Tender Intelligence — {client_name}</title></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
max-width:680px;margin:0 auto;padding:20px;color:#2c3e50;background:#fff;">
<div style="background:#2c3e50;color:white;padding:22px;border-radius:6px;margin-bottom:26px;">
  <div style="font-size:11px;text-transform:uppercase;letter-spacing:2px;opacity:.7;">Tender Intelligence</div>
  <h1 style="margin:4px 0;font-size:20px;">Weekly Digest</h1>
  <div style="opacity:.8;font-size:13px;">{client_name} · {period_from} – {period_to}</div>
</div>
<div style="background:#eaf4fb;border-radius:6px;padding:14px;margin-bottom:22px;font-size:14px;color:#2471a3;">
  <b>{len(notices)} relevant tenders</b> this week —
  <span style="color:{C['HIGH']}">{len(hi)} high</span>,
  <span style="color:{C['MEDIUM']}">{len(me)} medium</span>,
  {len(lo)} low priority.
</div>
{sec('High Priority', hi, 1)}
{sec('Medium Priority', me, len(hi)+1)}
{sec('Low Priority', lo, len(hi)+len(me)+1)}
{'<p style="color:#aaa;text-align:center;font-size:13px;">No relevant tenders this week.</p>' if not notices else ''}
<div style="margin-top:36px;padding-top:16px;border-top:1px solid #eee;
font-size:12px;color:#aaa;text-align:center;">Generated {now} · Tender Intelligence</div>
</body></html>"""

def save(html, path):
    Path(path).write_text(html, encoding="utf-8")
    print(f"Digest saved: {path}")

def send_email(html, to_email, subject):
    smtp_host = os.getenv("SMTP_HOST","smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT","465"))
    smtp_user = os.getenv("SMTP_USER","")
    smtp_pass = os.getenv("SMTP_PASS","")
    if not smtp_user:
        print("SMTP not configured — skipping email")
        return False
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject; msg["From"] = smtp_user; msg["To"] = to_email
    msg.attach(MIMEText(html, "html", "utf-8"))
    try:
        with smtplib.SMTP_SSL(smtp_host, smtp_port) as s:
            s.login(smtp_user, smtp_pass)
            s.sendmail(smtp_user, to_email, msg.as_string())
        print(f"Email sent → {to_email}")
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False
