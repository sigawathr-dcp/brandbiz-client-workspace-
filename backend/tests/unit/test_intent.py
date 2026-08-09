"""Unit tests for intent detection (app/tools/intent.py)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tools.intent import (
    CODING_MODEL_CODE,
    RESEARCH_MODEL_CODE,
    classify_intent,
    detect_intent_model,
    is_coding_request,
    is_research_request,
)


class TestIsCodingRequest:
    @pytest.mark.parametrize("text", [
        "Write a function to sort a list",
        "Implement a class for user authentication",
        "Debug this error in my code",
        "Fix the bug in the login script",
        "Refactor this program to use async/await",
        "Build an API endpoint for user login",
        "What is the best way to fix this Python bug?",
        "Explain the algorithm for quicksort",
        "How does recursion work?",
        "I keep getting a syntax error in my script",
        "Can you write a unit test for this function?",
        "เขียนโค้ดสำหรับการเรียงลำดับ",
        "แก้ไขบัก",
        "โค้ดนี้แก้ยังไง",
    ])
    def test_coding_true(self, text: str) -> None:
        assert is_coding_request(text) is True

    @pytest.mark.parametrize("text", [
        "Hello!",
        "What is the capital of France?",
        "Who is the president of the US?",
        "Tell me the latest news about AI",
        "Search for information about climate change",
        "Why is the sky blue?",
    ])
    def test_coding_false(self, text: str) -> None:
        assert is_coding_request(text) is False


class TestIsResearchRequest:
    @pytest.mark.parametrize("text", [
        "What is quantum computing?",
        "Who is Elon Musk?",
        "When did World War II end?",
        "Where is the Eiffel Tower located?",
        "How does photosynthesis work?",
        "Why is the sky blue?",
        "Research the history of AI",
        "Look up the price of gold",
        "Search for information about climate change",
        "Find out the latest news on the election",
        "Latest news about the stock market",
        "Current status of the Thailand economy",
        "Recent development in LLM technology",
        "ค้นหาข้อมูลเกี่ยวกับ AI",
        "ข่าวล่าสุดเกี่ยวกับเศรษฐกิจ",
        "หาข้อมูลเรื่องสภาพอากาศ",
    ])
    def test_research_true(self, text: str) -> None:
        assert is_research_request(text) is True

    @pytest.mark.parametrize("text", [
        "Hello!",
        "Write a Python function",
        "Fix this bug in my code",
        "Refactor this class",
        "Generate a unit test",
    ])
    def test_research_false(self, text: str) -> None:
        assert is_research_request(text) is False


class TestClassifyIntent:
    """Tests for the async LLM-based classifier."""

    def _make_router(self, label: str):
        """Return a mock router whose local client streams `label` as content."""
        from app.llm.base import ChatChunk

        async def _stream(messages, **opts):
            yield ChatChunk(content=label)

        client = MagicMock()
        client.stream_chat = _stream

        router = MagicMock()
        router.get.return_value = client
        return router

    async def test_llm_returns_coding(self) -> None:
        with patch("app.llm.router.get_router", return_value=self._make_router("coding")):
            assert await classify_intent("Write a function") == CODING_MODEL_CODE

    async def test_llm_returns_research(self) -> None:
        with patch("app.llm.router.get_router", return_value=self._make_router("research")):
            assert await classify_intent("What is quantum computing?") == RESEARCH_MODEL_CODE

    async def test_llm_returns_general(self) -> None:
        with patch("app.llm.router.get_router", return_value=self._make_router("general")):
            assert await classify_intent("Hello!") is None

    async def test_llm_returns_noisy_label(self) -> None:
        # Model may output "coding\n" or "coding." — still matched
        with patch("app.llm.router.get_router", return_value=self._make_router("coding\n")):
            assert await classify_intent("Debug this script") == CODING_MODEL_CODE

    async def test_fallback_to_regex_on_error(self) -> None:
        # LLM unavailable → falls back to regex
        router = MagicMock()
        router.get.side_effect = Exception("model offline")
        with patch("app.llm.router.get_router", return_value=router):
            # "Write a function" matches coding regex
            result = await classify_intent("Write a function to parse JSON")
            assert result == CODING_MODEL_CODE

    async def test_fallback_to_regex_stream_error(self) -> None:
        async def _failing_stream(messages, **opts):
            raise Exception("connection refused")
            yield  # make it a generator

        client = MagicMock()
        client.stream_chat = _failing_stream
        router = MagicMock()
        router.get.return_value = client

        with patch("app.llm.router.get_router", return_value=router):
            result = await classify_intent("What is the capital of France?")
            assert result == RESEARCH_MODEL_CODE


class TestDetectIntentModel:
    def test_coding_intent_returns_coding_model(self) -> None:
        assert detect_intent_model("Write a function to parse JSON") == CODING_MODEL_CODE

    def test_research_intent_returns_research_model(self) -> None:
        assert detect_intent_model("What is quantum computing?") == RESEARCH_MODEL_CODE

    def test_no_intent_returns_none(self) -> None:
        assert detect_intent_model("Hello!") is None
        assert detect_intent_model("Thank you") is None
        assert detect_intent_model("Can you help me?") is None

    def test_coding_takes_priority_over_research(self) -> None:
        # "What is the best way to fix this Python bug?" matches both
        # (research via "what is", coding via "fix" + "bug") — coding wins.
        result = detect_intent_model("What is the best way to fix this Python bug?")
        assert result == CODING_MODEL_CODE

    def test_thai_coding(self) -> None:
        assert detect_intent_model("เขียนฟังก์ชันสำหรับการเรียงลำดับ") == CODING_MODEL_CODE

    def test_thai_research(self) -> None:
        assert detect_intent_model("ค้นหาข้อมูลเกี่ยวกับ AI") == RESEARCH_MODEL_CODE
