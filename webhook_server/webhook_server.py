"""
Front-Tech — Webhook Server with Resend Email
"""
import os
import json
import random
import string
import urllib.request
import urllib.parse
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from dotenv import load_dotenv
import requests  # still useful for other potential calls
from resend import Resend  # ← new import

load_dotenv()
app = Flask(__name__)

# ── Configuration ──
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@front-tech.io")
DASHBOARD_URL = os.getenv("STREAMLIT_URL", "https://your-streamlit-url.up.railway.app")  # ← use your actual variable name
PAYPAL_EMAIL = os.getenv("PAYPAL_EMAIL", "")
PAYPAL_MODE = os.getenv("PAYPAL_MODE", "sandbox")
SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret")
CLIENTS_FILE = "clients.json"

# Bank details (for manual transfer fallback)
BANK_NAME = os.getenv("BANK_NAME", "Access Bank Botswana")
BANK_ACCOUNT_NAME = os.getenv("BANK_ACCOUNT_NAME", "Front-Tech (PTY) Ltd")
BANK_ACCOUNT_NUMBER = os.getenv("BANK_ACCOUNT_NUMBER", "1234567890")
BANK_SWIFT_CODE = os.getenv("BANK_SWIFT_CODE", "ABBLBWGX")

# PayPal URLs
if PAYPAL_MODE == "sandbox":
    PAYPAL_URL = "https://www.sandbox.paypal.com/cgi-bin/webscr"
    IPN_VERIFY_URL = "https://ipnpb.sandbox.paypal.com/cgi-bin/webscr"
else:
    PAYPAL_URL = "https://www.paypal.com/cgi-bin/webscr"
    IPN_VERIFY_URL = "https://ipnpb.paypal.com/cgi-bin/webscr"

PLAN_PRICES = {"Starter": "49.00", "Pro": "149.00", "Enterprise": "299.00"}

# Initialize Resend client once
resend_client = None
if RESEND_API_KEY:
    resend_client = Resend(RESEND_API_KEY)

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

# ========== EMAIL FUNCTIONS (Resend) ==========
def send_email(to_email, subject, html_content):
    """Send email using Resend API"""
    if not resend_client:
        print(f"[EMAIL SKIPPED] No RESEND_API_KEY. Would send to {to_email}")
        return False
    
    try:
        resend_client.Emails.send({
            "from": FROM_EMAIL,
            "to": to_email,
            "subject": subject,
            "html": html_content
        })
        print(f"[EMAIL SENT via Resend] → {to_email}")
        return True
    except Exception as e:
        print(f"[RESEND ERROR] {str(e)}")
        return False

def send_welcome_email(to_email, name, username, password, plan, payment_method="paypal"):
    """Send welcome email with credentials"""
    html = f"""
    <div style="font-family:sans-serif;max-width:560px;margin:0 auto;background:#04080f;color:#e8edf5;padding:40px;border-radius:12px">
      <h1 style="color:#fff">Welcome to <span style="color:#00e5a0">Front-Tech</span>! 🎉</h1>
      <p>Hi <strong>{name}</strong>, your <strong>{plan}</strong> plan is now active.</p>
      <div style="background:#0e1a2e;border:1px solid #1a2640;border-radius:10px;padding:24px;margin:24px 0">
        <p><strong>Dashboard URL:</strong> <a href="{DASHBOARD_URL}" style="color:#00e5a0">{DASHBOARD_URL}</a></p>
        <p><strong>Username:</strong> <code>{username}</code></p>
        <p><strong>Password:</strong> <code>{password}</code></p>
      </div>
      <p>Payment Method: {payment_method.capitalize()}</p>
      <a href="{DASHBOARD_URL}" style="display:inline-block;background:#00e5a0;color:#000;padding:14px 32px;border-radius:8px;text-decoration:none">Launch Dashboard →</a>
      <p style="margin-top:24px;font-size:0.9rem;color:#aaa;">If you didn't request this, please ignore this email.</p>
    </div>"""
    return send_email(to_email, f"Welcome to Front-Tech — Your {plan} Plan Activated", html)

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

