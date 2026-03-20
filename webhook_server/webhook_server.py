"""
Front-Tech — Complete Webhook Server (PayPal + Multiple Payment Options)
Handles: User signup, PayPal IPN, User login, Bank Transfer Requests, Email delivery
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
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "https://your-app.streamlit.app")
PAYPAL_EMAIL = os.getenv("PAYPAL_EMAIL", "frontech@example.com")
PAYPAL_MODE = os.getenv("PAYPAL_MODE", "sandbox")
SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret")
CLIENTS_FILE = "clients.json"

# Bank account details for Botswana
BANK_NAME = os.getenv("BANK_NAME", "Access Bank Botswana")
BANK_ACCOUNT_NAME = os.getenv("BANK_ACCOUNT_NAME", "Front-Tech (PTY) Ltd")
BANK_ACCOUNT_NUMBER = os.getenv("BANK_ACCOUNT_NUMBER", "1234567890")
BANK_SWIFT_CODE = os.getenv("BANK_SWIFT_CODE", "ABBLBWGX")
BANK_BRANCH = os.getenv("BANK_BRANCH", "Gaborone Main")

# Set PayPal URLs
if PAYPAL_MODE == "sandbox":
    PAYPAL_URL = "https://www.sandbox.paypal.com/cgi-bin/webscr"
    IPN_VERIFY_URL = "https://ipnpb.sandbox.paypal.com/cgi-bin/webscr"
    print("🔧 PayPal Mode: SANDBOX (for testing)")
else:
    PAYPAL_URL = "https://www.paypal.com/cgi-bin/webscr"
    IPN_VERIFY_URL = "https://ipnpb.paypal.com/cgi-bin/webscr"
    print("💰 PayPal Mode: LIVE (production)")

PLAN_PRICES = {"Starter": "49.00", "Pro": "149.00", "Enterprise": "299.00"}

# ========== FIND LANDING PAGE ==========

def find_landing_page():
    """Find the correct path to landing page"""
    import os
    
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    
    locations = [
        (parent_dir, 'landing'),
        (parent_dir, '.'),
        (current_dir, 'landing'),
        (current_dir, '.'),
    ]
    
    for base, folder in locations:
        try:
            path = os.path.join(base, folder) if folder != '.' else base
            if os.path.exists(path):
                for file in os.listdir(path):
                    if file.lower() == 'index.html' or file.lower() == 'index.htm':
                        if folder == 'landing' and base == parent_dir:
                            return '../landing', file
                        elif folder == '.' and base == parent_dir:
                            return '..', file
                        elif folder == 'landing':
                            return 'landing', file
                        else:
                            return '.', file
        except:
            pass
    
    return None, None

LANDING_PATH, INDEX_FILE = find_landing_page()
print(f"📁 Landing path: {LANDING_PATH}")
print(f"📄 Index file: {INDEX_FILE}")

# ========== HELPER FUNCTIONS ==========

def generate_password(length=10):
    chars = string.ascii_letters + string.digits
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

def make_username(name, email):
    base = ''.join(c for c in name.lower().replace(" ", "_") if c.isalnum() or c == '_') or email.split("@")[0]
    clients, u, i = load_clients(), base, 1
    while u in clients:
        u, i = f"{base}{i}", i + 1
    return u

def send_email(to_email, subject, html_content):
    """Generic email sender"""
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
    """Send welcome email with login credentials"""
    payment_method_display = {
        'paypal': 'PayPal',
        'card': 'Credit/Debit Card',
        'bank': 'Bank Transfer',
        'mobile': 'Mobile Money'
    }.get(payment_method, 'PayPal')
    
    html = f"""
    <div style="font-family:sans-serif;max-width:560px;margin:0 auto;background:#04080f;color:#e8edf5;padding:40px;border-radius:12px">
      <h1 style="color:#fff">Welcome to <span style="color:#00e5a0">Front-Tech</span>! 🎉</h1>
      <p style="color:#6b7a99;margin-bottom:24px">Hi <strong style="color:#fff">{name}</strong>, your <strong style="color:#fff">{plan}</strong> plan is active.</p>
      <div style="background:#0e1a2e;border:1px solid #1a2640;border-radius:10px;padding:24px;margin-bottom:24px">
        <p style="color:#6b7a99;font-size:.8rem;margin-bottom:12px">YOUR LOGIN CREDENTIALS</p>
        <p style="margin-bottom:8px"><strong>URL:</strong> <a href="{DASHBOARD_URL}" style="color:#00e5a0">{DASHBOARD_URL}</a></p>
        <p style="margin-bottom:8px"><strong>Username:</strong> <code style="background:#1a2640;padding:2px 8px;border-radius:4px">{username}</code></p>
        <p><strong>Password:</strong> <code style="background:#1a2640;padding:2px 8px;border-radius:4px">{password}</code></p>
      </div>
      <p style="margin-bottom:16px"><strong>Payment Method:</strong> {payment_method_display}</p>
      <a href="{DASHBOARD_URL}" style="display:inline-block;background:#00e5a0;color:#000;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:700">Launch Dashboard →</a>
      <p style="margin-top:24px;font-size:.85rem;color:#6b7a99">Questions? Reply to this email.<br/>— Front-Tech Team</p>
    </div>"""
    
    return send_email(to_email, f"Welcome to Front-Tech — Your {plan} Plan is Active", html)

def provision_client(name, email, plan, amount="", payment_method="paypal"):
    """Create active client account and send email"""
    clients = load_clients()
    username = make_username(name, email)
    password = generate_password()

    clients[username] = {
        "password": password,
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
    print(f"[PROVISIONED] {username} ({plan}) via {payment_method} — {email}")
    return username, password

# ========== ROUTES ==========

@app.route('/')
def serve_landing():
    """Serve the landing page"""
    if not LANDING_PATH or not INDEX_FILE:
        # Fallback: try to find and read the file directly
        import os
        current_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(current_dir)
        
        possible_files = [
            os.path.join(parent_dir, 'landing', 'index.html'),
            os.path.join(parent_dir, 'index.html'),
            os.path.join(current_dir, 'landing', 'index.html'),
            os.path.join(current_dir, 'index.html'),
        ]
        
        for filepath in possible_files:
            if os.path.exists(filepath):
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        return f.read(), 200, {'Content-Type': 'text/html'}
                except:
                    pass
        
        return jsonify({"error": "Landing page not found"}), 404
    
    try:
        return send_from_directory(LANDING_PATH, INDEX_FILE)
    except Exception as e:
        print(f"[ERROR] Cannot serve landing page: {e}")
        return jsonify({"error": str(e)}), 404

@app.route('/test')
def test_page():
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Front-Tech Test</title></head>
    <body style="background:#050810;color:#00e5a0;font-family:sans-serif;text-align:center;padding:50px;">
        <h1>🚀 Front-Tech Server is Running!</h1>
        <p>Your webhook server is working correctly.</p>
        <p>API URL: <code>/api/status</code></p>
        <p>Health: <code>/health</code></p>
        <hr>
        <p><a href="/" style="color:#00e5a0">Go to Landing Page</a></p>
    </body>
    </html>
    """

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "clients": len(load_clients()),
        "paypal_mode": PAYPAL_MODE,
        "time": datetime.now().isoformat()
    })

