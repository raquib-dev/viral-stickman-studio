# Repo analysis

What each of the five source repos contributes to Viral Stickman Studio, what we call directly, what
we adapt, and where they disagree. Every SKILL.md, every reference file and every Python tool in the
three skill packs was read in full; for stickman-kino and papercut-explainer every SKILL.md, every
`references/*.md`, the docs, `lib/prompts.mjs` and the voice/timing tools were read, and the render
kits (GSAP engine, Remotion TSX) were read structurally. Commits are pinned in `THIRD_PARTY.md`.

## 1. What each repo contributes

### kaomei/stickman-video-director → `directing-stickman-videos` (vendored, called)

- **Contract:** source → setup gate (ratio, duration in 10 s multiples, Style 1–5) → **Phase A**
  director's proposal → explicit approval → **Phase B**: N = duration/10 standalone ~10 s Omni Flash
  prompts. Any global change invalidates approval. The app honours this as a GATE.
- **5-stage arc:** Golden Hook → Disrupting Assumptions → Unveiling Insider Secrets → Ultimate Truth →
  Elevation & Discussion, with clip allocation tables per duration (`storyboard-template.md`).
- **Word budget:** 20–25 English words per 10 s clip; each clip has three timed beats
  `[0–3s] [3–7s] [7–10s]`, ≥4 visual devices, a visible change every 2–3 s, named continuity hand-offs.
- **Character anchors:** Style 1 Light/Dark tested faceless blocks, Style 2 beanie anchor, Style 4
  cozy anchor, Style 5 historical cel-shaded anchor (new upstream file `historical-cartoon.md`, now
  vendored). Anchors and a frozen voice block are repeated **verbatim** in every clip.
- **Prompt hygiene:** no on-screen text in generated clips (overlays are a separate post-production
  list), no hex/RGB colours, audio-only VO, no liquid morphing, 720p / 24 fps target.
- **Evidence notes:** consistency results are dated, sample-specific Flow tests, not guarantees. We
  keep that honesty in the UI ("prompt compliance ≠ observed output").

### Jakeschincariol/youtube-agent-skill → `yt-*` (vendored, called)

| Tool | Used by stage | How |
|---|---|---|
| `yt-script/hookscore.py` (+ `hooks.json`, 21 formulas) | 3 Patterns, 5 Hooks | subprocess `--json`; panel SPECIFICITY/ADDRESS/STAKES/CURIOSITY/BREVITY, formula classifier |
| `yt-viral/swipe.py` | 2 Discovery | subprocess `--json --min`; multiple over channel median (≥4 videos/channel) + title formula |
| `yt-package/title.py` | 8 Packaging | subprocess `--json --thumb`; title/thumbnail pairing lint |
| `yt-chapters/chapters.py` | 8 Packaging | subprocess on the final `.srt`; validates YouTube chapter rules |
| `yt-retention/retention.py` | 9 Learn | subprocess on the Studio CSV `--transcript`; hook leak, cliffs, slide |
| `yt-edit/deadair.py` | 3 Patterns (timing parser), QA | SRT/VTT/whisper loader; dead-air check on our own narration |

Skills run through the Agent SDK: `yt-script` (hooks + beat-marked script), `yt-package`, `yt-seo`,
`yt-chapters` (retitling), `yt-shorts` (cut-downs), `yt-retention`, `yt-viral` (interpretation).
Not used in the pipeline: `yt-comment`, `yt-plan`, `yt-audit` (available to the user in Claude Code).

### Jakeschincariol/instagram-agent-skill → `ig-*` (vendored, called)

| Tool | Used by stage | How |
|---|---|---|
| `ig-reel/hookscore.py` (+ `hooks.json`, 26 formulas) | 3, 5 | subprocess `--json`; LENGTH/SPECIFICITY/STAKES/FRONTLOAD/ADDRESS + dealbreakers |
| `ig-reel/beats.py` | 5 Script | subprocess `--json --wpm --target`; hook > 3 s, beat > 4 s, abstract runs, loop check |
| `ig-viral/swipe.py` | 2 Discovery | subprocess on a TSV built from pasted links/stats; outlier multiple, formula, hook score |
| `ig-caption/caption.py` | 8 Packaging | subprocess `--json --keywords` |
| `ig-human/humanize.py`, `detect.py`, `slop.json` | 5, 8 | subprocess on narration and every text block |

