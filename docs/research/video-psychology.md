# Video psychology: what drives watch time and shares

Each mechanism has: **mechanism** (what the research says), **in a short video** (how it shows up),
**stickman staging** (a concrete way to show it with our Omni Flash stick figures), and **misuse**.

## How to read the evidence labels

- **Strong**: peer-reviewed, replicated or a large field dataset.
- **Moderate**: one solid peer-reviewed study, or a strong study run outside video.
- **Weak / lab-to-video leap**: real research, but applying it to short video is our inference.
- **Creator lore**: practitioner claims with no controlled evidence. These are labelled lore and treated that way.

**How I checked sources:** this container's network policy blocks direct page fetches, so each
citation was checked through web search results restricted to the publisher, PubMed, DOI or
university-repository domains. I read abstracts and summaries, not full papers. A number appears below
only if a search result showed it next to its source. DOIs marked † came from secondary listings and
should be confirmed at doi.org before you quote them formally.

---

## 1. Curiosity gap / information-gap theory (Loewenstein)

- **Mechanism.** Curiosity is a form of deprivation. It comes from noticing a gap between what we know
  and what we want to know, and it grows as the gap becomes specific and feels closable. Loewenstein,
  "The psychology of curiosity: A review and reinterpretation", *Psychological Bulletin* 116(1),
  75–98 (1994), DOI 10.1037/0033-2909.116.1.75†
  ([citation record](https://stafforini.com/works/loewenstein-1994-psychology-curiosity-review/),
  [Columbia syllabus listing](https://psychology.columbia.edu/sites/default/files/content/Curiosity%20syllabus_Fall%202019.pdf)).
  In fMRI, curiosity about trivia answers tracked activity in the caudate, a region tied to
  anticipated reward. People spent scarce tokens or waiting time to get answers they were curious
  about, and recall of surprising answers 1–2 weeks later was better when curiosity had been high.
  Kang et al., *Psychological Science* 20(8), 963–973 (2009), DOI 10.1111/j.1467-9280.2009.02402.x
  ([PubMed](https://pubmed.ncbi.nlm.nih.gov/19619181/)). **Strong** for curiosity as a reward state;
  **lab-to-video leap** for retention.
- **In a short video.** The hook names a specific unknown ("why your brain treats future-you like a
  stranger") and holds the answer back until the payoff. The gap has to be specific. "You won't
  believe this" names no gap.
- **Stickman staging.** Show half the picture: the figure lifts the corner of a giant sheet over an
  oversized object and lets go just before we see it. Or show two identical doors where one is wrong.
- **Misuse.** A gap the video never closes is clickbait. Viewers drop off, and the satisfaction-survey
  signal YouTube uses (see `platform-signals-2026.md`) punishes it. A gap closed in the same sentence
  is no gap at all; yt `hookscore.py` docks CURIOSITY for "because / which means".

## 2. Zeigarnik effect and open loops

- **Mechanism.** The classic claim is that people remember unfinished tasks better than finished ones.
  A 2025 meta-analysis (Ghibellini & Meier, *Humanities and Social Sciences Communications* 12,
  DOI 10.1057/s41599-025-05000-w,
  [RePEc](https://ideas.repec.org/a/pal/palcom/v12y2025i1d10.1057_s41599-025-05000-w.html),
  [authors' PDF](https://boristheses.unibe.ch/4796/1/23ghibellini_r.pdf)) found **no general memory
  advantage** for unfinished tasks, but a reliable tendency to **resume** them (the Ovsiankina effect).
  The authors write that the Zeigarnik effect "lacks universal validity". **Strong evidence against the
  popular memory version; moderate evidence for a resumption pull.**
- **In a short video.** The useful part is resumption, not memory. An announced, unfinished sequence
  ("three reasons, and the third is the one nobody uses") gives viewers something to finish.
- **Stickman staging.** A three-slot rack with two slots lit and one dark. Or a progress bar the
  figure pushes along that stops at two thirds until the payoff clip.
- **Misuse.** Do not justify stacked open loops by citing "Zeigarnik memory". It does not replicate.
  Opening loops you never close is the same failure as §1.

## 3. Pattern interrupts and the orienting response

- **Mechanism.** The orienting response is an automatic shift of attention toward novel or changing
  stimuli. Lang's Limited Capacity Model treats a video's structural features, such as cuts and
  onsets, as triggers that pull automatic processing resources toward the message, up to the point of
  overload. Lang, "The Limited Capacity Model of Mediated Message Processing", *Journal of
  Communication* 50(1), 46–70 (2000), DOI 10.1111/j.1460-2466.2000.tb02833.x
  ([record](https://www.scinapse.io/papers/2163176562),
  [overview](https://en.wikipedia.org/wiki/LC4MP)). Over 70 years of Hollywood film, shot lengths
  became more correlated with their neighbours and the spectrum trended toward 1/f, which the authors
  link to holding attention. Cutting, DeLong & Nothelfer, *Psychological Science* 21, 440–447 (2010),
  DOI 10.1177/0956797610361679
  ([SAGE](https://journals.sagepub.com/doi/10.1177/0956797610361679)). **Moderate** (TV and film
  research; short-form is an inference).
- **In a short video.** A visible change every few seconds: a new shot, a new object, a camera move, a
  sound accent. Also bigger stage-level interrupts, such as a scene flip or a tone change, at points
  where attention usually sags.
- **Stickman staging.** The figure freezes mid-run, the frame jolts and the colour palette flips. A
  giant object crashes in from off-frame. A hard cut from a wide shot to an extreme close-up of one
  prop. The director skill already asks for a visible change every 2–3 s.
- **Misuse.** Overload. Lang's model predicts encoding falls once demands exceed capacity. Interrupts
  that have nothing to do with the spoken idea are spectacle. The director skill bans "unrelated
  spectacle" and liquid morphing.

## 4. Loss aversion and stakes

- **Mechanism.** In prospect theory, losses loom larger than equivalent gains (Kahneman & Tversky,
  *Econometrica* 47(2), 1979, DOI 10.2307/1914185†). The general claim is contested: Gal & Rucker
  argue that the evidence "does not support that losses, on balance, tend to be any more impactful
  than gains". *Journal of Consumer Psychology* 28(3), 497–516 (2018)
  ([SSRN](https://papers.ssrn.com/abstract=3049660),
  [Kellogg](https://www.kellogg.northwestern.edu/academics-research/research/detail/2018/the-loss-of-loss-aversion-will-it-loom-larger/)).
  **Moderate and contested.** The narrower, safer claim is that naming a concrete cost makes the
  message relevant.
- **In a short video.** A **stakes line** early on: what it costs the viewer to keep doing the current
  thing. ig-reel puts THE STAKE at 0:02–0:07, and both hookscore panels score STAKES.
- **Stickman staging.** Coins drain out of a hole in the figure's pocket. An hourglass empties onto a
  pile labelled with an icon. A trapdoor opens under a step the figure is about to take.
- **Misuse.** Invented or inflated costs, fear-mongering, and health or finance scare claims. Never
  invent the number (all three skill packs forbid it). In personal finance especially, YouTube's
  policy excludes monetization for AI personas presented as human experts on financial topics (see
  `platform-signals-2026.md`).

## 5. Peak-end rule

- **Mechanism.** People judge a past experience mostly by its worst or best moment and its final
  moment, and largely ignore duration. In the classic study, participants preferred a longer
  cold-water trial that ended slightly less painfully. Kahneman, Fredrickson, Schreiber & Redelmeier,
  "When More Pain Is Preferred to Less: Adding a Better End", *Psychological Science* 4(6), 401–405
  (1993), DOI 10.1111/j.1467-9280.1993.tb00589.x†
  ([APS page](https://www.psychologicalscience.org/journals/psychological-science/j.1467-9280.1993.tb00589.x/)).
  **Strong** for retrospective judgement; **lab-to-video leap** for how a video gets rated afterwards.
- **In a short video.** Build one clear peak (the biggest reveal) and end on a high, not a trail-off.
  This matters because the end is roughly when YouTube's satisfaction surveys and likes happen
  (inference).
- **Stickman staging.** The peak is the single exaggerated beat: a snap zoom on the payoff object and
  the one big accent colour. The ending is a resolved pose, such as the figure standing on the summit
  it climbed, followed by a clean hold.
- **Misuse.** A fake peak (overselling a mild point) or an ending made of three CTAs. Both packs
  say one ask.

## 6. Social proof

- **Mechanism.** People copy what others appear to choose. In a 14,341-person online music market,
  showing download counts made success **more unequal and less predictable**. Quality mattered only
  partly. Salganik, Dodds & Watts, *Science* 311, 854–856 (2006), DOI 10.1126/science.1121066
  ([PDF](https://pdodds.w3.uvm.edu/research/papers/years/2006/salganik2006a.pdf)). **Strong.**
- **In a short video.** "Most people…" framing, crowd reactions, and pointing to a well-known study.
  The real lever is mostly outside the video (view counts, comments), which we cannot fake and must not.
- **Stickman staging.** A crowd of identical figures all walks one way while our figure turns the
  other way. The crowd's choice is shown, then questioned.
- **Misuse.** Fabricated popularity ("millions are switching…") or fake testimonials. The Salganik
  result also warns that early social signals are noisy, so do not over-read one outlier (§ swipe
  sample-size caveats in the packs).

## 7. Identity and in-group signalling

- **Mechanism.** People sometimes choose differently from the majority to signal who they are,
  especially in domains that carry identity, like music or hairstyles. Berger & Heath, "Where consumers
  diverge from others", *Journal of Consumer Research* 34(2), 121–134 (2007), DOI 10.1086/519142
  ([RePEc](https://ideas.repec.org/a/oup/jconrs/v34y2007i2p121-134.html)). Sharing is partly
  self-presentation. On social platforms, posts about a political **out-group** were shared about
  twice as often, and each out-group term raised the odds of a share by 67%. Rathje, Van Bavel & van
  der Linden, *PNAS* 118(26) (2021), DOI 10.1073/pnas.2024292118
  ([PMC](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8256037/)). **Strong, observational.**
- **In a short video.** Name the viewer precisely ("if you get paid on the 1st and you're broke by the
  20th") so sending it to a friend says something about the sender. Instagram's head names sends per
  reach as a key signal (see `platform-signals-2026.md`).
- **Stickman staging.** The figure joins a small, recognisable group (people holding the same odd
  prop). The "send this to…" person is shown as a second figure.
- **Misuse.** Out-group animosity. It spreads, as Rathje et al. show, but it builds outrage, not
  trust. Blueprint rule: target an identity, never attack an out-group.

## 8. Deliberate mistake / intentional error (comment bait)

- **Mechanism (evidence split).** The *pratfall effect* is lab evidence that a **competent** person who
  makes a blunder becomes more likeable, while a mediocre one becomes less likeable. Aronson, Willerman
  & Floyd, *Psychonomic Science* 4, 227–228 (1966), DOI 10.3758/BF03342263
  ([abstract](https://paperity.org/p/59814503/the-effect-of-a-pratfall-on-increasing-interpersonal-attractiveness)).
  **Moderate, old, lab.** The tactic of planting a small error so viewers rush to correct it
  ("Cunningham's Law") is **creator lore**. I found no controlled study of it.
- **In a short video.** One small, harmless, **visual or trivial** slip (a miscounted prop, a misspelt
  sign in a post-production overlay, a figure counting "1, 2, 4") that sparks corrections in the
  comments without misleading anyone about the substance.
- **Stickman staging.** The figure confidently stacks blocks labelled with icons and puts one upside
  down. Or the figure "counts" three coins while four are visible. Keep it in the picture, never in a
  fact or number the video is teaching.
- **Misuse.** A wrong **fact** in an explainer, especially finance or health. That is misinformation,
  not bait. Blueprint rule: at most one per video, never in the claim, number or advice, and it is
  always flagged in the project notes so you know it is intentional.

## 9. Controversy vs polarisation

- **Mechanism.** Moderate controversy raises the chance people talk about something, but past a
  moderate level, more controversy **lowers** it, because interest rises while discomfort rises
  faster. Chen & Berger, "When, Why, and How Controversy Causes Conversation", *Journal of Consumer
  Research* 40(3), 580–593 (2013), DOI 10.1086/671465
  ([Penn repository](https://repository.upenn.edu/handle/20.500.14332/39527),
  [Wharton summary](https://knowledge.wharton.upenn.edu/article/finding-companys-controversy-sweet-spot/)).
  Polarising out-group content spreads, but that is the misuse described in §7. **Strong.**
- **In a short video.** A *contestable* take on an idea, not on people ("budgeting apps make most
  people spend more"), with a real split for viewers to argue about in the comments.
- **Stickman staging.** A balance scale. A split screen with two figures picking different doors. The
  Stage-5 discussion question is shown as two paths, with the figure pausing between them.
- **Misuse.** Rage bait, attacks on groups, or contrarian takes with no evidence. Papercut's "Verdict
  or conflict" pattern works only with a real split.

## 10. IKEA / effort-justification effect (saves)

- **Mechanism.** People value things they built themselves more, but **only when they finish**. When
  creations were destroyed or left incomplete, the effect disappeared. Norton, Mochon & Ariely,
  *Journal of Consumer Psychology* 22(3), 453–460 (2012), DOI 10.1016/j.jcps.2011.08.002
  ([Duke record](https://scholars.duke.edu/publication/861385),
  [Harvard DASH PDF](https://dash.harvard.edu/bitstream/handle/1/12136084/norton%20mochon%20ariely%20third%20round[1].pdf)).
  The related effort-justification finding: Aronson & Mills, *Journal of Abnormal and Social
  Psychology* 59(2), 177–181 (1959), DOI 10.1037/h0047195†. **Moderate. The link to saves is our
  inference.**
- **In a short video.** Give viewers a small, completable task to do later: a 3-step method, a
  fill-in-the-blank, a "try this tonight". Saves are the natural action for it.
- **Stickman staging.** The figure assembles a simple 3-piece machine across the video. The last piece
  clicks in at the payoff, and the finished machine is the "screenshot" frame.
- **Misuse.** Tasks too big to finish (the effect needs completion), or "save this" asks on content
  with nothing worth saving.

## 11. Parasocial address ("you" framing)

- **Mechanism.** Media figures who speak to the audience directly create an "illusion of
  face-to-face relationship". Horton & Wohl, "Mass communication and para-social interaction",
  *Psychiatry* 19(3), 215–229 (1956), DOI 10.1080/00332747.1956.11023049†
  ([citation](https://en.wikipedia.org/wiki/Richard_Wohl)). Generic "you" helps people normalise
  experiences and draw meaning from them (Orvell, Kross & Gelman, *Science*, 2017, "How 'you' makes
  meaning", [U-Michigan summary](https://prod.lsa.umich.edu/psych/news-events/all-news/faculty-news/faculty-graduate-student-research-spotlight.html);
  DOI not confirmed in my search). **Moderate**.
- **In a short video.** Say "you" in the first six words (yt hookscore ADDRESS) and use second person
  throughout. The off-screen narrator is a consistent, recognisable voice, which is why the director
  skill freezes the voice block.
- **Stickman staging.** The figure turns to camera on the key line, then goes back to the action
  (brief, not idle staring, which the skill bans). The viewer's "proxy" figure mirrors the viewer's
  problem.
- **Misuse.** False intimacy ("I made this just for you") or "you" sentences that accuse the viewer.
  An AI persona presented as a human financial expert is excluded from monetization on YouTube (see
  `platform-signals-2026.md`).

## Also relevant: arousal drives sharing

High-arousal emotions (awe, anger, anxiety) made New York Times articles more likely to be shared, and
low-arousal sadness made them less likely. Berger & Milkman, "What Makes Online Content Viral?",
*Journal of Marketing Research* 49(2), 192–205 (2012), DOI 10.1509/jmr.10.0353
([Wharton PDF](https://faculty.wharton.upenn.edu/wp-content/uploads/2011/11/Virality.pdf)).
**Strong (news articles; video is an inference).** For us: prefer awe and "aha" over doom. Anxiety
spreads but fits a stakes line, not a whole video.

## Honest limits

These are mechanisms about attention, memory and sharing. None of them proves that a given video
went viral *because* of a technique. The app's pattern labels are judgements about a transcript's
words, and the README says so.
