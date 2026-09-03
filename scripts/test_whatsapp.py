import os
import sys
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv
from app.notifications.whatsapp import send_whatsapp_recovery_message

load_dotenv()

print("=" * 60)
print("?? TESTING WHATSAPP NOTIFICATION INTEGRATION")
print("=" * 60)

sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
phone = os.getenv("CUSTOMER_WHATSAPP_PHONE", "").strip()

print(f"Twilio Account SID : {sid[:8]}... (Configured: {bool(sid)})")
print(f"Twilio Auth Token   : {'*' * 8 if token else 'Not configured'}")
print(f"Target Phone Number : {phone or 'Not configured'}")
print("-" * 60)

if not sid or not token or not phone:
    print("??  TWILIO CREDENTIALS NOT FOUND IN .env")
    print("To enable live WhatsApp to your phone, add to .env:")
    print("TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
    print("TWILIO_AUTH_TOKEN=your_auth_token_here")
    print("CUSTOMER_WHATSAPP_PHONE=+919876543210")
else:
    test_msg = "?? Test from Revenue Recovery Agent: Your WhatsApp notification integration is WORKING!"
    print(f"Sending test WhatsApp message to {phone}...")
    res = send_whatsapp_recovery_message(to_phone=phone, message=test_msg)
    print("Result:", res)
    if res.get("status") == "success":
        print("? SUCCESS! Check your phone on WhatsApp.")
    else:
        print("? Error dispatching message:", res.get("error"))
print("=" * 60)
