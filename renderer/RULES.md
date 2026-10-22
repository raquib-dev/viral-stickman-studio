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
7. **One character, one look; colours follow the content.** Every clip uses the same rig, stick-figure
   proportions (`LEN` in `src/rig.js`) and style pack for the whole video. Within that style, the *mood*
   (palette) follows what each beat says and may change mid-clip, always by a smooth blend (0.8 s).
   A mood never changes the style, the character or the set.
11. **Everything has a name in `catalog.json`.** Styles, moods, props, gestures, hats, clips, expressions,
    shots and transitions are listed there. The Python planner and validator read it, and a test fails if
    it differs from what the built renderer supports.
12. **Keep things in the frame.** Planned props and badges are placed for a 9:16 frame (beside the
    character at chest height, or on the floor next to them). Two-character shots back off until both
    figures are fully visible.
8. **Offline and licensed.** Every model, font and library is in the repo or in `package.json` with an
   exact version, under a licence listed in `THIRD_PARTY.md` (CC0, MIT, OFL, Apache-2.0). No CDN, no
   network access at render time.
9. **Plugs in, never replaces.** `local-threejs` is one render backend behind the same interface as the
   others. The render stage, retries, the clip tracker, stitch and the other backends are unchanged.
   The vendored skills are not edited.
10. **Reviewed in phases.** The look (Phase 1) is approved before the motion library, the AI scene
    planner and the asset generator are built on top of it.
13. **Natural, not robotic.** The rig's clips are only the base. On top, every character gets: bendy limbs
    (two straight parts joined by a rounded bend, never locked straight), overlap (hands and forearms trail
    the body by ~0.1 s), breathing, a weight shift on planted feet with soft knees, relaxed hanging arms when
    idle, beat gestures and head nods that follow the voice, small glances, and gestures that ease in with a
    gentle overshoot. All of it is computed from time, so rule 2 still holds. `"limbs": "rigid"` on an actor
    (or the scene) brings back straight segments.
14. **AI plans are checked, repaired, or replaced, never trusted blindly.** The "Plan 3D scenes" stage
    asks the writing model for a scene plan per clip (data only, names from `catalog.json`, the approved
    Phase A row as its brief). `check_and_repair` then maps unknown names to safe defaults, clamps times
    and positions into the clip and the frame, trims clutter (2 actors, 3 props, 2 panels, 2 badges), and
    removes any on-screen number the voiceover does not say. A plan that still fails gets one retry with
    the errors, then the keyword plan is used. Hand-edited plan files (no `_planned_by`) are never
    overwritten.
15. **AI-drawn props are data and take the palette.** A drawing is a list of low-poly shapes from
    `asset_shapes`, each coloured by a role from `asset_colors` (never a free colour) with an optional motion
    from `asset_motions`. `normalize_asset` drops anything else, caps it at 40 parts, and stands it on the
    floor at a sensible height. Drawings are cached per project and embedded in each scene that uses them,
    so a render never depends on a file that might change; Redraw updates every scene that uses it.
16. **Your edits win.** A plan saved from the scene editor (`"_planned_by": "editor"`) or written by hand
    is never replaced by the AI planner, unless you press Re-plan on that clip and confirm.
17. **Any humanoid animation pack, retargeted by direction.** A pack's skeleton is matched by bone name
    (this rig, Quaternius/Unreal, Mixamo, Blender), turned to face +Z, and only its bone directions are
    used, so it drives the same stick figure. Core moves prefer the pack's versions; `pack:<clip>` names any
    other pack clip. Without a pack, everything still works on the base rig. The repo ships one (KayKit
    Adventurers, CC0; Blender bone names, no neck bone: its chest stands in).
18. **Only light sources glow, and no frame blows out.** Bloom starts above linear 1.0, so lit skin and paper
    cards never haze; the character's colour stays under paper white; each frame renders a tiny linear-HDR
    copy of itself and lowers exposure (to x0.72 at most) only when its own 96th-percentile highlight would clip.
    A plan's `exposure`, `bloom` and `handheld` are clamped to safe ranges. Pure in the frame, so stills match.