def provision_client(name, email, plan, amount="", payment_method="paypal"):
    clients = load_clients()
    username = make_username(name, email)
    password = generate_password()
    
    clients[username] = {
        "password": password,           # ← plain text (we'll improve with JWT later)
        "name": name,
        "email": email,
        "plan": plan,
        "amount": amount,
        "status": "active",
        "payment_method": payment_method,
        "created": datetime.now().isoformat()
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
    return jsonify({
        "status": "ok",
        "clients": len(load_clients()),
        "paypal_mode": PAYPAL_MODE,
        "email_provider": "Resend" if RESEND_API_KEY else "Not configured"
    })

@app.route('/api/demo', methods=['POST'])
def api_demo():
    data = request.json
    name = data.get('name')
    email = data.get('email')
    
    if not name or not email:
        return jsonify({"error": "Name and email required"}), 400
    
    clients = load_clients()
    for info in clients.values():
        if info.get('email') == email and info.get('status') in ['active', 'demo']:
            return jsonify({"error": "You already have an account. Please login."}), 400
    
    username = make_username(name, email)
    demo_password = generate_password(8)
    
    clients[username] = {
        "name": name,
        "email": email,
        "plan": "Demo",
        "status": "demo",
        "demo_access": True,
        "temp_password": demo_password,
        "created": datetime.now().isoformat()
    }
    save_clients(clients)
    
    demo_html = f"""
    <h1>Front-Tech Demo Access</h1>
    <p>Hi {name}, your 7-day demo account is ready!</p>
    <p><strong>Dashboard:</strong> <a href="{DASHBOARD_URL}">{DASHBOARD_URL}</a></p>
    <p><strong>Username:</strong> {username}</p>
    <p><strong>Password:</strong> {demo_password}</p>
    <p>This demo expires in 7 days. Upgrade anytime on our website.</p>"""
    
    send_email(email, "Your Front-Tech Demo Access is Ready", demo_html)
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
    
    clients = load_clients()
    username = make_username(name, email)
    temp_password = generate_password()
    
    clients[username] = {
        "name": name,
        "email": email,
        "plan": plan,
        "status": "pending",
        "payment_method": payment_method,
        "temp_password": temp_password,
        "created": datetime.now().isoformat()
    }
    save_clients(clients)
    
    if not PAYPAL_EMAIL:
        return jsonify({"error": "PayPal not configured. Please use bank transfer."}), 400
    
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
    bwp_amount = float(price) * 13.5  # approximate rate
    
    bank_html = f"""
    <h2>Bank Transfer Instructions - {plan} Plan</h2>
    <p>Hi {name}, please make a transfer for:</p>
    <ul>
      <li><strong>Bank:</strong> {BANK_NAME}</li>
      <li><strong>Account Name:</strong> {BANK_ACCOUNT_NAME}</li>
      <li><strong>Account Number:</strong> {BANK_ACCOUNT_NUMBER}</li>
      <li><strong>SWIFT/BIC:</strong> {BANK_SWIFT_CODE}</li>
      <li><strong>Amount:</strong> BWP {bwp_amount:.2f} (≈ USD ${price})</li>
      <li><strong>Reference:</strong> CHURN-{plan[:3]}-{name[:5].upper()}</li>
    </ul>
    <p>We'll activate your account within 24 hours after confirmation.</p>
    <p>Questions? Reply to this email.</p>"""
    
    send_email(email, f"Bank Transfer Details - {plan} Plan", bank_html)
    return jsonify({"message": "Bank transfer instructions sent to your email"})

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
    print(f"🚀 Front-Tech server starting on port {port}")
    print(f"📧 Email: {'✅ Resend' if RESEND_API_KEY else '❌ Not configured'}")
    print(f"💰 PayPal: {'✅' if PAYPAL_EMAIL else '❌'} ({PAYPAL_MODE})")
    print(f"📊 Dashboard: {DASHBOARD_URL}")
    app.run(host="0.0.0.0", port=port, debug=False)
