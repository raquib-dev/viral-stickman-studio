# Architecture

## 1. Decisions

| Decision | Choice | Why |
|---|---|---|
| Backend language | **Python 3.12+ / FastAPI** | All 12 skill-pack tools are stdlib Python and are called as subprocesses; `claude-agent-sdk` (0.2.170), `google-genai` (2.32.0) and `fal-client` (1.0.3) all have first-class Python SDKs; one language for wrappers, labeler, scorer and tests. Node would add a second runtime just to shell out to Python. |
| Agent runtime | **Claude Agent SDK** (`claude_agent_sdk.query`) | Runs the **real vendored skills**: `ClaudeAgentOptions(cwd=<repo>, setting_sources=["user","project"], skills=[...], model=...)`. `"project"` loads `.claude/skills/` and `CLAUDE.md`; `"user"` also loads `~/.claude/skills` if you have them. The wheel bundles the Claude Code CLI. |
| Models | `claude-opus-5-5` for direction/research/scripts; `claude-sonnet-5-5` for bulk beat labeling | Configurable in Settings (`config/settings.json`). |
| Job store | **SQLite** (stdlib `sqlite3`, WAL) at `data/studio.sqlite3` | Zero-install on Windows; jobs, logs, costs, gates. Files in `projects/<slug>/` stay the source of truth for content. |
| Worker queue | In-process **asyncio worker pool** with persisted jobs | No Redis/Celery to install on Windows. Two lanes: `general` (concurrency 2) and `render` (concurrency 1, so paid clips run one at a time). On restart, `running` jobs become `interrupted` and can be re-run. |
| Live updates | **SSE** (`GET /api/jobs/{id}/events`, `GET /api/projects/{slug}/events`) | One-way log/progress stream; native `EventSource` in the browser; simpler than WebSockets through proxies. |
| Frontend | **React 18 + Vite + TypeScript + Tailwind** (`darkMode: "class"`) | As specified. Dev server proxies `/api` to FastAPI; production build is served by FastAPI as static files so you run one process. |
| Render | Pluggable `RenderBackend` interface: `mock`, `omni-gemini`, `omni-fal`, (`kino` later) | Dry-run uses `mock` (ffmpeg placeholder clips), so the whole pipeline is free to test. |
| Media | **ffmpeg** (concat, ASS captions, drawtext overlays, `loudnorm` two-pass to −16 LUFS / −1 dBTP), optional **faster-whisper** for word timing | ffmpeg 6.1 here has `loudnorm`, `ass`, `subtitles`, `drawtext`. |

## 2. Process layout

```
browser (React, :5173 dev)  ──/api──►  FastAPI (:8000)
                                          │
                     ┌────────────────────┼──────────────────────────┐
                     ▼                    ▼                          ▼
              SQLite job store     Worker pool (asyncio)      projects/<slug>/ files
                                          │
           ┌──────────────┬───────────────┼────────────────┬───────────────────┐
           ▼              ▼               ▼                ▼                   ▼
   ToolRunner       AgentRunner      YouTubeClient    RenderBackend        MediaKit
   (subprocess:     (Agent SDK →     (Data API v3,    (mock | omni-gemini  (ffmpeg,
   hookscore,       real skills;     yt-dlp subs)     | omni-fal | kino)   captions,
   beats, swipe…)   FixtureAgent in                                         loudnorm)
                    dry-run)
```

## 3. Repository layout

```
.claude/skills/            vendored skills (unmodified) — THIRD_PARTY.md
config/voice/              youtube.md, instagram.md (passed to skills explicitly)
config/pricing.json        render rates per backend/resolution (editable)
config/settings.json       models, budget cap, dry_run, defaults (no secrets)
backend/app/
  main.py                  FastAPI app, static frontend, routers
  settings.py              .env loading (keys never leave this module), settings.json
  db.py                    SQLite schema + queries
  jobs.py                  Job model, worker pool, SSE broadcaster, log redaction
  gates.py                 gate state machine
  paths.py                 project folder layout
  tools/                   one thin wrapper per pack tool (JSON in/out, exit-code policy)
  agent/                   AgentRunner (SDK), FixtureAgent (dry-run), prompt builders
  stages/                  niche, discover, patterns, topics, hooks, script, direction,
                           render, package, learn — one module each
  analysis/                blueprint labeler, niche profile + heatmap, topic scorer
  render/                  base.py, mock.py, omni_gemini.py, omni_fal.py, cost.py,
                           stitch.py, captions.py, overlays.py
  sources/                 youtube.py (Data API), transcripts.py (yt-dlp/paste), instagram.py (paste)
frontend/                  React app
docs/                      repo-analysis, research/, architecture (this file)
projects/<slug>/           per-project outputs (gitignored)
tests/                     pytest unit + e2e dry run; frontend/e2e Playwright
```

