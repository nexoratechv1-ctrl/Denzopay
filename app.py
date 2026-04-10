import os
import secrets
import base64
import requests
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = 'pesapal-test-secret-key'

# ==================== PESAPAL CONFIG ====================
PESAPAL_ENV = os.environ.get('PESAPAL_ENVIRONMENT', 'sandbox')
PESAPAL_BASE_URL = {
    'sandbox': 'https://cybqa.pesapal.com/pesapalv3/api',
    'production': 'https://pay.pesapal.com/v3'
}[PESAPAL_ENV]

CONSUMER_KEY = os.environ.get('PESAPAL_CONSUMER_KEY')
CONSUMER_SECRET = os.environ.get('PESAPAL_CONSUMER_SECRET')

# ==================== FUNCTIONS ====================
def get_access_token():
    """Pata Access Token kutoka Pesapal."""
    url = f"{PESAPAL_BASE_URL}/Auth/RequestToken"
    credentials = f"{CONSUMER_KEY}:{CONSUMER_SECRET}"
    encoded = base64.b64encode(credentials.encode()).decode()
    headers = {
        'Authorization': f'Basic {encoded}',
        'Content-Type': 'application/json'
    }
    resp = requests.post(url, headers=headers, json={})
    if resp.status_code == 200:
        return resp.json().get('token')
    else:
        raise Exception(f"Token error: {resp.text}")

def register_ipn():
    """Jisajili IPN URL (kwa ajili ya taarifa za malipo)."""
    token = get_access_token()
    url = f"{PESAPAL_BASE_URL}/URLSetup/RegisterIPN"
    # Tumia ngrok au URL yako halisi ikiwa unajaribu kwenye simu
    ipn_url = url_for('ipn_endpoint', _external=True)
    payload = {
        "url": ipn_url,
        "ipn_notification_type": "GET"
    }
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    resp = requests.post(url, json=payload, headers=headers)
    if resp.status_code == 200:
        return resp.json().get('ipn_id')
    else:
        print(f"IPN registration failed: {resp.text}")
        return None

def initiate_payment(amount, reference, description, phone=None, email=None):
    """Anzisha malipo na urudishe redirect URL."""
    token = get_access_token()
    url = f"{PESAPAL_BASE_URL}/Transactions/SubmitOrderRequest"
    
    # Tarehe ya mwisho (siku 1)
    expiry = (datetime.utcnow() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%S+03:00')
    
    payload = {
        "id": reference,
        "currency": "TZS",
        "amount": amount,
        "description": description,
        "callback_url": url_for('payment_callback', _external=True),
        "notification_id": session.get('ipn_id'),
        "billing_address": {
            "email_address": email or "test@example.com",
            "phone_number": phone or "0712345678",
            "country_code": "TZ",
            "first_name": "Test",
            "last_name": "User"
        },
        "cart": {
            "items": [
                {
                    "name": description,
                    "quantity": 1,
                    "unit_price": amount
                }
            ]
        }
    }
    
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    resp = requests.post(url, json=payload, headers=headers)
    if resp.status_code == 200:
        data = resp.json()
        return data.get('redirect_url')
    else:
        raise Exception(f"Payment initiation error: {resp.text}")

# ==================== ROUTES ====================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/pay', methods=['POST'])
def pay():
    amount = request.form.get('amount')
    phone = request.form.get('phone')
    email = request.form.get('email')
    
    if not amount:
        flash('Please enter amount', 'danger')
        return redirect(url_for('index'))
    
    # Jisajili IPN (kama haijasajiliwa)
    if 'ipn_id' not in session:
        ipn_id = register_ipn()
        if ipn_id:
            session['ipn_id'] = ipn_id
        else:
            flash('Failed to register IPN. Please try again.', 'danger')
            return redirect(url_for('index'))
    
    reference = f"TEST_{secrets.token_hex(8)}"
    session['pending_reference'] = reference
    description = f"Test Payment of {amount} TZS"
    
    try:
        redirect_url = initiate_payment(
            amount=float(amount),
            reference=reference,
            description=description,
            phone=phone,
            email=email
        )
        return redirect(redirect_url)
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')
        return redirect(url_for('index'))

@app.route('/callback')
def payment_callback():
    """Pesapal itamrudisha mtumiaji hapa baada ya malipo."""
    order_tracking_id = request.args.get('OrderTrackingId')
    order_merchant_reference = request.args.get('OrderMerchantReference')
    
    if order_tracking_id:
        flash('Payment processed. We will confirm shortly.', 'info')
        # Unaweza kuangalia status kupitia API ya Pesapal hapa
        return redirect(url_for('status', tracking_id=order_tracking_id))
    else:
        flash('Payment cancelled or failed.', 'warning')
        return redirect(url_for('index'))

@app.route('/status/<tracking_id>')
def status(tracking_id):
    """Angalia hali ya malipo kwa kutumia OrderTrackingId."""
    try:
        token = get_access_token()
        url = f"{PESAPAL_BASE_URL}/Transactions/GetTransactionStatus"
        headers = {'Authorization': f'Bearer {token}'}
        params = {'orderTrackingId': tracking_id}
        resp = requests.get(url, headers=headers, params=params)
        if resp.status_code == 200:
            data = resp.json()
            return jsonify(data)
        else:
            return jsonify({'error': resp.text}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/ipn')
def ipn_endpoint():
    """Pesapal itaitisha URL hii kutoa taarifa ya malipo (Instant Payment Notification)."""
    order_tracking_id = request.args.get('OrderTrackingId')
    order_merchant_reference = request.args.get('OrderMerchantReference')
    
    if order_tracking_id:
        # Unaweza kuhifadhi taarifa kwenye database au log
        print(f"IPN received: Tracking ID={order_tracking_id}, Reference={order_merchant_reference}")
    return 'OK', 200

if __name__ == '__main__':
    app.run(debug=True, port=5002)
