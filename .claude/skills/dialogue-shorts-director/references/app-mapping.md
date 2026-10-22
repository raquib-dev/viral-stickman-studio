# Mapping to the app's Dialogue short pipeline

This is where the reference style lives in the app:
- `backend/app/dialogue.py`: the rules, shots, timing and scene;
- the local-threejs renderer: sets in `renderer/src/env.js`, AIs in `mascot.js`, poses and faces in `rig.js`;
- Settings → Dialogue shorts.

## Built to the reference measurements

| Reference | App |
|---|---|
| First word at 0.37 s; median gap 0.47 s (quick 0.15-0.3 s, beat 0.6-1.0 s) | `LEAD` 0.37; `GAPS` quick 0.2 / normal 0.45 / beat 0.9; a turn across a clip cut keeps its gap (`clip_lead`) |
| Cuts 0.15 s before the next speaker's first word | `CUT_LEAD` 0.15; a beat cuts to the listener about 0.33 s after the previous line |
| Her MCU; the AI at desk height with her soft behind it, alternating sides; a frontal wide | shots `a_cu`, `a_third`, `m_<who>_l/r` (focus on the AI, her body blurred, the AI turned to face the angle), `wide` |
| A wide every 8-12 lines; the last line on the wide, then a 1.5-2 s pull-back | a wide after 9 lines without one; the final clip holds 1.7 s and dollies back (`end_hold`) |
| The same speaker going on keeps the shot | `cut: false` in the plan |
| A slow push-in on every shot, no shake | `push` on every key, `handheld` 0 |
| Poses change on cuts: mug, phone, arms crossed, temple, palm, both hands, finger | `pose` per line, held until changed, snapped on the cut |
| Closed-eye smile; worried brows with a blush | expressions `content`, `embarrassed`, `worried` |
| The AIs have no mouth and get small square eyes when caught out | `mascot_mouth` off by default; mascot face `caught` |
| A cube with glowing eyes; a gradient cloud with `>_` | mascot shapes `cube`, `cloud`; cast `c` and `d` (switch on in Cast) |
| Morning, rain, bokeh night and dusk outside the window | office looks `morning`, `rain`, `night`, `dusk` |
| Whiteboard explainer: title, jargon struck through in red, stick figures, arrows, labels, a pointer | `classroom` set; `board` items per line, each shown as its word is said |
| Captions: dark translucent box about 11 % from the top, 0.15 s fade-in, up until the next line | `build_line_ass`, `caption_lines` |
| An ambience bed (rain, city, room) with no music, fading out with the pull-back | bed `auto` → `rain` / `city` / `room` |
| About -15 LUFS, 30 fps | `dialogue.lufs` -15, `dialogue.fps` 30 |
| Length follows the dialogue | each clip ends on its last line (`clip_end`) |

## Still different

- In the reference classroom the girl sits on a chair. The app's chibi stands behind the school desk; it reads
  the same in the board wide and in her profile shot.
- The references sometimes prop a phone on a stand facing the AI. In the app the phone is only ever in her hand.
- Accent and voice timbre come from the voices you pick (ElevenLabs voice IDs or Kokoro names). The reference
  voices can't be identified from measurements.
