"""
scripts/hash_passwords.py
Run once after install to replace HASH_PLACEHOLDER values in auth_config.yaml
with real bcrypt hashes.

Usage:
    python scripts/hash_passwords.py
"""
import yaml
import streamlit_authenticator as stauth
from pathlib import Path

CONFIG = Path(__file__).parent.parent / "auth_config.yaml"

# Map username → plain-text password (edit these before running)
PASSWORDS = {
    "recruiter1":  "recruit123",
    "manager1":    "manage123",
    "exec1":       "exec123",
    "compliance1": "comply123",
}

with open(CONFIG) as f:
    config = yaml.safe_load(f)

hashed = stauth.Hasher(list(PASSWORDS.values())).generate()

for (username, _), hashed_pw in zip(PASSWORDS.items(), hashed):
    config["credentials"]["usernames"][username]["password"] = hashed_pw

with open(CONFIG, "w") as f:
    yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

print("✅ Passwords hashed and written to auth_config.yaml")
print("   Users:", list(PASSWORDS.keys()))
