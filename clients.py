"""
clients.py — Dynamic client loader for Front-Tech Churn Predictor
Merges hardcoded base clients with webhook-provisioned clients from clients.json
Place this file in the same folder as app.py
"""

import json, os, hashlib

CLIENTS_FILE = os.path.join(os.path.dirname(__file__), "clients.json")

# Hardcoded base clients — always available
BASE_CLIENTS = {
    "demo_client": {
        "password_hash": hashlib.sha256("demo123".encode()).hexdigest(),
        "name": "Demo Client",
        "role": "client",
        "plan": "Pro",
    },
}


def load_all_clients() -> dict:
    """
    Returns merged dict of hardcoded + webhook-provisioned clients.
    Called on every login attempt so new clients appear instantly.
    """
    clients = dict(BASE_CLIENTS)

    if os.path.exists(CLIENTS_FILE):
        try:
            with open(CLIENTS_FILE) as f:
                dynamic = json.load(f)

            # Normalize: webhook_server saves plain passwords,
            # convert them to hashed format so app.py verify_pw() works
            for username, data in dynamic.items():
                if "password" in data and "password_hash" not in data:
                    data["password_hash"] = hashlib.sha256(
                        data["password"].encode()
                    ).hexdigest()
                    data.setdefault("role", "client")
                clients[username] = data

        except Exception as e:
            print(f"[clients.py] Could not load clients.json: {e}")

    return clients