# ========== API ENDPOINTS ==========

@app.route('/api/signup', methods=['POST'])
def api_signup():
    """User registration - creates pending user and returns PayPal link"""
    data = request.json
    name = data.get('name')
    email = data.get('email')
    plan = data.get('plan', 'Starter')
    payment_method = data.get('payment_method', 'paypal')

    if plan not in PLAN_PRICES:
        return jsonify({"error": "Invalid plan"}), 400

    price = PLAN_PRICES.get(plan)

    clients = load_clients()
    for username, info in clients.items():
        if info.get('email') == email:
            if info.get('status') == 'active':
                return jsonify({"error": "Email already registered. Please login."}), 400

    # Create pending user
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

    # Create PayPal payment URL
    paypal_url = f"{PAYPAL_URL}?cmd=_xclick&business={PAYPAL_EMAIL}&item_name={plan} Plan&amount={price}&currency_code=USD&notify_url={request.host_url}paypal-ipn&return_url={request.host_url}?payment=success"

    return jsonify({"payment_url": paypal_url})

@app.route('/api/request-bank-transfer', methods=['POST'])
def request_bank_transfer():
    """Handle bank transfer requests for Botswana customers"""
    data = request.json
    name = data.get('name')
    email = data.get('email')
    plan = data.get('plan')
    phone = data.get('phone', '')
    price = PLAN_PRICES.get(plan, "49.00")
    
    # Create pending user
    clients = load_clients()
    username = make_username(name, email)
    temp_password = generate_password()
    
    # Convert price to BWP (approximate, adjust as needed)
    bwp_amount = float(price) * 13.5  # Approximate USD to BWP
    
    clients[username] = {
        "name": name,
        "email": email,
        "plan": plan,
        "status": "pending_bank_transfer",
        "payment_method": "bank_transfer",
        "temp_password": temp_password,
        "phone": phone,
        "created": datetime.now().isoformat()
    }
    save_clients(clients)
    
    # Send bank transfer instructions email
    bank_html = f"""
    <div style="font-family:sans-serif;max-width:560px;margin:0 auto;background:#04080f;color:#e8edf5;padding:40px;border-radius:12px">
      <h1 style="color:#fff">Bank Transfer Instructions</h1>
      <p style="color:#6b7a99;margin-bottom:24px">Hi <strong style="color:#fff">{name}</strong>, thank you for choosing the <strong style="color:#fff">{plan}</strong> plan.</p>
      
      <div style="background:#0e1a2e;border:1px solid #1a2640;border-radius:10px;padding:24px;margin-bottom:24px">
        <h3 style="color:#00e5a0;margin-bottom:16px">Bank Details</h3>
        <p><strong>Bank:</strong> {BANK_NAME}</p>
        <p><strong>Account Name:</strong> {BANK_ACCOUNT_NAME}</p>
        <p><strong>Account Number:</strong> {BANK_ACCOUNT_NUMBER}</p>
        <p><strong>Branch:</strong> {BANK_BRANCH}</p>
        <p><strong>SWIFT Code:</strong> {BANK_SWIFT_CODE}</p>
        <p><strong>Amount:</strong> BWP {bwp_amount:.2f} (USD ${price})</p>
        <p><strong>Reference:</strong> CHURN-{plan[:3]}-{username[:5].upper()}</p>
      </div>
      
      <p style="margin-bottom:16px">Once payment is confirmed, you'll receive your login credentials within 24 hours.</p>
      
      <p style="margin-top:24px;font-size:.85rem;color:#6b7a99">Questions? Reply to this email or contact us at hello@front-tech.io<br/>— Front-Tech Team</p>
    </div>"""
    
    send_email(email, f"Bank Transfer Instructions - {plan} Plan", bank_html)
    
    # Notify admin
    admin_html = f"""
    <p>New bank transfer request:</p>
    <ul>
        <li><strong>Name:</strong> {name}</li>
        <li><strong>Email:</strong> {email}</li>
        <li><strong>Plan:</strong> {plan}</li>
        <li><strong>Amount:</strong> ${price}</li>
        <li><strong>Phone:</strong> {phone}</li>
        <li><strong>Username:</strong> {username}</li>
    </ul>
    <p>Awaiting payment confirmation.</p>"""
    
    send_email(SMTP_USER, f"💰 Bank Transfer Request - {name} ({plan})", admin_html)
    
    return jsonify({"message": f"Bank transfer details have been sent to {email}. Please complete payment within 48 hours."})

