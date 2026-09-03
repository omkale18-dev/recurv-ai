import os
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

def send_recovery_email(to_email: str = "", amount: float = 1499.0, decline_reason: str = "expired_card", payment_url: str = "https://rzp.io/rzp/FZeBaY8") -> dict:
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_pass = os.getenv("SMTP_PASS", "").strip().replace(" ", "")
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    
    target_email = to_email.strip() or os.getenv("CUSTOMER_EMAIL", "").strip() or smtp_user
    
    if not smtp_user or not smtp_pass or not target_email:
        logger.info("[EMAIL NOTE] SMTP credentials or target email not configured. Skipping.")
        return {
            "status": "simulated",
            "reason": "SMTP credentials not configured",
            "to": target_email,
            "payment_url": payment_url
        }
        
    reason_clean = decline_reason.replace("_", " ").title()
    
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[Recurv AI] Action Required: Resolve your ₹{amount:,.0f} subscription payment"
    msg["From"] = f"Recurv AI <{smtp_user}>"
    msg["To"] = target_email
    
    html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body {{ font-family: Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 20px; }}
.container {{ max-width: 560px; margin: 0 auto; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; }}
.header {{ background: #0f172a; padding: 24px; text-align: center; color: #ffffff; }}
.header h1 {{ margin: 0; font-size: 22px; font-weight: 800; letter-spacing: -0.5px; }}
.header h1 span {{ color: #38bdf8; }}
.body {{ padding: 32px 28px; color: #334155; line-height: 1.6; }}
.amount-badge {{ font-size: 28px; font-weight: 800; color: #0f172a; text-align: center; margin: 20px 0; }}
.reason-box {{ background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 12px 16px; color: #991b1b; font-size: 14px; margin-bottom: 24px; }}
.cta-button {{ display: block; width: 240px; margin: 28px auto; padding: 14px 20px; background: #2563eb; color: #ffffff !important; text-align: center; text-decoration: none; font-weight: 700; font-size: 15px; border-radius: 8px; }}
.footer {{ background: #f8fafc; padding: 20px; text-align: center; font-size: 12px; color: #94a3b8; border-top: 1px solid #f1f5f9; }}
</style>
</head>
<body>
<div class="container">
<div class="header">
<h1>Recurv <span>AI</span></h1>
</div>
<div class="body">
<p>Hello,</p>
<p>We noticed that your recent subscription payment could not be processed automatically.</p>
<div class="amount-badge">INR {amount:,.0f}</div>
<div class="reason-box">
<strong>Decline Reason:</strong> {reason_clean}
</div>
<p>To avoid any disruption to your services, please click below to update your payment method via Razorpay secure checkout:</p>
<a href="{payment_url}" class="cta-button" target="_blank">Complete Payment</a>
<p style="font-size: 12px; color: #64748b; text-align: center;">This recovery link will expire in 48 hours.</p>
</div>
<div class="footer">
Secured by Razorpay | Tamper-evident SHA-256 Audit Trail
</div>
</div>
</body>
</html>"""
    
    msg.attach(MIMEText(html_content, "html"))
    
    try:
        server = smtplib.SMTP(smtp_host, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, target_email, msg.as_string())
        server.quit()
        logger.info("[EMAIL DISPATCHED] Successfully sent recovery email to %s", target_email)
        return {
            "status": "success",
            "to": target_email,
            "amount": amount,
            "payment_url": payment_url
        }
    except Exception as exc:
        logger.error("[EMAIL ERROR] Failed to send email: %s", exc)
        return {
            "status": "error",
            "error": str(exc)
        }