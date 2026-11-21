# Technical test — backend engineer

Welcome! This test mirrors how we actually work: an existing codebase, a
feature to ship, and AI agents as part of the toolbox.

**AI agents (Claude Code, Cursor, Copilot, ...) are explicitly encouraged.**

**Time budget:** 2–3 hours. If you hit the limit, submit what you have with
honest notes on what's missing. **Expected setup:** the [README](README.md)
quickstart should have everything running in under 10 minutes; if it doesn't,
something is wrong on our side — tell us.

## Deliverables

1. **One merge request** against `master`, implementing the task below.
2. **Design notes** in the merge request description: the scope you settled
   on, the decisions that mattered, and what you left out.
3. **Your agent transcript(s)**: export or copy the full conversation(s) you had
   with your agent(s) into a `transcripts/` directory. Unedited, including the
   dead ends.

Before you submit: `make lint typecheck test` green locally.

## The task — discount codes

Here is the brief, in full, as we got it:

> *"Sales channels want to be able to run promotions — let people use a
> discount code when they book. Codes shouldn't be usable more times than we
> agreed with the partner."*

That is all we know. What it commits us to, and what is out of scope, is yours
to decide — say so in the design notes.

## The debrief

There is nothing to write up beyond the above. In the follow-up interview we
go through this codebase with you, screen shared, and expect you to explain how
it works — the code you wrote and the code around it.

**Expect questions on the code you were given, not only on your own.** They
have no particular focus: any part of the codebase is fair game, from how a
request becomes a booking to how the test suite is set up. Budget some of your
time to read the codebase before you change it — the main workflow (search,
booking, expiry) and the tests included — rather than spending all of it on
the task.
