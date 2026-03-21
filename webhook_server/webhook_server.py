"""
Front-Tech Webhook Server (Flask + Resend Email)
"""
import os
import json
import random
import string
import urllib.request
import urllib.parse
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
from resend import Resend

load_dotenv()
app = Flask(__name__)

# Enable CORS for API endpoints (helps with frontend fetch issues)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# ── Configuration ──
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@front-tech.io")
DASHBOARD_URL = os.getenv("STREAMLIT_URL", "https://your-streamlit.up.railway.app")  # ← change to your real Streamlit URL
PAYPAL_EMAIL = os.getenv("PAYPAL_EMAIL", "")
PAYPAL_MODE = os.getenv("PAYPAL_MODE", "sandbox")
SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-key-please")
CLIENTS_FILE = "clients.json"

# Bank details for manual transfer
BANK_NAME = os.getenv("BANK_NAME", "Access Bank Botswana")
BANK_ACCOUNT_NAME = os.getenv("BANK_ACCOUNT_NAME", "Front-Tech (PTY) Ltd")
BANK_ACCOUNT_NUMBER = os.getenv("BANK_ACCOUNT_NUMBER", "1234567890")
BANK_SWIFT_CODE = os.getenv("BANK_SWIFT_CODE", "ABBLBWGX")

# PayPal config
if PAYPAL_MODE == "sandbox":
    PAYPAL_URL = "https://www.sandbox.paypal.com/cgi-bin/webscr"
    IPN_VERIFY_URL = "https://ipnpb.sandbox.paypal.com/cgi-bin/webscr"
else:
    PAYPAL_URL = "https://www.paypal.com/cgi-bin/webscr"
    IPN_VERIFY_URL = "https://ipnpb.paypal.com/cgi-bin/webscr"

PLAN_PRICES = {"Starter": "49.00", "Pro": "149.00", "Enterprise": "299.00"}

# Resend client
resend_client = None
if RESEND_API_KEY:
    resend_client = Resend(RESEND_API_KEY)

# ── Landing page location ──
def find_landing_page():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    possible = [
        os.path.join(parent_dir, 'landing', 'index.html'),
        os.path.join(parent_dir, 'index.html'),
        os.path.join(current_dir, 'landing', 'index.html'),
        os.path.join(current_dir, 'index.html'),
    ]
    for path in possible:
        if os.path.exists(path):
            folder = os.path.dirname(path)
            filename = os.path.basename(path)
            if folder == parent_dir:
                return '..', filename
            elif 'landing' in folder:
                return '../landing', filename
            else:
                return '.', filename
    return None, None

LANDING_PATH, INDEX_FILE = find_landing_page()
print(f"📁 Landing path: {LANDING_PATH or 'NOT FOUND'}")
print(f"📄 Index file: {INDEX_FILE or 'NOT FOUND'}")

# ── Email ──
def send_email(to_email, subject, html_content):
    if not resend_client:
        print(f"[EMAIL SKIPPED] No Resend key → {to_email}")
        return False
    try:
        resend_client.Emails.send({
            "from": FROM_EMAIL,
            "to": to_email,
            "subject": subject,
            "html": html_content
        })
        print(f"[EMAIL SENT] → {to_email}")
        return True
    except Exception as e:
        print(f"[RESEND ERROR] {str(e)}")
        return False

def send_welcome_email(to_email, name, username, password, plan, payment_method="paypal"):
    html = f"""
    <div style="font-family:sans-serif; max-width:560px; margin:0 auto; background:#04080f; color:#e8edf5; padding:40px; border-radius:12px;">
      <h1 style="color:#fff">Welcome to <span style="color:#00e5a0">Front-Tech</span>!</h1>
      <p>Hi <strong>{name}</strong>, your <strong>{plan}</strong> plan is active.</p>
      <div style="background:#0e1a2e; border:1px solid #1a2640; border-radius:10px; padding:24px; margin:24px 0;">
        <p><strong>Dashboard:</strong> <a href="{DASHBOARD_URL}" style="color:#00e5a0">{DASHBOARD_URL}</a></p>
        <p><strong>Username:</strong> <code>{username}</code></p>
        <p><strong>Password:</strong> <code>{password}</code></p>
      </div>
      <p>Payment: {payment_method.capitalize()}</p>
      <a href="{DASHBOARD_URL}" style="display:inline-block; background:#00e5a0; color:#000; padding:14px 32px; border-radius:8px; text-decoration:none;">Open Dashboard</a>
    </div>"""
    send_email(to_email, f"Front-Tech – {plan} Plan Active", html)

# ── Helpers ──
def generate_password(length=10):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def load_clients():
    if os.path.exists(CLIENTS_FILE):
        with open(CLIENTS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_clients(clients):
    with open(CLIENTS_FILE, 'w') as f:
        json.dump(clients, f, indent=2)
    print(f"[{datetime.now():%H:%M:%S}] Saved {len(clients)} clients")

def make_username(name, email):
    base = ''.join(c for c in name.lower().replace(" ", "_") if c.isalnum() or c == '_') or email.split("@")[0]
    clients = load_clients()
    u, i = base, 1
    while u in clients:
        u = f"{base}{i}"
        i += 1
    return u

# ── Routes ──
@app.route('/')
def serve_landing():
    if not LANDING_PATH or not INDEX_FILE:
        return jsonify({"error": "Landing page not found"}), 404
    return send_from_directory(LANDING_PATH, INDEX_FILE)

@app.route('/health')
def health():
    return jsonify({
        "status": "ok",
        "port": os.getenv("PORT", "unknown"),
        "email": "Resend" if RESEND_API_KEY else "disabled",
        "clients": len(load_clients())
    })

@app.route('/api/demo', methods=['POST'])
def api_demo():
    data = request.json or {}
    name = data.get('name')
    email = data.get('email')
    if not name or not email:
        return jsonify({"error": "Name and email required"}), 400

    clients = load_clients()
    if any(info.get('email') == email for info in clients.values()):
        return jsonify({"error": "Email already registered"}), 400

    username = make_username(name, email)
    password = generate_password(8)

    clients[username] = {
        "name": name, "email": email, "plan": "Demo",
        "status": "demo", "temp_password": password,
        "created": datetime.now().isoformat()
    }
    save_clients(clients)

    html = f"""
    <h2>Front-Tech Demo Ready</h2>
    <p>Hello {name},</p>
    <p><strong>Dashboard:</strong> {DASHBOARD_URL}</p>
    <p><strong>Username:</strong> {username}</p>
    <p><strong>Password:</strong> {password}</p>
    <p>Valid for 7 days.</p>"""
    send_email(email, "Your Front-Tech Demo Access", html)

    return jsonify({"success": True})

@app.route('/api/signup', methods=['POST'])
def api_signup():
    data = request.json or {}
    name = data.get('name')
    email = data.get('email')
    plan = data.get('plan', 'Starter')
    method = data.get('payment_method', 'paypal')

    if plan not in PLAN_PRICES:
        return jsonify({"error": "Invalid plan"}), 400

    # ... (rest of signup logic – PayPal redirect, pending status, etc.)
    # For brevity – keep your existing code here

    return jsonify({"message": "Signup received – payment flow starts"})

# Add your other routes (/api/login, /api/request-bank-transfer, /paypal-ipn) here
# They remain the same as in previous versions

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    print(f"Starting on 0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
