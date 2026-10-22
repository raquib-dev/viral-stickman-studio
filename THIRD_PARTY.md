# Third-party code

The skill packs below are vendored, unmodified, into `.claude/skills/` so the app's Claude Agent SDK
loads them as project skills and the repo works the same on any machine after `git pull`. Each skill
folder carries its pack's `LICENSE`. All three are MIT.

| Pack | Upstream | Commit | Vendored folders | License |
|---|---|---|---|---|
| Stickman Video Director | https://github.com/kaomei/stickman-video-director | `70199c86911d84de9804441ce581eeb25142efba` | `directing-stickman-videos` (includes Style 5, `references/historical-cartoon.md`) | MIT, © 2026 Stickman Video Director contributors |
| YouTube agent skill | https://github.com/Jakeschincariol/youtube-agent-skill | `a2feb2104981a375ffd4f87ee04f4f5344ac43c6` | `yt-audit yt-chapters yt-comment yt-edit yt-package yt-plan yt-retention yt-script yt-seo yt-shorts yt-viral` | MIT, © 2026 Jake Schincariol |
| Instagram agent skill | https://github.com/Jakeschincariol/instagram-agent-skill | `d03c56bb598be770c60b201f94237e5d1a4268a6` | `ig-audit ig-caption ig-carousel ig-comment ig-dm ig-human ig-plan ig-profile ig-reel ig-reply ig-repurpose ig-story ig-viral` | MIT, © 2026 Jake Schincariol |

The skill folders must stay siblings: `yt-viral/swipe.py`, `yt-chapters/chapters.py` and
`yt-retention/retention.py` import from `../yt-script` and `../yt-edit`; `ig-viral/swipe.py` imports
from `../ig-reel`.

## three.js renderer (`renderer/`)

| Asset | Source | License |
|---|---|---|
| `renderer/public/models/stickman-rig.glb`: skeleton + 14 animation clips | "RobotExpressive" by Tomás Laulhé (Quaternius), with facial morphs by Don McCurdy, from the three.js repository `examples/models/gltf/RobotExpressive/` | CC0 1.0 (public domain). Its robot meshes are hidden; the stick figure, face, hats, props and sets are this project's own, built in code |
| three.js `0.180.0` (npm) | https://github.com/mrdoob/three.js | MIT |
| Inter `@fontsource/inter 5.2.5` | https://rsms.me/inter/ | SIL Open Font License 1.1 |
| JetBrains Mono `@fontsource/jetbrains-mono 5.2.5` | https://www.jetbrains.com/lp/mono/ | SIL Open Font License 1.1 |
| Caveat `@fontsource/caveat 5.2.5` (cozy/prehistoric cards) | https://github.com/googlefonts/caveat | SIL Open Font License 1.1 |
| EB Garamond `@fontsource/eb-garamond 5.2.5` (historical cards) | https://github.com/octaviopardo/EBGaramond12 | SIL Open Font License 1.1 |
| playwright-core `1.56.1` (npm), drives the headless browser | https://github.com/microsoft/playwright | Apache-2.0 |
| `renderer/public/models/anim-pack.glb`: humanoid skeleton + 76 animation clips (its meshes are hidden) | "KayKit : Adventurers Character Pack 1.0" (`Knight.glb`) by Kay Lousberg (www.kaylousberg.com), from https://github.com/KayKit-Game-Assets/KayKit-Character-Pack-Adventures-1.0 (`addons/kaykit_character_pack_adventures/Characters/gltf/Knight.glb`) | CC0 1.0, per the pack's `LICENSE.txt` |

## Read-only references (not committed)

`scripts/fetch_vendor.sh` clones these into the gitignored `vendor/` folder for study. No code from them
is copied into this repo; ideas adapted from them are credited in `docs/repo-analysis.md`.

| Repo | Commit | License |
|---|---|---|
| https://github.com/dsauce/stickman-kino | `d3d665301c0b62f04c885785e6bd6044de0785c6` | MIT, © 2026 Prerit Ahuja |
| https://github.com/0xS4N4TG/papercut-explainer | `ff8223abc8136cc09e8d7e9b62ecb5d080c389e1` | MIT, © 2026 sanat |

## Updating a pack

Re-copy the folders from a newer upstream commit, keep each `LICENSE`, update the commit here, and run
the test suite (the tool wrappers pin the CLI flags they rely on).
