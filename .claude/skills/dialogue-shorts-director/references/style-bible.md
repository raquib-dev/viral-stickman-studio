# Style bible

Everything below was observed in the seven reference reels. The source is noted in brackets, v1-v7
(the list is in `reference-breakdowns.md`). "Measured" means the value was computed from the file,
and "observed" means it was read off sampled frames.

## Format

- 720x1280, 30 fps, H.264 with AAC 44.1 kHz stereo (measured, all seven).
- 41.4-57.2 s long (measured). The length follows the conversation; nothing is padded to 60 s.
- Low-poly 3D look: flat-shaded facets on every character and prop, soft global light, strong
  depth of field, a warm key from the desk side and cool light from the window.

## Characters

### The girl (the human; she is never named)
- Big round head, peach skin with visible facets, small black dot eyes, and a tiny dark line for a
  mouth that opens into a small rectangle when she talks.
- Large round thin black glasses that are wider than her eyes.
- Long dark-brown hair with a side part, falling past her shoulders.
- Bright yellow chunky jacket, open, over a black tee.
- Headphones around her head in the late-night office episodes [v4, v7].
- **Faces she makes:**
  - deadpan neutral (most of the time);
  - flat brows for skeptical or tired [v4, v7];
  - one raised brow [v3 "Why not?"];
  - worried brows with a blush on her cheeks [v3 ending "Too soon, Claude."];
  - eyes closed in a content half-smile [v1 "You won't remember."];
  - a small smile on the final wide [v1, v4].
- **Poses** change between shots, and inside a shot she is still (observed):
  - hands around a white mug [v1];
  - holding a phone and looking down at it [v2, v6];
  - arms crossed [v5 from the middle on, v6];
  - hand at her chin or temple, thinking [v7];
  - open palm gesturing at the other AI [v5 "He's faster."];
  - both hands forward, "both of you" [v5];
  - pointing a finger up, assigning jobs [v4];
  - seated sideways in profile at a school desk [v3 whiteboard].
- **Movement:** she does not bob or sway. She blinks, her mouth flaps with the voice, and her pose
  and expression are set per shot.

### Claude (the main AI)
- An orange low-poly flower or star blob with 5-6 rounded lobes and stubby orange feet. It sits on
  the desk in front of her, to the left of the keyboard.
- Two black vertical rectangle eyes. **It has no mouth.**
- **Its acting is all in the eyes:**
  - tall rectangles are neutral or earnest;
  - small squares are unsure or caught out ["...I was asking a question.", "You deleted three thousand."];
  - its body turns toward what it looks at, such as the phone in v6.
- **Character:** earnest, helpful, literal. It loops into assistant mode ("Hello! How can I help you
  today?") and asks too many clarifying questions ("Quick question.").

### Cursor [v4]
- A black cube on two black round feet, with two glowing white rectangle eyes (emissive).
- Eager and fast; it starts before being asked ("Hi! I already started.").

### Codex [v4, v5]
- A blue-to-purple gradient cloud blob with a white `>_` prompt glyph for a face and dark blue feet.
- Terse and over-confident; its tic is "Done." It acts first and asks never.

## Sets

**The desk.** Every set except v3 shares it, seen from the front:
- the girl behind it;
- a monitor at frame right showing coloured code lines;
- a keyboard, a white mug, a notepad with a pen, and yellow and orange sticky notes;
- a small orange object at the far left edge;
- a ceiling or desk lamp at top right, visible in the wide shots;
- a big window behind her with a city skyline.

**Time of day.** The window sets the mood, and it is the one thing that changes between episodes:

| Look | Sky | Used for |
|---|---|---|
| Morning | pale blue sky, grey towers, soft daylight | tender or wholesome (v1) |
| Rainy night | dark blue-grey, white rain streaks, a red light in the far background | cosy or awkward (v2, v5) |
| Late night, bokeh | near-black blue, warm and cool bokeh dots, lit windows | crunch or work (v4, v7) |
| Dusk | purple-to-pink gradient sky, warm bokeh | casual or fun (v6) |

**The classroom whiteboard (v3).**
- A whiteboard on an easel in front of a window, a bookshelf at the right, and a leafy wall pattern.
- The girl sits at a wooden school desk on a teal chair, side-on to camera.
- Claude stands on a stack of three books (green, purple, yellow) and points a long thin stick at
  the board.
- **Board content appears in sync with the words**, popping in instantly with no drawing animation:
  - "What is an API?" heading at the top, underlined;
  - a jargon word appears in navy when said ("interface", "systems", "software"), and a red
    strike-through cancels it when she says "No. Simpler.";
  - then the metaphor: stick figures (YOU, WAITER in green, KITCHEN as a box) with double green
    arrows;
  - then labels in blue and red (= front end, = API, = back end).
- The pointer stick moves to point at whatever was just added.

## Captions
- One caption per spoken line; a long line wraps to 2 lines (3 at most for explainer lines).
- White bold sans serif, about 30 px tall at 1280 px, centred.
- Dark slate box behind it (about #2b3036 at 80 % opacity) with rounded corners and tight padding.
- Positioned with its top edge at about 10-12 % of frame height, over the window and above the
  characters' heads.
- **Fades in over about 0.15-0.2 s** (a semi-transparent frame was caught at a line start [v3, v4]).
  The whole line appears at once, with no word-by-word reveal.
- Stays up until the next line replaces it, including through the pause.
- Writing in the caption:
  - a leading "..." marks a hesitation;
  - quotes are kept ("Still. Is he kind to you?");
  - CAPS are not used; emphasis lives in the voice;
  - an interrupted line shows only what was said.
- A small semi-transparent channel handle sits at about 62 % of frame height, centred [v3, v4].
  Use the user's own handle, or nothing.

## Audio (measured)

- **Loudness:** -14.7 to -16.3 LUFS integrated, loudness range 5.4-10.1 LU, true peak up to
  +0.6 dBFS. The references are not peak-limited; ours should cap at -1 dBTP.
- **Bed:** a constant broadband ambience about 45-55 dB under the voice peaks, present from frame
  one and never dropping to silence (under -40 dB there are almost no gaps). It is room, rain or
  city tone, not music: the spectrogram shows no sustained tones and no beat. It tapers out over
  the final pull-back.
- **Voices:** cleanly recorded TTS-style voices, dry, with no music under them.
  - The girl's voice measures roughly 175-235 Hz: a female mid-register voice, delivered flat
    and dry.
  - Claude's voice measures roughly 105-150 Hz: a male mid-low voice, calm and polite. When it
    switches into "assistant mode" ("Hello! How can I help you today?") it jumps to about
    255-270 Hz, bright and chirpy, and that jump is the joke.
  - Codex measures about 95-110 Hz: deep, flat, one word at a time.
  - Cursor is brighter, quicker and eager.
  - Accent cannot be determined from these measurements (the frequency analysis gives pitch and
    timing, not pronunciation). Pick ElevenLabs voices by ear for the character traits above.
- **Sound effects:** none were identified at cuts or for actions. The reels run on voice plus
  ambience.
