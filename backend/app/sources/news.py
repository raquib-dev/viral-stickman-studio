"""Live AI news and real user problems, from public sources only (no login, nothing behind auth):

- Hacker News (the public Algolia search API): launches, outages, long discussions;
- Reddit's public JSON listings (r/ClaudeAI, r/ChatGPT, ...): what users run into and complain about;
- GitHub issues on public repos (anthropics/claude-code, openai/codex, google-gemini/gemini-cli): real bugs, the
  reactions show how many people hit them;
- RSS/Atom feeds: status pages (outages), product blogs and changelogs (updates).

Every item keeps its source URL, date and engagement, and is tagged with the AI tools it mentions and a kind
(problem, update, outage, discussion). Authors' names are never kept: the videos are about situations, not people.
"""
from __future__ import annotations

import datetime as dt
import email.utils
import hashlib
import html
import math
import re
import time
import xml.etree.ElementTree as ET
from typing import Callable
from urllib.parse import quote_plus

import httpx

UA = "viral-stickman-studio/1.0 (local topic research; read-only)"
TOOLS = [("Claude", r"\bclaude|anthropic|\bsonnet\b|\bopus\b|\bhaiku\b"), ("Codex", r"\bcodex\b"),
         ("ChatGPT", r"chat ?gpt|openai|\bgpt-?\d"), ("Gemini", r"\bgemini\b|\bbard\b|deepmind"),
         ("Cursor", r"\bcursor\b"), ("Copilot", r"copilot"), ("Grok", r"\bgrok\b"), ("DeepSeek", r"deepseek"),
         ("Llama", r"\bllama\b"), ("Mistral", r"\bmistral\b")]
PROBLEM = re.compile(r"\b(bug|broken|breaks?|error|fails?|failing|crash\w*|limit\w*|rate.?limit|usage cap|outage|down|"
                     r"degraded|refund|worse|nerf\w*|lazy|forgot|forgets|ignor\w+|halluc\w+|deleted?|wiped|stuck|loop\w*|"
                     r"slow|annoying|frustrat\w+|why does|keeps?)\b", re.I)
UPDATE = re.compile(r"\b(releas\w+|launch\w*|introduc\w+|announc\w+|now available|new model|update[sd]?|ships?|"
                    r"rolling out|available today|v\d+(\.\d+)*|changelog)\b", re.I)
OUTAGE = re.compile(r"\b(incident|outage|degraded|elevated error|partial|major|investigating|resolved|identified|"
                    r"monitoring)\b", re.I)
KIND_WEIGHT = {"problem": 1.0, "outage": 1.0, "update": 0.9, "discussion": 0.7}
STOP = set("""a an the and or but of to in on at for with from by is are was were be it its this that these those i you we
they my your our their me us them what why how when where who which do does did not no yes just so very really can will
would should could have has had about into than then there here as if all any some more most get got make makes ai""".split())


def tools_in(text: str) -> list[str]:
    return [name for name, rx in TOOLS if re.search(rx, text or "", re.I)]


