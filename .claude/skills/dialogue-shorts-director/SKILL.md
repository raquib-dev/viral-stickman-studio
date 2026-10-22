---
name: dialogue-shorts-director
description: >-
  Write and direct a 40-60 s vertical dialogue short in the "human developer + AI mascots at a desk"
  style: deadpan two-hander about living with AI tools, a hard cut per line, captions at the top, a
  final wide that pulls back. Use when the user asks for a dialogue short, a Claude/AI mascot skit,
  "a video like the reference reels", a script for the Dialogue short format, or wants an existing
  dialogue script, shot plan or render checked against the reference style.
---

# dialogue-shorts-director

Built from a shot-by-shot study of seven reference reels (41-57 s each, 720x1280, 30 fps). Every
number here was measured from those files (frame sampling, scene-cut detection, speech-energy and
pitch tracking, EBU R128 loudness). Read the references before writing anything longer than a hook:

- `references/style-bible.md`: characters, sets, lighting, props, caption and audio spec.
- `references/camera-and-edit.md`: the shot vocabulary, cut timing, shot lengths, the ending.
- `references/script-formula.md`: premise types, line rules, the joke engines, structure, title.
- `references/reference-breakdowns.md`: the seven reels dissected (premise, beats, shot pattern).
- `references/app-mapping.md`: how this maps onto the app's Dialogue short pipeline, and what the
  app does not do yet.

## The style in one paragraph

A girl developer (round glasses, long dark hair, yellow jacket over a black tee) sits at her desk
facing camera. Her AI tools are small low-poly creatures on the desk: an orange flower-star (Claude)
and, in group episodes, a black cube with glowing eyes (Cursor) and a blue-purple cloud with a `>_`
on its face (Codex). They talk in very short lines. She is dry and deadpan; the AI is earnest,
literal and a little off. Each line gets its own shot: her medium close-up, or the mascot at desk
height with her body huge and soft behind it. Hard cuts land about 0.15 s before each speaker's
first word. The dialogue sits in a dark caption box at the top. Under it there is room tone and no
music. The last line plays on a frontal wide, and the camera keeps pulling back for about 2 s after
the talking stops. Every story ends on a callback, a loop or a sharp button.

## Workflow

1. **Premise (one sentence)** from one of the five premise types in `script-formula.md`. Name the
   AI quirk the joke runs on (no memory, literalism, over-asking, over-acting, speed, "you're
   absolutely right", can't eat or touch things).
2. **Beat sheet**: hook, then 3-4 escalating exchanges, a turn, a callback, a button. 26-40 lines
   in total. A 45-55 s reel is about 30-38 lines.
3. **Write the lines** to the rules in `script-formula.md`: 1-9 words, mostly 2-6. Open with
   "[AI name]. [situation]." Mark each line with its timing: quick, normal or beat.
   - For ElevenLabs v4, put the performance inside the text: audio tags, stretched words, CAPS on
     the stressed word.
   - A leading "..." in a line means a beat before it, and it stays in the caption.
4. **Shot list**: one shot per line, from the vocabulary in `camera-and-edit.md`.
   - Open on her MCU.
   - Use a frontal wide in the opening third for any group or new-character moment, and once mid-way.
   - The last line goes on the wide, then the pull-back.
5. **Title and caption**: the lowercase two-sentence premise, then one question to the comments,
   then 3-6 hashtags. Format in `script-formula.md`.
6. **Check** with the list below, then hand over the script, shot list and copy as files and copy
   blocks.

## Checks before it ships

- [ ] The first word is spoken at about 0.37 s (all seven references start between 0.37 and 0.41 s).
- [ ] The video is 40-58 s and follows the dialogue. Do not pad it to 60.
- [ ] Gaps between lines:
  - median about 0.45 s;
  - quick answers 0.15-0.3 s;
  - beats 0.6-1.0 s;
  - at most two pauses over 1 s.
- [ ] Shots average 1.8-2.6 s, which is 18-26 shots in a 45-55 s reel.
- [ ] No shot repeats the previous shot's framing, except a held shot across one speaker's two lines.
- [ ] Every cut lands 0.13-0.20 s before the next speaker's first word. Listener reaction shots are
  the exception and come 0.3-0.6 s after a line ends.
- [ ] Captions:
  - one per line, 1-2 lines, white bold on a dark translucent rounded box with its top edge at about 10-12 % of frame height;
  - fade in over about 0.15 s;
  - the full line stays up until the next line replaces it;
  - interrupted lines show what was said ("Should it have a").
- [ ] Audio:
  - continuous room or ambience bed (rain, city night), no music;
  - about -15 LUFS integrated (references: -14.7 to -16.3);
  - the bed fades out with the final pull-back.
- [ ] The ending:
  - the last line plays on the frontal wide;
  - the pull-back runs about 1.5-2 s after the last word;
  - no fade to black, no end card.
- [ ] The script has a callback to an earlier line or tic, and a button that either loops to the
  opening or lands a short reversal.

## Hard rules (from the project's CLAUDE.md)

- Never post, comment or DM anywhere. Output is files and copy blocks.
- Numbers inside the story are jokes and are allowed ("sixty-one times", "eight of me"). Never
  present a real-world statistic without a source URL.
- **Write new jokes and new lines.** Use the formulas, not the reference reels' scripts; their lines
  are quoted in the references only to show the shape.
- **Don't copy another creator's identifying marks:** no `@canwebuildthis` watermark and no "Can We
  Build This?" series name. Use the user's own handle and series title.
- AI product names (Claude, Cursor, Codex, ChatGPT) are fine in dialogue and hashtags. Mascot
  designs should be the user's own, not a company's logo.
