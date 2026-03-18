"""
Run this script to generate a hashed password for a new client.
Usage:
    python hash_password.py
Then copy the output hash into auth_config.yaml
"""
import bcrypt

password = input("Enter password to hash: ").strip()
hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
print(f"\nHashed password (copy into auth_config.yaml):\n{hashed}\n")