def keywords(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9][a-z0-9'+.-]{2,}", (text or "").lower()) if w not in STOP}


def classify(title: str, text: str, source: str, hint: str = "") -> str:
    blob = f"{title} {hint} {text[:300]}"
    if source == "github":
        return "problem"
    if source == "status":
        return "outage"
    if source == "feed":
        return "update" if not OUTAGE.search(blob) else "outage"
    if re.search(r"bug|complaint|issue|help", hint or "", re.I) or PROBLEM.search(title):
        return "problem"
    if UPDATE.search(title) or re.search(r"news|announcement|update", hint or "", re.I):
        return "update"
    return "problem" if PROBLEM.search(blob) else "discussion"


def plain(text: str, n: int = 500) -> str:
    """Readable excerpt: no HTML tags, markdown links reduced to their words, whitespace collapsed."""
    t = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
    t = re.sub(r"```.*?```", " [code] ", t, flags=re.S)
    t = re.sub(r"\s+", " ", t).strip()
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "…"


def _id(source: str, url: str) -> str:
    return f"{source}-{hashlib.sha1(url.encode()).hexdigest()[:8]}"


def _item(source: str, where: str, title: str, url: str, text: str, date: dt.datetime, engagement: int,
          comments: int = 0, discussion_url: str = "", hint: str = "") -> dict:
    title = plain(title, 200)
    return {"id": _id(source, url), "source": source, "where": where, "title": title, "url": url,
            "discussion_url": discussion_url or url, "text": plain(text), "date": date.astimezone(dt.timezone.utc).isoformat(timespec="minutes"),
            "engagement": int(engagement or 0), "comments": int(comments or 0),
            "kind": classify(title, plain(text), "status" if source == "feed" and "status" in where.lower() else source, hint),
            "tools": tools_in(f"{title} {text} {where}")}


# ---- sources -----------------------------------------------------------------------------------

def fetch_hn(http: httpx.Client, queries: list[str], since: dt.datetime, per: int = 15) -> list[dict]:
    out = []
    for q in queries:
        r = http.get("https://hn.algolia.com/api/v1/search", params={
            "query": q, "tags": "story", "numericFilters": f"created_at_i>{int(since.timestamp())}", "hitsPerPage": per})
        r.raise_for_status()
        for h in r.json().get("hits", []):
            disc = f"https://news.ycombinator.com/item?id={h.get('objectID')}"
            out.append(_item("hackernews", "Hacker News", h.get("title") or "", h.get("url") or disc, h.get("story_text") or "",
                             dt.datetime.fromtimestamp(int(h.get("created_at_i") or 0), dt.timezone.utc),
                             h.get("points") or 0, h.get("num_comments") or 0, disc))
    return out


def _reddit_window(days: int) -> str:
    return "day" if days <= 1 else "week" if days <= 7 else "month" if days <= 31 else "year"


def fetch_reddit(http: httpx.Client, subs: list[str], queries: list[str], days: int, per: int = 25) -> list[dict]:
    if not subs:
        return []
    multi = "+".join(re.sub(r"[^A-Za-z0-9_]", "", s) for s in subs)
    window = _reddit_window(days)
    urls = [f"https://www.reddit.com/r/{multi}/top.json?t={window}&limit={per}"]
    urls += [f"https://www.reddit.com/r/{multi}/search.json?q={quote_plus(q)}&restrict_sr=1&sort=top&t={window}&limit={per}"
             for q in queries]
    out = []
    for u in urls:
        r = http.get(u)
        r.raise_for_status()
        for c in (r.json().get("data") or {}).get("children", []):
            d = c.get("data") or {}
            if d.get("over_18") or d.get("stickied"):
                continue
            link = "https://www.reddit.com" + (d.get("permalink") or "")
            out.append(_item("reddit", f"r/{d.get('subreddit', '')}", d.get("title") or "", link, d.get("selftext") or "",
                             dt.datetime.fromtimestamp(float(d.get("created_utc") or 0), dt.timezone.utc),
                             d.get("score") or 0, d.get("num_comments") or 0, link, d.get("link_flair_text") or ""))
    return out


def fetch_github(http: httpx.Client, repos: list[str], queries: list[str], since: dt.datetime, per: int = 15,
                 token: str | None = None) -> list[dict]:
    headers = {"Accept": "application/vnd.github+json", **({"Authorization": f"Bearer {token}"} if token else {})}
    out = []
    for repo in repos:
        for q in [""] + queries[:2]:                   # search allows 10 requests a minute without a token
            terms = f"repo:{repo} is:issue created:>{since.date().isoformat()}" + (f" {q}" if q else "")
            r = http.get("https://api.github.com/search/issues", params={"q": terms, "sort": "reactions", "order": "desc",
                                                                         "per_page": per}, headers=headers)
            r.raise_for_status()
            for it in r.json().get("items", []):
                out.append(_item("github", repo, it.get("title") or "", it.get("html_url") or "", it.get("body") or "",
                                 dt.datetime.fromisoformat((it.get("created_at") or "1970-01-01T00:00:00Z").replace("Z", "+00:00")),
                                 (it.get("reactions") or {}).get("total_count", 0), it.get("comments") or 0))
    return out


def _date(s: str | None) -> dt.datetime | None:
    if not s:
        return None
    try:
        d = email.utils.parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:
            d = dt.datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def parse_feed(xml_text: str, url: str) -> list[dict]:
    """RSS 2.0 or Atom entries as items (status pages read as outages, blogs and changelogs as updates)."""
    root = ET.fromstring(xml_text)
    A = "{http://www.w3.org/2005/Atom}"
    title = (root.findtext("channel/title") or root.findtext(f"{A}title") or url).strip()
    where = title if len(title) <= 60 else title[:57] + "…"
    out = []
    for it in root.findall("channel/item"):
        d = _date(it.findtext("pubDate"))
        link = (it.findtext("link") or "").strip()
        if d and link:
            out.append(_item("feed", where, it.findtext("title") or "", link, it.findtext("description") or "", d, 0))
    for e in root.findall(f"{A}entry"):
        d = _date(e.findtext(f"{A}updated") or e.findtext(f"{A}published"))
        ln = e.find(f"{A}link")
        link = (ln.get("href") if ln is not None else "") or ""
        if d and link:
            out.append(_item("feed", where, e.findtext(f"{A}title") or "", link,
                             e.findtext(f"{A}summary") or e.findtext(f"{A}content") or "", d, 0))
    return out


def fetch_feed(http: httpx.Client, url: str) -> list[dict]:
    r = http.get(url)
    r.raise_for_status()
    return parse_feed(r.text, url)


# ---- gather, rank -------------------------------------------------------------------------------

def rank(items: list[dict], brief_kw: set[str], days: int, now: dt.datetime | None = None) -> list[dict]:
    """score = (0.6 engagement within its source + 0.4 freshness) x kind weight + a brief-match bonus. Items that
    match the brief float up; with a brief, items sharing none of its words are dropped."""
    now = now or dt.datetime.now(dt.timezone.utc)
    top = {}
    for it in items:
        top[it["source"]] = max(top.get(it["source"], 0), it["engagement"] + it["comments"])
    out = []
    for it in items:
        eng = it["engagement"] + it["comments"]
        e = math.log1p(eng) / math.log1p(top[it["source"]]) if top[it["source"]] else 0.5
        age = max(0.0, (now - dt.datetime.fromisoformat(it["date"])).total_seconds() / 86400)
        fresh = 0.5 ** (age / max(1.0, days / 2))
        kw = keywords(f"{it['title']} {it['text']}")
        match = len(kw & brief_kw) / max(1, min(len(brief_kw), 4)) if brief_kw else 0.0
        if brief_kw and not match:
            continue
        s = (0.6 * e + 0.4 * fresh) * KIND_WEIGHT.get(it["kind"], 0.7) + 0.5 * min(1.0, match)
        out.append({**it, "score": round(s, 3), "age_days": round(age, 1)})
    out.sort(key=lambda x: -x["score"])
    return out


def _dedupe(items: list[dict]) -> list[dict]:
    seen, out = set(), []
    for it in items:
        k1, k2 = it["url"].split("?")[0].rstrip("/").lower(), re.sub(r"[^a-z0-9]", "", it["title"].lower())[:60]
        if k1 in seen or k2 in seen:
            continue
        seen.update({k1, k2})
        out.append(it)
    return out


SOURCES = ("hackernews", "reddit", "github", "feeds")


def gather(cfg: dict, queries: list[str], brief: str = "", log: Callable[..., None] = lambda *a, **k: None,
           transport: httpx.BaseTransport | None = None, token: str | None = None) -> dict:
    """Everything from the enabled sources in the last `days`, ranked. A source that fails is logged and skipped
    (one blocked site never stops the research)."""
    days = int(cfg.get("days", 14))
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    on = cfg.get("sources") or {}
    hn_q = list(dict.fromkeys(queries or cfg.get("hn_queries") or []))[:6]
    status, items = {}, []
    with httpx.Client(timeout=20, headers={"User-Agent": UA}, transport=transport, follow_redirects=True) as http:
        jobs: list[tuple[str, Callable[[], list[dict]]]] = []
        if on.get("hackernews", True):
            jobs.append(("hackernews", lambda: fetch_hn(http, hn_q, since)))
        if on.get("reddit", True):
            jobs.append(("reddit", lambda: fetch_reddit(http, cfg.get("subreddits") or [], queries[:3], days)))
        if on.get("github", True):
            jobs.append(("github", lambda: fetch_github(http, cfg.get("github_repos") or [], queries, since, token=token)))
        if on.get("feeds", True):
            for url in cfg.get("feeds") or []:
                jobs.append((f"feed {url}", lambda url=url: [i for i in fetch_feed(http, url) if dt.datetime.fromisoformat(i["date"]) >= since]))
        for name, fn in jobs:
            t0 = time.time()
            try:
                got = fn()
                status[name] = {"ok": True, "count": len(got)}
                items += got
                log(f"{name}: {len(got)} items in {time.time() - t0:.1f}s")
            except Exception as e:                     # a blocked or changed source: skip it, say why
                msg = f"HTTP {e.response.status_code}" if isinstance(e, httpx.HTTPStatusError) else f"{type(e).__name__}: {str(e)[:120]}"
                status[name] = {"ok": False, "count": 0, "error": msg}
                log(f"{name}: skipped ({msg})", "warn")
    brief_kw = keywords(brief)
    ranked = rank(_dedupe(items), brief_kw, days)[: int(cfg.get("max_items", 60))]
    return {"items": ranked, "sources": status, "days": days, "queries": queries, "brief": brief,
            "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")}


def check(cfg: dict, transport: httpx.BaseTransport | None = None, token: str | None = None) -> dict:
    """One small request per source, to show in Settings which ones answer from this machine."""
    small = {**cfg, "days": 7, "hn_queries": (cfg.get("hn_queries") or ["Claude"])[:1], "subreddits": (cfg.get("subreddits") or [])[:1],
             "github_repos": (cfg.get("github_repos") or [])[:1], "max_items": 5}
    return gather(small, [], "", transport=transport, token=token)["sources"]
