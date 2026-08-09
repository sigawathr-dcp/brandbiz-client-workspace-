from __future__ import annotations

import asyncio
import re
import time
from typing import AsyncIterator

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from app.llm.base import ChatChunk, ChatMessage, LLMClient, LLMProviderError


def _google_message(exc: genai_errors.APIError) -> str:
    """Extract the human-readable message from a Google genai APIError."""
    raw = str(exc)
    m = re.search(r"'message':\s*'([^']+)'", raw)
    if m:
        return m.group(1)
    # Trim the JSON blob if present (everything after the first '{')
    idx = raw.find("{")
    return raw[:idx].strip() if idx != -1 else raw

_DEFAULT_TEXT_MODEL = "gemini-2.5-flash"
_DEFAULT_IMAGE_MODEL = "imagen-4.0-fast-generate-001"
_VEO_POLL_INTERVAL_S = 10  # seconds between status polls
_VEO_TIMEOUT_S = 600  # 10-minute hard timeout


class GoogleClient(LLMClient):
    def __init__(
        self,
        api_key: str,
        text_model: str = _DEFAULT_TEXT_MODEL,
        image_model: str = _DEFAULT_IMAGE_MODEL,
    ) -> None:
        self._text_model = text_model
        self._image_model = image_model
        self._client = genai.Client(api_key=api_key)

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        **opts,
    ) -> AsyncIterator[ChatChunk]:
        system_text: str | None = None
        contents: list[dict] = []
        for m in messages:
            if m.role == "system":
                system_text = m.content
            else:
                role = "model" if m.role == "assistant" else "user"
                contents.append({"role": role, "parts": [{"text": m.content}]})

        config_args: dict = {}
        if system_text is not None:
            config_args["system_instruction"] = system_text
        if "max_tokens" in opts:
            config_args["max_output_tokens"] = opts.pop("max_tokens")
        config_args.update(opts)

        config: genai_types.GenerateContentConfig | None = (
            genai_types.GenerateContentConfig(**config_args) if config_args else None
        )

        try:
            prompt_tokens: int | None = None
            completion_tokens: int | None = None
            finish_reason: str | None = None

            async for chunk in await self._client.aio.models.generate_content_stream(
                model=self._text_model,
                contents=contents,
                config=config,
            ):
                if chunk.text:
                    yield ChatChunk(content=chunk.text, model=self._text_model)
                if chunk.usage_metadata is not None:
                    um = chunk.usage_metadata
                    if um.prompt_token_count is not None:
                        prompt_tokens = um.prompt_token_count
                    if um.candidates_token_count is not None:
                        completion_tokens = um.candidates_token_count
                if chunk.candidates:
                    fr = chunk.candidates[0].finish_reason
                    if fr is not None:
                        fr_val = fr.value if hasattr(fr, "value") else 0
                        if fr_val != 0:
                            finish_reason = fr.name if hasattr(fr, "name") else str(fr)

            yield ChatChunk(
                content="",
                model=self._text_model,
                finish_reason=finish_reason,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
        except genai_errors.APIError as exc:
            code = getattr(exc, "code", None)
            raise LLMProviderError(_google_message(exc), provider_code=code) from exc
        except LLMProviderError:
            raise
        except Exception as exc:
            raise LLMProviderError(f"google unreachable: {exc}") from exc

    async def generate_image(self, prompt: str) -> bytes:
        """Generate an image using Imagen. Returns raw image bytes (PNG/JPEG)."""
        try:
            response = await asyncio.to_thread(
                lambda: self._client.models.generate_images(
                    model=self._image_model,
                    prompt=prompt,
                    config=genai_types.GenerateImagesConfig(number_of_images=1),
                )
            )
            return response.generated_images[0].image.image_bytes
        except genai_errors.APIError as exc:
            code = getattr(exc, "code", None)
            raise LLMProviderError(_google_message(exc), provider_code=code) from exc
        except LLMProviderError:
            raise
        except Exception as exc:
            raise LLMProviderError(f"google unreachable: {exc}") from exc

    async def generate_image_gemini(
        self,
        prompt: str,
        model: str = "gemini-3.1-flash-image",
        references: list[tuple[bytes, str]] | None = None,
    ) -> tuple[bytes, str]:
        """Generate an image via a Gemini model using generate_content with IMAGE modality.

        Unlike Imagen, this path uses the standard content-generation API and does
        not require a separately billed Imagen quota.

        ``references`` is an optional list of (image_bytes, mime_type) pairs that
        are prepended to the prompt as inline image parts so the model can use them
        as style or subject references.

        Returns:
            (image_bytes, mime_type) — raw image bytes and the MIME type reported
            by the API (e.g. ``"image/jpeg"`` or ``"image/png"``).
        """
        import base64 as _b64

        try:
            if references:
                contents: object = [
                    genai_types.Part.from_bytes(data=data, mime_type=mime)
                    for data, mime in references
                ] + [prompt]
            else:
                contents = prompt

            response = await asyncio.to_thread(
                lambda: self._client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=genai_types.GenerateContentConfig(
                        response_modalities=["IMAGE"],
                    ),
                )
            )
            for candidate in response.candidates or []:
                for part in (candidate.content.parts or []):
                    if part.inline_data is not None:
                        data = part.inline_data.data
                        mime_type: str = getattr(part.inline_data, "mime_type", None) or "image/jpeg"
                        # SDK may return bytes or a base64 string depending on version
                        if isinstance(data, (bytes, bytearray)):
                            return bytes(data), mime_type
                        return _b64.b64decode(data), mime_type
            raise LLMProviderError(
                f"Gemini model '{model}' returned no image data in the response"
            )
        except genai_errors.APIError as exc:
            code = getattr(exc, "code", None)
            raise LLMProviderError(_google_message(exc), provider_code=code) from exc
        except LLMProviderError:
            raise
        except Exception as exc:
            raise LLMProviderError(f"google unreachable: {exc}") from exc

    async def generate_music(
        self, prompt: str, *, model: str = "lyria-3-clip-preview"
    ) -> tuple[bytes, str]:
        """Generate music via Lyria. Returns (audio_bytes, mime_type) e.g. ('audio/mpeg').

        Calls generate_content with AUDIO modality and extracts inline audio bytes.
        Default output is MP3 at 44.1 kHz stereo.
        """
        import base64 as _b64

        try:
            response = await asyncio.to_thread(
                lambda: self._client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                    ),
                )
            )
            for candidate in response.candidates or []:
                for part in (candidate.content.parts or []):
                    if part.inline_data is not None:
                        data = part.inline_data.data
                        mime_type: str = getattr(part.inline_data, "mime_type", None) or "audio/mpeg"
                        # SDK may return bytes or a base64 string depending on version
                        if isinstance(data, (bytes, bytearray)):
                            return bytes(data), mime_type
                        return _b64.b64decode(data), mime_type
            raise LLMProviderError(
                f"Lyria model '{model}' returned no audio data in the response"
            )
        except genai_errors.APIError as exc:
            code = getattr(exc, "code", None)
            raise LLMProviderError(_google_message(exc), provider_code=code) from exc
        except LLMProviderError:
            raise
        except Exception as exc:
            raise LLMProviderError(f"google unreachable: {exc}") from exc

    async def generate_video(
        self,
        prompt: str,
        *,
        model: str,
        aspect_ratio: str = "16:9",
        duration_seconds: int = 5,
    ) -> tuple[bytes, str]:
        """Generate a video using Veo. Returns (mp4_bytes, 'video/mp4').

        Submits a long-running generate_videos job, polls until done (up to
        ``_VEO_TIMEOUT_S`` seconds), then extracts inline video bytes.
        Raises ``LLMProviderError`` on provider errors or timeout.
        """
        try:
            # Submit job (blocking SDK call → run in thread)
            def _submit() -> object:
                return self._client.models.generate_videos(
                    model=model,
                    prompt=prompt,
                    config=genai_types.GenerateVideosConfig(
                        aspect_ratio=aspect_ratio,
                        duration_seconds=duration_seconds,
                        number_of_videos=1,
                    ),
                )

            operation = await asyncio.to_thread(_submit)

            # Poll until done or timeout
            deadline = time.monotonic() + _VEO_TIMEOUT_S
            while not operation.done:
                if time.monotonic() >= deadline:
                    raise LLMProviderError(
                        f"Veo job timed out after {_VEO_TIMEOUT_S}s"
                    )
                await asyncio.sleep(_VEO_POLL_INTERVAL_S)
                operation = await asyncio.to_thread(
                    lambda op=operation: self._client.operations.get(op)
                )

            # Extract inline video bytes
            generated = operation.response.generated_videos
            if not generated:
                raise LLMProviderError("Veo returned no generated videos in response")
            video = generated[0].video
            if video is None:
                raise LLMProviderError("Veo generated_videos[0].video is None")
            # With the Gemini Developer API (api_key auth) Veo returns a uri
            # rather than inline bytes; download the file to obtain the bytes.
            video_bytes: bytes | None = getattr(video, "video_bytes", None)
            if video_bytes is None:
                video_bytes = await asyncio.to_thread(
                    lambda: self._client.files.download(file=video)
                )
            if not video_bytes:
                raise LLMProviderError("Veo returned no downloadable video bytes")
            mime_type = getattr(video, "mime_type", None) or "video/mp4"
            return bytes(video_bytes), mime_type

        except genai_errors.APIError as exc:
            code = getattr(exc, "code", None)
            raise LLMProviderError(_google_message(exc), provider_code=code) from exc
        except LLMProviderError:
            raise
        except Exception as exc:
            raise LLMProviderError(f"google unreachable: {exc}") from exc
