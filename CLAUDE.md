# Viral Stickman Studio — notes for Claude

Project skills live in `.claude/skills/` (vendored, unmodified; see `THIRD_PARTY.md`). Do not edit them;
override behaviour from the app's prompts instead.

## Path overrides for the vendored skills

The yt-* and ig-* skills mention files under `~/.claude/`. In this project use these instead:

| Skill text says | Use |
|---|---|
| `~/.claude/youtube/voice.md` | `config/voice/youtube.md` |
| `~/.claude/instagram/voice.md` | `config/voice/instagram.md` |
| `~/.claude/instagram/swipe.md` | `projects/<slug>/research/swipe.md` |
| `~/.claude/instagram/log.md`, `plan.md` | `projects/<slug>/research/log.md`, `plan.md` |

## Hard rules

- Never publish, post, comment, like, follow or DM on any platform. Every output ends as files and copy blocks.
- Never log into Instagram or any account; never scrape behind auth.
- Never invent a statistic. Numbers need a source URL or come from the user.
- Never print, log or store API keys (`GEMINI_API_KEY`, `FAL_KEY`, `YOUTUBE_API_KEY`).
- Use `python3` in Linux/macOS shells; the app resolves the interpreter itself (`sys.executable`).