## 4. Project folder (inspectable outside the app)

```
projects/<slug>/
  project.json             niche, sub-topics, platforms, style, ratio, duration, competitors, gates
  research/                discovery.json, swipe-yt.json, swipe-ig.tsv, swipe.md, transcripts/*.srt,
                           patterns/<video>.json, niche-profile.json, heatmap.json, topics.json, learn/
  script/                  hooks.json (+ both hookscore panels), script.md, beats.json, humanized.md,
                           detect.json
  direction/               phase-a.md, phase-a.annotations.json, phase-b.md, prompts/clip-NN.txt
  clips/                   clip-NN.mp4, clip-NN.json (attempts, interaction id, cost, status)
  final/                   stitched.mp4, captions.ass, words.json, final.mp4, loudness.json
  package/                 titles.json, thumbnail.md, description.md, chapters.txt, caption-ig.md,
                           cutdowns.md, copy-blocks.md
```

## 5. Stages (each is a re-runnable job)

Every stage implements `async run(ctx) -> StageResult` with declared inputs (files it reads) and outputs
(files it writes). It logs to the job, records `cost_usd` (agent usage from the SDK `ResultMessage`,
render spend from provider usage), and can be re-run on its own; re-running a stage marks downstream
stages **stale** (not deleted).

| # | Stage | Calls (direct) | Calls (Agent SDK skill) | Gate after |
|---|---|---|---|---|
| 1 | **niche** | — | voice.md drafting from 3 transcripts using the `yt-*`/`ig-*` "write my voice.md" instruction | — |
| 2 | **discover** | YouTube Data API (`search.list`, `videos.list`, `playlistItems.list`), `yt-dlp --write-auto-subs`, `yt-viral/swipe.py --json --min 2`, `ig-viral/swipe.py --json --out` | `yt-viral`, `ig-viral` (interpretation only) | — |
| 3 | **patterns** | blueprint regex labeler, `yt-script/hookscore.py`, `ig-reel/hookscore.py`, `yt-edit/deadair.py` loader | Sonnet labeling against `how_to_detect.llm_question` | — |
| 4 | **topics** | topic scorer (pure function) | Opus: candidate generation + stick-figure fit rubric | **GATE: pick topic** |
| 5a | **hooks** | both `hookscore.py` | `yt-script` / `ig-reel` (5 hooks, SAY/WRITE/SHOW) | **GATE: pick hook** |
| 5b | **script** | `ig-reel/beats.py --wpm 150 --target`, `ig-human/humanize.py`, `ig-human/detect.py` | `yt-script`/`ig-reel` (5-stage script, beats placed by niche profile), `ig-human` (structural rewrites) | — |
| 6a | **direction-a** | annotation pass (blueprint × profile → timeline marks) | `directing-stickman-videos` Phase A | **GATE: approve Phase A** (the skill's own rule) |
| 6b | **direction-b** | anchor/voice-block equality check, colour-notation check | `directing-stickman-videos` Phase B | — |
| 7 | **render** | cost estimator, `RenderBackend`, `stitch` (ffmpeg), captions, loudnorm | — | **GATE: confirm cost** before any paid clip; hard budget cap |
| 8 | **package** | `yt-package/title.py`, `yt-chapters/chapters.py`, `ig-caption/caption.py`, `humanize.py`/`detect.py` | `yt-package`, `yt-seo`, `yt-chapters`, `ig-caption`, `ig-human`, `yt-shorts`, `ig-repurpose` | — |
| 9 | **learn** | `yt-retention/retention.py --transcript` | `yt-retention`, `ig-audit` | updates niche profile |

### Gates

`gates.py` stores `{name, status: pending|approved|rejected, payload_hash, decided_at, note}` in
`project.json` and SQLite. A downstream stage refuses to start unless its gate is `approved` **for
the current payload hash**. Editing the approved Phase A (or changing ratio/duration/style) changes the
hash and re-opens the gate, matching the director skill's "a global change invalidates approval".
The UI shows every gate as Approve / Edit / Reject.

## 6. Agent runner

```python
ClaudeAgentOptions(
    cwd=REPO_ROOT, setting_sources=["user", "project"],
    skills=["directing-stickman-videos"],        # only the skills the stage needs
    allowed_tools=["Read", "Glob", "Grep", "Bash(python *)", "Write(projects/<slug>/**)"],
    model=settings.model_direction,              # claude-opus-5-5 / claude-sonnet-5-5
    max_budget_usd=settings.agent_budget_per_stage,
    permission_mode="default", can_use_tool=deny_network_and_posting,
)
```

- **Prompt contract:** each stage prompt names the skill, gives the voice path override
  (`config/voice/youtube.md` instead of `~/.claude/youtube/voice.md`, and so on; see `CLAUDE.md`), the
  input files, and an **output file + JSON shape** to write. The runner validates the file and retries
  once on a schema error.
- **Gate honouring:** Phase A and Phase B are separate agent calls. Phase B is only invoked after the
  gate is approved, and its prompt includes the approved Phase A verbatim plus the approval record.
- **Safety:** `can_use_tool` denies web posting tools, any Instagram/YouTube write, and Bash outside
  `python <skill tool>` / `ffprobe`. Never-publish is enforced in code, not only by prompt.
- **Dry-run:** `FixtureAgent` implements the same interface and writes deterministic, clearly
  labelled fixture outputs (`"_fixture": true`) for the sample niche, so every downstream tool, gate
  and UI path runs for free. Real pack tools (hookscore, beats, swipe, title, chapters, caption,
  humanize, detect, retention) **still run for real** on the fixture text.
- **Credentials:** the SDK uses your `ANTHROPIC_API_KEY` from `.env` or your Claude Code login. It is
  never stored in SQLite or sent to the frontend.

## 7. Discovery details

- **YouTube** (needs `YOUTUBE_API_KEY`): `search.list` (type=video, q=niche + "stick figure animation"
  / "animated explainer" bias terms, `videoDuration` per target format) → candidate channels →
  `channels.list` uploads playlist → `playlistItems.list` + `videos.list` for the last ~30 uploads →
  rows `{channel,title,views,url,duration}` → `swipe.py` computes the multiple over each channel's own
  median. A quota meter shows units spent (10,000/day default; `search.list` has its own bucket since
  1 Jun 2026).
- **Transcripts:** the Data API cannot download other people's captions (`captions.download` needs
  edit rights). We use `yt-dlp --skip-download --write-auto-subs --sub-format json3` (public, no
  login, the method `ig-viral` documents), at low volume, with a **paste transcript** fallback.
  `yt-dlp` is optional; without it, paste only.
