# Roadmap

What's planned, in what order, and why that order. No dates. This is a personal
project and the ordering matters more than any schedule.

The session handoff notes hold current session state and stay out of the repo. This
file holds everything past the current session. When an item ships, move it to the
feature history in `PROJECT.md` with the reasoning attached and delete it here.

## Ordering principle

Two things drive the order below.

The sync model only knows how to do per-player state. Every stat today is owned by
one player's browser and broadcast through `pushSnapshot()`. Anything table-level
needs an answer to who owns it, and that answer is currently missing.

The server holds nothing between games. Its player table is in memory and does not
survive a restart. Anything that remembers across games needs that to change.

Work that needs neither of those is cheap. Work that needs one is a real project.
Work that needs both goes last.

---

## Now: table-wide designations

Monarch, initiative, city's blessing, day/night. All four are single-holder states
that the whole table needs to see.

This is where the sync model runs out. Every existing stat has a natural owner.
A designation only one player can hold does not, and the obvious workaround of
letting one browser hold it raises the question of what happens when two people tap
at the same moment.

A coin flip resolves a tie at the table, which is fine for play. It is not an answer
for the code, because the same question comes back immediately with the turn tracker.

- [ ] Decide how table-level state is owned and how conflicts resolve
- [ ] Monarch and initiative first, since those come up most
- [ ] Day/night and city's blessing after, same mechanism

Worth solving this properly rather than special-casing monarch, since the next item
depends on the same answer.

## Then: turn tracker

Whose turn it is, plus a turn counter. Blocked on the designation work above, and
only worth building once that question has a real answer.

Deliberately not included: per-player turn timers or a chess clock. Some groups love
them, some find them hostile, and this one hasn't asked.

## Later: persistence, then history

The two features that would make the app worth using over months are a game log and
win/loss records by player and deck. Both need the server to remember things between
games, which it currently does not.

- [ ] Decide what persistence looks like. A file on disk is probably enough; this is
      a kitchen-table app and the playgroup is small
- [ ] Game log: life totals over time, so "how did I get to 14" is answerable
- [ ] Win/loss by player and deck

Ordering within this block matters. The log is a byproduct of persistence and comes
nearly free once it exists. Win/loss records need player identity that survives a
session, which is a bigger question than it sounds: right now a player is whoever
opened a browser.

---

## Not planned

Things considered and set aside, recorded so they don't get re-litigated.

| Item | Why not |
| --- | --- |
| Planechase, Archenemy, two-headed giant | Niche unless the group actually plays them. Revisit if that changes |
| Turn timers and chess clocks | Changes the feel of the table. Nobody has asked |
| Storm count, spells cast this turn | Too transient to be worth a control that has to be reset constantly |
| A framework or build step | The single-file, no-build constraint is deliberate. Anything needing a bundler is the wrong answer here |
