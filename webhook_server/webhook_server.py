"""
Front-Tech — Complete Webhook Server
"""

import os
import json
import random
import string
import smtplib
import urllib.request
import urllib.parse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

# ── Configuration ──
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", SMTP_USER)
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "https://your-streamlit.streamlit.app")
PAYPAL_EMAIL = os.getenv("PAYPAL_EMAIL", "")
PAYPAL_MODE = os.getenv("PAYPAL_MODE", "sandbox")
SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret")
CLIENTS_FILE = "clients.json"

# Bank details
BANK_NAME = os.getenv("BANK_NAME", "Access Bank Botswana")
BANK_ACCOUNT_NAME = os.getenv("BANK_ACCOUNT_NAME", "Front-Tech (PTY) Ltd")
BANK_ACCOUNT_NUMBER = os.getenv("BANK_ACCOUNT_NUMBER", "1234567890")
BANK_SWIFT_CODE = os.getenv("BANK_SWIFT_CODE", "ABBLBWGX")

# PayPal URLs
if PAYPAL_MODE == "sandbox":
    PAYPAL_URL = "https://www.sandbox.paypal.com/cgi-bin/webscr"
    IPN_VERIFY_URL = "https://ipnpb.sandbox.paypal.com/cgi-bin/webscr"
    print("🔧 PayPal Mode: SANDBOX")
else:
    PAYPAL_URL = "https://www.paypal.com/cgi-bin/webscr"
    IPN_VERIFY_URL = "https://ipnpb.paypal.com/cgi-bin/webscr"
    print("💰 PayPal Mode: LIVE")

PLAN_PRICES = {"Starter": "49.00", "Pro": "149.00", "Enterprise": "299.00"}

# ========== FIND LANDING PAGE ==========

