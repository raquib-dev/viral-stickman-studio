"""SYNTHETIC discovery data for dry runs. Every row is marked synthetic and every channel name says so.
It exists to exercise swipe.py, the labeler, the profile and the topic board for free. It is not
evidence about any real niche and the UI labels it 'SYNTHETIC - not real data' wherever it appears."""
from __future__ import annotations

import random

TITLES = [
    "Your Brain Thinks Future You Is a Stranger", "Why Saving Money Feels Like Losing",
    "The Real Reason Budgets Fail in Week Three", "Stop Blaming Willpower for Your Savings",
    "Why Every Raise Leaves You Broke", "The Psychology of Impulse Buying", "Why You Avoid Your Bank Balance",
    "Mental Accounting Explained Simply", "How Anchoring Tricks You at Checkout", "Why Tax Refunds Disappear",
    "The Latte Myth Nobody Questions", "Loss Aversion in 60 Seconds", "Why Rich Habits Feel Boring",
    "The Sunk Cost Trap in Your Wallet", "Why Sales Make You Spend More", "Your Brain on Payday",
    "Why Small Purchases Add Up Invisibly", "The Comparison Trap and Your Spending",
    "Why Future Rewards Feel Smaller", "How to Make Saving Automatic",
]

# beat sentences used to build synthetic transcripts with known positions
HOOKS = ["Your brain thinks future you is a stranger.", "Stop blaming willpower for this.",
         "Nobody tells you why saving hurts.", "You're paying for this every single month.",
         "Why does tonight always win?"]
STAKES = ["And it costs you money every month you wait.", "That habit is costing you more than you think.",
          "You lose a little every payday."]
BODY = ["Most people think it's about discipline.", "That sounds right, and it's wrong.",
        "Picture your future self for a second.", "The reward feels far away.", "Today feels loud.",
        "Your brain discounts anything later.", "So the near choice keeps winning.", "It happens on autopilot."]
REHOOKS = ["But here's the catch.", "And get this.", "But that's not the whole story.",
           "Here's the thing nobody mentions."]
PAYOFFS = ["Here's how to fix it: automate the choice.", "That's why the answer is a system.",
           "So the real fix is removing the decision."]
MISTAKE = "Count them: one, two, four steps."
CTAS = ["Comment which one you'd pick.", "Tell me in the comments if you'd try it.", "Comment SAVE and I'll explain."]


def yt_rows(niche: str, seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    rows = []
    for c in range(6):
        channel = f"SYNTHETIC Channel {chr(65 + c)}"
        base = rng.choice([8_000, 20_000, 45_000, 120_000])
        for k in range(8):
            title = TITLES[(c * 3 + k) % len(TITLES)]
            mult = rng.choice([0.4, 0.7, 0.9, 1.0, 1.1, 1.3, 2.4, 3.8, 6.5, 11.0]) if k % 3 == 0 else rng.uniform(0.5, 1.4)
            if "Future You" in title or "Willpower" in title:
                mult = max(mult, 5.0 + c)
            rows.append({"channel": channel, "title": title, "views": int(base * mult),
                         "url": f"synthetic://yt/{c}-{k}", "duration": rng.choice([42, 55, 58, 61]),
                         "synthetic": True})
    return rows


def ig_tsv(seed: int = 11) -> str:
    rng = random.Random(seed)
    lines = ["account\tfollowers\tmedian\tviews\thook"]
    for a in range(5):
        median = rng.choice([3_000, 9_000, 15_000])
        for k in range(4):
            hook = HOOKS[(a + k) % len(HOOKS)] if k % 2 == 0 else BODY[(a + k) % len(BODY)]
            mult = rng.choice([0.6, 0.9, 1.2, 3.5, 8.0])
            lines.append(f"@synthetic_{a}\t{median * 4}\t{median}\t{int(median * mult)}\t{hook}")
    return "\n".join(lines) + "\n"


def transcript(video_index: int, duration: float, seed: int = 3) -> list[tuple[float, float, str]]:
    """A timed synthetic transcript with beats at deliberately varied positions (cues as (s, e, text))."""
    rng = random.Random(seed + video_index)
    rehook_a = rng.uniform(0.33, 0.42)
    rehook_b = rng.uniform(0.66, 0.76)
    payoff = rng.uniform(0.72, 0.82)
    plan: list[tuple[float, str]] = [(0.0, rng.choice(HOOKS)), (rng.uniform(2.6, 4.8), rng.choice(STAKES))]
    plan += [(rehook_a, rng.choice(REHOOKS)), (rehook_b, rng.choice(REHOOKS)), (payoff, rng.choice(PAYOFFS)),
             (0.9, rng.choice(CTAS))]
    if video_index % 3 == 0:
        plan.append((rng.uniform(0.42, 0.55), MISTAKE))
    # convert fractions to seconds (values < 1 are fractions)
    timed = sorted(((t if t >= 1 or t == 0 else t * duration), s) for t, s in plan)
    cues: list[tuple[float, float, str]] = []
    t = 0.0
    body = iter(BODY * 3)
    for at, sentence in timed:
        while t + 2.5 < at:
            s = next(body)
            cues.append((round(t, 2), round(t + 2.3, 2), s))
            t += 2.5
        t = max(t, at)
        cues.append((round(t, 2), round(t + 2.6, 2), sentence))
        t += 2.8
    # loop ending: echo a hook word
    hook_word = cues[0][2].split()[-1].strip(".?!").lower()
    cues.append((round(min(t, duration - 2.4), 2), round(duration - 0.2, 2), f"Remember the {hook_word}."))
    return cues


NEWS = [("problem", "reddit", "r/ClaudeAI", "Hit my usage limit again before lunch", 840, 210),
        ("problem", "github", "anthropics/claude-code", "Agent deletes test files instead of fixing the failing test", 120, 45),
        ("update", "hackernews", "Hacker News", "New coding model release: faster, cheaper, longer context", 610, 380),
        ("outage", "feed", "Status page (synthetic)", "Elevated error rates on chat completions", 0, 0),
        ("problem", "reddit", "r/ChatGPT", "It keeps saying 'you're absolutely right' and changes nothing", 1520, 330),
        ("discussion", "hackernews", "Hacker News", "Ask: how do you stop an AI from over-engineering a simple fix?", 290, 240),
        ("problem", "reddit", "r/GeminiAI", "Asked for one function, got a whole framework", 430, 95)]


def news_items(days: int = 14) -> list[dict]:
    """SYNTHETIC live-news items for dry runs (every one says so in its URL and its `synthetic` flag)."""
    import datetime as dt
    now = dt.datetime.now(dt.timezone.utc)
    out = []
    for k, (kind, src, where, title, eng, com) in enumerate(NEWS):
        out.append({"id": f"syn-{k + 1}", "source": src, "where": where, "title": title,
                    "url": f"https://synthetic.invalid/news/{k + 1}", "discussion_url": f"https://synthetic.invalid/news/{k + 1}",
                    "text": "SYNTHETIC item for a dry run, not a real post.", "kind": kind, "engagement": eng, "comments": com,
                    "date": (now - dt.timedelta(days=k % max(1, days))).isoformat(timespec="minutes"),
                    "tools": [], "score": round(1 - k / 10, 3), "age_days": float(k % max(1, days)), "synthetic": True})
    return out
