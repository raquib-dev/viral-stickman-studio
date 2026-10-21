# Viral Stickman Studio

A local web app that takes you from a niche to finished stick-figure videos. It finds viral topics, works
out why the winners worked, writes and directs the video, renders it with Gemini Omni Flash 1.1, and
packages it.

**It never publishes, posts, comments or DMs anything.** Every output ends as files in
`projects/<slug>/` plus copy blocks in the UI. You publish by hand.

```
Niche → Discover → Patterns ("why it worked") → Topics ⏸ → Hooks ⏸ → Script → Phase A ⏸ → Phase B
      → Render ⏸(cost) → Stitch → Package          … you publish … → Learn → (next video's beats move)
```

⏸ marks a **gate**. In Settings each gate is either *pause for me* (the default) or *auto*. **Run pipeline**
chains every stage and shows live progress per stage. It stops at paused gates and continues the
moment you approve.

---

## 1. Setup on Windows 11

Use short paths (Windows path-length limits). These steps assume `C:\src`.

### Prerequisites (one time)

| Tool | Install | Check |
|---|---|---|
| Python 3.12 (python.org installer, **not** the Microsoft Store stub). Tick "Add python.exe to PATH". | https://www.python.org/downloads/windows/ | `python --version` |
| Node.js 20 LTS or newer | https://nodejs.org/ | `node --version` |
| ffmpeg (includes ffprobe) | PowerShell: `winget install Gyan.FFmpeg`, then open a new terminal | `ffmpeg -version` |
| Git | https://git-scm.com/download/win | `git --version` |

If `ffmpeg` is still not found, put its full paths in `.env` (`FFMPEG_PATH=C:\ffmpeg\bin\ffmpeg.exe`,
`FFPROBE_PATH=...`).

### Get the code and install (PowerShell)

```powershell
cd C:\src
git clone https://github.com/raquib-dev/viral-stickman-studio.git
cd viral-stickman-studio
git checkout claude/optimistic-meitner-km62vw      # until the PR is merged

python -m venv .venv
.\.venv\Scripts\Activate.ps1                         # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install yt-dlp                                   # optional: public YouTube transcripts for "why it worked"
pip install faster-whisper                           # optional: word-accurate caption timing on real renders

cd frontend
npm install
npm run build                                        # FastAPI serves the built UI
cd ..

copy .env.example .env                               # then fill in your keys (section 2)
```

Git Bash works the same way: use `source .venv/Scripts/activate` and `cp .env.example .env`.

