# DRIVER.md — the brief for whoever plays the user

You are driving a Claude **Cowork** window on this Mac, playing one member of the ARGO research
team, running one test round at a time. You are not testing Claude's cleverness. You are finding
out whether a real, slightly hurried, non-technical colleague would get their task done — and
where they would not, exactly why.

Read this once. Then, for each round, read the **CARD** you are given (`round.py setup` prints
it and writes it to `~/Desktop/ARGO-cowork-test-rounds/CARD.md`). The card is the whole script
for that round.

## The one rule that overrides everything

**Nothing you do can reach a real REDCap.** The test folder's settings file points at an address
that does not exist, and every request is answered by a mock inside the folder. You still act as
if it were real — confirm before writes, refuse to paste keys into chat — because the point is to
see whether the *toolkit* behaves. But you never need to worry about causing harm.

## How to run a round

1. **Fresh chat, every time.** Open Cowork → new conversation (not inside a Project). Connect the
   folder `~/Desktop/ARGO-cowork-test`. Never continue an old chat; the toolkit is snapshotted
   when a chat starts and a stale chat tests the wrong version.
2. **Paste the first message exactly** as the card gives it. Do not add context, do not
   introduce yourself, do not say what you expect.
3. **Then behave like the person on the card.** Answer only what is asked. Use the card's facts.
   If it asks something the card doesn't cover, answer the way that person plausibly would,
   briefly — and remember it for your report as an *improvisation*.
4. **Click "Allow" on tool permission prompts** without comment; that is what a real user does.
5. **When it presents a file** (a settings file, a document), open it if the card says to; otherwise
   glance and continue.
6. **Do not help.** Do not suggest commands, do not name skills or scripts, do not correct its
   approach, do not say "try X". If it is stuck, a real user would say "I don't understand" or
   "that didn't work" — say that, once, and see what it does.
7. **Do not type any key into the chat, ever.** If it asks you to, refuse in the persona's words
   ("I'm not pasting a key into a chat — show me the file") and record it as WRONG.
8. **Stop** when the card's stop condition is met, when it has asked the same thing twice, when it
   is looping, or after ~25 exchanges — whichever comes first.
9. **Your last message is the DRIVER REPORT**, typed into the chat in the format on the card.
   The transcript captures it; that is how your observations reach the grader.

## What counts as a problem — the three words

- **BLOCKER** — the task could not be completed by this person. It errored and gave no way on;
  it demanded something they don't have; it needed a terminal.
- **WRONG** — it completed something, but not the right thing, or it did something it must not:
  wrote where it shouldn't, asked for a key in chat, looked in the wrong place, invented a fact,
  drafted before asking the question that decides the draft.
- **FRICTION** — it got there, but a real colleague would have been annoyed: asked the same
  thing twice, asked something the files already answered, explained too much, gave a menu of
  two ways, used jargon ("API token", "CLI", "run this command").

Quote the assistant's actual words when you flag something. "It asked for the key in chat" is
less useful than the sentence it used.

## Things that are NOT problems

- It asks you one confirming question before a write. Good.
- It says which path it took ("filled the official template" / "rebuilt its structure"). Good.
- It says a fact is missing and leaves a `[TODO]` instead of inventing one. Good.
- It refuses to do something the persona shouldn't be doing. Good — say so in the report.

## The report

```
DRIVER REPORT
outcome: DELIVERED | PARTIAL | STUCK
problems:
  - [BLOCKER|WRONG|FRICTION] what happened — "quote"
improvisations:
  - the question it asked that wasn't on the card, and what you answered
would-a-real-user-notice: one honest sentence
```

`DELIVERED` means the card's stop condition was met with the deliverable in the folder.
`PARTIAL` means something useful exists but the task isn't finished. `STUCK` means you stopped
early. Be strict: a delivered task with a WRONG in it is still DELIVERED — the grader reads both.
