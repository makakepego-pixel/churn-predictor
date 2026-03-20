"""
Front-Tech — Complete Webhook Server (PayPal + Gmail)
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

# Set PayPal URLs
if PAYPAL_MODE == "sandbox":
    PAYPAL_URL = "https://www.sandbox.paypal.com/cgi-bin/webscr"
    IPN_VERIFY_URL = "https://ipnpb.sandbox.paypal.com/cgi-bin/webscr"
else:
    PAYPAL_URL = "https://www.paypal.com/cgi-bin/webscr"
    IPN_VERIFY_URL = "https://ipnpb.paypal.com/cgi-bin/webscr"

PLAN_PRICES = {"Starter": "49.00", "Pro": "149.00", "Enterprise": "299.00"}

# ========== FIND LANDING PAGE ==========

def find_landing_page():
    """Find the correct path to landing page"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    
    # Try all possible locations
    locations = [
        (parent_dir, 'landing'),  # ../landing
        (parent_dir, '.'),         # ..
        (current_dir, 'landing'),  # ./landing
        (current_dir, '.'),        # .
    ]
    
    for base, folder in locations:
        try:
            path = os.path.join(base, folder) if folder != '.' else base
            if os.path.exists(path):
                for file in os.listdir(path):
                    if file.lower() == 'index.html' or file.lower() == 'index.htm':
                        # Return relative path from where Flask will run
                        if folder == 'landing':
                            return f"../{folder}", file
                        elif folder == '.' and base == parent_dir:
                            return '..', file
                        else:
                            return folder, file
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

def send_welcome_email(to_email, name, username, password, plan):
    if not SMTP_USER or not SMTP_PASS:
        print(f"[EMAIL SKIPPED] Would send to {to_email}")
        return

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
      <a href="{DASHBOARD_URL}" style="display:inline-block;background:#00e5a0;color:#000;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:700">Launch Dashboard →</a>
      <p style="margin-top:24px;font-size:.85rem;color:#6b7a99">Questions? Reply to this email.<br/>— Front-Tech Team</p>
    </div>"""

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Welcome to Front-Tech — Your {plan} Plan is Active"
        msg["From"] = f"Front-Tech <{FROM_EMAIL}>"
        msg["To"] = to_email
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(FROM_EMAIL, to_email, msg.as_string())
        print(f"[EMAIL SENT] → {to_email}")
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")

def provision_client(name, email, plan, amount=""):
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
        "created": datetime.now().isoformat()
    }
    save_clients(clients)
    send_welcome_email(email, name, username, password, plan)
    return username, password

# ========== ROUTES ==========

@app.route('/')
def serve_landing():
    """Serve the landing page"""
    # Try multiple approaches
    if LANDING_PATH and INDEX_FILE:
        try:
            return send_from_directory(LANDING_PATH, INDEX_FILE)
        except Exception as e:
            print(f"[ERROR] send_from_directory failed: {e}")
    
    # Fallback: try to find and read the file directly
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    
    possible_files = [
        os.path.join(parent_dir, 'landing', 'index.html'),
        os.path.join(parent_dir, 'landing', 'index.HTML'),
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

@app.route('/test')
def test_page():
    """Simple test page"""
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
        <p><a href="/" style="color:#00e5a0">Try Landing Page</a></p>
        <p><a href="/debug" style="color:#00e5a0">Debug Info</a></p>
    </body>
    </html>
    """

@app.route('/debug')
def debug_info():
    """Debug endpoint"""
    import os
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    
    debug = {
        "current_dir": current_dir,
        "parent_dir": parent_dir,
        "landing_path_config": LANDING_PATH,
        "index_file_config": INDEX_FILE,
        "current_dir_files": os.listdir(current_dir) if os.path.exists(current_dir) else [],
        "parent_dir_files": os.listdir(parent_dir) if os.path.exists(parent_dir) else [],
    }
    
    # Check specific locations
    locations = [
        os.path.join(parent_dir, 'landing'),
        parent_dir,
        current_dir,
    ]
    
    for loc in locations:
        if os.path.exists(loc):
            debug[f"files_in_{loc}"] = os.listdir(loc)
    
    return jsonify(debug)

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "clients": len(load_clients()),
        "paypal_mode": PAYPAL_MODE,
        "time": datetime.now().isoformat()
    })

@app.route('/api/signup', methods=['POST'])
def api_signup():
    data = request.json
    name = data.get('name')
    email = data.get('email')
    plan = data.get('plan', 'Starter')

    if plan not in PLAN_PRICES:
        return jsonify({"error": "Invalid plan"}), 400

    price = PLAN_PRICES.get(plan)

    clients = load_clients()
    for username, info in clients.items():
        if info.get('email') == email:
            if info.get('status') == 'active':
                return jsonify({"error": "Email already registered. Please login."}), 400

    username = make_username(name, email)
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
            if info.get('status') == 'active':
                if info.get('password') == password:
                    return jsonify({
                        "dashboard_url": f"{DASHBOARD_URL}?username={username}&email={email}"
                    })
            elif info.get('temp_password') == password:
                return jsonify({
                    "dashboard_url": f"{DASHBOARD_URL}?demo=true&email={email}"
                })

    return jsonify({"error": "Invalid email or password"}), 401

@app.route('/api/status', methods=['GET'])
def api_status():
    return jsonify({"status": "ok", "message": "Front-Tech API is running"})

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
                        save_clients(clients)
                        send_welcome_email(payer_email, name, username, permanent_password, plan)
                        found = True
                        break

                if not found:
                    provision_client(name, payer_email, plan, str(amount))

    return "OK", 200

@app.route("/clients")
def list_clients():
    if request.args.get("secret") != SECRET_KEY:
        return jsonify({"error": "Unauthorized"}), 401
    clients = load_clients()
    safe_clients = {u: {"name": v.get("name"), "email": v.get("email"), "plan": v.get("plan"), "status": v.get("status")}
                    for u, v in clients.items()}
    return jsonify({"count": len(clients), "clients": safe_clients})

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    print(f"🚀 Front-Tech server running on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
