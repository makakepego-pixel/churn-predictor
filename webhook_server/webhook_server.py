"""
Front-Tech Landing Page + API Server (Flask + Resend)
Railway-compatible version – March 2026
"""
import os
import json
import random
import string
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
from resend import Resend

load_dotenv()
app = Flask(__name__)

# Enable CORS – very important for fetch POST requests from the frontend
CORS(app, supports_credentials=True, origins="*")

# ── Config ────────────────────────────────────────────────────────────────
RESEND_API_KEY   = os.getenv("RESEND_API_KEY", "")
FROM_EMAIL       = os.getenv("FROM_EMAIL", "noreply@front-tech.io")
DASHBOARD_URL    = os.getenv("STREAMLIT_URL", "https://your-dashboard.up.railway.app")
PAYPAL_EMAIL     = os.getenv("PAYPAL_EMAIL", "")
PAYPAL_MODE      = os.getenv("PAYPAL_MODE", "sandbox")
SECRET_KEY       = os.getenv("SECRET_KEY", "change-this-in-production")

CLIENTS_FILE     = "clients.json"
PLAN_PRICES      = {"Starter": 49.00, "Pro": 149.00, "Enterprise": 299.00}

# Resend client
resend = Resend(RESEND_API_KEY) if RESEND_API_KEY else None

# ── Find landing page ─────────────────────────────────────────────────────
def locate_landing_page():
    base = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base, '..', 'landing', 'index.html'),
        os.path.join(base, 'landing', 'index.html'),
        os.path.join(base, 'index.html'),
        os.path.join(base, '..', 'index.html'),
    ]
    for path in candidates:
        if os.path.exists(path):
            return os.path.dirname(path), os.path.basename(path)
    return None, None

LANDING_DIR, INDEX_FILENAME = locate_landing_page()
print(f"Landing dir : {LANDING_DIR or 'NOT FOUND'}")
print(f"Index file  : {INDEX_FILENAME or 'NOT FOUND'}")

# ── Email ─────────────────────────────────────────────────────────────────
def send_email(to_email: str, subject: str, html: str) -> bool:
    if not resend:
        print(f"[EMAIL SKIPPED] RESEND_API_KEY missing → {to_email}")
        return False
    try:
        resend.Emails.send({
            "from": FROM_EMAIL,
            "to": to_email,
            "subject": subject,
            "html": html
        })
        print(f"[EMAIL SENT] → {to_email}")
        return True
    except Exception as e:
        print(f"[RESEND ERROR] {str(e)}")
        return False

# ── Helpers ───────────────────────────────────────────────────────────────
def generate_password(length: int = 10) -> str:
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

def load_clients() -> dict:
    if os.path.exists(CLIENTS_FILE):
        try:
            with open(CLIENTS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading clients.json: {e}")
    return {}

def save_clients(clients: dict):
    try:
        with open(CLIENTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(clients, f, indent=2)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Saved {len(clients)} clients")
    except Exception as e:
        print(f"Error saving clients.json: {e}")

def make_username(name: str, email: str) -> str:
    base = name.lower().replace(" ", "_")
    base = "".join(c for c in base if c.isalnum() or c == "_") or email.split("@")[0]
    clients = load_clients()
    uname, i = base, 1
    while uname in clients:
        uname = f"{base}{i}"
        i += 1
    return uname

# ── Routes ────────────────────────────────────────────────────────────────
@app.route('/')
def serve_landing():
    if not LANDING_DIR or not INDEX_FILENAME:
        return jsonify({"error": "Landing page not found"}), 404
    return send_from_directory(LANDING_DIR, INDEX_FILENAME)

@app.route('/health')
def health():
    port = os.getenv("PORT", "unknown")
    return jsonify({
        "status": "ok",
        "port": port,
        "resend_active": bool(RESEND_API_KEY),
        "clients_file_exists": os.path.exists(CLIENTS_FILE),
        "clients_count": len(load_clients())
    })

@app.route('/test')
def test():
    return "<h1>Backend is alive!</h1><p>Port: {}</p>".format(os.getenv("PORT", "unknown"))

@app.route('/api/demo', methods=['POST'])
def api_demo():
    try:
        data = request.get_json(silent=True) or {}
        name  = data.get('name', '').strip()
        email = data.get('email', '').strip()

        if not name or not email:
            return jsonify({"error": "Name and email are required"}), 400

        clients = load_clients()
        if any(v.get('email') == email for v in clients.values()):
            return jsonify({"error": "Email already registered"}), 409

        username = make_username(name, email)
        password = generate_password(8)

        clients[username] = {
            "name": name,
            "email": email,
            "plan": "Demo",
            "status": "demo",
            "password": password,  # plain for MVP – hash in production
            "created": datetime.now().isoformat()
        }
        save_clients(clients)

        html = f"""
        <h2>Front-Tech Demo Access</h2>
        <p>Hi {name},</p>
        <p><strong>Dashboard:</strong> <a href="{DASHBOARD_URL}">{DASHBOARD_URL}</a></p>
        <p><strong>Username:</strong> {username}</p>
        <p><strong>Password:</strong> {password}</p>
        <p>This demo expires in 7 days.</p>
        """
        send_email(email, "Your Front-Tech Demo is Ready", html)

        return jsonify({"success": True, "message": "Demo credentials sent to your email"})
    except Exception as e:
        print(f"[DEMO ERROR] {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/api/signup', methods=['POST'])
def api_signup():
    try:
        data = request.get_json(silent=True) or {}
        name  = data.get('name', '').strip()
        email = data.get('email', '').strip()
        plan  = data.get('plan', 'Starter')

        if not name or not email:
            return jsonify({"error": "Name and email required"}), 400

        if plan not in PLAN_PRICES:
            return jsonify({"error": "Invalid plan"}), 400

        # For MVP: just acknowledge – real payment flow can be added later
        return jsonify({
            "success": True,
            "message": f"Signup for {plan} received – payment flow would start here",
            "price": PLAN_PRICES[plan]
        })
    except Exception as e:
        print(f"[SIGNUP ERROR] {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT") or 8080)
    print(f"RAILWAY: Starting on 0.0.0.0 port {port} (env PORT={os.getenv('PORT')})")
    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        use_reloader=False,
        threaded=True
    )
