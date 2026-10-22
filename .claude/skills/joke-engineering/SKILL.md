---
name: joke-engineering
description: >-
  Diagnose and punch up jokes in a short comedy script by treating each joke as a connection the viewer
  completes. Use for a punch-up pass on a dialogue short's lines, a hook, a pinned comment or cover text:
  when a joke falls flat, is predictable, too obscure, over-explained or bloated.
license: MIT
metadata:
  author: jwynia (adapted for this project)
  source: https://github.com/jwynia/agent-skills/tree/e02ec7e226a6e4f8419fd3b88a1d8e472d421b32/skills/creative/humor/joke-engineering
---

# Joke engineering: a punch-up pass

Adapted from jwynia's `joke-engineering` skill (MIT; see NOTICE.md). This version keeps the method and fits it to
this project's format: deadpan dialogue shorts about living with AI tools, for viewers worldwide.

## The idea

A joke is a connection between two ideas that the viewer completes in their own head. When a joke doesn't
land, one property of that connection is off. Find which one, fix that, and leave the rest alone.

## Nine properties

| Property | What it means here | When it fails |
|---|---|---|
| Connection distance | How far apart the two ideas are | Too close: the viewer saw it coming. Too far: the viewer is lost |
| Density | How many links reinforce the joke | One thin link: a shrug |
| Resolution | The click of "getting it" | The punchline doesn't follow from the setup |
| Specificity | Exact details | "late at night" instead of "1 AM"; "a lot" instead of "sixty-one times" |
| Irony layering | Contradictions inside contradictions | A flat "the AI is bad" with no twist |
| Viewer completion | The last step is the viewer's | The line explains its own joke |
| Compression | Ideas per word | A setup so long the punch arrives late |
| Resilience | Works without a special reference | Only developers, or only Americans, get it |
| Authenticity | Sounds like this character | A line nobody in this scene would say |

## Six states and the fix for each

- **H1 Too obvious.** The viewer sees the punchline coming. Fix: shift the frame. Answer a different question
  than the one asked, or take the request too literally.
- **H2 Too obscure.** The joke needs knowledge the viewer may not have (a coding term, a US show, a local
  idiom). Fix: give the scene the context and keep the words everyday. Never add an explanation line.
- **H3 Too thin.** One link only. Fix: let one element do two jobs. Pay off a number or phrase planted
  earlier, or turn the AI's habit back on itself.
- **H4 Over-explained.** The punchline is said instead of implied. Fix: cut the line one beat early. Let a
  silence, a look or a one-word answer finish it.
- **H5 Forced voice.** The joke is clever but out of character. Fix: say it the way this person would. She
  is dry and tired; the AI is earnest and literal.
- **H6 Bloated setup.** Momentum dies before the punch. Fix: remove every word that explains rather than sets up.

## The irony gradient (this format's engine)

The strongest jokes here put big effort against a small target:

- high effort on a trivial task (sixty-one rounds of feedback on one blue);
- perfect execution of the wrong task (it "tidied" the desktop by deleting it);
- a complex system for a simple need (eight copies of itself for a login page);
- confident speed and the wrong result ("Done." about something nobody asked for).

## Before and after, in our format

Each pair is speaker: line. The fixes keep each line's speaker, length and timing.

**H4 over-explained**
> before · Claude: I deleted your desktop because you asked me to tidy it.
> after  · Codex: Deleted it.
> after  · Mia: The whole desktop?
> after  · Codex: It's tidy.

The viewer joins "tidy" and "deleted" in their own head; saying it out loud killed it.

**H1 too obvious → frame shift**
> before · Mia: Did you finish the feature? · Claude: Yes, it's finished!
> after  · Mia: Did you finish the feature? · Claude: I finished three. You asked for one.

The literal yes became an over-delivery, the AI's habit turned into the joke.

**H2 too obscure → everyday words**
> before · Claude: I refactored the monolith into microservices.
> after  · Claude: I split your one app into twelve. They don't talk to each other.

A developer still nods; a viewer who never coded gets it from "they don't talk to each other".

**H6 bloat → compression**
> before · Mia: You know, every single morning when I come in, you've forgotten everything we did.
> after  · Mia: ...We've met.

Two words carry the whole premise when the beat before them is right.

**H3 thin → a callback that does two jobs**
> earlier · Claude: You say "you're absolutely right" forty times a day.
> later   · Mia: Anyone can say no. · Claude: I can't. I say "you're absolutely right."

The planted number and phrase come back as the turn.

## Rules for a punch-up pass in this project

1. Fix only the weak jokes. A line that already works stays as it is; most lines do.
2. Keep every line's speaker, timing (quick, normal, beat), pose and whiteboard items. Line 1 (the approved
   hook) never changes. Keep the number of lines the same.
3. Keep lines short: 2-6 words, never more than 9 (a whiteboard explanation up to 16). Keep delivery tags in
   square brackets, at most 2 a line, and keep "..." where a beat sits.
4. Plain international English: common words a viewer reading captions in their second language knows; no US
   slang, idioms, sports or TV references. Tech words only when the scene explains them.
5. Never add real-world statistics. Numbers are in-story details about these characters.
6. Name the state (H1-H6) you fixed for each changed line, in one short note.

## Anti-patterns

- **Over-engineering.** Not every line is a joke; the setup lines that make the punch work stay plain.
- **Density at all costs.** One clean link beats three tangled ones. Short and dry is the house style.
- **Explaining the implicit.** If a joke needs a follow-up line to explain it, cut the explanation, not the joke.
- **Voice erasure.** A technically better joke in the wrong voice is worse. Keep each character's way of talking.
- **One metric only.** Shorter (compression) can make a line obscure (resilience). Check both.

This pass can say which property is off and propose a fix. Whether a joke is actually funny is the
creator's call and the viewers' comments.
