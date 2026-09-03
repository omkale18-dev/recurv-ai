import os, logging, urllib.request, urllib.parse, base64, json, urllib.error
from dotenv import load_dotenv
load_dotenv()
logger = logging.getLogger(__name__)

def send_whatsapp_recovery_message(to_phone: str = '', message: str = '', amount: float = 1499.0, link_url: str = 'https://rzp.io/rzp/FZeBaY8') -> dict:
    account_sid = os.getenv('TWILIO_ACCOUNT_SID', '').strip()
    auth_token = os.getenv('TWILIO_AUTH_TOKEN', '').strip()
    from_number = os.getenv('TWILIO_WHATSAPP_FROM', 'whatsapp:+14155238886').strip()
    target_phone = to_phone.strip() or os.getenv('CUSTOMER_WHATSAPP_PHONE', '').strip()
    content_sid = os.getenv('TWILIO_CONTENT_SID', '').strip()
    
    if not account_sid or not auth_token or not target_phone:
        return {'status': 'simulated', 'reason': 'Twilio credentials not in .env', 'to': target_phone, 'message': message}
    
    if not target_phone.startswith('whatsapp:'):
        target_phone = f'whatsapp:{target_phone}'
    if not from_number.startswith('whatsapp:'):
        from_number = f'whatsapp:{from_number}'
        
    url = f'https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json'
    
    post_params = {
        'From': from_number,
        'To': target_phone,
    }
    
    if content_sid:
        post_params['ContentSid'] = content_sid
        post_params['ContentVariables'] = json.dumps({'1': f"INR {amount:,.0f}", '2': link_url})
    else:
        post_params['Body'] = message
        
    data = urllib.parse.urlencode(post_params).encode('utf-8')
    req = urllib.request.Request(url, data=data, method='POST')
    creds = f'{account_sid}:{auth_token}'
    req.add_header('Authorization', f'Basic {base64.b64encode(creds.encode()).decode()}')
    req.add_header('Content-Type', 'application/x-www-form-urlencoded')
    
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            res_json = json.loads(resp.read().decode('utf-8'))
            sid = res_json.get('sid')
            logger.info('WhatsApp dispatched to %s SID=%s', target_phone, sid)
            return {'status': 'success', 'message_sid': sid, 'to': target_phone}
    except urllib.error.HTTPError as exc:
        err_msg = exc.read().decode('utf-8')
        try:
            err_json = json.loads(err_msg)
            detailed = f"Twilio Error {err_json.get('code')}: {err_json.get('message')}"
        except Exception:
            detailed = err_msg
        logger.error('WhatsApp HTTP error: %s', detailed)
        return {'status': 'error', 'error': detailed}
    except Exception as exc:
        logger.error('WhatsApp error: %s', exc)
        return {'status': 'error', 'error': str(exc)}
