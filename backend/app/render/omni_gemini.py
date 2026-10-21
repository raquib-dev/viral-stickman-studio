"""Gemini Omni Flash 1.1 via the official google-genai SDK and the Interactions API.

Verified against google-genai 2.32.0 and docs/research/platform-signals-2026.md:
model `gemini-omni-1.1-flash` (the preview ID shuts down 2026-10-22), response_format type=video with
aspect_ratio/resolution/duration, video_config.task, previous_interaction_id for 10 s extensions up
to 40 s, first/last-frame image_to_video, output in interaction.output_video, usage tokens for cost.
"""
from __future__ import annotations

import asyncio
import base64
from pathlib import Path

import httpx

from ..settings import secret
from .base import ClipResult, ClipSpec, Log, RenderError
from .cost import gemini_cost_from_tokens
from .media import last_frame

MODEL_ID = "gemini-omni-1.1-flash"
POLL_SECONDS = 8
TIMEOUT_SECONDS = 15 * 60


class OmniGeminiBackend:
    name = "omni-gemini"

    def __init__(self) -> None:
        key = secret("GEMINI_API_KEY")
        if not key:
            raise RenderError("GEMINI_API_KEY is not set in .env", retryable=False)
        from google import genai  # imported lazily so dry-run never needs the SDK configured
        self._client = genai.Client(api_key=key)
        self._key = key

    def _request(self, clip: ClipSpec, prev: ClipResult | None) -> dict:
        req: dict = {
            "model": MODEL_ID,
            "response_format": {"type": "video", "aspect_ratio": clip.ratio, "resolution": clip.resolution,
                                "duration": f"{int(clip.duration)}s"},
            "background": True,
            "store": True,
        }
        if clip.continuity == "extend" and prev and prev.interaction_id:
            req["previous_interaction_id"] = prev.interaction_id
            req["generation_config"] = {"video_config": {"task": "extend"}}
            # aspect ratio is inherited on extend/edit; setting it errors on edit tasks
            req["response_format"].pop("aspect_ratio", None)
            req["input"] = clip.prompt
        elif clip.continuity == "first_frame" and prev and prev.last_frame and prev.last_frame.exists():
            img = base64.b64encode(prev.last_frame.read_bytes()).decode()
            req["generation_config"] = {"video_config": {"task": "image_to_video"}}
            req["input"] = [{"type": "image", "data": img, "mime_type": "image/png"},
                            {"type": "text", "text": clip.prompt}]
        else:
            req["generation_config"] = {"video_config": {"task": "text_to_video"}}
            req["input"] = clip.prompt
        return req

    async def render_clip(self, clip: ClipSpec, prev: ClipResult | None, log: Log) -> ClipResult:
        req = self._request(clip, prev)
        task = req["generation_config"]["video_config"]["task"]
        log(f"omni-gemini clip {clip.index + 1}: {task}, {clip.ratio} {clip.resolution} {clip.duration:.0f}s")
        try:
            inter = await asyncio.to_thread(lambda: self._client.interactions.create(**req))
        except Exception as e:  # SDK raises typed errors; classify by status text
            raise RenderError(f"create failed: {type(e).__name__}: {e}", retryable=_retryable(e)) from e
        iid = inter.id
        waited = 0
        while getattr(inter, "status", None) in ("in_progress", None) and waited < TIMEOUT_SECONDS:
            await asyncio.sleep(POLL_SECONDS)
            waited += POLL_SECONDS
            try:
                inter = await asyncio.to_thread(lambda: self._client.interactions.get(iid))
            except Exception as e:
                log(f"poll error (will retry): {type(e).__name__}")
                continue
            log(f"clip {clip.index + 1}: {inter.status} after {waited}s")
        if inter.status != "completed":
            raise RenderError(f"interaction {iid} ended as {inter.status}", retryable=inter.status != "cancelled")
        video = inter.output_video
        if video is None:
            raise RenderError(f"interaction {iid} completed without output_video")
        out = clip.out_path
        assert out is not None
        out.parent.mkdir(parents=True, exist_ok=True)
        if getattr(video, "data", None):
            data = video.data
            out.write_bytes(base64.b64decode(data) if isinstance(data, str) else data)
        elif getattr(video, "uri", None):
            async with httpx.AsyncClient(timeout=120, follow_redirects=True) as http:
                r = await http.get(video.uri, headers={"x-goog-api-key": self._key})
                r.raise_for_status()
                out.write_bytes(r.content)
        else:
            raise RenderError("output_video has neither data nor uri")
        tokens = int(getattr(getattr(inter, "usage", None), "total_output_tokens", 0) or 0)
        cost = gemini_cost_from_tokens(tokens) if tokens else 0.0
        lf = last_frame(out, out.with_suffix(".last.png"))
        log(f"clip {clip.index + 1}: saved, {tokens} output tokens = ${cost:.2f}")
        return ClipResult(clip.index, out, clip.duration, cost, self.name, interaction_id=iid, last_frame=lf,
                          meta={"output_tokens": tokens, "task": task})


def _retryable(e: Exception) -> bool:
    s = str(e)
    return any(code in s for code in ("429", "500", "502", "503", "504", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "timeout"))
