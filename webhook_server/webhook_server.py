"""
Front-Tech — Complete Backend Server
Handles: User registration, PayPal webhooks, Login, Email
"""

import os
import json
import random
import string
import smtplib
import hashlib
import hmac
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, redirect, session
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'default-secret-key-change-me')

# ── Configuration ──
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
FROM_EMAIL = os.getenv("FROM_EMAIL", SMTP_USER)
STREAMLIT_URL = os.getenv("STREAMLIT_URL", "https://churn-predictor.streamlit.app")
PAYPAL_EMAIL = os.getenv("PAYPAL_EMAIL")
CLIENTS_FILE = "clients.json"

# Plan prices
PLAN_PRICES = {
    "Starter": "49.00",
    "Pro": "149.00",
    "Enterprise": "299.00"
}

# ========== HELPER FUNCTIONS ==========

def generate_password(length=12):
    chars = string.ascii_letters + string.digits + "!@#$"
    return ''.join(random.choices(chars, k=length))

def load_clients():
    if os.path.exists(CLIENTS_FILE):
        with open(CLIENTS_FILE) as f:
            return json.load(f)
    return {}

def save_clients(clients):
    with open(CLIENTS_FILE, "w") as f:
        json.dump(clients, f, indent=2)
    print(f"[{datetime.now():%H:%M:%S}] Saved {len(clients)} clients")

def make_username(email):
    base = email.split("@")[0].lower()
    base = ''.join(c for c in base if c.isalnum() or c == '_')
    clients = load_clients()
    username, counter = base, 1
    while username in clients:
        username = f"{base}{counter}"
        counter += 1
    return username

def send_welcome_email(to_email, name, username, password, plan):
    """Send welcome email with login credentials"""
    if not SMTP_USER or not SMTP_PASS:
        print(f"[EMAIL SKIPPED] Would send: {username} / {password} to {to_email}")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Welcome to Front-Tech — Your {plan} Plan is Active"
    msg["From"] = f"Front-Tech <{FROM_EMAIL}>"
    msg["To"] = to_email

    html = f"""
    <div style="font-family:sans-serif;max-width:560px;margin:0 auto;
                background:#04080f;color:#e8edf5;padding:40px;border-radius:12px">
      <h1 style="color:#fff;margin-bottom:8px">
        Welcome to <span style="color:#00e5a0">Front-Tech</span> 🎉
      </h1>
      <p style="color:#6b7a99;margin-bottom:32px">
        Your <strong style="color:#fff">{plan}</strong> plan is now active.
      </p>
      <div style="background:#0e1a2e;border:1px solid #1a2640;
                  border-radius:10px;padding:24px;margin-bottom:32px">
        <p style="color:#6b7a99;font-size:.85rem;margin-bottom:16px">
          YOUR LOGIN CREDENTIALS
        </p>
        <p style="margin-bottom:8px"><strong>Username:</strong> {username}</p>
        <p style="margin-bottom:8px"><strong>Password:</strong> {password}</p>
        <p><strong>Login URL:</strong> <a href="{STREAMLIT_URL}" style="color:#00e5a0">{STREAMLIT_URL}</a></p>
      </div>
      <a href="{STREAMLIT_URL}"
         style="display:inline-block;background:#00e5a0;color:#000;
                padding:14px 32px;border-radius:8px;text-decoration:none;
                font-weight:700">
        Launch Dashboard →
      </a>
      <p style="margin-top:32px;font-size:.85rem;color:#6b7a99">
        Questions? Reply to this email.<br/>— The Front-Tech Team
      </p>
    </div>
    """
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(FROM_EMAIL, to_email, msg.as_string())
        print(f"[EMAIL SENT] → {to_email}")
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")

# ========== API ENDPOINTS ==========

