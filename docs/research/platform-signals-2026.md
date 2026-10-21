# Platform signals and render APIs (as of 21 October 2026)

Official sources come first and reputable analyses second. **Verification method:** this container's
network policy blocks direct page fetches of google.com, youtube.com, instagram.com and fal.ai.
Every claim below was therefore checked through web-search results **restricted to the official
domain** (I quote or summarise what those results showed from that page). The one exception is the
Gemini SDK, which I read directly from the official `google-genai` 2.32.0 wheel on PyPI. Re-check
anything here on the live page before relying on it for money.

---

## YouTube (long-form)

| Signal / fact | What YouTube says | Source |
|---|---|---|
| Recommendations are personalised from behaviour signals | Compares your habits with similar viewers. "Over 80 billion" signals. | [On YouTube's recommendation system (blog)](https://blog.youtube/inside-youtube/on-youtubes-recommendation-system/) |
| Watch time | Added as a signal in 2012. Views fell about 20% right after, and YouTube accepted that. | same |
| Satisfaction | Viewer surveys (1–5 stars). Only 4–5 star ratings count as "valued watchtime". An ML model predicts responses for viewers who did not answer. | same; [How YouTube recommendations work](https://support.google.com/youtube/answer/16089387?hl=en) |
| Other feedback | Likes, shares, dislikes, "Not interested", "Don't recommend channel" | same |
| Retention report | "Intro" = share still watching after 30 s. Typical retention = your last 10 similar-length videos. Highlights need ≥60 s and ≥100 views. | [Key moments for audience retention](https://support.google.com/youtube/answer/9314415?hl=en) |
| View counting | From 24 Aug 2026 views count when playback starts, on all formats. CTR, AVD and retention metrics are unchanged. YPP pay uses engaged views. | [How engagement metrics are counted](https://support.google.com/youtube/answer/2991785?hl=en); [Engaged views explained](https://blog.youtube/inside-youtube/engaged-views-youtube-explained/) |
| Chapters | First timestamp 00:00, ≥3 timestamps ascending, each ≥10 s | [Video Chapters](https://support.google.com/youtube/answer/9884579?hl=en) |
| End screens | Final 5–20 s, video ≥25 s, up to 4 elements | [Add end screens](https://support.google.com/youtube/answer/6388789?hl=en) |
| **Inauthentic content** | From 15 Jul 2025 "repetitious" was renamed "inauthentic" and covers mass-produced or repetitive content. AI content made "with generic or unoriginal templates" that adds no original insight is not monetizable. The spam policy's example: "the exact same background music and repetitive AI generated imagery across many videos, with each video reading out an AI-generated script". AI personas presented as human experts on **financial**, health, legal or political topics will not be monetized. | [Channel monetization policies](https://support.google.com/youtube/answer/1311392?hl=en); [Spam policy](https://support.google.com/youtube/answer/2801973?hl=en) |

**Weighting:** YouTube does not publish weights. Treat ordering claims in third-party guides as
unverified.

## YouTube Shorts

| Fact | Source |
|---|---|
| Shorts can run up to **3 minutes** (vertical or square uploads on or after 15 Oct 2024) | [Understand three-minute Shorts](https://support.google.com/youtube/answer/15424877?hl=en) |
| Views count every start **and replay**, with no minimum watch time, from 31 Mar 2025. The old metric became "Engaged views". | [Get started creating Shorts](https://support.google.com/youtube/answer/10059070?hl=en) |
| "Viewed (vs. swiped away)" metric in Studio analytics | [YouTube Community announcement](https://support.google.com/youtube/community-video/273390203/new-youtube-shorts-metric-viewed-vs-swiped-away?hl=en) (official staff post, ~3.5 years old) |
| Non-original Shorts (re-uploads, compilations with nothing added) are not monetized | [Shorts monetization policies](https://support.google.com/youtube/answer/12504220?hl=en-GB) |

## Instagram Reels

| Signal / fact | What Instagram / Meta says | Source |
|---|---|---|
| Top signals for creators | Adam Mosseri (Jan 2025 video series) named **watch time, likes per reach and sends per reach**. Likes matter slightly more for followers ("connected"), sends slightly more for non-followers ("unconnected"). He did not rank them. | Reported by [Social Media Today](https://www.socialmediatoday.com/news/instagram-shares-algorithm-insights-2025/738034/) (secondary; the primary is Mosseri's own Instagram/Threads video, which I could not open) |
| Sends per reach | Mosseri: sends per reach correlate with reach "more than anything else" in his experience | [Social Media Today](https://www.socialmediatoday.com/news/instagram-chief-reiterates-sends-now-key-focus/720531/) (secondary) |
| Long videos | Instagram looks at seconds watched as well as % watched, so longer videos are not penalised | [Social Media Today](https://www.socialmediatoday.com/news/instagram-longer-video-watch-time-versus-completion-rate/740916/) (secondary) |
| Ranking system | Scores ~100 candidate reels. Predictions include sharing off-platform, watching **< 3 s**, watching more than 95% of viewers of same-length reels, comment, follow, use audio. Models change frequently. | [Instagram Reels Chaining AI system](https://transparency.meta.com/features/explaining-ranking/ig-reels-chaining/) (official; page ~344 days old at search time) |
| Ranking explained | Thousands of signals. Explore leans on how many and how fast others like, comment, share and save. | [Instagram Ranking Explained](https://about.instagram.com/blog/announcements/instagram-ranking-explained) (official, 2023) |
| Hashtags | Instagram is limiting hashtags to **five** per post/reel, favouring "a few targeted tags over many generic ones" | [Social Media Today](https://www.socialmediatoday.com/news/instagram-implements-new-limits-on-hashtag-use/808309/) (secondary). `ig-caption/caption.py` cites the @creators announcement as 18 Dec 2025; I could not open the primary. |
| Ads safe zone (9:16) | Keep ~14% top, 35% bottom, 6% sides free of key creative | [Meta Ads Guide: Instagram Reels](https://www.facebook.com/business/ads-guide/update/image/instagram-reels) |
| Other accounts' reels via API | No official API returns other accounts' reel stats. `ig-viral` collects by reading public listings, with a paste fallback. | `.claude/skills/ig-viral/SKILL.md` (pack) |

**Evidence gap:** I found no 2026 primary Instagram statement that changes the Jan 2025 signal list.

---

## Gemini Omni Flash 1.1 (render backend `omni-gemini`)

| Fact | Value | Source |
|---|---|---|
| Model ID (stable, GA) | `gemini-omni-1.1-flash`, released **27 Aug 2026** | [Model page](https://ai.google.dev/gemini-api/docs/models/gemini-omni-flash), [release notes](https://ai.google.dev/gemini-api/docs/changelog); also in `google-genai` 2.32.0 `_gaos/types/interactions/model.py` |
| Preview ID | `gemini-omni-flash-preview`, **deprecated, shuts down 22 Oct 2026** (tomorrow). The app must not use it. | [Pricing page / model page](https://ai.google.dev/gemini-api/docs/pricing) |
| API surface | **Interactions API**: `client.interactions.create(model=..., input=[...], response_format={...}, generation_config={"video_config": {...}}, previous_interaction_id=..., background=..., store=...)`, then `.get`, `.cancel`, `.delete` | [Omni docs](https://ai.google.dev/gemini-api/docs/omni), [Interactions API reference](https://ai.google.dev/api/interactions-api); method names and params read from the SDK wheel |
| `response_format` (video) | `type: "video"`, `aspect_ratio: "16:9" \| "9:16"`, `resolution: "360p" \| "720p" \| "1080p" \| "4k"` (default 720p), `duration` (string), `delivery: "inline" \| "uri"` | SDK `videoresponseformat.py` |
| Tasks | `video_config.task`: `text_to_video`, `image_to_video`, `reference_to_video`, `edit`, `extend` (auto-detected if omitted) | SDK `videoconfig.py` |
| Clip length | **3–10 s** per generation, 24 FPS, with generated audio | [Model page](https://ai.google.dev/gemini-api/docs/models/gemini-omni-flash) |
| Extension | **10 s steps up to 40 s total**, chained with `previous_interaction_id`. Input video for edit/extend is capped at 10 s. | [Omni 1.1 launch blog](https://blog.google/innovation-and-ai/technology/developers-tools/build-with-gemini-omni-1-1-flash/), [Omni docs](https://ai.google.dev/gemini-api/docs/omni) |
| First/last frame | `image_to_video` with one image (first frame) or two (first + last frame interpolation) | [Omni docs](https://ai.google.dev/gemini-api/docs/omni) |
| Resolution | Native **720p**. **1080p and 4K are upscaled.** 360p is up to 60% faster at about a third of the 720p cost. | [Omni docs](https://ai.google.dev/gemini-api/docs/omni), [launch blog](https://blog.google/innovation-and-ai/technology/developers-tools/build-with-gemini-omni-1-1-flash/) |
| Output | `interaction.output_video` (base64 `data` or `uri`); `status`: in_progress / completed / failed / cancelled / requires_action; `usage.total_output_tokens` | SDK `interaction.py`, `usage.py` |
| **Pricing (Standard, 720p)** | **$17.50 per 1M video output tokens; 5,792 tokens per second of 720p ≈ $0.10/s** (≈ $1.01 per 10 s clip) | [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing) |
| Pricing, other resolutions | 360p ≈ ⅓ of 720p per the launch blog. **I did not see an official token rate for 1080p/4K upscaling in the results**, so the app shows those as "unverified; set it in Settings". | [launch blog](https://blog.google/innovation-and-ai/technology/developers-tools/build-with-gemini-omni-1-1-flash/) |
| Access | Paid tier only; no free tier | [Model page](https://ai.google.dev/gemini-api/docs/models/gemini-omni-flash) |
| Known issue | A forum report: edit/extend with `background=true, store=true` returns an id, then later GETs fail with 400. Single unconfirmed report. | [Developers forum](https://discuss.ai.google.dev/t/gemini-interactions-api-video-to-video-blobstore-400-bug-report/188709) |
| Aspect ratio on edits | Reported error: "Aspect ratio cannot be set in response format for edit task". Set the ratio at generation. | forum reports via search (lore-level) |

**Cost model the app uses.** `cost = seconds × rate[resolution]`, with the 720p rate derived from the
official token rate (5,792 tok/s × $17.50/1M = $0.10136/s). The real bill is read back from
`usage.total_output_tokens` after each clip and recorded in the job log. Rates live in
`config/pricing.json`, so you can update them without a code change.

## fal.ai hosted equivalent (render backend `omni-fal`)

| Fact | Value | Source |
|---|---|---|
| Endpoints | `google/gemini-omni-flash/v1.1/text-to-video`, `/image-to-video`, `/reference-to-video`, `/edit` | [fal T2V](https://fal.ai/models/google/gemini-omni-flash/v1.1/text-to-video), [T2V API](https://fal.ai/models/google/gemini-omni-flash/v1.1/text-to-video/api), [R2V API](https://fal.ai/models/google/gemini-omni-flash/v1.1/reference-to-video/api) |
| T2V inputs | `prompt`; `aspect_ratio` 16:9 \| 9:16 (default 16:9); `resolution` 360p \| 720p \| 1080p \| 4k (default 720p); `duration` integer seconds (default 8; I did not see an explicit v1.1 range) | same |
| I2V inputs | `image_url` (opening frame), optional `end_image_url` | [fal I2V](https://fal.ai/models/google/gemini-omni-flash/v1.1/image-to-video) |
| Pricing (v1.1, per output second) | **360p $0.03 · 720p $0.10 · 1080p $0.15 · 4K $0.30**; no separate audio charge | same pages |
| Auth / client | `FAL_KEY` env var; Python `fal-client` (1.0.3 on PyPI today), `fal_client.subscribe(endpoint, arguments=...)` | [fal T2V](https://fal.ai/models/google/gemini-omni-flash/v1.1/text-to-video) |
| Extension chaining | Not listed as a v1.1 endpoint in the results. Continuity on fal uses I2V with the previous clip's last frame. | inference from the endpoint list |

## Consequences for the build

1. Model ID `gemini-omni-1.1-flash`, never the preview ID.
2. Default render: **720p native, 10 s clips** (the director skill's N = duration/10), with an optional
   upscale setting that is off by default because its price is unverified for the Gemini API.
3. Continuity: try **first/last-frame** `image_to_video` with the previous clip's last frame (both
   backends), and offer **extend** chaining (Gemini only) for runs of ≤40 s.
4. Long-form stickman explainers made by a pipeline need **visible original insight** (your voice, your
   topic choice and your script), with no reused template or music across videos, or they risk
   YouTube's inauthentic-content policy. Personal-finance narration must not present the narrator as
   a human financial expert. The app shows both warnings on the Package screen.
5. The **YouTube Data API cannot download other people's captions**: `captions.download` needs edit
   permission on the video and costs 200 units
   ([captions.download](https://developers.google.com/youtube/v3/docs/captions/download)). Default
   quota is 10,000 units/day, and from 1 Jun 2026 `search.list` has its own bucket
   ([quota calculator](https://developers.google.com/youtube/data/determine_quota_cost),
   [revision history](https://developers.google.com/youtube/data/revision_history)). Public
   transcripts are therefore pulled with `yt-dlp --write-auto-subs` (no login, the method `ig-viral`
   documents), with a paste-transcript fallback. Stats and channel medians use the Data API.
