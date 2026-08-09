"""
Live Anthropic API smoke test.

Requires ANTHROPIC_API_KEY to be set in .env or the environment.
Skipped automatically if the key is absent.

Cost: one call to claude-haiku-4-5-20251001 with max_tokens=16 — < $0.001.
"""
import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set — skipping live API test",
)


@pytest.mark.asyncio
async def test_say_hi_returns_streamed_response_with_token_counts():
    from app.llm.anthropic import AnthropicClient
    from app.llm.base import ChatMessage

    client = AnthropicClient(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        model="claude-haiku-4-5-20251001",  # cheapest model to minimise cost
    )

    chunks = [
        c async for c in client.stream_chat(
            [ChatMessage(role="user", content="Say hi")],
            max_tokens=16,
        )
    ]

    text = "".join(c.content for c in chunks if c.content)
    final = chunks[-1]

    assert text, "Expected non-empty response text"
    assert final.prompt_tokens is not None and final.prompt_tokens > 0, (
        f"prompt_tokens should be > 0, got {final.prompt_tokens}"
    )
    assert final.completion_tokens is not None and final.completion_tokens > 0, (
        f"completion_tokens should be > 0, got {final.completion_tokens}"
    )
    assert final.finish_reason in ("end_turn", "max_tokens"), (
        f"Unexpected finish_reason: {final.finish_reason}"
    )

    print(f"\n  response text : {text!r}")
    print(f"  prompt_tokens : {final.prompt_tokens}")
    print(f"  output_tokens : {final.completion_tokens}")
    print(f"  finish_reason : {final.finish_reason}")