@app.route('/api/signup', methods=['POST'])
def api_signup():
    """Step 1: User registers, gets PayPal payment link"""
    data = request.json
    email = data.get('email')
    name = data.get('name')
    plan = data.get('plan', 'Starter')
    
    # Validate plan
    if plan not in PLAN_PRICES:
        return jsonify({"error": "Invalid plan"}), 400
    
    # Check if user already exists
    clients = load_clients()
    for username, info in clients.items():
        if info.get('email') == email:
            if info.get('status') == 'active':
                return jsonify({"error": "Email already registered. Please login."}), 400
            elif info.get('status') == 'pending':
                # Resend payment link
                price = PLAN_PRICES.get(plan)
                paypal_url = f"https://www.paypal.com/cgi-bin/webscr?cmd=_xclick&business={PAYPAL_EMAIL}&item_name={plan} Plan&amount={price}&currency_code=USD&notify_url={request.host_url}paypal-webhook&return_url={request.host_url}api/auth-success?email={email}"
                return jsonify({"payment_url": paypal_url})
    
    # Create pending user
    username = make_username(email)
    temp_password = generate_password()
    
    clients[username] = {
        "name": name,
        "email": email,
        "plan": plan,
        "status": "pending",
        "temp_password": temp_password,
        "created": datetime.now().isoformat()
    }
    save_clients(clients)
    
    # Create PayPal payment URL
    price = PLAN_PRICES.get(plan)
    paypal_url = f"https://www.paypal.com/cgi-bin/webscr?cmd=_xclick&business={PAYPAL_EMAIL}&item_name={plan} Plan&amount={price}&currency_code=USD&notify_url={request.host_url}paypal-webhook&return_url={request.host_url}api/auth-success?email={email}"
    
    return jsonify({
        "payment_url": paypal_url,
        "message": "Redirecting to PayPal..."
    })

@app.route('/api/login', methods=['POST'])
def api_login():
    """Step 3: User logs in, gets redirect to Streamlit dashboard"""
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    clients = load_clients()
    
    for username, info in clients.items():
        if info.get('email') == email:
            # Check if user is active
            if info.get('status') != 'active':
                return jsonify({"error": "Account not activated. Please complete payment."}), 401
            
            # Check password (simple for now - use bcrypt in production)
            stored_password = info.get('password')
            if stored_password and stored_password == password:
                # Create session
                session['username'] = username
                session['email'] = email
                session['plan'] = info.get('plan')
                
                # Return Streamlit dashboard URL with auth token
                return jsonify({
                    "dashboard_url": f"{STREAMLIT_URL}?username={username}&email={email}&token={hashlib.md5(f'{email}{username}'.encode()).hexdigest()[:16]}",
                    "success": True
                })
            elif info.get('temp_password') == password:
                # Demo or pending user with temp password
                return jsonify({
                    "dashboard_url": f"{STREAMLIT_URL}?username={username}&email={email}&demo=true",
                    "success": True
                })
    
    return jsonify({"error": "Invalid email or password"}), 401

@app.route('/api/auth-success', methods=['GET'])
def auth_success():
    """After PayPal payment, redirect user to login"""
    email = request.args.get('email')
    return redirect(f"{os.getenv('NETLIFY_URL', 'https://your-site.netlify.app')}/login-success?email={email}")

@app.route('/paypal-webhook', methods=['POST'])
def paypal_webhook():
    """Step 2: PayPal confirms payment, activates user"""
    data = request.form.to_dict()
    
    print(f"[PAYPAL WEBHOOK] Received: {data}")
    
    payment_status = data.get('payment_status')
    payer_email = data.get('payer_email')
    item_name = data.get('item_name')
    txn_id = data.get('txn_id')
    
    if payment_status != 'Completed':
        return jsonify({"status": "ignored"}), 200
    
    # Find pending user by email
    clients = load_clients()
    updated = False
    
    for username, info in clients.items():
        if info.get('email') == payer_email and info.get('status') == 'pending':
            # Activate user
            permanent_password = generate_password()
            info['status'] = 'active'
            info['password'] = permanent_password
            info['transaction_id'] = txn_id
            info['payment_date'] = datetime.now().isoformat()
            info['plan'] = item_name.replace(' Plan', '')
            
            save_clients(clients)
            
            # Send welcome email with credentials
            send_welcome_email(
                payer_email,
                info.get('name', payer_email),
                username,
                permanent_password,
                info.get('plan', 'Pro')
            )
            
            updated = True
            print(f"[ACTIVATED] {username} - {payer_email}")
            break
    
    if not updated:
        print(f"[WARNING] No pending user found for {payer_email}")
    
    return jsonify({"status": "success"}), 200

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "healthy",
        "clients": len(load_clients()),
        "active_clients": len([c for c in load_clients().values() if c.get('status') == 'active'])
    }), 200

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"🚀 Front-Tech API server running on port {port}")
    print(f"📁 Clients file: {CLIENTS_FILE}")
    print(f"📧 Email: {'✅ ENABLED' if SMTP_USER and SMTP_PASS else '❌ DISABLED'}")
    app.run(host="0.0.0.0", port=port, debug=False)
