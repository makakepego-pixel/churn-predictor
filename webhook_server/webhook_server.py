"""
Front-Tech — PayPal Webhook Server + Landing Page
"""

import os
import json
import random
import string
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# ── Config — set all values in .env file ──
SMTP_HOST         = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT         = int(os.getenv("SMTP_PORT", 587))
SMTP_USER         = os.getenv("SMTP_USER")
SMTP_PASS         = os.getenv("SMTP_PASS")
FROM_EMAIL        = os.getenv("FROM_EMAIL", SMTP_USER)
DASHBOARD_URL     = os.getenv("DASHBOARD_URL", "https://your-app.railway.app")
CLIENTS_FILE      = "clients.json"

# ── Map PayPal product names to your plan names ──
PLAN_MAP = {
    "Starter Plan - Churn Predictor": "Starter",
    "Pro Plan - Churn Predictor": "Pro",
    "Enterprise Plan - Churn Predictor": "Enterprise",
    "Starter": "Starter",
    "Pro": "Pro", 
    "Enterprise": "Enterprise"
}

# ========== LANDING PAGE ROUTES ==========

@app.route('/')
@app.route('/index')
@app.route('/index.html')
def serve_landing():
    """Serve the main landing page"""
    return send_from_directory('../landing', 'index.HTML')

@app.route('/landing/<path:filename>')
def serve_landing_files(filename):
    """Serve static files (CSS, images, etc.) if needed"""
    return send_from_directory('../landing', filename)

# ========== PAYPAL WEBHOOK ==========

def generate_password(length=12):
    """Generate a random password"""
    chars = string.ascii_letters + string.digits + "!@#$"
    return ''.join(random.choices(chars, k=length))

def load_clients():
    """Load existing clients from JSON file"""
    if os.path.exists(CLIENTS_FILE):
        with open(CLIENTS_FILE) as f:
            return json.load(f)
    return {}

def save_clients(clients):
    """Save clients to JSON file"""
    with open(CLIENTS_FILE, "w") as f:
        json.dump(clients, f, indent=2)
    print(f"[{datetime.now():%H:%M:%S}] Saved {len(clients)} clients")

def make_username(email):
    """Generate unique username from email"""
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
    msg["Subject"] = "Welcome to Front-Tech — Your Dashboard Access"
    msg["From"]    = f"Front-Tech <{FROM_EMAIL}>"
    msg["To"]      = to_email

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
        <p style="margin-bottom:8px">
          <strong>URL:</strong>
          <a href="{DASHBOARD_URL}" style="color:#00e5a0">{DASHBOARD_URL}</a>
        </p>
        <p style="margin-bottom:8px"><strong>Username:</strong> {username}</p>
        <p><strong>Password:</strong> {password}</p>
      </div>
      <a href="{DASHBOARD_URL}"
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

def provision_client(email, name, plan):
    """Create client account and send credentials"""
    clients  = load_clients()
    username = make_username(email)
    password = generate_password()
    
    clients[username] = {
        "password": password,
        "name":     name,
        "email":    email,
        "plan":     plan,
        "created":  datetime.now().isoformat(),
        "payment_method": "paypal"
    }
    
    save_clients(clients)
    send_welcome_email(email, name, username, password, plan)
    print(f"[PROVISIONED] {username} ({plan}) — {email}")
    
    return username, password

@app.route("/paypal-webhook", methods=["POST"])
def paypal_webhook():
    """Handle PayPal IPN (Instant Payment Notification)"""
    data = request.form.to_dict()
    
    print(f"[PAYPAL WEBHOOK] Received: {json.dumps(data, indent=2)}")
    
    payment_status = data.get('payment_status')
    txn_id = data.get('txn_id')
    
    if payment_status != 'Completed':
        print(f"[PAYPAL] Payment not completed. Status: {payment_status}")
        return jsonify({"status": "ignored", "reason": f"Status: {payment_status}"}), 200
    
    payer_email = data.get('payer_email')
    first_name = data.get('first_name', '')
    last_name = data.get('last_name', '')
    full_name = f"{first_name} {last_name}".strip() or payer_email.split('@')[0]
    
    item_name = data.get('item_name', 'Pro Plan - Churn Predictor')
    plan = PLAN_MAP.get(item_name, 'Pro')
    
    mc_gross = data.get('mc_gross', '0')
    mc_currency = data.get('mc_currency', 'USD')
    
    print(f"[PAYPAL] Payment completed! TXN: {txn_id}, Amount: {mc_gross} {mc_currency}, Plan: {plan}")
    
    if payer_email:
        username, password = provision_client(payer_email, full_name, plan)
        return jsonify({
            "status": "success", 
            "username": username,
            "plan": plan
        }), 200
    else:
        print(f"[PAYPAL ERROR] No email in IPN")
        return jsonify({"error": "No email provided"}), 400

@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint for Railway"""
    return jsonify({
        "status": "healthy", 
        "clients": len(load_clients()),
        "payment_method": "paypal"
    }), 200

@app.route("/admin/clients", methods=["GET"])
def list_clients():
    """Simple client list"""
    clients = load_clients()
    safe_clients = {}
    for username, data in clients.items():
        safe_clients[username] = {
            "name": data.get("name"),
            "email": data.get("email"),
            "plan": data.get("plan"),
            "created": data.get("created"),
            "payment_method": data.get("payment_method", "paypal")
        }
    return jsonify(safe_clients)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"🚀 Front-Tech PayPal webhook server running on port {port}")
    print(f"📁 Clients will be saved to: {CLIENTS_FILE}")
    print(f"🌐 Landing page available at: http://localhost:{port}")
    print(f"📧 Email sending: {'✅ ENABLED' if SMTP_USER and SMTP_PASS else '❌ DISABLED'}")
    app.run(host="0.0.0.0", port=port, debug=False)
