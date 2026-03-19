"""
Front-Tech — Stripe Webhook Server
When a client pays, this server:
  1. Receives the Stripe payment event
  2. Creates username + password automatically
  3. Saves to clients.json
  4. Emails login credentials to the client

Deploy free on Railway: railway.app
Run locally: python webhook_server.py
"""

import os, json, random, string, smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from flask import Flask, request, jsonify
import stripe
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# ── Config — set all values in .env file ──
stripe.api_key    = os.getenv("STRIPE_SECRET_KEY")
WEBHOOK_SECRET    = os.getenv("STRIPE_WEBHOOK_SECRET")
SMTP_HOST         = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT         = int(os.getenv("SMTP_PORT", 587))
SMTP_USER         = os.getenv("SMTP_USER")
SMTP_PASS         = os.getenv("SMTP_PASS")
FROM_EMAIL        = os.getenv("FROM_EMAIL", SMTP_USER)
DASHBOARD_URL     = os.getenv("DASHBOARD_URL", "https://your-app.streamlit.app")
CLIENTS_FILE      = "clients.json"

# ── Replace with your real Stripe Price IDs ──
PLAN_MAP = {
    "price_STARTER_ID_HERE":    "Starter",
    "price_PRO_ID_HERE":        "Pro",
    "price_ENTERPRISE_ID_HERE": "Enterprise",
}


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
    if not SMTP_USER or not SMTP_PASS:
        print(f"[EMAIL SKIPPED] Credentials: {username} / {password}")
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
    clients  = load_clients()
    username = make_username(email)
    password = generate_password()
    clients[username] = {
        "password": password,
        "name":     name,
        "email":    email,
        "plan":     plan,
        "created":  datetime.now().isoformat(),
    }
    save_clients(clients)
    send_welcome_email(email, name, username, password, plan)
    print(f"[PROVISIONED] {username} ({plan}) — {email}")


def revoke_access(customer_id):
    try:
        customer = stripe.Customer.retrieve(customer_id)
        email    = customer.get("email", "")
        clients  = load_clients()
        to_del   = [u for u, v in clients.items() if v.get("email") == email]
        for u in to_del:
            del clients[u]
            print(f"[REVOKED] {u}")
        if to_del:
            save_clients(clients)
    except Exception as e:
        print(f"[REVOKE ERROR] {e}")


@app.route("/webhook", methods=["POST"])
def stripe_webhook():
    payload    = request.get_data()
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        return jsonify({"error": "Invalid signature"}), 400

    etype = event["type"]
    print(f"[WEBHOOK] {etype}")

    if etype == "checkout.session.completed":
        s      = event["data"]["object"]
        email  = s.get("customer_email") or s.get("customer_details", {}).get("email", "")
        name   = s.get("customer_details", {}).get("name", email.split("@")[0])
        pid    = s.get("metadata", {}).get("price_id", "")
        plan   = PLAN_MAP.get(pid, "Pro")
        if email:
            provision_client(email, name, plan)

    elif etype == "invoice.payment_succeeded":
        inv    = event["data"]["object"]
        email  = inv.get("customer_email", "")
        name   = inv.get("customer_name", email.split("@")[0])
        pid    = (inv.get("lines", {}).get("data") or [{}])[0].get("price", {}).get("id", "")
        plan   = PLAN_MAP.get(pid, "Pro")
        emails = [v.get("email") for v in load_clients().values()]
        if email and email not in emails:
            provision_client(email, name, plan)

    elif etype == "customer.subscription.deleted":
        revoke_access(event["data"]["object"].get("customer"))

    return jsonify({"status": "ok"}), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "clients": len(load_clients())}), 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"Front-Tech webhook running on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
