# Viral Stickman Studio

A local web app that takes you from a niche to finished stick-figure videos. It finds viral topics, works
out why the winners worked, writes and directs the video, renders it with Gemini Omni Flash 1.1, and
packages it.

**It never publishes, posts, comments or DMs anything.** Every output ends as files in
`projects/<slug>/` plus copy blocks in the UI. You publish by hand.

```
Niche → AI news → Discover → Patterns ("why it worked") → Topics ⏸ → Hooks ⏸ → Script → Phase A ⏸ → Phase B
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
git checkout feature/local-ai-backends               # API + local options; until it is merged

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

**After every `git pull` or branch switch, rebuild the UI and restart the server**, or you keep seeing
the old screens (the server serves the built copy in `frontend/dist`, which is not in git):

```powershell
cd frontend; npm install; npm run build; cd ..
python -m uvicorn backend.app.main:app --port 8000      # then Ctrl+F5 in the browser
```

If you forget, the server prints a warning at startup and the page shows an orange "old build" banner.

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
| `GROQ_API_KEY` | Optional: Groq for writing (Settings → Writing model → **Groq only** or **Hybrid: Claude directs, Groq writes the rest**), voiceover (Voice → **Groq**) and caption timing (Caption timing → **Groq Whisper**); **Use Groq for everything** sets all three | https://console.groq.com/keys. Free tier is rate-limited; paid plans bill per token / audio. Some speech models need their terms accepted once in the console. |
| `ELEVENLABS_API_KEY` | Optional ElevenLabs voiceover for local video (Settings → Voice → ElevenLabs) | https://elevenlabs.io → Developers → API Keys. Billed per character on your ElevenLabs plan. |

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
   Optional **Base topic**: describe what the video should be about in your own words; the live research searches
   for it and every suggested topic is about it.
2. **Live AI news** (the second stage, shown on the Topics screen): what is actually happening with Claude,
   ChatGPT, Codex, Gemini, Cursor, Copilot and co. in the last 14 days, from public sources only (no login):
   - **Hacker News** (launches, long discussions), **Reddit** public listings (r/ClaudeAI, r/ChatGPT, ...: what
     users run into), **GitHub issues** on anthropics/claude-code, openai/codex and google-gemini/gemini-cli (real
     bugs; reactions show how many hit them), and **status pages and blogs** (outages, updates).
   - Each item is tagged problem, update, outage or discussion, with the tools it mentions, its date, its
     reactions and its link; authors' names are never kept. They are ranked by reactions, freshness and your
     brief.
   - **Topics** are then built from these real posts: each card says *what really happened* and links the posts
     it grows from, and scores higher the more people reacted. Hooks and scripts get the story with a rule: build
     the joke from the real situation, keep the facts as the sources state them, list them (with links) under
     Package → Claims to verify, and never name or quote the people who posted.
   - **Research a topic** (Topics screen): type what you want ("AI that says it fixed the bug but didn't",
     "this week's usage limits") and press **Research this**: it searches for it, then finds topics about it.
     Works before Discover has run.
   - Settings → **Research**: on/off, look-back days, which sources, the searches, subreddits, repos and feeds,
     and **Check sources** (which ones answer from your machine; a site that blocks the request is skipped, never
     fatal). Optional `GITHUB_TOKEN` in `.env` (no scopes) lifts GitHub's search limit.
3. **Run pipeline** (top bar). Each stage cell shows status and progress. Click a cell to open its
   screen. The live log is at the bottom.
4. **Gates** appear as orange panels with Approve / Reject, plus a note field.
   - **Topic** and **Hook**: click a card, then approve.
   - **Phase A**: edit the text if you like, then approve. Approval is tied to the exact text, so editing
     re-opens the gate. A rejection note feeds the director's next revision.
   - **Render cost**: shows the estimate and your budget cap.
5. **Render**: a per-clip grid and **Regenerate this clip only**. Stitch builds `final/final.mp4` with
   burned-in captions, the hook card, and loudness normalised to −16 LUFS.
6. **Package**: titles linted as title + thumbnail pairs, description, tags, chapters (long-form,
   60 s and over only), Instagram caption with lint, a **pinned comment** to post after publishing, a
   **cover image prompt** sized to the project's ratio (9:16 Shorts/Reels cover or 16:9 thumbnail), claims to
   verify, and policy notes. Each block has its own copy button. The description, pinned comment, cover prompt
   and caption each have **↻ Regenerate** with an optional note ("funnier", "shorter") that rewrites only that
   block. The writer gets the real video length and the actual script, so it can't invent a length; links,
   placeholder URLs and timestamps a short can't have are removed, and a stated length that isn't in the
   script is flagged under the description.
7. **Learn**: after you publish, upload the YouTube Studio retention CSV and/or paste Instagram
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

## 4. Local mode (your GPU, $0 per video)

Every AI piece has an API option and a local option. Pick them in **Settings**; the **Local services**
panel there checks what is installed and running, and tells you the command for anything missing.
The sidebar shows **LOCAL ($0)** when both writing and video run locally.

| Piece | API option | Local option | Setting |
|---|---|---|---|
| Writing (research, scripts, direction) | Claude Agent SDK | Any OpenAI-compatible server: **Ollama** or LM Studio with `qwen3:8b` (about 5 GB, fits 8 GB VRAM). **Hybrid** keeps Claude for Phase A/B only. Or hosted: **Groq** (`GROQ_API_KEY`, OpenAI-compatible, e.g. `openai/gpt-oss-120b`), alone or as **Hybrid: Claude + Groq** | Writing model → Provider |
| Video | omni-fal, omni-gemini | **local-stickman**: built-in animator, needs only ffmpeg + Pillow, about 8 s per clip on a laptop CPU. **local-comfyui**: Wan 2.1 1.3B / LTX-Video in ComfyUI on your GPU | Render → Backend |
| Voiceover (local video only; Omni speaks on its own) | **ElevenLabs** (`ELEVENLABS_API_KEY`; pick voices with "Load my voices") or **Groq** speech (`GROQ_API_KEY`, default model `canopylabs/orpheus-v1-english`, voices troy/hannah); both fall back to Kokoro/Piper if a call fails | **Kokoro-82M** (`pip install kokoro soundfile`, Apache-2.0) or **Piper** (`pip install piper-tts` + a voice `.onnx`, MIT) | Voice and captions |
| Caption timing | **Groq Whisper** (`whisper-large-v3-turbo`, `GROQ_API_KEY`) | faster-whisper, on the GPU when CTranslate2 sees CUDA | Voice and captions |

Setup for an RTX 5050 laptop (8 GB):

```powershell
# writing: Ollama from https://ollama.com, then
ollama pull qwen3:8b
# voice + captions (in the app's venv)
pip install kokoro soundfile faster-whisper
# RTX 50-series needs PyTorch built for CUDA 12.8 or newer:
pip install torch --index-url https://download.pytorch.org/whl/cu128
```

Then in Settings: turn **Dry run** off, Writing model → **Local LLM only** (or **Hybrid**), Render →
**local-stickman**, Voiceover → **auto**. Local renders skip the cost gate (they cost $0).

### three.js renderer (recommended local video: 3D low-poly stickman)

`local-threejs` draws a 3D low-poly stick figure with expressions and a talking mouth, glowing code panels,
stat badges, lighting and camera moves, frame by frame in a hidden browser on your GPU. It renders in
seconds per clip, is free, and gives the same video every time. The rules it follows, and the scene-plan
format, are in `renderer/RULES.md`.

```powershell
# Node.js 20+ from https://nodejs.org, then in the project folder:
cd renderer
npm install
npm run build
cd ..
```

Then Settings → Render → Backend **local-threejs** → Save, and Local services → **↻ Check** (the "three.js
renderer" row turns green). On Windows it renders with Microsoft Edge, which is already installed. Try the
demo directly: `node renderer/render.mjs --scene renderer/scenes/demo.json --out demo.mp4`.

**Six looks**, matching the directing skill's styles (the project's Style picks one; Settings → Render →
Look can force another): Minimalist (1), Modern studio tech (2A), Cinematic story (2B), Prehistoric (3),
Cozy storytelling (4), Historical (5). Each has its own set, lighting, character material, card style,
fonts and colour grade, in dark and light.

**Colours follow the content.** Each beat gets a mood from its words: money lines go green-gold, warnings
red, wins gold, calm lines blue, tech cyan, secrets purple, memories sepia. When a line turns ("...but...")
the colour shifts at that moment. Settings → Render → Colours can turn this off or fix one mood.

**What the planner does per clip:** a prop from the topic (about 40, e.g. coins, clock, laptop, phone,
heart, warning, scroll, crown, spear) placed beside the character or held in their hand; a gesture
(point, present, think, facepalm, shrug, cheer, arms crossed, hands on hips, hold, explain); a hat from
roles (king → crown, soldier → helmet); a walk-in on the first clip; a second character for "they / vs /
boss" lines; two camera shots; a fade in at the start of the video and out at its end (clips cut straight
into each other, so the story never dips to black between them); and a stat badge only for numbers the
voiceover says.

**Exposure and quality checks.** Only light sources glow (bloom starts above normal brightness, so skin and
paper cards never haze over), the character's colour is kept below paper white, and each frame measures its own
highlights and lowers exposure only when they would clip (bright close-ups, white cards); dark scenes are left
alone. Every clip's log ends with a frame report (`QA ... frames, mean brightness ...`) and warns about
near-black frames that no fade explains or frames that are mostly pure white. Stitch writes
`final/qa.json`: frame count, audio vs video length, unexpected black dips (with the clip seam they sit on),
caption overlaps; problems also show as `QA:` warnings in the job log.

Each clip's scene comes from `projects/<slug>/scenes/clip-NN.json` if that file exists (the plan the app
made is saved next to the clip as `clips/clip-NN.scene.json`: copy it there and edit), otherwise from the
planner above. Edit, then **Regenerate this clip only**. The format and the rules are in
`renderer/RULES.md`.

**AI scene planner (the "3D plan" step, after Phase B).** With local-threejs selected, your writing model
(Claude, local or hybrid: in hybrid it counts as direction, so Claude does it) stages every clip from the
approved Phase A row and the voiceover: colour moods timed to the words, 1-3 gestures, props the line
mentions, an optional note or code panel in the line's own words, a badge only for numbers it says, a second
character when the line is about someone else, and 2-4 named camera shots, plus one sentence on why. The
app checks every plan (unknown names → safe defaults, everything kept in frame, unspoken numbers removed),
retries once, and falls back to the keyword plan, so a render never fails because of the planner. The
Render page shows each clip's plan, its repairs and a **Re-plan** button. The prompt is about 1,200 tokens, so
it fits a local 8B model's context.

**AI-drawn props.** When no built-in prop fits ("a dragon guards my savings"), the planner asks for a new one
and the writing model draws it as low-poly shapes (coloured by the palette's roles, with moving parts such as
wings or a jaw). The app checks it, stands it on the floor at a sensible size, renders a preview, and reuses it
in every clip. Render page → **Props drawn by AI**: see them, **Redraw** one (every clip using it updates),
**★ To library** to reuse it in all projects (saved in `config/assets/`), or **✎ Draw prop** yourself by name.

**Scene editor.** Render page → a clip's **✎ Edit** opens it: a timeline of voice, colour, gestures, faces,
props and camera; rows for every part (moods, gestures and what they point at, faces, body moves, gaze, hats,
walking in, a second character, props and where they go, badges, note/code panels, camera shots,
fades); a JSON tab; **Check** (shows what would be repaired), **Preview frame** at any moment (a real render,
seconds on your GPU), **Save** and **Save & re-render clip**. Saved edits are yours: the AI planner keeps them.

### Dialogue shorts (a person and her AIs, 3D, a cut per line)

A second video format next to the narrated stickman: a person and her AI (a small creature on the desk) trade
short, deadpan lines, cut on every line, with line captions at the top and an ambience bed under the voices.
The style, timing and shots are modelled on a shot-by-shot study of seven reference reels (the
`dialogue-shorts-director` skill in `.claude/skills/` has the full breakdown and the measured numbers).
Everything renders on this machine with **local-threejs**.

**After pulling this branch:** `cd renderer; npm run build; cd ..; cd frontend; npm run build; cd ..`, restart.

**Make one:** New project → **Video format: Dialogue short** → give the characters names → create. Then
Settings → Render → Backend **local-threejs**, and run the pipeline as usual (topics → hooks → script → … →
stitch). Differences from the narrated format:

- **Hooks:** the SAY line is the first line, the person to her AI, written as a performance:
  `[exasperated] Claaauude. The client said it's GREAT.` (scored on its plain words).