- **Instagram:** no API, no login, no scraping. A **paste form** (links + account, followers, median
  by eye, views, hook, length, CTA) writes ig `swipe.py`'s TSV. YouTube Shorts serve as the second
  corpus, as `ig-viral` suggests.
- **Dry-run:** a synthetic fixture dataset for "personal finance psychology", flagged
  `SYNTHETIC — not real data` everywhere it appears.

## 8. Pattern extraction and the niche profile

1. **Label** each transcript (word-timed) against every blueprint rule: regex patterns first
   (deterministic, unit-tested), then one Sonnet call per video that answers the rules'
   `llm_question`s in a single JSON response. Output: `[{rule_id, type, t_seconds, pct, quote,
   method, confidence}]`.
2. **Classify the hook** with both `hookscore.py` panels and both formula sets.
3. **Aggregate** across the top outliers, weighted by `log2(multiple)`: per rule type, the median
   position (s and %), interquartile range, presence rate and count, e.g. *"re-hook at ~38% and ~71%,
   stakes by 0:04, one comment-bait mistake in 3/8 videos"*. Every claim carries `n` and the video ids
   it came from.
4. **Heatmap:** 20 bins × rule types, values = weighted share of videos with that beat in that bin.
5. **Profile application:** `profile_overridable` rules take the profile's median window when n ≥ 5
   videos, otherwise the blueprint default, and the UI says which one was used.

## 9. Topic scorer (pure, unit-tested)

`score = 0.35·outlier_evidence + 0.25·gap + 0.20·stickman_fit + 0.20·niche_fit`, each in 0–1:
- **outlier_evidence:** related outliers' `log2(multiple)` normalised, capped, with a sample-size penalty.
- **gap:** demand (sum of views of related videos) vs supply (count of related videos above the niche
  median quality, i.e. multiple ≥1.5), with a penalty when ≥3 strong recent videos already exist.