def find_landing_page():
    import os
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    
    possible_paths = [
        os.path.join(parent_dir, 'landing', 'index.html'),
        os.path.join(parent_dir, 'index.html'),
        os.path.join(current_dir, 'landing', 'index.html'),
        os.path.join(current_dir, 'index.html'),
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            folder = os.path.dirname(path)
            filename = os.path.basename(path)
            # Return relative path from webhook_server folder
            if folder == parent_dir:
                return '..', filename
            elif folder == os.path.join(parent_dir, 'landing'):
                return '../landing', filename
            elif folder == current_dir:
                return '.', filename
            elif folder == os.path.join(current_dir, 'landing'):
                return 'landing', filename
    
    return None, None

LANDING_PATH, INDEX_FILE = find_landing_page()
print(f"📁 Landing path: {LANDING_PATH}")
print(f"📄 Index file: {INDEX_FILE}")

# ========== HELPER FUNCTIONS ==========

def generate_password(length=10):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def load_clients():
    if os.path.exists(CLIENTS_FILE):
        with open(CLIENTS_FILE) as f:
            return json.load(f)
    return {}

def save_clients(clients):
    with open(CLIENTS_FILE, "w") as f:
        json.dump(clients, f, indent=2)
    print(f"[{datetime.now():%H:%M:%S}] Saved {len(clients)} clients")

def make_username(name, email):
    base = ''.join(c for c in name.lower().replace(" ", "_") if c.isalnum() or c == '_') or email.split("@")[0]
    clients, u, i = load_clients(), base, 1
    while u in clients:
        u, i = f"{base}{i}", i + 1
    return u

def send_email(to_email, subject, html_content):
    if not SMTP_USER or not SMTP_PASS:
        print(f"[EMAIL SKIPPED] Would send to {to_email}")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"Front-Tech <{FROM_EMAIL}>"
        msg["To"] = to_email
        msg.attach(MIMEText(html_content, "html"))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(FROM_EMAIL, to_email, msg.as_string())
        print(f"[EMAIL SENT] → {to_email}")
        return True
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")
        return False

def send_welcome_email(to_email, name, username, password, plan, payment_method="paypal"):
    html = f"""
    <div style="font-family:sans-serif;max-width:560px;margin:0 auto;background:#04080f;color:#e8edf5;padding:40px;border-radius:12px">
      <h1 style="color:#fff">Welcome to <span style="color:#00e5a0">Front-Tech</span>! 🎉</h1>
      <p>Hi <strong>{name}</strong>, your <strong>{plan}</strong> plan is active.</p>
      <div style="background:#0e1a2e;border:1px solid #1a2640;border-radius:10px;padding:24px;margin:24px 0">
        <p><strong>URL:</strong> <a href="{DASHBOARD_URL}" style="color:#00e5a0">{DASHBOARD_URL}</a></p>
        <p><strong>Username:</strong> <code>{username}</code></p>
        <p><strong>Password:</strong> <code>{password}</code></p>
      </div>
      <p>Payment Method: {payment_method}</p>
      <a href="{DASHBOARD_URL}" style="display:inline-block;background:#00e5a0;color:#000;padding:14px 32px;border-radius:8px;text-decoration:none">Launch Dashboard →</a>
    </div>"""
    return send_email(to_email, f"Welcome to Front-Tech — Your {plan} Plan", html)

def provision_client(name, email, plan, amount="", payment_method="paypal"):
    clients = load_clients()
    username = make_username(name, email)
    password = generate_password()
    clients[username] = {
        "password": password, "name": name, "email": email,
        "plan": plan, "amount": amount, "status": "active",
        "payment_method": payment_method, "created": datetime.now().isoformat()
    }
    save_clients(clients)
    send_welcome_email(email, name, username, password, plan, payment_method)
    return username, password

# ========== ROUTES ==========

@app.route('/')
def serve_landing():
    if not LANDING_PATH or not INDEX_FILE:
        return jsonify({"error": "Landing page not found"}), 404
    try:
        return send_from_directory(LANDING_PATH, INDEX_FILE)
    except Exception as e:
        return jsonify({"error": str(e)}), 404

@app.route('/test')
def test_page():
    return "<h1>Front-Tech Server is Running!</h1>"

@app.route("/health")
def health():
    return jsonify({"status": "ok", "clients": len(load_clients()), "paypal_mode": PAYPAL_MODE})

@app.route('/api/demo', methods=['POST'])
def api_demo():
    data = request.json
    name = data.get('name')
    email = data.get('email')
    
    clients = load_clients()
    for username, info in clients.items():
        if info.get('email') == email:
            if info.get('status') == 'active':
                return jsonify({"error": "You already have an account. Please login."}), 400
    
    username = make_username(name, email)
    demo_password = generate_password(8)
    
    clients[username] = {
        "name": name, "email": email, "plan": "Demo", "status": "demo",
        "demo_access": True, "temp_password": demo_password,
        "created": datetime.now().isoformat()
    }
    save_clients(clients)
    
    demo_html = f"""
    <h1>Front-Tech Demo Access</h1>
    <p>Hi {name}, your demo account is ready!</p>
    <p><strong>URL:</strong> {DASHBOARD_URL}</p>
    <p><strong>Username:</strong> {username}</p>
    <p><strong>Password:</strong> {demo_password}</p>
    <p>This demo expires in 7 days.</p>"""
    
    send_email(email, "Your Front-Tech Demo Access", demo_html)
    return jsonify({"success": True, "message": "Demo credentials sent to your email"})

@app.route('/api/signup', methods=['POST'])
def api_signup():
    data = request.json
    name = data.get('name')
    email = data.get('email')
    plan = data.get('plan', 'Starter')
    payment_method = data.get('payment_method', 'paypal')
    
    if plan not in PLAN_PRICES:
        return jsonify({"error": "Invalid plan"}), 400
    
    price = PLAN_PRICES.get(plan)
    
    # Create pending user
    clients = load_clients()
    username = make_username(name, email)
    temp_password = generate_password()
    
    clients[username] = {
        "name": name, "email": email, "plan": plan,
        "status": "pending", "payment_method": payment_method,
        "temp_password": temp_password, "created": datetime.now().isoformat()
    }
    save_clients(clients)
    
    # Check if PayPal email is configured
    if not PAYPAL_EMAIL:
        return jsonify({"error": "PayPal is not configured. Please use bank transfer."}), 400
    
    paypal_url = f"{PAYPAL_URL}?cmd=_xclick&business={PAYPAL_EMAIL}&item_name={plan} Plan&amount={price}&currency_code=USD&notify_url={request.host_url}paypal-ipn&return_url={request.host_url}?payment=success"
    
    return jsonify({"payment_url": paypal_url})

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    clients = load_clients()
    for username, info in clients.items():
        if info.get('email') == email:
            if info.get('status') == 'active' and info.get('password') == password:
                return jsonify({"dashboard_url": f"{DASHBOARD_URL}?username={username}"})
            elif info.get('temp_password') == password:
                return jsonify({"dashboard_url": f"{DASHBOARD_URL}?demo=true"})
    return jsonify({"error": "Invalid credentials"}), 401

@app.route('/api/request-bank-transfer', methods=['POST'])
def request_bank_transfer():
    data = request.json
    name = data.get('name')
    email = data.get('email')
    plan = data.get('plan')
    price = PLAN_PRICES.get(plan, "49.00")
    
    bank_html = f"""
    <h2>Bank Transfer Instructions</h2>
    <p>Hi {name}, please transfer:</p>
    <p><strong>Bank:</strong> {BANK_NAME}</p>
    <p><strong>Account Name:</strong> {BANK_ACCOUNT_NAME}</p>
    <p><strong>Account Number:</strong> {BANK_ACCOUNT_NUMBER}</p>
    <p><strong>SWIFT:</strong> {BANK_SWIFT_CODE}</p>
    <p><strong>Amount:</strong> ${price}</p>
    <p><strong>Reference:</strong> CHURN-{plan[:3]}</p>
    <p>We'll activate your account within 24 hours.</p>"""
    
    send_email(email, f"Bank Transfer Instructions - {plan} Plan", bank_html)
    return jsonify({"message": "Bank transfer details sent to your email"})

@app.route("/paypal-ipn", methods=["POST"])
def paypal_ipn():
    raw = request.get_data(as_text=True)
    try:
        req = urllib.request.Request(
            IPN_VERIFY_URL,
            data=("cmd=_notify-validate&" + raw).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"})
        verified = urllib.request.urlopen(req, timeout=10).read().decode() == "VERIFIED"
    except Exception as e:
        print(f"[IPN ERROR] {e}")
        verified = False
    
    if verified:
        params = dict(urllib.parse.parse_qsl(raw))
        if params.get("payment_status") == "Completed":
            payer_email = params.get("payer_email")
            name = params.get("first_name", "") + " " + params.get("last_name", "")
            amount = float(params.get("mc_gross", 0))
            plan = "Enterprise" if amount >= 299 else "Pro" if amount >= 149 else "Starter"
            
            clients = load_clients()
            for username, info in clients.items():
                if info.get('email') == payer_email and info.get('status') == 'pending':
                    permanent_password = generate_password()
                    info['status'] = 'active'
                    info['password'] = permanent_password
                    info['plan'] = plan
                    save_clients(clients)
                    send_welcome_email(payer_email, name or payer_email, username, permanent_password, plan)
                    break
    return "OK", 200

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    print(f"🚀 Front-Tech server on port {port}")
    print(f"📧 Email: {'✅' if SMTP_USER else '❌'}")
    print(f"💰 PayPal: {'✅' if PAYPAL_EMAIL else '❌'} ({PAYPAL_MODE})")
    app.run(host="0.0.0.0", port=port, debug=False)