- **Script:** the writer picks one of five premise types:
  - a tender quirk;
  - explain like I'm five (the whiteboard);
  - a team of AIs;
  - something the AI can't do;
  - credit and work.

  It writes speaker-tagged lines to the format's rules (below). Each line has its acting, its timing and,
  optionally, her pose and whiteboard items. It also picks the **scene**: the set and the look outside the
  window. Lines are checked, revised up to 3 times, and grouped into clips of up to 10 s (a line is never
  split). Studio shows them per clip.
- **Direction A/B:** not needed (no Omni prompts); they finish instantly.
- **Script delivery:** every line carries its acting for ElevenLabs Eleven v4:
  - audio tags (`[deadpan]`, `[sighs]`, `[tender]`, `[hesitant]`, `[cheerfully]`...);
  - stretched words ("Claaauude.");
  - CAPS on the word that lands;
  - a leading "..." for a hesitation (kept in the captions);
  - a timing: **quick**, **normal** or **beat**.

  Tags never show in captions. Engines that cannot perform them (Kokoro, Piper, Groq, older ElevenLabs models)
  get the plain words.
- **Scene.** Two sets:
  - the **office desk**, with four looks outside the window: **morning**, **rainy night**, **late night** with
    city bokeh, and **dusk**;
  - the **classroom whiteboard** for explainers. The AI stands on a stack of books holding a pointer. The board
    fills in as the words are spoken: a title, jargon words she strikes out in red, stick figures and boxes
    joined by arrows, and "= meaning" labels.

  Settings → Dialogue shorts → **Set** / **Window look** force one; "auto" uses the script's choice.
