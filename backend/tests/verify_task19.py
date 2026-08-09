"""
Verification script for Task 1.9 acceptance criteria.
Run inside the backend-api Docker container where postgres/redis are reachable.

Acceptance criteria:
  POST /chat with {"conversation_id": null, "content": "hello"}
  returns a stream AND creates two rows in messages.
  Decrypting them via crypto module yields the plaintext.
"""
import asyncio
import json
import os
import sys
import uuid

# Point LLM at the fake server on the Docker host
os.environ["LLM_PRIMARY_URL"] = "http://host.docker.internal:8088"

# Invalidate any cached settings
import app.config as _cfg
_cfg.get_settings.cache_clear()

from datetime import datetime, timedelta, timezone

from jose import jwt
from sqlalchemy import select, text
from starlette.testclient import TestClient

from app.main import app
from app.db import engine
from app import crypto
from app.models.message import Message


JWT_SECRET = os.environ["JWT_SECRET"]
USER_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"


def make_token() -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": USER_ID,
            "email": "verify@test.com",
            "role": "L1",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=1)).timestamp()),
        },
        JWT_SECRET,
        algorithm="HS256",
    )


def banner(title: str) -> None:
    print(f"\n{'='*60}\n{title}\n{'='*60}")


DB_DSN = (
    f"postgresql://brandbiz:{os.environ['POSTGRES_PASSWORD']}"
    "@postgres:5432/brandbiz"
)


async def _query(sql: str, *args):
    import asyncpg
    conn = await asyncpg.connect(dsn=DB_DSN)
    try:
        return await conn.fetch(sql, *args)
    finally:
        await conn.close()


def count_messages_for_conversation(conv_id: uuid.UUID) -> int:
    rows = asyncio.run(_query(
        "SELECT COUNT(*) AS n FROM messages WHERE conversation_id = $1", str(conv_id)
    ))
    return rows[0]["n"]


def fetch_messages_for_conversation(conv_id: uuid.UUID) -> list:
    rows = asyncio.run(_query(
        "SELECT role, content_ciphertext, content_nonce, content_tag, key_version "
        "FROM messages WHERE conversation_id = $1 ORDER BY created_at",
        str(conv_id),
    ))
    return [(r["role"], bytes(r["content_ciphertext"]), bytes(r["content_nonce"]),
             bytes(r["content_tag"]), r["key_version"]) for r in rows]


