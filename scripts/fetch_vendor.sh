#!/usr/bin/env bash
# Clone the five reference repos into vendor/ at the commits docs/repo-analysis.md was written against.
# Read-only references: nothing here is installed globally. Run from the repo root (Git Bash on Windows).
set -euo pipefail
mkdir -p vendor
clone() { # url dir commit
  if [ ! -d "vendor/$2/.git" ]; then git clone -q "$1" "vendor/$2"; fi
  git -C "vendor/$2" fetch -q origin "$3" 2>/dev/null || git -C "vendor/$2" fetch -q --unshallow origin || true
  git -C "vendor/$2" checkout -q "$3"
  echo "vendor/$2 @ $3"
}
clone https://github.com/kaomei/stickman-video-director.git   stickman-video-director 70199c86911d84de9804441ce581eeb25142efba
clone https://github.com/Jakeschincariol/youtube-agent-skill.git youtube-agent-skill  a2feb2104981a375ffd4f87ee04f4f5344ac43c6
clone https://github.com/Jakeschincariol/instagram-agent-skill.git instagram-agent-skill d03c56bb598be770c60b201f94237e5d1a4268a6
clone https://github.com/dsauce/stickman-kino.git              stickman-kino          d3d665301c0b62f04c885785e6bd6044de0785c6
clone https://github.com/0xS4N4TG/papercut-explainer.git        papercut-explainer     ff8223abc8136cc09e8d7e9b62ecb5d080c389e1
