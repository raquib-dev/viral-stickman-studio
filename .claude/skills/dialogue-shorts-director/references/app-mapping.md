# Mapping to the app's Dialogue short pipeline

This is where the reference style meets the app (`backend/app/dialogue.py`, the local-threejs
renderer). Settings are under Settings → Dialogue shorts.

## Already matching

| Reference | App |
|---|---|
| One shot per line, hard cuts only | `plan_shots` plus `build_scene`: a cut key per line |
| Her MCU / the mascot at desk height with her behind / a frontal wide | the shot vocabulary `a_cu`, `a_third`, `b_cu`, `b_ots` (low angle on the mascot with her behind), `two`, `wide0`/`wide1` |
| Characters still; only faces, blinks and mouths move | `motion: "still"` (the default) |
| Captions per line at the top in a dark translucent box with a quick fade, tags stripped | `build_line_ass`, `caption_lines` |
| A slow push-in on every shot | the `push` field on every camera key (3-6 %) |
| A constant room-tone bed, no music | `dialogue.bed: "room"` with a sidechain duck |
| Length follows the dialogue, not padded to 60 s | each clip ends on its last line plus 0.3 s (`clip_end`) |
| Short performed lines, timing labels, a callback, a turn, a loop | `DIALOGUE_RULES` and the `dialogue_flags` checker |
| The lowercase title ending in a question | checked by `dialogue_flags` |

## Measured differences (tune or build)

1. **Pause lengths.**
   - The references measure a 0.47 s median gap: quick about 0.15-0.3 s, beat 0.6-1.0 s.
   - The app uses quick 0.06, normal 0.2, beat 0.75 (`GAPS` in `dialogue.py`).
   - The app's normal turn is less than half the reference pause. To match exactly, use about
     `{"quick": 0.2, "normal": 0.45, "beat": 0.9}`.
2. **First word at 0.37 s.** The app's `LEAD` is 0.22 s.
3. **Cut lead.** The references cut 0.15 s before speech; the app cuts 0.12 s before (normal) and
   0.04 s before (quick).
4. **The mascot's mouth.** The reference Claude has no mouth and acts with its eyes only. The app
   gives it a small mouth that opens with speech, at your earlier request (lip sync for all
   characters). Pick one.
5. **Poses per shot.** The reference girl changes pose between shots: mug, phone, arms crossed, hand
   at her temple, open palm. The app's still mode holds one rest pose for the whole video.
6. **Blush and the closed-eye smile.** The references use them on key lines. The app's faces
   already have brows (skeptical, worried); blush and a closed-eye smile are missing.
7. **Mascot eye shapes.** The references add a small-square "caught out" eye. The app's `EYES` table
   has `skeptical` (slits) and `surprised` but no small squares.
8. **The 1.5-2 s pull-back after the last word.** The app's last shot is a wide that pushes in, and
   the clip ends 0.3 s after the last word.
9. **Caption placement.** The references put the box's top edge at about 10-12 % of frame height;
   the app uses the platform safe zone's top margin plus 1 %. Check it on a still.
10. **More AI characters** (a cube with glowing eyes, a cloud with `>_`). The app's dialogue cast
    is two speakers, a and b.
11. **Sets.** The references use four looks for the window (morning, rain, bokeh night, dusk) and a
    whiteboard classroom with board content that appears in sync with the words and a pointer. The
    app has the office set with a dark or light theme.
12. **Loudness.** The references measure about -15 LUFS; the app normalises to -16 LUFS (fine for
    Shorts and Reels, and 1 dB quieter).
13. **Frame rate.** The references are 30 fps; the app's dialogue clips render at the project fps
    (24 by default).

Items 1-3, 8, 9, 12 and 13 are small parameter changes. Items 4-7 are renderer work on existing
characters. Items 10-11 are new assets.