def main():
    client = TestClient(app, raise_server_exceptions=False)
    token = make_token()
    headers = {"Authorization": f"Bearer {token}"}
    failures = []

    # ---------------------------------------------------------------
    # Step 1: POST /chat without auth → 401
    # ---------------------------------------------------------------
    banner("Step 1 — 401 without auth")
    r = client.post("/chat", json={"conversation_id": None, "content": "hello"})
    if r.status_code == 401:
        print(f"{PASS}  401 without token")
    else:
        print(f"{FAIL}  expected 401, got {r.status_code}")
        failures.append("no-auth should return 401")

    # ---------------------------------------------------------------
    # Step 2: POST /chat with auth → SSE stream
    # ---------------------------------------------------------------
    banner("Step 2 — SSE stream with valid token")
    r = client.post(
        "/chat",
        json={"conversation_id": None, "content": "hello"},
        headers=headers,
    )
    print(f"Status: {r.status_code}")
    print(f"Content-Type: {r.headers.get('content-type')}")

    if r.status_code != 200:
        print(f"{FAIL}  expected 200, got {r.status_code}: {r.text[:500]}")
        failures.append("POST /chat should return 200")
        print("\nSummary: FAILED (no stream returned)")
        sys.exit(1)

    if "text/event-stream" not in r.headers.get("content-type", ""):
        print(f"{FAIL}  expected text/event-stream content-type")
        failures.append("content-type should be text/event-stream")
    else:
        print(f"{PASS}  content-type: text/event-stream")

    # Parse SSE events
    raw_body = r.text
    print(f"\nRaw SSE body:\n{raw_body}")

    events = []
    for line in raw_body.splitlines():
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except Exception:
                pass

    print(f"\nParsed {len(events)} SSE events:")
    for e in events:
        print(f"  {e}")

    # Check start event
    start_events = [e for e in events if e.get("type") == "start"]
    if start_events:
        print(f"{PASS}  got 'start' event: {start_events[0]}")
        conversation_id = uuid.UUID(start_events[0]["conversation_id"])
        print(f"  conversation_id = {conversation_id}")
    else:
        print(f"{FAIL}  no 'start' event in SSE stream")
        failures.append("stream should have start event")
        conversation_id = None

    # Check content events
    content_events = [e for e in events if e.get("type") == "content"]
    if content_events:
        full_response = "".join(e.get("delta", "") for e in content_events)
        print(f"{PASS}  got {len(content_events)} content chunk(s), full response: {repr(full_response)}")
    else:
        print(f"{FAIL}  no content events")
        failures.append("stream should have content events")
        full_response = ""

    # Check done event
    done_events = [e for e in events if e.get("type") == "done"]
    if done_events:
        print(f"{PASS}  got 'done' event: {done_events[0]}")
    else:
        print(f"{FAIL}  no 'done' event")
        failures.append("stream should have done event")

    if not conversation_id:
        print(f"\nSummary: FAILED (no conversation_id from stream)")
        sys.exit(1)

    # ---------------------------------------------------------------
    # Step 3: Verify two rows in messages table
    # ---------------------------------------------------------------
    banner("Step 3 — two encrypted rows in messages")
    count = count_messages_for_conversation(conversation_id)
    print(f"Rows in messages for this conversation: {count}")
    if count == 2:
        print(f"{PASS}  exactly 2 rows created")
    else:
        print(f"{FAIL}  expected 2 rows, got {count}")
        failures.append(f"expected 2 message rows, got {count}")

    # ---------------------------------------------------------------
    # Step 4: Ciphertext is NOT plaintext, and decrypts to original
    # ---------------------------------------------------------------
    banner("Step 4 — ciphertext decrypt round-trip")
    rows = fetch_messages_for_conversation(conversation_id)
    for row in rows:
        role, ct, nonce, tag, kv = row
        # Verify ciphertext is not plaintext
        ct_bytes = bytes(ct)
        assert b"hello" not in ct_bytes, "user plaintext found in ciphertext!"
        assert b"Hello from the fake LLM" not in ct_bytes, "assistant plaintext in ciphertext!"

        plaintext = crypto.decrypt(ct_bytes, bytes(nonce), bytes(tag), kv)
        print(f"{PASS}  role={role!r:12s}  decrypted={plaintext!r}")

        if role == "user" and plaintext != "hello":
            print(f"{FAIL}  user message decrypt mismatch: {plaintext!r}")
            failures.append("user message should decrypt to 'hello'")
        elif role == "assistant" and not plaintext:
            print(f"{FAIL}  assistant message decrypts to empty string")
            failures.append("assistant message should not be empty")

    # ---------------------------------------------------------------
    # Probe: second request with same conversation_id reuses it
    # ---------------------------------------------------------------
    banner("Probe — second message continues same conversation")
    r2 = client.post(
        "/chat",
        json={"conversation_id": str(conversation_id), "content": "follow-up"},
        headers=headers,
    )
    print(f"Status: {r2.status_code}")
    count2 = count_messages_for_conversation(conversation_id)
    print(f"Rows after second message: {count2}")
    if count2 == 4:
        print(f"{PASS}  4 rows after 2 turns (conversation reused correctly)")
    else:
        print(f"{FAIL}  expected 4 rows after 2 turns, got {count2}")
        failures.append(f"expected 4 rows after 2nd turn, got {count2}")

    # ---------------------------------------------------------------
    # Probe: wrong conversation_id → error in SSE
    # ---------------------------------------------------------------
    banner("Probe — nonexistent conversation_id returns error event")
    bad_id = str(uuid.uuid4())
    r3 = client.post(
        "/chat",
        json={"conversation_id": bad_id, "content": "test"},
        headers=headers,
    )
    body3 = r3.text
    if "error" in body3:
        print(f"{PASS}  unknown conversation_id yields error event")
    else:
        print(f"⚠️   unknown conversation_id response: {body3[:200]}")

    # ---------------------------------------------------------------
    # Final verdict
    # ---------------------------------------------------------------
    banner("Result")
    if failures:
        print(f"{FAIL}  {len(failures)} failure(s):")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print(f"{PASS}  All checks passed — Task 1.9 VERIFIED")


if __name__ == "__main__":
    main()
