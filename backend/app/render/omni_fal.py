"""Gemini Omni Flash 1.1 hosted on fal.ai (google/gemini-omni-flash/v1.1/*), billed per output second."""
from __future__ import annotations

import asyncio
import os

import httpx

from ..settings import load_pricing, secret
from .base import ClipResult, ClipSpec, Log, RenderError
from .cost import clip_cost
from .media import last_frame

T2V = "google/gemini-omni-flash/v1.1/text-to-video"
I2V = "google/gemini-omni-flash/v1.1/image-to-video"


class OmniFalBackend:
    name = "omni-fal"

    def __init__(self) -> None:
        key = secret("FAL_KEY")
        if not key:
            raise RenderError("FAL_KEY is not set in .env", retryable=False)
        os.environ["FAL_KEY"] = key  # fal_client reads it from the process env; never logged
        import fal_client
        self._fal = fal_client

    async def render_clip(self, clip: ClipSpec, prev: ClipResult | None, log: Log) -> ClipResult:
        args = {"prompt": clip.prompt, "aspect_ratio": clip.ratio, "resolution": clip.resolution,
                "duration": int(clip.duration)}
        endpoint = T2V
        if clip.continuity in ("first_frame", "extend") and prev and prev.last_frame and prev.last_frame.exists():
            # fal has no extend endpoint in v1.1; continuity uses the previous clip's last frame
            image_url = await asyncio.to_thread(self._fal.upload_file, str(prev.last_frame))
            args["image_url"] = image_url
            args.pop("aspect_ratio", None)
            endpoint = I2V
        log(f"omni-fal clip {clip.index + 1}: {endpoint.rsplit('/', 1)[-1]}, {clip.ratio} {clip.resolution}")

        def _run():
            return self._fal.subscribe(endpoint, arguments=args, with_logs=False)
        try:
            result = await asyncio.to_thread(_run)
        except Exception as e:
            s = str(e)
            raise RenderError(f"fal request failed: {type(e).__name__}: {s[:300]}",
                              retryable=any(c in s for c in ("429", "500", "502", "503", "504", "timeout"))) from e
        url = (result.get("video") or {}).get("url")
        if not url:
            raise RenderError(f"fal returned no video url: keys={list(result)}")
        out = clip.out_path
        assert out is not None
        out.parent.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(timeout=180, follow_redirects=True) as http:
            r = await http.get(url)
            r.raise_for_status()
            out.write_bytes(r.content)
        cost = clip_cost(load_pricing(), self.name, clip.resolution, clip.duration)
        lf = last_frame(out, out.with_suffix(".last.png"))
        log(f"clip {clip.index + 1}: saved (${cost:.2f} at the listed per-second rate)")
        return ClipResult(clip.index, out, clip.duration, cost, self.name, last_frame=lf,
                          meta={"endpoint": endpoint, "request_id": result.get("request_id")})
