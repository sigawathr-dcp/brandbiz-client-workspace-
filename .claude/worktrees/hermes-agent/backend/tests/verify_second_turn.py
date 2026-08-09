"""Check second-turn conversation continuation."""
import os, uuid, json, traceback
os.environ["LLM_PRIMARY_URL"] = "http://host.docker.internal:8088"

import app.config as _cfg
_cfg.get_settings.cache_clear()

from datetime import datetime, timedelta, timezone
from jose import jwt
from starlette.testclient import TestClient
from app.main import app

JWT_SECRET = os.environ["JWT_SECRET"]
USER_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

now = datetime.now(timezone.utc)
token = jwt.encode(
    {"sub": USER_ID, "email": "verify@test.com", "role": "L1",
     "iat": int(now.timestamp()), "exp": int((now + timedelta(hours=1)).timestamp())},
    JWT_SECRET, algorithm="HS256",
)
headers = {"Authorization": f"Bearer {token}"}

client = TestClient(app, raise_server_exceptions=True)

# First call — new conversation
r1 = client.post("/chat", json={"conversation_id": None, "content": "hello"}, headers=headers)
events1 = [json.loads(l[6:]) for l in r1.text.splitlines() if l.startswith("data: ")]
conv_id = [e["conversation_id"] for e in events1 if e.get("type") == "start"][0]
print(f"First call: {r1.status_code}, conv_id={conv_id}")

# Second call — same conversation
r2 = client.post(
    "/chat",
    json={"conversation_id": conv_id, "content": "follow-up"},
    headers=headers,
)
print(f"Second call status: {r2.status_code}")
print(f"Second call body: {r2.text[:800]}")