Skills run through the Agent SDK: `ig-reel`, `ig-human` (structural rewrites the scripts only flag),
`ig-caption`, `ig-repurpose`, `ig-audit`, `ig-viral` (method + interpretation). Not used:
`ig-carousel`, `ig-story`, `ig-profile`, `ig-plan`, `ig-comment`, `ig-reply`, `ig-dm`.

### dsauce/stickman-kino (reference only, `vendor/`)

Deterministic code-rendered stickman films: `film.json` + `scenes.js` → HyperFrames/GSAP → headless
Chrome seek-render. 58 poses with 2-bone IK, a prop library (its docs say "~190"; I did not recount the
202 you mentioned), 15 transitions, local Kokoro TTS, procedural music/SFX, `sc.cue("word")`
narration-cued actions, a `check` + `snapshot` contact-sheet review loop, and `stickman prompts` (an
Omni/Veo prompt exporter credited to kaomei's method).

- **Adapt:** (a) the optional `kino` render backend later (film.json is a clean target for our Phase A
  storyboard); (b) the snapshot/contact-sheet QA idea for our per-clip previews (ffmpeg thumbnails);
  (c) `-16 LUFS` voice / `-30 LUFS` bed loudness targets for the loudness pass; (d) semantic accent
  slots a1/a2/a3 = problem/solution/reward, which matches kaomei's "three accents with meaning".
- **Do not reuse:** its prompt exporter (shorter, older Style 1 anchor and a looser voice line than the
  director skill's tested blocks); its mandatory 3–4 s intro preset (see conflict C8).

### 0xS4N4TG/papercut-explainer (reference only, `vendor/`)

Remotion pipeline: strategy → hook → script → storyboard → voice → build → QA. 17 camera moves,
11 cut kinds, word-by-word caption tags, a comment-keyword CTA scene, 79 synthesized SFX, Qwen3-TTS or
own VO with ASR word timing (`build_timing.py`, falls back to 2.75 w/s estimate).

- **Adapt:** (a) the **SAY / WRITE / SHOW / ALIGN** hook block — spoken line, frame-0 on-screen title,
  first-frame action, one shared idea — becomes the structure of each hook card in Studio; (b) the
  6-question hook check (complements both hookscore panels with judgement questions a regex cannot
  answer: "does it leave the answer for later?", "is every claim true to the facts sheet?"); (c) the
  competitor-reel analysis report format (hook layers at 0–2 s, shot list, single most stealable idea)
  for the "Why it worked" panel; (d) ASR-aligned word timing → burned-in captions, with the same
  estimate fallback; (e) SFX budget rule ("air" sounds ≤ 1 per 2.5 s); (f) post-publish autopsy order
  (hook → topic → format → audience → timing) for the Learn stage.
- **Do not reuse:** the Remotion kit, the 10-beat 22–30 s spine timings, the 3.5–4 words/s pace.

## 2. Reuse matrix

| Piece | Reuse directly | Adapt | Not used |
|---|---|---|---|
| `directing-stickman-videos` skill (Phase A/B, anchors, voice block) | ✔ via Agent SDK | timeline annotations from blueprint are layered on its Phase A output | |
| yt/ig Python tools (12) | ✔ subprocess, `--json` | thin wrappers that parse JSON and tolerate non-zero "verdict" exit codes | |
| yt/ig skills (script, package, seo, chapters, shorts, reel, human, caption, repurpose, audit, retention, viral) | ✔ via Agent SDK | voice-file paths overridden (see C12) | comment/plan/profile/story/dm/reply/carousel |
| kino engine + CLI | | optional `kino` backend, loudness targets, contact-sheet QA | prompt exporter, intros |
| papercut kit | | hook block, hook check, competitor report, ASR caption timing, SFX budget, autopsy order | Remotion kit, spine timings |

## 3. Conflicts and how we resolve them

| # | Conflict | Resolution |
|---|---|---|
| C1 | **Arc.** Director: 5 stages (Hook → Disrupt → Insider Secrets → Ultimate Truth → Elevation). Kino: 5-beat (Hook → Disrupt → Reveal → Payoff → Close). Papercut: 10-beat spine. ig-reel: Hook → Stake → Body → Payoff → Loop. yt-script: Hook (0–15 s) → Turn → Body → Payoff → Close. | The **director's 5 stages are the canonical arc**, because it is the skill that turns the script into Omni prompts and its Phase A checks enforce them. Kino's beats map 1:1 (Reveal = Insider Secrets, Payoff = Ultimate Truth, Close = Elevation). The other shapes become **beat-level overlays** placed by the blueprint/niche profile: *stakes line* (ig-reel's STAKE, by ~0:04), *re-hooks* (papercut's "And get this", yt-script's turn), *payoff marker* (yt-script "say you are delivering it"), *loop* (ig-reel). Styles 3 and 5 keep their own setup → escalation → payoff override, as the skill requires. |
| C2 | **Speaking rate.** yt-script 150 wpm; ig-reel/beats.py 165 wpm; director 20–25 words per 10 s (120–150 wpm); kino 2.4 w/s (144 wpm); papercut 3.5–4 w/s (210–240 wpm). | Omni Flash speaks the VO inside a fixed ~10 s clip, so the **director's ≤25 words per clip is the hard budget**. `beats.py` runs with **`--wpm 150`** (25 words/10 s) so its timings agree with the clip budget; a per-project override comes from the user's voice.md "Pace" field if they record their own VO. Papercut's 210+ wpm is rejected: it would overrun every Omni clip. yt-script's 150 wpm is used for long-form runtime estimates, unchanged. |
| C3 | **Hook window.** beats.py flags a hook past 3 s; ig-reel 0–2 s; yt-script "first 15 s is the whole job"; director 2–5 s short, up to 15 s long. | Two-level rule in the blueprint: the **opening line lands within 3 s on every format** (beats.py flag stays on), and for long-form the hook's three jobs (confirm the click, open a gap, prove the payoff exists) complete by 15 s. |
| C4 | **Two hookscore panels.** yt: SPECIFICITY/ADDRESS/STAKES/CURIOSITY/BREVITY, ideal 9–24 words. ig: LENGTH/SPECIFICITY/STAKES/FRONTLOAD/ADDRESS, ideal 5–12 words, plus dealbreakers. Both 60% mean + 40% weakest. | Run **both** on every hook and show both panels. Ranking uses the panel of the **primary platform** for the project (Shorts/Reels → ig, long-form → yt). For multi-platform projects rank by the mean of both and flag hooks whose scores disagree by > 20 points. Any ig dealbreaker hides a hook from the top-two unless the user overrides. Both are labelled heuristics (their own READMEs say AUC 0.83 bad-vs-real, ~0.56 hit-vs-miss). |
| C5 | **Two formula taxonomies.** yt 21 formulas (string ids, best multi-pattern count); ig 26 (numeric ids, first match in `classify_order`). | Store both labels per hook/title. A small name crosswalk (e.g. *The Statistic*, *Contrarian Flip*, *The Reveal*, *The Superlative*, *Someone Else's Result* exist in both) lets the niche profile aggregate by a merged label while keeping the originals. |
| C6 | **Outlier baseline.** yt swipe.py computes the channel median from the rows it is given (needs ≥4 per channel, default `--min 1.5`). ig swipe.py uses a hand-entered `median` (falls back to followers); ig-viral calls > 3x a signal. | YouTube: we fetch ~30 recent uploads per channel via the Data API and let `swipe.py` compute the median (`--min 2.0`, as its README example). Instagram: `ig-viral`'s method — the user enters the median by eye from public listings; we warn when only followers are given. Both multiples shown; ≥3x highlighted as "signal" per ig-viral. |
| C7 | **On-screen text.** Director: generated clips contain **no** words; overlays are a separate post-production list. ig-reel: hook card at frame 1, burned captions for the body. Papercut/kino burn banners and captions into the render. | Director wins **inside generation** (text in diffusion output garbles and drifts). Our ffmpeg stitch stage adds, in post: word-timed captions, the frame-0 hook card (papercut WRITE / ig-reel on-screen line, ≤6 words) and the director's overlay list, inside the platform safe zones from the research. |
| C8 | **Intros.** Kino requires a 3–4 s intro title preset before narration. yt-script, ig-reel and papercut all say no intro: the video starts on the hook. | **No intro.** The frame-0 hook card replaces kino's title sequence. Kino outro presets are not used; long-form gets an end-screen-safe final hold sized from YouTube's documented end-screen window. |
| C9 | **Ending.** Director Stage 5: punchline + open discussion question (not for Styles 3/5). ig-reel/yt-script: exactly one ask; last line echoes the hook (loop). Papercut: keyword CTA. | **Exactly one ask**, chosen per project (comment question by default, keyword CTA optional), and the **last line repeats a hook word** — this satisfies beats.py's loop check, the director's callback rule and papercut's "last line repeats the hook number". Styles 3/5 keep their no-question payoff. |
| C10 | **Voice source.** Director: Omni generates narration, frozen voice block in every prompt. Kino: lay your own TTS VO over AI clips for consistency. Papercut: TTS/recording + ASR timing. | Default: **Omni native audio** with the director's frozen voice block (the skill's tested path). Captions are timed by ASR (faster-whisper, if installed) on the stitched audio, else by distributing each clip's known VO text across its known clip window (exact boundaries, approximate words). An "external VO track" option is left as a documented extension, not built in v1. |
| C11 | **Change cadence.** Director: visual change every 2–3 s. Papercut: set every 1.5–3 s, event every 0.4–0.8 s. beats.py: spoken beat > 4 s flagged. | Inside clips: director's 2–3 s (it is what the prompts encode). beats.py's 4 s spoken-beat flag stays as a script-level check. Pattern interrupts *between* stages are placed from the niche profile. |
| C12 | **Voice/swipe file paths.** Packs read `~/.claude/youtube/voice.md`, `~/.claude/instagram/{voice,swipe,log}.md`. | Vendored skills stay unmodified. The app passes `config/voice/youtube.md`, `config/voice/instagram.md` and `projects/<slug>/research/swipe.md` explicitly in every skill prompt, and `CLAUDE.md` documents the same mapping for interactive use. `ig-viral/swipe.py --out` is pointed at the project folder. |
| C13 | **Instagram collection.** ig-viral: browse with the user's own logged-in browser, present. Brief: public listings only, never log in, paste fallback. | The app never drives a browser into Instagram. Primary IG path is **paste links + stats** into a form that writes ig swipe.py's TSV; secondary corpus is public YouTube Shorts (which ig-viral itself endorses). |
| C14 | **Exit codes.** ig `hookscore.py` exits 1 when the best hook < 70; `caption.py`, `detect.py` exit 1 when not READY/PASS. | Wrappers read `--json` stdout and treat exit 1 with valid JSON as a result, exit 2 / bad JSON as an error. |
| C15 | **Style 1 anchor wording.** kino's `lib/prompts.mjs` uses a shorter Style 1 anchor and a different narrator line than the director's tested blocks. | Director skill text is authoritative; kino's exporter is not used. A test asserts the anchor is identical across all Phase B prompts. |
| C16 | **Clip length.** Director assumes ~10 s Omni clips; kino clips are auto-length from TTS. | Omni path: fixed 10 s clips (verified against current API docs in `docs/research/platform-signals-2026.md`). Kino backend, if built, uses kino's own timings. |

## 4. Things the packs say that we must keep saying

- `hookscore.py` is a heuristic: "a low score is a reason to look again; a high score is not a promise".
- Formula labels are "a judgement about the words, not a claim about why the video got its views".
- `detect.py` is not GPTZero/Originality and cannot promise their verdicts.
- Nothing publishes. Every stage ends in files and copy blocks.
