"""YouTube Data API v3, read-only with an API key (no OAuth, no write methods exist in this module).

Quota (docs/research/platform-signals-2026.md): 10,000 units/day by default; search.list has its own
bucket since 2026-06-01; channels/playlistItems/videos.list cost 1 unit per call.
captions.download needs edit rights on the video, so transcripts come from sources/transcripts.py.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Callable

import httpx

from ..settings import secret

API = "https://www.googleapis.com/youtube/v3"
BIAS_TERMS = ["stick figure animation", "animated explainer", "stickman"]


class YouTubeError(RuntimeError):
    pass


def iso_duration(s: str) -> int:
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s or "")
    if not m:
        return 0
    d, h, mi, se = (int(x) if x else 0 for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + se


class YouTubeClient:
    def __init__(self, log: Callable[[str], None]):
        self.key = secret("YOUTUBE_API_KEY")
        if not self.key:
            raise YouTubeError("YOUTUBE_API_KEY is not set in .env (see README: 'Get a YouTube API key')")
        self.log = log
        self.units = {"search": 0, "other": 0}
        self.http = httpx.Client(timeout=30)

    def _get(self, path: str, params: dict, bucket: str = "other", cost: int = 1) -> dict:
        r = self.http.get(f"{API}/{path}", params={**params, "key": self.key})
        self.units[bucket] += cost
        if r.status_code != 200:
            try:
                reason = r.json()["error"]["errors"][0]["reason"]
            except Exception:
                reason = r.text[:200]
            raise YouTubeError(f"{path} HTTP {r.status_code}: {reason}")
        return r.json()

    def search_videos(self, query: str, duration: str = "any", max_results: int = 25, months: int = 12) -> list[str]:
        after = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30 * months)).strftime("%Y-%m-%dT%H:%M:%SZ")
        d = self._get("search", {"part": "snippet", "q": query, "type": "video", "maxResults": max_results,
                                 "videoDuration": duration, "publishedAfter": after, "relevanceLanguage": "en"},
                      bucket="search", cost=100)
        return [it["id"]["videoId"] for it in d.get("items", []) if it.get("id", {}).get("videoId")]

    def videos(self, ids: list[str]) -> list[dict]:
        out = []
        for i in range(0, len(ids), 50):
            d = self._get("videos", {"part": "snippet,statistics,contentDetails", "id": ",".join(ids[i:i + 50])})
            for v in d.get("items", []):
                out.append({"id": v["id"], "channel_id": v["snippet"]["channelId"], "channel": v["snippet"]["channelTitle"],
                            "title": v["snippet"]["title"], "views": int(v.get("statistics", {}).get("viewCount", 0)),
                            "duration": iso_duration(v["contentDetails"].get("duration", "")),
                            "published": v["snippet"].get("publishedAt"),
                            "url": f"https://www.youtube.com/watch?v={v['id']}"})
        return out

    def channel_recent(self, channel_id: str, n: int = 30) -> list[dict]:
        d = self._get("channels", {"part": "contentDetails", "id": channel_id})
        items = d.get("items") or []
        if not items:
            return []
        uploads = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
        p = self._get("playlistItems", {"part": "contentDetails", "playlistId": uploads, "maxResults": min(50, n)})
        ids = [it["contentDetails"]["videoId"] for it in p.get("items", [])]
        return self.videos(ids)

    def channel_ids_for(self, handles_or_urls: list[str]) -> list[str]:
        out = []
        for h in handles_or_urls:
            h = h.strip()
            m = re.search(r"(UC[0-9A-Za-z_-]{22})", h)
            if m:
                out.append(m.group(1))
                continue
            handle = h.rsplit("/", 1)[-1].lstrip("@")
            if handle:
                d = self._get("channels", {"part": "id", "forHandle": "@" + handle})
                out += [it["id"] for it in d.get("items", [])]
        return out

    def discover(self, niche: str, subtopics: list[str], competitors: list[str], fmt: str,
                 per_channel: int, max_channels: int) -> list[dict]:
        """Collect rows for yt-viral/swipe.py: recent uploads of channels that surfaced for the niche
        (biased toward stick-figure / animated-explainer formats) plus the user's known competitors."""
        duration = "short" if fmt in ("shorts", "reels") else "medium"
        queries = [f"{niche} {b}" for b in BIAS_TERMS[:2]] + [f"{s} {BIAS_TERMS[0]}" for s in subtopics[:2]]
        seen_channels: dict[str, str] = {}
        for q in queries:
            ids = self.search_videos(q, duration=duration)
            self.log(f"search '{q}': {len(ids)} videos")
            for v in self.videos(ids):
                seen_channels.setdefault(v["channel_id"], v["channel"])
        for cid in self.channel_ids_for(competitors):
            seen_channels.setdefault(cid, cid)
        rows = []
        for cid in list(seen_channels)[:max_channels]:
            vids = self.channel_recent(cid, per_channel)
            self.log(f"channel {seen_channels[cid]}: {len(vids)} recent uploads")
            rows += vids
        self.log(f"quota used: search {self.units['search']} units, other {self.units['other']} units")
        return rows