- **3D plan (direction):** one shot per line, free and instant.
  - Her medium close-up: centred, or off-centre now and then.
  - Each AI at desk height with her body soft and blurred behind it, alternating sides. The AI is turned to
    face each new angle on the cut.
  - A frontal wide at least every 10 lines. The opening is a wide when three or more characters talk, and the
    last line is always a wide.
  - When the same person goes on, the shot holds with no cut.

  In the classroom: the board shot, her in profile, and the AI on its books. Faces come from the tags and the
  words. The AIs act with their eyes, which go small and square when caught out. She gets a closed-eye smile on
  tender lines, and worried brows with a blush when embarrassed.
- **Her pose** changes only on cuts and holds until the next change: hands on the desk, a mug in both hands,
  reading a phone, arms crossed, a hand at her temple, an open palm, both hands forward, a finger raised. The
  script sets it; mornings default to the mug.
- **Render:** each line in its speaker's voice, laid out from the real voice lengths with the measured
  reference timing:
  - the first word at 0.37 s;
  - a normal turn 0.45 s, a quick comeback 0.2 s, a beat 0.9 s;
  - each hard cut lands 0.15 s before the next speaker's first word;
  - every shot pushes in slowly.

  A clip ends when its last line does, so the video runs as long as the conversation (a "60 s" short can
  come out shorter). The last line plays on the wide, and the camera keeps pulling back for 1.7 s after
  it. Dialogue clips render at **30 fps**. By default the characters keep still and only faces move.
  Settings → Dialogue shorts → **Character motion → Lively** adds nods, hand beats and hops.