19. **One story, no dips to black.** Clips cut straight into each other: `transition` fades only into the
    first clip and out of the last (applied at plan time and again at render time; an editor-saved plan keeps
    its own). A close-up is head and shoulders (zoom ≥ 0.9) and eases out to a medium shot while a note or
    badge is up; in 9:16 cards are fitted to the frame (≤ 1.15 m wide, top ≤ 2.2 m); props stay behind the
    actor's front line (z ≤ 0.6).
20. **Every render reports on itself.** render.mjs emits a `qa` event per clip (frames rendered vs expected,
    near-black frames no fade explains, mostly-white frames, how often the exposure guard acted); stitch writes
    `final/qa.json` for the whole video (frame count, audio vs video length, black dips, caption overlaps).

## Scene plan (version 2)

```jsonc
{
  "version": 2, "width": 720, "height": 1280, "fps": 24, "duration": 10, "seed": 7, "quality": "high",
  "style": "cozy",                 // minimal | modern | cinematic | prehistoric | cozy | historic, or a skill id 1/2A/2B/3/4/5
  "theme": "dark",                 // dark | light (each style has both)
  "mood": [{ "t": 0, "mood": "money" }, { "t": 3.8, "mood": "success" }],   // or one name; blends over 0.8 s
  "actors": [{
    "id": "hero", "position": [0, 0, 0], "facing": "camera",            // or radians
    "path": [{ "t": 0, "pos": [-1.6, 0, 0.3] }, { "t": 1.7, "pos": [0, 0, 0] }],  // walks/runs automatically
    "anim": [{ "t": 0, "clip": "Idle" }, { "t": 2.0, "clip": "ThumbsUp" }],
    "gestures": [{ "t": 2.4, "gesture": "point", "target": "p1", "dur": 2.2 }, { "t": 5, "gesture": "think" }],
    "look": [{ "t": 0, "at": "camera" }, { "t": 3, "at": "other" }],      // camera | actor id | prop id | left/right/up/down | [x,y,z]
    "face": [{ "t": 0, "expr": "surprised" }],
    "talk": [[0.4, 6.0]],                                              // or "mouth": {fps, values[]} from the voice
    "hat": "crown", "color": "#f1ece4", "limbs": "bendy"                 // bendy (default) | rigid
  }],
  "assets": { "dragon": { "height": 0.8, "parts": [{ "shape": "capsule", "size": [0.15, 0.4], "pos": [0, 0.3, 0], "color": "green",
               "motion": { "type": "flap", "axis": "x", "amount": 25 } }] } },   // AI-drawn props, embedded
  "props": [{ "id": "p1", "type": "coins", "pos": [0.55, 0, 0.15], "t_in": 1.0, "enter": "drop", "idle": "bob" },
            { "type": "custom:dragon", "pos": [-0.6, 0, 0.1] },
            { "type": "mug", "hold": { "actor": "hero", "hand": "R", "t": 0.6 } }],
  "panels": [{ "title": "theme/dark.ts", "lines": ["export const dark = {"], "t_in": 4.6, "pos": [0.6, 1.08, -0.3] },
             { "kind": "note", "title": "Three rules", "lines": ["Pay yourself first"], "pos": [0, 2.2, -1] }],
  "badges": [{ "text": "19 files changed", "t_in": 5.4, "pos": [0, 2.15, -0.4] }],
  "camera": [{ "t": 0, "shot": { "type": "medium", "target": "hero", "side": -0.18 } },
             { "t": 5, "shot": "closeup", "ease": "inOutCubic" },
             { "t": 10, "pos": [0, 1.6, 3], "look": [0, 1.2, 0], "orbit": 0.3 }],
  "transition": { "in": "fade", "out": "none" }                        // none | fade | iris | wipe
}
```

Style packs: the set, the character material, the card skin (glow, glass, flat, paper, parchment, slate), the
fonts and the grade. Moods: neutral, money, success, danger, calm, tech, mystery, nostalgia, sad, love, nature.
The full lists of props, gestures, hats, clips, expressions, shots and transitions are in `catalog.json`.
Version 1 scenes (`"theme": "warm-dark"` and no style) still render.