### Run

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn backend.app.main:app --port 8000
```

Open **http://localhost:8000**. The sample niche is pre-filled. **Settings → Dry run** is on by default,
so your first run costs $0 and needs no keys.

Developing the UI? Run `npm run dev` inside `frontend/` and open http://localhost:5173 (it proxies
`/api` to port 8000).

The vendored skills live in `.claude/skills/` (see `THIRD_PARTY.md`). The app loads them from the
project, so nothing needs to be in `~/.claude/skills`. If you do have your own skills there, they load
too.

---

## 2. API keys

All keys go in `.env` in the project folder. The file is gitignored. The app never logs, displays or
stores a key (no SQLite, no project files, no API responses). Settings shows only "is set / not set".
You only need the keys for the parts you run live.

| Key | Used for | How to get it |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude Agent SDK, which runs the skills | https://console.anthropic.com → API Keys. **Or** leave it empty and log in once with Claude Code (`claude login`); the SDK uses that login. |
| `FAL_KEY` | `omni-fal` render backend | https://fal.ai/dashboard/keys → Add key |
| `GEMINI_API_KEY` | `omni-gemini` render backend | https://aistudio.google.com/apikey. Omni Flash needs the **paid tier** (enable billing on that Google Cloud project). |
| `YOUTUBE_API_KEY` | Live YouTube discovery (search, stats, channel medians) | See below |

### Get a YouTube Data API key (about 5 minutes, free)

1. Open https://console.cloud.google.com/ and sign in.
2. Top bar → project picker → **New Project** → name it e.g. `stickman-studio` → Create, then select it.
3. Left menu → **APIs & Services → Library** → search **"YouTube Data API v3"** → **Enable**.
4. **APIs & Services → Credentials → + Create credentials → API key**. Copy the key.
5. Click the new key → **API restrictions → Restrict key → YouTube Data API v3** → Save.
   (Optional: under *Application restrictions* choose *IP addresses* and add your own IP.)
6. Put it in `.env`: `YOUTUBE_API_KEY=...`

This is a read-only key: it cannot post or change anything on any channel, and the app has no OAuth
or write code at all. The default quota is 10,000 units/day. `search.list` has its own quota bucket.
The Discover log shows the units each run uses.

---

## 3. Using it

1. **Niche**: niche, sub-topics, platforms, style (1–5), theme, ratio, duration, competitors. Paste
   transcripts of three of your own videos to draft `config/voice/youtube.md` and
   `config/voice/instagram.md`. You review and apply the drafts; every yt-*/ig-* skill reads these files.
2. **Run pipeline** (top bar). Each stage cell shows status and progress. Click a cell to open its
   screen. The live log is at the bottom.
3. **Gates** appear as orange panels with Approve / Reject, plus a note field.
   - **Topic** and **Hook**: click a card, then approve.
   - **Phase A**: edit the text if you like, then approve. Approval is tied to the exact text, so editing
     re-opens the gate. A rejection note feeds the director's next revision.
   - **Render cost**: shows the estimate and your budget cap.
4. **Render**: a per-clip grid and **Regenerate this clip only**. Stitch builds `final/final.mp4` with
   burned-in captions, the hook card, and loudness normalised to −16 LUFS.
5. **Package**: titles linted as title + thumbnail pairs, description, tags, chapters (long-form),
   Instagram caption with lint, claims to verify, policy notes, and copy buttons.
6. **Learn**: after you publish, upload the YouTube Studio retention CSV and/or paste Instagram
   insights. Findings shift the niche profile, so the next video's beats move.

Every stage is a separate job and can be re-run on its own. Downstream stages then show **stale**.

### Your first real render (30 s, 3 clips)

Do this once dry runs look right. You have a fal key, so:

1. `.env`: set `FAL_KEY` (and `ANTHROPIC_API_KEY` or `claude login` for the live Claude stages).
   Restart the server.
2. **Settings**:
   - untick **Dry run**
   - Backend **omni-fal**, Resolution **720p**, Continuity **first frame**
   - **Budget cap $5**
   - Gates: all **pause for me**
   - Save.
3. Create a project with **Duration 30** (3 clips) and run the pipeline.
4. At the **Render cost** gate you should see **3 clips × 10 s × $0.10/s = $3.00**, up to **$3.75** with the
   25% retry allowance. Approve only if that matches.
5. Watch each clip appear in the Render grid. Regenerate any single clip you don't like; each costs
   about $1.00 at 720p.

With `omni-gemini` instead, the estimate is $0.10136/s at 720p (5,792 tokens/s × $17.50 per 1M output
tokens), so about $1.01 per clip. The actual cost is read back from the API's token usage after each clip.

Where prices come from: `config/pricing.json`, citing `docs/research/platform-signals-2026.md`. Change a
rate there if a provider changes it. 1080p/4K on the Gemini API are upscaled and their price is
unverified, so the app refuses to estimate them until you add a rate.

---

## 4. Which skill or tool runs each stage

| Stage | Vendored skill (via Claude Agent SDK) | Pack tool (run directly) | Output |
|---|---|---|---|
| Niche | `yt-script` / `ig-reel` voice step | — | `research/voice-draft-*.md` |
| Discover | `yt-viral`, `ig-viral` (interpretation) | `yt-viral/swipe.py`, `ig-viral/swipe.py`; YouTube Data API; `yt-dlp` captions | `research/discovery.json`, `swipe.md`, `transcripts/` |
| Patterns | (Sonnet labeler on blueprint questions) | blueprint regex labeler, `yt-script/hookscore.py`, `ig-reel/hookscore.py` | `research/patterns/*.json`, `niche-profile.json` |
| Topics | `yt-viral`, `ig-viral` | topic scorer | `research/topics.json` |
| Hooks | `ig-reel` / `yt-script` | both `hookscore.py`; `ig-viral/swipe.py` formula classifier | `script/hooks.json` |
| Script | `ig-reel` / `yt-script`, `ig-human` | `ig-reel/beats.py --wpm 150`, `ig-human/humanize.py`, `detect.py` | `script/script.json`, `beats.json`, `human.json` |
| Phase A | `directing-stickman-videos` | blueprint annotations | `direction/phase-a.md` |
| Phase B | `directing-stickman-videos` | verbatim anchor / voice-block / colour-notation checks | `direction/phase-b.md`, `prompts/clip-NN.txt` |
| Render | — | `mock` / `omni-gemini` (google-genai Interactions API) / `omni-fal` (fal-client) | `clips/clip-NN.mp4` |
| Stitch | — | ffmpeg concat, ASS captions, two-pass `loudnorm` | `final/final.mp4`, `.srt` |
| Package | `yt-package`, `yt-seo`, `yt-chapters`, `ig-caption`, `ig-human`, `yt-shorts`, `ig-repurpose` | `yt-package/title.py`, `yt-chapters/chapters.py`, `ig-caption/caption.py`, `humanize.py`, `detect.py` | `package/copy-blocks.md` |
| Learn | `yt-retention`, `ig-audit` | `yt-retention/retention.py` | `research/learn/report.json`, `learned.json` |

Models are set in Settings: `claude-opus-5-5` for direction and research, `claude-sonnet-5-5` for bulk
labeling.

Design documents:
- `docs/repo-analysis.md`: what each source repo contributes, and how conflicts between them were resolved
- `docs/research/`: psychology, direction craft, platform signals, `virality-blueprint.json`
- `docs/architecture.md`

---

## 5. Tests

```powershell
pip install -r requirements-dev.txt
python -m pytest                       # unit tests + end-to-end dry run (about 1 min; needs ffmpeg)

cd frontend
npx playwright install chromium        # once
npx playwright test                    # drives the full dry run in a headless browser at 1280 px
```

The Playwright test starts the server itself (`VSS_PYTHON` = path to your venv's python, if `python` is
not it). It creates a project called "UI dry run …"; afterwards you can delete its folder under
`projects/` (or call `DELETE /api/projects/<slug>?delete_files=true`). The test refuses to run if Dry run is
off, so it can never trigger a paid render. Playwright's bundled Chromium cannot play H.264, so the test checks
video elements and posters, not playback. Chrome, Edge and Firefox play the clips normally.

---

## 6. Known limits (read this)

- **`hookscore.py` is a heuristic, not a predictor.** By its authors' own measurement it separates
  deliberately bad hooks from real ones well (AUC 0.83) and a creator's hits from their misses barely
  at all (about 0.56). A low score is a reason to look again; a high score is not a promise.
- **Pattern labels are judgements about the words, not proof of causation.** "Top videos re-hook at
  ~38%" describes their transcripts. It does not show the re-hook caused the views. Transcripts can't
  show cuts, so pattern interrupts are labelled as a *proxy* from pauses and openers.
- **Instagram discovery is partly manual by design.** There is no official API for other accounts'
  reels. The app never logs in and never scrapes. You paste links and stats (median by eye from public
  profiles, as `ig-viral` describes), and YouTube Shorts serve as the second corpus.
- **YouTube transcripts** come from public auto-captions through `yt-dlp` at low volume, or from your
  paste. The Data API only downloads captions for videos you can edit.
- **Dry-run data is synthetic.** Discovery rows, transcripts and agent outputs in dry run are fixtures,
  labelled *SYNTHETIC* or *dry-run fixture* everywhere they appear. They exercise the pipeline and
  prove nothing about a niche.
- **Repeating the prompt text does not guarantee consistency.** Repeating the character anchor and
  voice block verbatim is the director skill's tested method, not a guarantee. Watch and listen to
  real clips; the app checks prompt compliance, not what the model actually rendered.
- **Caption timing** on real renders is word-accurate only with `faster-whisper` installed. Otherwise
  each clip's known narration is spread across its 10 s window.
- **Rates change.** Omni pricing and limits were checked on 21 Oct 2026 (the preview model ID
  `gemini-omni-flash-preview` shut down on 22 Oct 2026; the app uses `gemini-omni-1.1-flash`).
- **Platform policy.** Stick-figure explainers made in a pipeline must show your own insight, and
  should vary music and imagery across videos, to stay clear of YouTube's inauthentic-content policy.
  Never present the narrator as a human financial expert. The Package screen repeats both notes.
- **Not yet verified against live services:** real Claude Agent SDK calls, live YouTube discovery and a
  real Omni render were built against the official SDKs and docs, but could not run in the build
  environment (no keys there). Section 3 shows how to run them; please report what you see.

## Project layout

```
.claude/skills/        vendored skills (unmodified)    config/        settings, pricing, voice profiles
backend/app/           FastAPI, stages, agent, render  frontend/      React + Vite + Tailwind UI
docs/                  analysis, research, blueprint   tests/         pytest (unit + e2e dry run)
projects/<slug>/       research/ script/ direction/ clips/ final/ package/   (gitignored)
```
