"""
Front-Tech — Complete Webhook Server (PayPal + Gmail)
Handles: User signup, PayPal IPN, User login, Email delivery
Deploy on Railway: railway.app
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
SMTP_HOST     = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", 587))
SMTP_USER     = os.getenv("SMTP_USER", "")
SMTP_PASS     = os.getenv("SMTP_PASS", "")
FROM_EMAIL    = os.getenv("FROM_EMAIL", SMTP_USER)
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "https://your-app.streamlit.app")
PAYPAL_EMAIL  = os.getenv("PAYPAL_EMAIL", "frontech@example.com")
SECRET_KEY    = os.getenv("SECRET_KEY", "change-this-secret")
CLIENTS_FILE  = "clients.json"

# Plan prices
PLAN_PRICES = {
    "Starter": "49.00",
    "Pro": "149.00",
    "Enterprise": "299.00"
}


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
    """Send welcome email with login credentials"""
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
        "created": datetime.now().isoformat()
    }
    save_clients(clients)
    send_welcome_email(email, name, username, password, plan)
    print(f"[PROVISIONED] {username} ({plan}) — {email}")
    return username, password


# ========== ROUTES ==========

@app.route('/')
def serve_landing():
    """Serve the landing page"""
    return send_from_directory('../landing', 'index.html')


@app.route('/landing/<path:filename>')
def serve_landing_files(filename):
    """Serve static files if needed"""
    return send_from_directory('../landing', filename)


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "clients": len(load_clients()),
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

    # Validate plan
    if plan not in PLAN_PRICES:
        return jsonify({"error": "Invalid plan"}), 400

    price = PLAN_PRICES.get(plan)

    # Check if user already exists
    clients = load_clients()
    for username, info in clients.items():
        if info.get('email') == email:
            if info.get('status') == 'active':
                return jsonify({"error": "Email already registered. Please login."}), 400
            elif info.get('status') == 'pending':
                # Resend payment link
                paypal_url = f"https://www.paypal.com/cgi-bin/webscr?cmd=_xclick&business={PAYPAL_EMAIL}&item_name={plan} Plan&amount={price}&currency_code=USD&notify_url={request.host_url}paypal-ipn&return_url={request.host_url}?payment=success"
                return jsonify({"payment_url": paypal_url})

    # Create pending user
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

    # Create PayPal payment URL
    paypal_url = f"https://www.paypal.com/cgi-bin/webscr?cmd=_xclick&business={PAYPAL_EMAIL}&item_name={plan} Plan&amount={price}&currency_code=USD&notify_url={request.host_url}paypal-ipn&return_url={request.host_url}?payment=success"

    return jsonify({
        "payment_url": paypal_url,
        "message": "Redirecting to PayPal..."
    })


@app.route('/api/login', methods=['POST'])
def api_login():
    """User login - returns dashboard URL"""
    data = request.json
    email = data.get('email')
    password = data.get('password')

    clients = load_clients()

    for username, info in clients.items():
        if info.get('email') == email:
            # Check if active account
            if info.get('status') == 'active':
                if info.get('password') == password:
                    return jsonify({
                        "dashboard_url": f"{DASHBOARD_URL}?username={username}&email={email}"
                    })
            # Check if pending/demo
            elif info.get('temp_password') == password:
                return jsonify({
                    "dashboard_url": f"{DASHBOARD_URL}?demo=true&email={email}"
                })

    return jsonify({"error": "Invalid email or password"}), 401


@app.route('/api/status', methods=['GET'])
def api_status():
    """API status check"""
    return jsonify({"status": "ok", "message": "Front-Tech API is running"})


# ========== PAYPAL WEBHOOK ==========

@app.route("/paypal-ipn", methods=["POST"])
def paypal_ipn():
    """
    PayPal IPN auto-provisioning.
    Configure in PayPal: Profile → Selling Tools → Instant Payment Notifications
    URL: https://your-app.up.railway.app/paypal-ipn
    """
    raw = request.get_data(as_text=True)

    # Verify IPN with PayPal
    try:
        req = urllib.request.Request(
            "https://ipnpb.paypal.com/cgi-bin/webscr",
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

            # Determine plan from amount
            if amount >= 299:
                plan = "Enterprise"
            elif amount >= 149:
                plan = "Pro"
            else:
                plan = "Starter"

            if payer_email:
                # Find pending user by email
                clients = load_clients()
                found = False

                for username, info in clients.items():
                    if info.get('email') == payer_email and info.get('status') == 'pending':
                        # Activate user
                        permanent_password = generate_password()
                        info['status'] = 'active'
                        info['password'] = permanent_password
                        info['amount'] = str(amount)
                        info['transaction_id'] = params.get('txn_id')
                        info['payment_date'] = datetime.now().isoformat()
                        info['plan'] = plan
                        save_clients(clients)

                        send_welcome_email(payer_email, name, username, permanent_password, plan)
                        print(f"[ACTIVATED] {username} - {payer_email}")
                        found = True
                        break

                if not found:
                    # Create new active user if not found
                    provision_client(name, payer_email, plan, str(amount))

    return "OK", 200


# ========== ADMIN ROUTES ==========

@app.route("/clients")
def list_clients():
    """List all clients (admin only)"""
    if request.args.get("secret") != SECRET_KEY:
        return jsonify({"error": "Unauthorized"}), 401
    clients = load_clients()
    safe_clients = {u: {"name": v.get("name"), "email": v.get("email"), "plan": v.get("plan"), "status": v.get("status")}
                    for u, v in clients.items()}
    return jsonify({"count": len(clients), "clients": safe_clients})


@app.route("/notify", methods=["POST"])
def manual_notify():
    """Manually provision a client after PayPal payment"""
    data = request.get_json() or {}
    if data.get("secret") != SECRET_KEY:
        return jsonify({"error": "Unauthorized"}), 401

    name = data.get("name", "")
    email = data.get("email", "")
    plan = data.get("plan", "Pro")
    amount = data.get("amount", "")

    if not name or not email:
        return jsonify({"error": "name and email required"}), 400

    u, p = provision_client(name, email, plan, amount)
    return jsonify({"status": "provisioned", "username": u})


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    print(f"🚀 Front-Tech server running on port {port}")
    print(f"📁 Clients file: {CLIENTS_FILE}")
    print(f"📧 Email: {'✅ ENABLED' if SMTP_USER and SMTP_PASS else '❌ DISABLED'}")
    app.run(host="0.0.0.0", port=port, debug=False)
