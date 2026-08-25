import os
from dotenv import load_dotenv
import razorpay

load_dotenv()

KEY_ID = os.getenv("RAZORPAY_KEY_ID")
KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

client = razorpay.Client(auth=(KEY_ID, KEY_SECRET))


def test_connection():
    """Quick sanity check — hits Razorpay's Orders API to confirm credentials work."""
    orders = client.order.all({"count": 1})
    print("Connected to Razorpay. Sample response:", orders)


if __name__ == "__main__":
    test_connection()