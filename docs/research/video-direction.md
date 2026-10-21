# Video direction: craft for short-form and explainer videos

Evidence labels and the verification method are the same as in `video-psychology.md`. Platform
documentation counts as **official**. The skill packs we vendor count as **pack guidance**: their
authors' practice, sometimes measured, mostly not. **Creator lore** means practitioner claims with no
controlled evidence.

## 1. Hook archetypes and the first 1–3 seconds

**What the platforms measure.**
- Meta's Reels ranking documentation lists a prediction of "how likely you are to watch less than
  three seconds" of a reel ([Instagram Reels Chaining AI system](https://transparency.meta.com/features/explaining-ranking/ig-reels-chaining/)).
  **Official.** The 3-second mark is something the system models, not folklore.
- YouTube's retention report has an "Intro" key moment: the share of viewers still watching after
  the **first 30 seconds**. YouTube's advice is to align the thumbnail and title with the opening
  ([Measure key moments for audience retention](https://support.google.com/youtube/answer/9314415?hl=en)).
  **Official.**
- YouTube Shorts analytics reports "Viewed (vs. swiped away)"
  ([YouTube Community announcement](https://support.google.com/youtube/community-video/273390203/new-youtube-shorts-metric-viewed-vs-swiped-away?hl=en)).
  **Official (community post, about 3.5 years old).**

**Archetypes.** The packs give us 21 YouTube and 26 Instagram formulas (`.claude/skills/yt-script/hooks.json`,
`.claude/skills/ig-reel/hooks.json`) plus papercut's 7 patterns. They group into five families:
*number/statistic*, *mistake/negative command*, *contrarian flip*, *named result / receipt*, and
*question / mid-sentence cold open*. **Pack guidance.** The packs' own READMEs say the formula label
"is a judgement about the words, not a claim about why the video got its views".

**Rules we apply.**
- The opening line lands within **3 s** on every format. This is beats.py's `HOOK_WINDOW`, it matches
  the Meta prediction above, and it is pack guidance. Long-form completes the hook's three jobs
  (confirm the click, open a gap, prove the payoff exists) by **15 s** (yt-script, pack guidance) and
  protects the 30 s Intro metric (official).
- Three aligned layers, papercut's **SAY / WRITE / SHOW**: the spoken line, a 2–5 word on-screen card
  that does *not* repeat the spoken words, and frame 0 already mid-action. All three point at one
  idea. **Pack guidance.**
- No greeting, no channel intro, no "in this video". These are ig hookscore dealbreakers and a
  yt-script rule. **Pack guidance.**

## 2. Cut frequency and visual change rate

- Film research: Hollywood shot structure moved toward 1/f correlated shot lengths, which the authors
  link to holding attention (Cutting, DeLong & Nothelfer 2010, [SAGE](https://journals.sagepub.com/doi/10.1177/0956797610361679)).
  **Moderate, film rather than short-form.**
- Educational video: across 6.9 million edX watching sessions, shorter videos held engagement better.
  Informal talking-head and tablet-drawing styles did well (Guo, Kim & Rubin, L@S 2014,
  DOI 10.1145/2556325.2566239, [PDF](https://up.csail.mit.edu/other-pubs/las2014-pguo-engagement.pdf)).
  **Strong for MOOCs.**
- Pack guidance: the director skill asks for a visible change every **2–3 s** inside each 10 s clip.
  Papercut's analysis of its reference reels reports scenes averaging **2.8 s**, with 2–4 events per
  scene, one every **0.4–0.8 s** on a stressed word (`papercut-qa`, "Pacing stats"). beats.py flags any
  spoken beat over **4 s**. All of these are **pack guidance / creator analysis, not controlled
  studies.**
- **Our rule:** inside a clip, change every 2–3 s (encoded in the Omni prompts). At the script level,
  no spoken beat over 4 s. Stage-level interrupts follow the niche profile (blueprint
  `pattern-interrupt-cadence`).

## 3. Motion in frame 1

Papercut: frame 0 is "the most striking moment, already mid-action. No establishing shot, no fade-in."
ig-reel: "Motion in the first frame, not a static face." **Pack guidance.** The mechanism is the
orienting response (`video-psychology.md` §3). For Omni prompts, the `[0–3s]` beat of clip 1 must
start mid-action. The director skill already bans idle openings.

## 4. On-screen text rules and safe zones

**Generated clips carry no text** (director skill: diffusion models garble text, and hex codes
render as text). All text is added in post by our ffmpeg stage.

**9:16 (Reels / Shorts).**
- Meta's ads guidance: leave roughly **14% at the top, 35% at the bottom and 6% on each side** free of
  text, logos and key creative ([Meta Ads Guide, Instagram Reels](https://www.facebook.com/business/ads-guide/update/image/instagram-reels);
  [safe zone help](https://www.facebook.com/business/help/980593475366490/)). **Official for ads.**
  Organic Reels have the same UI chrome (caption, action rail), so applying it to them is a
  reasonable **inference**.
- ig-reel's organic rule on 1080×1920: nothing above y=230 or below y=1440, and keep the right 230 px
  clear. **Pack guidance.** On a 1920 px frame that is 12% top and 25% bottom, which is *less*
  conservative than Meta's 14%/35%.
- **Our rule:** use the stricter of the two on every edge. Top 14%, bottom 35%, left 6%, and right
  21% (ig-reel's 230 px of 1080, which keeps text clear of the action rail; Meta's 6% is the
  looser figure there). I found no official YouTube Shorts safe-zone spec, so Shorts use the same box,
  labelled **inference**.
- Six words or fewer per card. The hook card is up at frame 1. **Pack guidance (ig-reel).**

**16:9 (long-form).**
- End screens occupy the **final 5–20 s** and need a video of at least 25 s
  ([Add end screens](https://support.google.com/youtube/answer/6388789?hl=en)). **Official.** Keep
  those seconds free of overlays and give them a calm visual hold.
- Captions sit in the lower third, clear of the progress bar. That is **convention**; I found no
  official numeric spec.

**Captions.** In a Verizon Media / Publicis Media survey of 5,616 US adults, 69% said they watch
video with the sound off in public places, and 80% of caption users were not hearing-impaired
([Streaming Media summary](https://www.streamingmedia.com/Articles/News/Online-Video-News/80-of-Video-Caption-Users-Arent-Hearing-Impaired-Finds-Verizon-131860.aspx)).
**Moderate (self-report survey; I could not confirm the year from the results).** We burn in
word-timed captions by default (also ig-reel guidance).

## 5. Audio and SFX punctuation

- Voice first. Kino mixes VO at −16 LUFS over a −30 LUFS music bed; papercut normalises VO to
  −16 LUFS. **Pack guidance**, consistent with the common streaming loudness target. Our loudness pass
  targets −16 LUFS integrated for the master. That is our choice; neither platform publishes a
  required LUFS that I found.
- SFX land on the **visual** frame, not the word (kino). Use 1–3 per clip (kino). "Air" sounds (whoosh,
  whip) at most one every 2.5 s (papercut). **Pack guidance.**
- Omni generates its own SFX. The director skill asks for "synchronized crisp SFX on physical actions"
  and a BGM continuity lock across clips.

## 6. Rhythm of narration vs visuals

- Each 10 s Omni clip carries 20–25 words in three beats `[0–3s] [3–7s] [7–10s]`, with the visual on
  or just before the stressed word (director skill; kino `sc.cue`). **Pack guidance.**
- Shorten the VO rather than speed it up (director, papercut). **Pack guidance.**
- The rate conflict (150 vs 165 vs 2.4 w/s vs 3.5–4 w/s) is resolved in `docs/repo-analysis.md` C2:
  ≤25 words per clip and beats.py at 150 wpm.

## 7. Loopable endings

- YouTube counts a Shorts view each time a Short starts or **replays**, with no minimum watch time
  (since 31 March 2025, [Get started creating Shorts](https://support.google.com/youtube/answer/10059070?hl=en)).
  From **24 August 2026** views are counted on play for all formats, while "engaged views" (past the
  first seconds) drive monetization
  ([How engagement metrics are counted](https://support.google.com/youtube/answer/2991785?hl=en);
  [Engaged views explained](https://blog.youtube/inside-youtube/engaged-views-youtube-explained/)).
  **Official.**
- Meta predicts "how likely you are to watch more of a reel than 95% of users who watched reels of the
  same length" ([Reels Chaining](https://transparency.meta.com/features/explaining-ranking/ig-reels-chaining/)).
  **Official.** A seamless loop extends watch time relative to length (**inference**).
- **Technique:** the last line echoes a word from the hook (beats.py loop check, ig-reel guidance).
  The last frame visually matches frame 0 (the director's continuity rule applied from the end back
  to the start).

## 8. Re-hooks ("but here's the catch") and where they go

- Evidence for re-engaging viewers mid-video is **creator lore**. The leaked MrBeast production guide
  (reported, never confirmed by the company) calls the first minute "the most important minute" and
  describes "re-engagement" content inserted around **3 and 6 minutes**
  ([Gigazine](https://gigazine.net/gsc_news/en/20240917-mrbeast-youtube-production),
  [Passionfruit](https://passionfru.it/mrbeast-leaked-document-81151/)). Papercut's spine puts
  "And get this" before the peak and an honest "catch" after it. **Pack guidance.**
- Mechanism support: resumption pull (Ovsiankina) and the curiosity gap (`video-psychology.md`
  §1–2).
- **Our rule:** defaults are re-hooks at the stage boundaries, roughly 30–40% and 65–75% of runtime
  (end of Disrupting Assumptions, end of Ultimate Truth). **The niche pattern profile overrides these
  defaults** once there is evidence from the user's niche. Long-form also gets one every ~3 minutes
  (lore, labelled as such).

## 9. Callout placement

A "callout" is a short on-screen label pointing at the thing being said: an arrow plus 2–5 words.
- It appears on the stressed word and is removed within one beat (papercut banners: 3–7 words, every
  2–3 s, never repeating the VO). **Pack guidance.**
- In our pipeline, callouts are **post-production overlays** from the director's overlay list, placed
  inside the safe zone and never covering the figure's head or the caption band.

## 10. CTA placement and count

- **One ask.** yt-script ("One ask. Not three"), ig-reel, ig-caption (`caption.py` counts asks and
  warns at two or more), papercut. **Pack guidance, unanimous.**
- Placement: at the **payoff** (the last 3 s in Reels per ig-reel; after the payoff in long-form,
  before the end screen). Never at the start: yt-script calls an early subscribe pitch "the single
  most common cause of the 0:30 cliff". **Pack guidance.**
- Keyword CTAs ("comment STRANGER") must be one sayable word (ig-caption). Our app never sends DMs;
  keyword delivery is the user's own approved tooling.

## 11. Chaptering for long-form

YouTube's rules: the first timestamp is 00:00, there are at least three timestamps in ascending order,
and each chapter is at least 10 s long ([Video Chapters](https://support.google.com/youtube/answer/9884579?hl=en)).
**Official.** `yt-chapters/chapters.py` validates exactly these three rules. Our 5-stage arc gives
natural chapter boundaries. Every chapter title is rewritten as a promise in 3–5 words (yt-chapters).

## 12. Retention-curve shapes and what causes each cliff

YouTube describes four shapes: **flat** (watched start to finish), **gradual decline** (losing
interest), **spikes** (rewatching or sharing) and **dips** (abandoning or skipping). Top moments that
appear late suggest moving that content earlier
([key moments](https://support.google.com/youtube/answer/9314415?hl=en)). **Official.**
`yt-retention/retention.py` splits the curve into **hook leak** (first 30 s), **cliffs** (single steep
drops) and **slide** (the steady bleed). Its thresholds (under 25% hook leak counts as healthy) are
**pack guidance**.

| Shape | Usual cause (pack guidance + inference) | Fix in our pipeline |
|---|---|---|
| Steep loss in 0–3 s / 0–30 s | hook does not match title or thumbnail; static frame 0; greeting | re-run Hooks stage; SAY/WRITE/SHOW alignment |
| Cliff at a stage boundary | topic change with no signposting; an early CTA | add a re-hook line; move the CTA |
| Cliff in the middle | long setup; one beat > 4 s; repeated idea | beats.py flags; cut the beat |
| Steady slide | pacing | cut, don't rewrite (yt-retention) |
| Drop in the last 5–20 s | end screen / credits ("normal", per YouTube) | none needed; keep the payoff before it |
| Spike | rewatch or share moment | note the beat type; reinforce in the niche profile |
