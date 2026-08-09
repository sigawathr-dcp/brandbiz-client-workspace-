"""Generate a short-lived test JWT for the demo admin user. Dev use only."""
import os, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Hardcoded demo values already present in demo_seed.py in this repo
os.environ["POSTGRES_PASSWORD"] = "12345"
os.environ["ENCRYPTION_KEY"] = "dsLIVp2jf2zWt6r221644BRLChNuWF08+YF7c2RT9Rc="
os.environ["JWT_SECRET"] = "86eea55b46f72283a75b0353d0f68ed029ccf78044154e25b22ade163e090c49"
os.environ.setdefault("REDIS_CACHE_URL", "redis://localhost:6379/0")

sys.path.insert(0, str(Path(__file__).parent))
from jose import jwt as jose_jwt

secret = os.environ["JWT_SECRET"]
admin_id = "5a3f8036-fb1c-4015-a924-1d6b0ca34ced"
exp = datetime.now(timezone.utc) + timedelta(hours=1)
token = jose_jwt.encode({"sub": admin_id, "exp": exp}, secret, algorithm="HS256")
print(token)
