import os
import secrets
from flask import Flask, render_template, request, jsonify, session
from clickpesa import ClickPesaClient, Currency
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

app = Flask(__name__)
app.secret_key = 'test-payment-secret-key'

# ==================== SANIDI CLIENT WA CLICKPESA ====================
def get_client():
    return ClickPesaClient(
        client_id=os.environ.get('CLICKPESA_CLIENT_ID'),
        api_key=os.environ.get('CLICKPESA_API_KEY'),
        environment='sandbox'   # 'production' for real money
    )

# ==================== ROUTES ====================
@app.route('/')
def index():
    return render_template('payment_form.html')

@app.route('/initiate', methods=['POST'])
def initiate():
    """Anzisha malipo kulingana na data kutoka form."""
    amount = request.form.get('amount')
    phone = request.form.get('phone')
    provider = request.form.get('provider')   # 'VODACOM', 'TIGO', 'AIRTEL', 'HALOTEL'
    
    if not amount or not phone or not provider:
        return jsonify({'error': 'Tafadhali jaza sehemu zote'}), 400
    
    # Tengeneza order reference ya kipekee
    order_ref = f"TEST_{secrets.token_hex(8)}"
    
    try:
        client = get_client()
        # Anzisha malipo
        transaction = client.initiate_ussd_push(
            amount=str(amount),
            currency=Currency.TZS,
            order_reference=order_ref,
            phone_number=phone
        )
        # Hifadhi order_ref kwenye session kwa ajili ya kuangalia status
        session['last_order'] = order_ref
        return jsonify({
            'success': True,
            'message': f'Malipo yameanzishwa kwa {provider}. Tafadhali angalia simu yako na ingiza PIN.',
            'order_ref': order_ref
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/status/<order_ref>')
def status(order_ref):
    """Angalia hali ya malipo."""
    try:
        client = get_client()
        result = client.query_payment_status(order_ref)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5001)
