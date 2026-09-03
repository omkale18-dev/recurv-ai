import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv
from app.notifications.email_service import send_recovery_email

load_dotenv()

print("=" * 60)
print("EMAIL RECOVERY NOTIFICATION TEST")
print("=" * 60)

smtp_user = os.getenv("SMTP_USER", "").strip()
smtp_pass = os.getenv("SMTP_PASS", "").strip()
customer_email = os.getenv("CUSTOMER_EMAIL", "").strip() or smtp_user

print(f"SMTP User (Sender)  : {smtp_user or 'Not configured'}")
print(f"SMTP Password       : {'*' * 8 if smtp_pass else 'Not configured'}")
print(f"Customer Email (To) : {customer_email or 'Not configured'}")
print("-" * 60)

if not smtp_user or not smtp_pass:
    print("SMTP CREDENTIALS NOT CONFIGURED IN .env")
else:
    print(f"Sending test recovery email to {customer_email}...")
    res = send_recovery_email(
        to_email=customer_email,
        amount=1499.0,
        decline_reason="expired_card",
        payment_url="https://rzp.io/rzp/FZeBaY8"
    )
    print("Result:", res)
    if res.get("status") == "success":
        print("SUCCESS! Check your Gmail inbox for the recovery email.")
    else:
        print("Error sending email:", res.get("error"))
print("=" * 60)