- **stickman_fit:** rubric (concrete physical metaphor available, no real people's faces needed, no
  on-screen text dependence, no charts that diffusion would garble) scored by the agent, 1–5 → 0–1.
- **niche_fit:** overlap with the niche and its sub-topics (keyword Jaccard + agent rating).
Weights live in `config/settings.json`. The board shows each component and the evidence rows behind it.

## 10. Render

```python
class RenderBackend(Protocol):
    name: str
    def estimate(self, plan: RenderPlan) -> CostEstimate: ...
    async def render_clip(self, clip: ClipSpec, prev: ClipResult | None) -> ClipResult: ...
```

- `ClipSpec`: prompt text (Phase B verbatim), ratio, resolution, duration (10 s), continuity mode
  (`none` | `first_frame` from the previous clip's last frame | `extend` via `previous_interaction_id`,
  Gemini only, ≤40 s chains).
- **omni-gemini:** `client.interactions.create(model="gemini-omni-1.1-flash", input=[...],
  response_format={"type": "video", "aspect_ratio", "resolution", "duration"},
  generation_config={"video_config": {"task": ...}}, background=True, store=True)`, then poll `.get`
  with backoff. Reads `usage.total_output_tokens` and decodes `output_video`.
- **omni-fal:** `fal_client.subscribe("google/gemini-omni-flash/v1.1/text-to-video" | ".../image-to-video", arguments=...)`.
- **mock:** ffmpeg `color` + `drawtext` (clip number, beat labels) + `sine` tone, exact duration and
  ratio, written in about a second.
- **Retries:** up to 2 per clip, exponential backoff on 429/5xx; a failed clip doesn't block others
  being shown, but stitching requires all of them. **Regenerate this clip only** re-renders one
  `clip-NN`.
- **Cost:** `config/pricing.json` rates; the estimate counts clips × seconds × rate × (1 + retry
  allowance). **GATE:** the render job pauses for approval of the exact estimate. **Hard cap:**
  `budget_cap_usd` per video in Settings, checked before each clip against
  `spent + next_clip_estimate`; the render stops (not fails) at the cap.
- **Stitch:** concat (re-encode to a uniform fps/size), captions from word timings (faster-whisper on
  the stitched audio if installed, else each clip's known VO spread across its 10 s window), hook card
  and director overlays with the safe-zone validator, `loudnorm` two-pass (−16 LUFS, −1 dBTP).

## 11. Secrets

- `.env` (gitignored) holds `ANTHROPIC_API_KEY` (optional if you use Claude login), `GEMINI_API_KEY`,
  `FAL_KEY` and `YOUTUBE_API_KEY`; `.env.example` is committed.
- `settings.py` is the only reader. Keys are passed to SDK clients in memory, never written to SQLite,
  logs, project files or HTTP responses. `/api/settings` returns only `{"gemini": true|false, ...}`.
- A logging filter redacts any configured key value and common key patterns (`AIza…`, `sk-ant-…`)
  from job logs before they reach SQLite/SSE. A test asserts that redaction works.

## 12. Never publish

No code path posts, uploads, comments, likes, follows or DMs. The YouTube client only has read
methods (API key, no OAuth). There is no Instagram client. The agent's tool permissions deny
network-write tools. Packaging ends in `package/copy-blocks.md` plus copy buttons.

## 13. Testing

- **Unit:** blueprint labeler (regex + timing → pct), niche profile aggregation, topic scorer, cost
  estimator + budget cap, tool wrappers (exit-code policy), gate hash invalidation, key redaction.
- **E2E dry run:** sample niche *"personal finance psychology, stickman, 60s, 9:16, Style 1 dark"*
  from niche setup to packaged output with `FixtureAgent` + `mock` render, auto-approving gates,
  asserting every project file exists and the final MP4 is 60 s ±0.5, 1080×1920, and about −16 LUFS.
- **UI:** Playwright (Chromium preinstalled) drives the same dry run through the browser at 1280 px,
  in both light and dark mode.

## 14. Windows notes

Paths stay short (`projects/<slug>`, slugs ≤ 40 chars). Subprocesses use `sys.executable` (so the
`python` vs `python3` Store-stub issue never arises) and `subprocess` lists (no shell). Child
processes get `PYTHONUTF8=1` (the pack tools print `·` and `→`). ffmpeg is found on PATH or via
`FFMPEG_PATH` in `.env`.
