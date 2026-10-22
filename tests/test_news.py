"""Live AI news research: each public source parsed from its API shape (faked with httpx.MockTransport), a failing
source skipped, ranking with a brief, the news component of the topic score, and the News -> Topics flow."""
import datetime as dt
import json

import httpx

from backend.app import db, paths
from backend.app import stages  # noqa: F401  (registers the stages)
from backend.app.analysis import topics as T
from backend.app.jobs import manager
from backend.app.sources import news as N

NOW = dt.datetime.now(dt.timezone.utc)
TS = int((NOW - dt.timedelta(days=1)).timestamp())
ISO = (NOW - dt.timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
RSS = f"""<?xml version="1.0"?><rss version="2.0"><channel><title>Claude Status - Incident History</title>
<item><title>Elevated errors on Claude Opus</title><link>https://status.example/incidents/1</link>
<pubDate>{(NOW - dt.timedelta(days=1)).strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate>
<description>&lt;p&gt;We are investigating elevated error rates.&lt;/p&gt;</description></item>
<item><title>Old incident</title><link>https://status.example/incidents/0</link><pubDate>Mon, 01 Jan 2024 00:00:00 +0000</pubDate></item>
</channel></rss>"""
ATOM = f"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>Changelog</title>
<entry><title>Copilot agent mode is now available</title><link href="https://blog.example/changelog/1"/>
<updated>{ISO}</updated><summary>Rolling out today.</summary></entry></feed>"""


def handler(req: httpx.Request) -> httpx.Response:
    u = str(req.url)
    assert "User-Agent" in req.headers and "viral-stickman-studio" in req.headers["User-Agent"]
    if "hn.algolia.com" in u:
        return httpx.Response(200, json={"hits": [{"objectID": "1", "title": "Claude Code now supports background agents",
                                                   "url": "https://news.example/a", "points": 420, "num_comments": 230,
                                                   "created_at_i": TS, "author": "someone"}]})
    if "reddit.com" in u:
        return httpx.Response(200, json={"data": {"children": [
            {"data": {"title": "Hit my usage limit again before lunch", "selftext": "Pro plan, three prompts, limit reached.",
                      "permalink": "/r/ClaudeAI/comments/x1/hit/", "score": 900, "num_comments": 310, "created_utc": TS,
                      "subreddit": "ClaudeAI", "link_flair_text": "Complaint", "author": "someone"}},
            {"data": {"title": "nsfw", "over_18": True, "permalink": "/r/x/2", "created_utc": TS}},
            {"data": {"title": "Weekly thread", "stickied": True, "permalink": "/r/x/3", "created_utc": TS}}]}})
    if "api.github.com" in u:
        return httpx.Response(200, json={"items": [{"title": "Agent deletes the failing test instead of fixing it",
                                                    "html_url": "https://github.com/anthropics/claude-code/issues/9",
                                                    "body": "Steps: ask it to fix a test. It removes the test.", "created_at": ISO,
                                                    "reactions": {"total_count": 150}, "comments": 40, "user": {"login": "someone"}}]})
    if u.endswith("history.rss"):
        return httpx.Response(200, text=RSS)
    if u.endswith("changelog/feed/"):
        return httpx.Response(200, text=ATOM)
    return httpx.Response(403, text="blocked")


CFG = {"days": 14, "max_items": 50, "sources": {"hackernews": True, "reddit": True, "github": True, "feeds": True},
       "hn_queries": ["Claude"], "subreddits": ["ClaudeAI"], "github_repos": ["anthropics/claude-code"],
       "feeds": ["https://status.example/history.rss", "https://blog.example/changelog/feed/", "https://blocked.example/feed.xml"]}


def test_gather_reads_every_source_and_skips_a_blocked_one():
    logs = []
    data = N.gather(CFG, [], "", lambda t, lv="info": logs.append((lv, t)), httpx.MockTransport(handler))
    items = data["items"]
    by = {i["source"]: i for i in items}
    assert {"hackernews", "reddit", "github", "feed"} <= set(by)
    assert by["reddit"]["kind"] == "problem" and by["reddit"]["where"] == "r/ClaudeAI" and by["reddit"]["tools"] == ["Claude"]
    assert by["github"]["kind"] == "problem" and by["github"]["engagement"] == 150
    assert by["hackernews"]["discussion_url"] == "https://news.ycombinator.com/item?id=1"
    kinds = {i["title"]: i["kind"] for i in items}
    assert kinds["Elevated errors on Claude Opus"] == "outage" and kinds["Copilot agent mode is now available"] == "update"
    assert "Old incident" not in kinds and "nsfw" not in kinds and "Weekly thread" not in kinds   # old, adult, pinned: out
    assert not any("someone" in json.dumps(i) for i in items)          # authors are never kept
    assert data["sources"]["feed https://blocked.example/feed.xml"] == {"ok": False, "count": 0, "error": "HTTP 403"}
    assert any(lv == "warn" and "skipped" in t for lv, t in logs)
    assert all(a["score"] >= b["score"] for a, b in zip(items, items[1:]))
    assert "<p>" not in json.dumps(items)                                 # HTML stripped from excerpts


def test_brief_filters_and_boosts():
    data = N.gather(CFG, ["usage limit"], "usage limit before lunch", transport=httpx.MockTransport(handler))
    assert data["items"] and data["items"][0]["title"] == "Hit my usage limit again before lunch"
    assert all(N.keywords(i["title"] + " " + i["text"]) & N.keywords("usage limit before lunch") for i in data["items"])
    checked = N.check(CFG, transport=httpx.MockTransport(handler))
    assert checked["hackernews"]["ok"] and not checked["feed https://blocked.example/feed.xml"]["ok"]


def test_topic_score_counts_real_posts_only_when_there_is_news():
    news = [{"id": "a", "score": 1.0, "title": "t", "url": "u", "where": "w", "kind": "problem", "date": "d"},
            {"id": "b", "score": 0.5, "title": "t2", "url": "u2", "where": "w", "kind": "update", "date": "d"}]
    cands = [{"id": "x", "title": "usage limits", "angle": "a", "stickman_fit": 3, "news_ids": ["a"]},
             {"id": "y", "title": "usage limits", "angle": "a", "stickman_fit": 3, "news_ids": ["b"]},
             {"id": "z", "title": "usage limits", "angle": "a", "stickman_fit": 3}]
    ranked = T.score_candidates(cands, [], "ai tools", news=news)
    comp = {r["id"]: r["components"]["news"] for r in ranked}
    assert comp == {"x": 1.0, "y": 0.5, "z": 0.0} and [r["id"] for r in ranked] == ["x", "y", "z"]
    assert ranked[0]["sources"][0]["url"] == "u" and "sources" not in ranked[2]
    plain = T.score_candidates(cands[2:], [], "ai tools")
    assert "news" not in plain[0]["components"]                         # no live news: the weight does not count


async def test_brief_runs_news_then_topics_grounded_in_it():
    await manager.start()
    slug = "news-brief"
    db.upsert_project(slug, slug, {"name": slug, "niche": "AI coding tools", "subtopics": [], "platforms": ["shorts"], "style": "1",
                                   "theme": "dark", "ratio": "9:16", "duration": 30, "format": "dialogue",
                                   "topic_brief": "AI that deletes tests instead of fixing them"})
    _, fut = manager.submit(slug, "news", {})
    assert await fut == "succeeded"
    _, fut = manager.submit(slug, "topics", {})                          # no discovery or patterns yet: still works
    assert await fut == "succeeded"
    await manager.stop()
    root = paths.project_dir(slug)
    news = json.loads((root / "research/news.json").read_text())
    assert news["synthetic"] and news["brief"].startswith("AI that deletes")
    tp = json.loads((root / "research/topics.json").read_text())
    top = tp["topics"][0]
    assert tp["brief"].startswith("AI that deletes") and top["story"] and top["sources"] and "news" in top["components"]
    from backend.app.agent import tasks
    assert "REAL STORY" in tasks.hooks(top, "AI", "shorts", []).prompt


def test_research_endpoint_saves_the_brief_and_runs_news_then_topics(monkeypatch):
    import asyncio

    from fastapi.testclient import TestClient

    from backend.app import main
    calls = []

    def submit(slug, stage, params=None):
        calls.append((stage, params))
        f = asyncio.get_event_loop().create_future()
        f.set_result("succeeded")
        return len(calls), f
    monkeypatch.setattr(main.manager, "submit", submit)
    monkeypatch.setattr(N, "check", lambda cfg, transport=None, token=None: {"hackernews": {"ok": True, "count": 1}})   # no real requests in tests
    db.upsert_project("brief-api", "brief-api", {"name": "brief-api", "niche": "AI tools", "platforms": ["shorts"]})
    with TestClient(main.app) as c:
        r = c.post("/api/projects/brief-api/research", json={"brief": "  Gemini vs ChatGPT for homework  "}).json()
        assert c.get("/api/research/check").json() == {"sources": {"hackernews": {"ok": True, "count": 1}}}
    assert r["brief"] == "Gemini vs ChatGPT for homework"
    assert db.get_project("brief-api")["data"]["topic_brief"] == "Gemini vs ChatGPT for homework"
    assert calls[0] == ("news", {"brief": "Gemini vs ChatGPT for homework"}) and calls[1][0] == "topics"