- **Stitch:**
  - whole-line captions in a dark translucent box at about 11 % from the top, staying up until the next line
    replaces them;
  - an **ambience bed** that follows the window (rain, a city at night, room tone by day; no music);
  - loudness at **-15 LUFS** (like the references);
  - `final/qa.json`.

**Punch-up pass** (Settings → Dialogue shorts → *Punch-up pass on scripts*, on by default): after a script passes
its checks, one more writing pass with the `joke-engineering` skill diagnoses each punchline (too obvious, too
obscure, too thin, over-explained, forced, bloated) and rewrites only the weak ones. It keeps every line's
speaker, timing, pose and board items, and never touches the hook. A rewrite that breaks a rule (too long, a new
checker flag) is thrown away and the script stays as written. Studio shows what changed and why. Turn it off to save
one model call per script (useful on Groq's free plan).

**The writing rules** (`backend/app/dialogue.py`, also given to the writing model):
- lines of 2-6 words (max 9; a whiteboard explanation line max 16), with at least 2 one- or two-word punches;
- nobody speaks more than 3 lines in a row. With two characters each has at least 30% of the lines; in a group
  she has 25% and each AI at least 8%;
- 1-4 beats; at least 2 oddly specific in-story numbers ("sixty-one times", "1 AM"), never facts about the
  world (no percentages, studies or surveys; they are flagged);
- a callback, a turn in the second half, and an ending that loops back;
- line 1 is the approved hook;
- a lowercase title (two mirrored sentences, then a question to the viewer);
- classroom scripts need a board title and at least 4 board items.

**Cast** (Render page → Cast): names and roles (the roles steer the writing), voices, and looks.
- The person: hair style and colour, skin, jacket and shirt colours, glasses, headphones, and a **face
  variant**.
- The main AI: shape (flower, star, blob, bean, cube, cloud) and colour.
- **Extra AIs for group episodes:** switch on character **c** and/or **d**. The defaults are a terse
  blue-purple cloud with a `>_` face that answers "Done." and an eager dark cube with glowing eyes. Each has
  its own name, role, voice, shape, colours and voice pitch.

**Preview cast** renders them at the desk. Changing a look, voice or scene re-renders only the clips it
affects.

**Voices with ElevenLabs:** Settings → Voice → ElevenLabs. Dialogue lines always use **Eleven v4** (the top
model, the one that performs the tags) with a drama preset (stability 0.3; Settings → Dialogue shorts → Voice
expressiveness: lower is more emotional). Set the AI voices under **Dialogue AI voices**:
- **main**;
- **deep, terse** (mascot2);
- **bright, quick** (mascot3).

Empty means the male voice. Kokoro defaults to `am_puck`, `am_onyx` and `am_echo`.

**More settings** (Settings → Dialogue shorts):
- **Mascot pitch** for the main AI;
- **Sound bed**: `auto`, `room`, `rain`, `city`, `none`, or the path of your own audio file;
- **Bed level**;
- **Close-up background blur**;
- **Frame rate**;
- **Loudness**;
- **Pull-back after the last line**;
- **Give the AIs a talking mouth**. Off by default, as in the reference style; on gives each AI a small mouth
  that opens with its voice.

Note: the default AIs are named Claude, Codex and Cursor, like the references. For a channel, use your own
mascot designs and names: a well-known product's logo, colours or name belong to its owner.

### Animation pack (included: more human movement)

The base rig's moves come from a robot character. The repo now ships a CC0 humanoid animation pack,
`renderer/public/models/anim-pack.glb` (Kay Lousberg's **KayKit Adventurers**, 75 animations, from the official
KayKit repository on GitHub): walking with an arm swing, running, a relaxed idle, sitting, a natural jump, cheer
and more. Its meshes are hidden; only its bone directions drive the stick figure.

Nothing to do beyond rebuilding the renderer after `git pull` (`cd renderer; npm run build`). Settings → Local
services shows **Animation pack: installed**, and each clip's render log names the moves it maps (Idle → Idle,
Walking → Walking_A, Running → Running_A, Sitting → Sit_Chair_Idle). Settings → Render → Animation pack →
**off** goes back to the robot moves. To use another pack (e.g. Quaternius's Universal Animation Library,
https://quaternius.itch.io/universal-animation-library), save its GLB over `anim-pack.glb` and rebuild.

Any humanoid rig works (Quaternius/Unreal, Mixamo or Blender bone names): its bones are matched by name, it is
turned to face the camera, and only its bone directions drive the stick figure. Other pack clips can be used in
a scene as `"pack:<clip name>"`.

### ComfyUI on Windows (optional: AI-generated video on your GPU)

1. **Download ComfyUI portable**: https://github.com/comfyanonymous/ComfyUI/releases → latest release →
   `ComfyUI_windows_portable_nvidia.7z`. Extract it with 7-Zip to a short path, e.g. `C:\ComfyUI`. The portable
   build ships its own Python and a PyTorch for recent NVIDIA cards, so nothing else to install.
2. **Download the three Wan 2.1 files** from https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/tree/main/split_files
   (click each file → *download*), and put them here:

   | File | Folder |
   |---|---|
   | `diffusion_models/wan2.1_t2v_1.3B_fp16.safetensors` (≈2.8 GB) | `C:\ComfyUI\ComfyUI\models\diffusion_models\` |
   | `text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors` (≈6.7 GB) | `C:\ComfyUI\ComfyUI\models\text_encoders\` |
   | `vae/wan_2.1_vae.safetensors` (≈250 MB) | `C:\ComfyUI\ComfyUI\models\vae\` |

   The names must match exactly: the app's workflow `config/comfyui/wan21-t2v-1.3b.json` uses them.
   Do **not** use `Wan2.1_VAE.pth` or `models_t5_umt5-xxl-enc-bf16.pth` from the `Wan-AI/Wan2.1-T2V-1.3B` repo:
   those are for Wan's own Python code, not ComfyUI. Settings → Local services lists any file ComfyUI is
   missing, with what it found instead.
3. **Start it**: double-click `C:\ComfyUI\run_nvidia_gpu.bat`. Leave the window open; it is ready when it
   prints `To see the GUI go to: http://127.0.0.1:8188`.
4. **Check from the app**: Settings → Local services → **↻ Check**. The ComfyUI row turns green and shows your
   GPU and free VRAM.
5. **Render**: Settings → Render → Backend **local-comfyui** → Save. Start with a 30 s project. Each clip takes
   several minutes on an 8 GB laptop GPU; the clip card shows "generating on GPU… 120s" while it works.

If the clip card says *ComfyUI rejected the workflow*, a file name in step 2 does not match. If it says
*GPU out of memory*, set Settings → Render → ComfyUI → Frames to 49 (about 3 s). Close games and other GPU
apps while rendering. When writing also runs locally, the app unloads the Ollama model before a ComfyUI
render so both never sit in the 8 GB at once.

To use your own workflow, export it in ComfyUI with *Save (API format)* (turn on dev mode in the
settings first) and put `{{PROMPT}}`, `{{NEGATIVE}}`, `{{WIDTH}}`, `{{HEIGHT}}`, `{{FRAMES}}`, `{{FPS}}`, `{{SEED}}`
(and `{{IMAGE}}` for image-to-video) in place of those values.

### Which local writing model?

| Model | Size | On an 8 GB GPU | Use it for |
|---|---|---|---|
| `qwen3:8b` | ≈5 GB | Fully on the GPU: fast | The default. Fine for everything now that the app inserts the Phase B blocks |
| `qwen3:14b` | ≈9 GB | Does not fit: Ollama runs part of it on the CPU. Slower; needs 16 GB+ system RAM | Better hooks and scripts if you can wait |

Ollama is used through its native API: the app sets the context size per call (Settings → Writing model →
Context tokens, default 8192) and warns in the log if a prompt or reply was cut.

**Honest limits.** A local 8B model writes noticeably weaker hooks and much weaker Phase A/B direction
than Claude: use Hybrid if you can. local-stickman draws simple, consistent figures from keywords in
each beat. It does not follow the Phase B prompt word for word the way Omni does. ComfyUI video drifts
more between clips than Omni.

### Watching a run

- **Pipeline strip:** live elapsed time per stage, how many times each stage ran (×N), and the last
  error on hover. When a stage fails, a red line shows the error, and the button becomes **Resume from
  <stage>** (finished stages are kept).
- **Render:** every clip card shows *queued / rendering / retrying / done / failed*, the attempt
  (try 2/3), the step it is on, and a live timer. Each card keeps an attempt history with each error and
  how long it took. While a clip regenerates, or if the regenerate fails, its last good render stays
  visible. The header counts done clips, attempts and failures, with an ETA.
- **Activity** (sidebar): every job with its parameters (*clip 6 only*), duration, cost and error.
  Click one for its full log, filtered by level, and **Retry this job** or **Cancel**.

## 5. Which skill or tool runs each stage

| Stage | Vendored skill (via Claude Agent SDK) | Pack tool (run directly) | Output |
|---|---|---|---|
| Niche | `yt-script` / `ig-reel` voice step | — | `research/voice-draft-*.md` |
| AI news | — (a short query-writing call when you give a brief) | Hacker News Algolia API, Reddit public JSON, GitHub issue search, RSS/Atom feeds (`backend/app/sources/news.py`) | `research/news.json` |
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

## 6. Tests

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

### After updating: what you need to do

After `git pull` on this version (video quality fixes + bundled animation pack):

```powershell
cd renderer; npm run build; cd ..      # renderer: exposure, framing, QA report, animation pack
cd frontend; npm run build; cd ..      # UI: Fill in box for script gaps
```

Then restart the app and, for a project you already rendered:

1. Render page (top) or Studio → Script: if a box says the script needs a number only you know (e.g.
   `{{your number}}`), type your real value and press **Fill in**, or press **✦ Rewrite without the number**.
2. Render → **Re-plan** the clips (optional: plans saved before this version are repaired at render time
   anyway: no fades between clips, no placeholder badges) and **Regenerate** every clip, then run **Stitch**.
3. Read the `QA` lines in the Activity log or `final/qa.json`.

Optional: `pip install faster-whisper` for word-accurate caption timing, or Settings → Voice and captions →
Caption timing → **Groq Whisper** (with `GROQ_API_KEY`).

**All on Groq:** put `GROQ_API_KEY` in `.env`, restart, Settings → Writing model → **Use Groq for everything** →
Save. Writing, voiceover and caption timing then run on Groq (video still renders locally with three.js). If a
Groq voice call fails a clip falls back to Kokoro/Piper; if Groq Whisper fails captions fall back to
faster-whisper or the estimate. Check the speech model and voice names in the Groq console if the voice fails.

## 7. Known limits (read this)

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
  each clip's narration is spread across the stretch where its voice actually plays (local backends record
  it), or across the 10 s window for Omni clips.
- **Script gaps.** When the script needs a figure only you know it writes `{{your number}}`. A box at the top
  of the Render page (and in Studio → Script) lists them: type your value and press **Fill in**, or press
  **✦ Rewrite without the number** and the writing model rephrases those lines so they need none (checked: no
  gap left, no new numbers, hook kept). A real render stops until one of the two is done. Settings → Writing
  model → **Script gaps → rewrite automatically** does the rewrite by itself, so renders never stop there. The
  app never invents the number.
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
