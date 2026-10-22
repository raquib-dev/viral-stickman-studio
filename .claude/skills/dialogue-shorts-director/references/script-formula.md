# Script formula

## The five premise types (all seven references fit one of them)

| Type | Engine | References |
|---|---|---|
| **Tender quirk** | An AI limitation turned into something sweet: it forgets, it can't eat, it is "millions of me" | v1 (it forgets every morning; she remembers), v2 (mom thinks it's a person) |
| **Explain like I'm five** | She bans jargon; the AI finds a metaphor on a whiteboard; she tests edge cases; it names the concepts | v3 (API = waiter) |
| **Team of AIs** | Several AI tools with clashing personalities on one task | v4 (launch tomorrow: Cursor builds early, Codex says "Done.", Claude asks questions), v5 (Claude asks four questions, Codex asks none) |
| **AI can't do the human thing** | A plain human pleasure the AI can't have | v6 (it can look at reels but can't like them) |
| **Credit and work** | Who really did the work; the human's taste vs the AI's output | v7 (she said no 61 times; "that's the job") |

## Line rules

- **Hook:** the human says the AI's name, then the situation, all in at most 8 words. "Claude. Good
  morning." "Claude. My mom thinks you're a person." "Claude. Explain an API like I'm five." For a
  group: "Okay, everyone. The client wants to launch tomorrow."
- **Length:** 1-9 words a line, mostly 2-6. A one-word line ("No." "Done." "Eleven." "And?") is a
  weapon; use it 3-6 times a reel. An explainer line may run to about 15 words, but only on the
  whiteboard shot.
- **Count:** 26-40 lines for 41-57 s.
- **Speakers:** she has about half the lines and asks most of the questions. The AI answers,
  deflects or over-delivers. In group reels the second and third AIs get 3-6 lines each, each with
  a tic.
- **Register:** plain spoken English, contractions, no slang, no emoji, nothing the AI couldn't
  plausibly say.
- **Hesitation:** "..." at the start of a line is a beat before it. Use it 3-6 times, on the lines
  that carry the feeling: "...We've met." "...It's complicated." "...That's actually good."
- **Interruption:** at most once a reel, someone barges in mid-line. The caption shows the cut-off
  words ("Should it have a" / "Dark mode. Yes. It has one now.").
- **Numbers in the story:** specific and absurd. "forty times a day", "sixty-one times", "forty-one
  reels", "eight of me", "four thousand lines", "two pixels off", "1 AM". They are comedy, not
  statistics.

## Joke engines that repeat across the set

- **Literal AI:** it takes a human phrase at face value ("Did you?" "No."; "I can't eat." "More for
  me.").
- **The AI's known tics as callbacks:** "You're absolutely right" (v2, v7), "Quick question" (v5),
  "Hello! How can I help you today?" (v1), "Done." (Codex).
- **A personality clash** in group reels: one asks too much, one asks nothing, one starts before
  the brief.
- **A reversal of care:** the human turns out to be the one who remembers or protects ("I know. I
  wrote it down anyway." "Someone has to remember.").
- **The human's deadpan veto:** "No. Simpler." "I'm five." "Too soon, Claude."

## Structure (beats with line counts for about 34 lines)

1. **Hook (lines 1-2):** the premise is stated and the AI reacts, so the conflict is clear by about
   4 s.
2. **Escalation (lines 3-20):** 3-4 short exchanges, each one pushing the quirk further.
   - Alternate who gets the laugh.
   - Put one wide on the line that widens the stakes.
3. **Turn (about 60-70 % in):** a reveal that reframes the premise.
   - v1: she writes it all down.
   - v5: Codex deleted the desktop.
   - v3: "That's a bug."
4. **Callback (the last 25 %):** bring back the tic or line planted earlier, with a twist.
5. **Button (the last 1-2 lines, on the wide):** one of these:
   - a **loop** to the opening (v1 ends where it began, with "Hello! How can I help you today?");
   - a **reversal** from the side character (v5 "All of them.");
   - a **self-own** (v3 "Too soon, Claude.", with a blush);
   - a **deadpan cap** (v2 "More for me.").

## Performance notes (for ElevenLabs v4 in this app)

- The girl is flat, tired and dry, and gets warmer only on the tender lines. Use few tags:
  [deadpan], [sighs], [quietly], occasionally [exasperated] on a name ("Claaauude.").
- Claude is calm, polite and sincere. Its assistant-mode lines are bright and chirpy ([cheerfully]).
  Small-eyes moments are [hesitant].
- Codex is flat, low and quick; one word. Cursor is upbeat and fast ([excited]).
- Timing labels: about 60 % normal, 20 % quick, 15 % beat. A beat goes before any "..." line.

## Title and caption (from the reference titles)

```
<series name>? | <premise sentence one>. <contrast sentence two>. | <one question to the comments>? #<ai> #<ai> #aitools #<topic>
```

- Everything is lowercase except AI product names in hashtags.
- The two premise sentences mirror each other:
  - "every morning he forgets. every morning she remembers."
  - "one asks four questions. one asks none."
  - "he can look. he can't like. it's been an hour."
- The question invites a personal story or a vote:
  - "what's the nicest thing your AI ever said that it won't remember?"
  - "which one are you working with today?"
  - "what's the pettiest thing you've made your AI redo?"
- Explainer series: "explain it like i'm five part N: <question>? no technical words allowed."
  followed by "which tech word should Claude explain next?"
- A tool shout-out reel says so plainly: "not sponsored. <tool> is free and open source by
  <author>."
- Use the user's own series name, not the reference channel's.