@app.route('/api/login', methods=['POST'])
def api_login():
    """User login - returns dashboard URL"""
    data = request.json
    email = data.get('email')
    password = data.get('password')

    clients = load_clients()

    for username, info in clients.items():
        if info.get('email') == email:
            if info.get('status') == 'active':
                if info.get('password') == password:
                    return jsonify({
                        "dashboard_url": f"{DASHBOARD_URL}?username={username}&email={email}"
                    })
            elif info.get('temp_password') == password:
                return jsonify({
                    "dashboard_url": f"{DASHBOARD_URL}?demo=true&email={email}"
                })
            elif info.get('status') == 'pending_bank_transfer':
                return jsonify({"error": "Your payment is pending confirmation. You'll receive an email once processed."}), 401

    return jsonify({"error": "Invalid email or password"}), 401

@app.route('/api/status', methods=['GET'])
def api_status():
    return jsonify({"status": "ok", "message": "Front-Tech API is running"})

# ========== PAYPAL WEBHOOK ==========

@app.route("/paypal-ipn", methods=["POST"])
def paypal_ipn():
    """PayPal IPN auto-provisioning"""
    raw = request.get_data(as_text=True)

    try:
        req = urllib.request.Request(
            IPN_VERIFY_URL,
            data=("cmd=_notify-validate&" + raw).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"})
        verified = urllib.request.urlopen(req, timeout=10).read().decode() == "VERIFIED"
    except Exception as e:
        print(f"[IPN VERIFY ERROR] {e}")
        verified = False

    if verified:
        params = dict(urllib.parse.parse_qsl(raw))
        print(f"[IPN] Verified: {params.get('txn_id')}")

        if params.get("payment_status") == "Completed":
            payer_email = params.get("payer_email", "")
            first_name = params.get("first_name", "")
            last_name = params.get("last_name", "")
            name = f"{first_name} {last_name}".strip() or payer_email.split("@")[0]
            amount = float(params.get("mc_gross", 0))

            if amount >= 299:
                plan = "Enterprise"
            elif amount >= 149:
                plan = "Pro"
            else:
                plan = "Starter"

            if payer_email:
                clients = load_clients()
                found = False

                for username, info in clients.items():
                    if info.get('email') == payer_email and info.get('status') == 'pending':
                        permanent_password = generate_password()
                        info['status'] = 'active'
                        info['password'] = permanent_password
                        info['amount'] = str(amount)
                        info['transaction_id'] = params.get('txn_id')
                        info['payment_date'] = datetime.now().isoformat()
                        info['plan'] = plan
                        info['payment_method'] = 'paypal'
                        save_clients(clients)
                        send_welcome_email(payer_email, name, username, permanent_password, plan, 'paypal')
                        print(f"[ACTIVATED] {username} - {payer_email}")
                        found = True
                        break

                if not found:
                    provision_client(name, payer_email, plan, str(amount), 'paypal')

    return "OK", 200

# ========== ADMIN ROUTES ==========

@app.route("/clients")
def list_clients():
    if request.args.get("secret") != SECRET_KEY:
        return jsonify({"error": "Unauthorized"}), 401
    clients = load_clients()
    safe_clients = {u: {"name": v.get("name"), "email": v.get("email"), "plan": v.get("plan"), 
                        "status": v.get("status"), "payment_method": v.get("payment_method")}
                    for u, v in clients.items()}
    return jsonify({"count": len(clients), "clients": safe_clients})

@app.route("/admin/confirm-bank-transfer", methods=["POST"])
def confirm_bank_transfer():
    """Admin endpoint to confirm bank transfer payments"""
    data = request.json
    if data.get("secret") != SECRET_KEY:
        return jsonify({"error": "Unauthorized"}), 401
    
    email = data.get("email")
    clients = load_clients()
    
    for username, info in clients.items():
        if info.get('email') == email and info.get('status') == 'pending_bank_transfer':
            permanent_password = generate_password()
            info['status'] = 'active'
            info['password'] = permanent_password
            info['payment_date'] = datetime.now().isoformat()
            info['payment_method'] = 'bank_transfer'
            save_clients(clients)
            send_welcome_email(email, info.get('name'), username, permanent_password, info.get('plan'), 'bank_transfer')
            return jsonify({"success": True, "username": username})
    
    return jsonify({"error": "User not found"}), 404

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    print(f"🚀 Front-Tech server running on port {port}")
    print(f"📁 Landing path: {LANDING_PATH}")
    print(f"📄 Index file: {INDEX_FILE}")
    print(f"📁 Clients file: {CLIENTS_FILE}")
    print(f"📧 Email: {'✅ ENABLED' if SMTP_USER and SMTP_PASS else '❌ DISABLED'}")
    print(f"💳 Payment Methods: PayPal, Credit/Debit Card, Bank Transfer, Mobile Money")
    app.run(host="0.0.0.0", port=port, debug=False)
