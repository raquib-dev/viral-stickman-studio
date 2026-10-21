# three.js animation renderer: rules

These rules keep the renderer reliable, repeatable and safe. Every change to `renderer/` and to the
`local-threejs` backend must keep them. The tests check the ones that can be checked automatically.

1. **The AI never writes code.** It writes a *scene plan*, a JSON file in the format below. The renderer only
   reads data from it. Unknown clips or expressions are rejected (`validate_scene`), and the clip fails
   with a clear message instead of rendering something wrong.
2. **Same input, same video.** No clock, no `Math.random`. Every frame is a pure function of
   `(scene, t)`. Noise, blinks and grain are seeded (`src/util.js`). Re-rendering a clip gives the same
   frames.
3. **Frames are rendered, not recorded.** `render.mjs` asks for frame *i* and waits for it, so a slow
   machine gives a slower render, never dropped or stuttering frames.
4. **Exact output.** Each clip is exactly `duration` seconds at the project's ratio, resolution and a
   constant frame rate, so stitch timing never drifts.
5. **Text is engine-drawn, and only from the plan.** Code panels, badges and signs show text the plan
   gives them, drawn crisply on canvases. Captions, the hook card and callouts are still added by the
   stitch step. The keyword planner only puts a number on screen when the voiceover itself says it (no
   invented statistics, see CLAUDE.md).
6. **Respect the safe zones.** Keep the character and elements inside the band left free by the hook
   card (top), word captions (lower middle) and platform buttons (bottom and right), using the same
   margins as `backend/app/render/overlays.py`.
7. **One character, one look.** Every clip uses the same rig and stick-figure proportions (`LEN` in
   `src/rig.js`), and the same theme for the whole video.
8. **Offline and licensed.** Every model, font and library is in the repo or in `package.json` with an
   exact version, under a licence listed in `THIRD_PARTY.md` (CC0, MIT, OFL, Apache-2.0). No CDN, no
   network access at render time.
9. **Plugs in, never replaces.** `local-threejs` is one render backend behind the same interface as the
   others. The render stage, retries, the clip tracker, stitch and the other backends are unchanged.
   The vendored skills are not edited.
10. **Reviewed in phases.** The look (Phase 1) is approved before the motion library, the AI scene
    planner and the asset generator are built on top of it.

## Scene plan (version 1)

```jsonc
{
  "version": 1, "width": 720, "height": 1280, "fps": 24, "duration": 10,
  "theme": "warm-dark",            // warm-dark | cool-dark | light
  "seed": 7, "quality": "high",    // high = bloom + depth of field, medium = bloom, draft = neither
  "actors": [{
    "id": "hero", "position": [0, 0, 0], "facing": 0,              // metres, radians
    "anim": [{ "t": 0, "clip": "Idle" }, { "t": 1.1, "clip": "No" }], // 0.35 s cross-fades; one-shots return to Idle
    "face": [{ "t": 0, "expr": "surprised" }, { "t": 3.6, "expr": "confused" }],
    "talk": [[0.35, 3.2]],                                         // or "mouth": {fps, values[]} from the voice
    "color": "#f1ece4"
  }],
  "panels": [{ "title": "theme/dark.ts", "lines": ["export const dark = {"], "t_in": 4.6,
               "pos": [0.6, 1.08, -0.3], "rot": [0, -0.3, 0], "w": 1.5 }],
  "badges": [{ "text": "19 files changed • +1,256", "t_in": 5.4, "pos": [0, 2.75, -0.7], "size": 0.95 }],
  "camera": [{ "t": 0, "pos": [0, 1.6, 1.3], "look": [0, 1.58, 0], "fov": 32 },
             { "t": 4.6, "pos": [0.35, 1.85, 4.4], "look": [0.1, 1.65, -0.5], "fov": 40, "ease": "inOutCubic" }]
}
```

Clips (from the CC0 rig): Idle, Walking, Running, Dance, Death, Sitting, Standing, Jump, Yes, No, Wave,
Punch, ThumbsUp, WalkJump. Expressions: neutral, happy, surprised, sad, angry, confused, thinking,
skeptical. Elements also take `from`, `t_out`, `ease`, `scale`, `float`, `glow`.
