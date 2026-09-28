# PROJECT.md — MTG Counter, development notes

This file is for whoever (or whatever AI session) picks up development next.
`README.md` is the player-facing doc — how to run it, how to use it.
This file is the maintainer-facing doc — how it's built, why it's built that
way, and the conventions to follow so new features fit in cleanly.

## What this is

A life/mana/token counter for kitchen-table Magic. Each player runs it on
their own phone, all pointed at one host computer on the same wifi. It's a
personal project for a regular playgroup, not a product — optimize for "our
table's actual habits" over generality.

## Architecture

Three files do all the work, no build step, no framework, no dependencies
beyond the Python standard library. There are no third-party packages at
all any more, which is what lets the distributed bundle run on Python's
embeddable runtime (see Distribution below):

- **`index.html`** — the entire client. HTML, CSS, and JS all in one file,
  vanilla JS in an IIFE, ES5-ish style (`var`, function expressions — no
  arrow functions, no classes, no build/transpile step, so keep new code in
  that same style for consistency). Includes a small QR encoder (see the
  share modal section below).
- **`server.py`** — `http.server`-based. Serves `index.html` and anything
  under `assets/`, read off disk on every request (no caching), and
  nothing else in the folder (see "What the server will serve" below), plus
  a tiny JSON API (`GET/POST/DELETE /api/players/<id>`) backed by an
  in-memory dict (`PLAYERS`) guarded by a lock. Nothing is persisted to
  disk — restarting the server wipes the table. It also runs a small mDNS
  responder on a daemon thread so phones can reach the host as
  `mtg.local` (see the mDNS section below).
- **`start.bat` / `start.sh`** — launchers. `start.bat` prefers a bundled
  `python\python.exe` if one is sitting next to it, and falls back to a
  system Python otherwise, so the same file works in this source folder and
  in the distributed bundle.
- **`make-bundle.ps1` / `make-bundle.bat`** — build tooling, not part of the
  app. Produces the ready-to-run zip. See Distribution below.
- **`assets/`** — images the app loads. Currently just the goblin sprite
  sheet for the table pet. Art here has its own license, recorded
  in `assets/CREDITS.md`; anything added to this folder needs an entry there.
- **`tools/`** — standalone developer tools, not part of the app and not
  served by `server.py`. `tools/sprite-inspector/` auditions sprite sheet
  animations and exports a frame map; its README says how to run it.

There's no database, no accounts, no auth. Whoever's JSON hits the server
first with a given player id is "at the table."

## What the server will serve

`is_public_path()` in `server.py` is an allowlist: `/`, `/index.html`, and
files under `/assets/`, plus the two API routes. Everything else is a 404,
and directory listings are off. The check decodes and normalises the path
first, so `..` and its percent-encoded spellings can't climb out of
`assets/`.

This exists because the plain `SimpleHTTPRequestHandler` behaviour served
the whole folder, with listings, to anyone on the wifi: docs, tests, build
output, and whatever else someone keeps next to the app. Harmless at one
table, less so once other people unzip it wherever they like.

If the app ever needs another static file, put it in `assets/` rather than
widening the allowlist. `test_static.py` checks both directions (served and
refused) and should be re-run after touching the handler.

## The sync model — the most important thing to understand

Every player's browser holds its own full `state` object and is the source
of truth for that player. Two independent mechanisms move data around:

1. **`saveState()`** writes `state` to `localStorage` on that phone, so a
   page reload doesn't lose progress. This covers the *entire* state object
   automatically since it's just `JSON.stringify(state)`.
2. **`pushSnapshot()`** POSTs a *subset* of `state` to the server every time
   `saveState()` runs, and `fetchTable()` polls `GET /api/players` every
   1.5s (`POLL_MS`) to see everyone else's latest snapshot.

**Not everything in `state` is broadcast.** Look at the object literal
inside `pushSnapshot()` — only fields listed there reach other players.
Right now that's `name, accent, icon, life, startingLife, mana, tokens,
creatures, rollStatus`. Commander damage is the deliberate exception: it's
personal bookkeeping (damage *you've* taken from each opponent) and stays
local, never broadcast. **When you add a new stat, decide on purpose
whether it belongs in that snapshot object or not** — that's a real design
choice each time (see the Creature Counters section below for how that
question got worked through), not just an implementation detail.

A second, separate visibility layer exists on top of that: the Table view
shows a collapsed card per player (name, icon, accent, life) and an
expanded detail (mana, tokens, creature counters) that only renders once
someone taps the card open (`expandedIds`). So "broadcast" and "visible by
default" are two different decisions — something can sync to the table but
still stay tucked behind a tap.

## The mDNS responder (`mtg.local`)

`server.py` answers multicast DNS A-record queries for one name, so
players can type `http://mtg.local:8000` instead of an IP. It exists
because the QR code only helps if you can see the host computer's screen,
and the host PC is often in another room.

It is deliberately **not** a general Bonjour implementation. It answers A
queries for exactly one name and does nothing else: no service discovery,
no PTR/SRV/TXT records, no conflict probing before claiming the name. A
kitchen table doesn't need any of that, and each of those would be more
surface area to get wrong. If the name ever collides with another device,
the fix is `MTG_MDNS_NAME`, not a probing implementation.

Design points worth keeping if this gets touched:

- **Everything fails soft.** The numeric address always works, so an mDNS
  problem must never stop the game from starting. The thread sets
  `MDNS_STATUS` and `MDNS_READY`; `main()` waits up to 2s for that and
  prints either the extra address or the reason it's unavailable. A
  malformed packet from some other device on the LAN is swallowed and the
  loop continues.
- **The QR code still points at the numeric address, on purpose.** A QR is
  a "this definitely works" path and `.local` resolution isn't universal
  (reliable on iOS/iPadOS, varies on Android). Don't "simplify" the QR to
  the name.
- **Port 5353 is shared, not owned.** `SO_REUSEADDR` (plus `SO_REUSEPORT`
  where it exists) means we coexist with an existing Bonjour install,
  which Windows machines often have via iTunes, Adobe apps or printer
  software. Verified working with two responders bound simultaneously.
- **The group is joined on EVERY local interface** (`local_ipv4s()`),
  not just the one the default route points at, falling back to
  `INADDR_ANY` if none of them take. A Windows laptop routinely has wifi,
  ethernet and virtual adapters from VPN/VM/remote-desktop software;
  picking one and guessing wrong leaves the responder up but deaf, which
  is a miserable thing to debug. `MDNS_JOINED` records what it actually
  joined, and `test_mdns.py` prints it.
- **`MDNS_STATS` counts packets seen, queries matched, and answers sent.**
  It exists so that "mtg.local doesn't work" can be narrowed down without
  guessing: no packets at all means blocked inbound or the wrong adapter;
  packets but no queries means a parsing bug; answers sent but nothing
  received means something is eating the reply.
- **The IP is re-read, not captured once** (`get_lan_ip_cached`, 30s), so
  a laptop that changes networks mid-session still answers correctly.
- **Unicast replies go out before the multicast one**, as independent
  sends, so a multicast failure can't swallow the direct answer to a
  client that set the QU bit.
- Windows Firewall needs to allow Python on UDP 5353. That's the most
  likely reason for it to be silently unavailable on a fresh machine.

### Android does not resolve `.local`. Confirmed, settled, don't retry it.

Tested on a real Android phone on the same wifi with the responder
running and `test_mdns.py` fully passing: Chrome shows
`DNS_PROBE_FINISHED_NXDOMAIN`. That error is the tell — it means Android
sent `mtg.local` to the router's DNS resolver, got a definitive "no such
name" back, and never attempted mDNS at all. Android has mDNS in the
platform (`NsdManager`) but does not wire it into general hostname
resolution, so Chrome can't reach it. There is no client-side trick and
nothing the server can do differently.

So `mtg.local` is an iPhone/iPad convenience and the docs now say so
plainly rather than hedging with "varies by device". **Android's answer
is the share modal** — scan the QR, or get the link texted from a phone
that's already in. That's exactly the case it was built for, so the
feature set is complete; this is a limitation, not a gap.

Rejected, for the record, so nobody re-litigates them:

- **Running a DNS server on the host.** Phones ask the router for DNS,
  so this would mean changing the router's DHCP to hand out the host PC
  as the network's resolver. That hijacks all DNS for every device on
  the network to save typing an IP at a card game. Absolutely not.
- **A different suffix instead of `.local`.** Doesn't help. Android
  would still send it to the router's DNS and still get NXDOMAIN. The
  suffix isn't the problem; the resolver path is.
- **LLMNR / NetBIOS.** Windows speaks both, Android speaks neither.

What *would* work, and is documented in the README as worth a try
because it costs nothing: a router that registers DHCP client hostnames
in its own DNS (then the host PC's plain name resolves for everyone,
Android included), or a manual static host entry in the router pointing
a short name at the host. Both are router-dependent and out of this
project's hands, which is why they're user documentation rather than
code.

### Do not test this over loopback unicast

The first version of `test_mdns.py` sent its query to `127.0.0.1:5353`.
That passed on Linux and **failed on the Windows host**, and the feature
was fine — the test was wrong. When two processes share a UDP port,
Windows delivers an incoming *unicast* packet to exactly one of the bound
sockets and does not promise it will be yours; with Bonjour already on
5353, the query went to Bonjour, which ignored it. *Multicast* is
different: every socket that joined the group gets a copy, which is why
the real path works and the loopback shortcut doesn't.

So the live test sends to `224.0.0.251:5353` the way a phone does, and
the loopback unicast attempt is kept only as an `INFO` line. If you ever
see that INFO line report "unanswered" on Windows, that is expected and
means nothing.

`test_mdns.py` ships alongside the app (stdlib only, nothing to install).
Unlike the Playwright checks it's worth keeping in the folder, because
running it **on the Windows host** is the fastest way to find out whether
the responder actually binds there — if Windows Firewall is blocking UDP
5353, or something else owns the port, the live-socket section says so in
one line. It covers the wire-format helpers
(encoding, compression pointers, pointer loops, truncated labels,
case-insensitive matching, multi-question queries, ignoring AAAA and other
devices' names) and then runs the real responder and queries it over a
real socket. Re-run it after touching any of the parsing.

## The share modal and the QR encoder

Tapping "Show the join code" (sign-in screen) or "Invite" (Table section
header) opens a modal with a QR code, the address as selectable text, and
a `Text the link` button. The point is that the host PC is often in
another room: once one player is in, their phone is the join station for
everyone else.

- **There are two copies of the encoder**, one in `index.html` (JS, for the
  modal) and one in `server.py` (Python, for the console). `test_qr.py`
  asserts they produce identical matrices, so they cannot drift. The
  duplication is deliberate: it's what lets each side stand alone.
- **The QR encoder is written into `index.html` rather than pulled from a
  CDN.** The app has to work on a LAN with no internet — that's its whole
  premise — so an external script tag would break exactly when it matters.
  There's also no build step to bundle one with.
- **The Python copy replaced the optional `qrcode` package.** The bundle
  runs on Python's embeddable runtime, which ships without pip, so an
  optional dependency could never install there. Removing it also means the
  console QR now always works instead of only when a pip install happened to
  succeed.
- **Scope is narrow on purpose**: byte mode, EC level M, versions 1-3
  only. That caps the payload at 42 bytes, which comfortably covers every
  address this thing produces (`http://192.168.100.100:8000` is 27).
  Versions 1-3 are single-block at EC level M, so there's no block
  interleaving, which is most of the complexity of a general encoder.
  Over 42 bytes `qrMatrix()` returns `null` and the modal hides the QR and
  shows just the link — a real fallback, not an error state. If a future
  change needs longer payloads, adding version 4+ means adding block
  interleaving; don't just extend the version table.
- **The QR is black on white, never accent-themed.** Contrast is what
  makes it scan across a table at an angle.
- **The canvas is drawn at an integer module scale and never resized by
  CSS** (`scale = floor(232 / modules)`). A fractional scale makes some
  modules a pixel wider than others, which is what a camera at an angle
  struggles with.
- **The shared address comes from `GET /api/join`, not
  `window.location.origin`.** This matters: a player who joined by typing
  `mtg.local` would otherwise pass `mtg.local` on to an Android phone that
  can't resolve it. The server always hands back its numeric address, and
  offers `mtg.local` as a labelled alternative underneath. `location.origin`
  is only the fallback if the server doesn't answer.
- **The `sms:` href branches on iOS vs Android.** With no recipient
  number, iOS wants `sms:&body=` and Android wants `sms:?body=`. Getting
  it wrong opens an empty message, which defeats the button, so the
  user-agent sniff earns its place here.
- `navigator.share()` and `navigator.clipboard` are **not** options: both
  require a secure context and this is plain HTTP over a LAN. The address
  is rendered as a real `<a>` with `user-select:all` so long-press-to-copy
  works instead.

Nothing about this touches `state` or `pushSnapshot()` — it's a display of
the server's own address, not player data.

### OpenCV can't read some valid symbols. Don't "fix" the encoder for it.

`test_qr.py` used to fail on exactly one address, `http://192.0.2.2:8943`,
with OpenCV decoding it as an empty string. Chased it down properly, and the
encoder is fine:

- The canvas pixels matched the encoder's matrix exactly.
- Seven of the eight masks for that string decoded under OpenCV. The one
  that didn't happened to be the one ISO penalty scoring picks for that
  content.
- `qr_roundtrip.py`, an independently written decoder that shares no code
  with either encoder, reads all eight masks back correctly.
- Upscaling and extra padding didn't help, so it isn't resolution or quiet
  zone.

So the symbol is valid and OpenCV's detector simply can't find it. The
penalty implementation matches what mainstream encoders do (patterns checked
within the symbol, no quiet-zone padding), which means phone cameras have
been reading masks chosen this way for twenty years.

**Measured scope.** Swept 1,524 realistic LAN addresses
(`http://192.168.{0,1,2,4,10,68}.{1..254}:8000`). Every single one
round-trips correctly through `qr_roundtrip.py`, so the encoder is sound
across the whole address space this app will ever produce. OpenCV failed on
11 of them, 0.7%, and the failures land on masks 1, 2, 4 and 5. So it is not
a mask-specific fault and don't go looking for one; it's a data-dependent
quirk in that particular detector. Note that it can flip with DHCP:
`192.168.2.34` reads fine and `192.168.2.53` does not.

**Confirmed against a real camera** (2026-09-18): an Android phone scanned
the code for `http://192.168.2.34:8000` off the host console with no
trouble. Android's reader is Google's ML Kit, the most widely deployed QR
decoder there is, which is the evidence that actually matters. That address
lands on mask 2 and OpenCV reads it too, so the awkward 0.7% case has still
never been put in front of a phone.

The consequence for testing: **correctness is judged by `qr_roundtrip.py`,
not by OpenCV.** That decoder needs only the standard library, so `test_qr.py`
now runs anywhere, including the Windows host, and `test_share.py` reads the
QR back out of the canvas pixels rather than asking OpenCV. OpenCV is still
run when it's installed, but a failure there prints as INFO. If you ever see
that INFO count jump a lot, it's worth a look; a single entry is expected.

## Distribution

Two ways this goes out:

- **Source folder** (this one). Needs a Python on the machine. This is what
  development happens in.
- **Ready-to-run bundle**, built by `make-bundle.bat`. Downloads Python's
  Windows embeddable package (~10MB: runtime and stdlib, no installer, no
  registry, no PATH), verifies its SHA-256 against the value pinned in
  `make-bundle.ps1`, unpacks it into `python\`, and zips the app around it.
  The recipient extracts and double-clicks. Nothing is installed; deleting
  the folder is a complete uninstall.

Notes for whoever touches this next:

- **The bundle can't be emailed.** Gmail blocks `.exe` attachments, including
  inside a `.zip`, including inside `.gz`/`.bz2`, and it rejects
  password-protected archives specifically so you can't route around it. It
  goes out as a file attached to a GitHub release, and the zip itself is
  git-ignored.
- **What goes in the bundle** is `$AppFiles` and `$AppDirs` in
  `make-bundle.ps1`: the app, the launcher, README, LICENSE, and `assets/`
  whole (its `CREDITS.md` has to travel with the art). PROJECT.md, tests and
  `tools/` stay out.
- **PyInstaller was considered and rejected.** An unsigned one-file exe trips
  SmartScreen ("Windows protected your PC"), which is a scarier moment for a
  non-technical recipient than a Python installer and teaches the wrong
  instinct. Packed exes also draw antivirus false positives. Signing fixes
  SmartScreen and costs a few hundred dollars a year, which is absurd here.
  The embeddable runtime is a signed python.exe straight from python.org and
  avoids all of it.
- **Bumping the Python version** means changing `$Version` *and* `$Sha256` in
  `make-bundle.ps1` together. The checksum is on that release's page at
  python.org. The script aborts on a mismatch rather than bundling something
  that isn't what python.org published; don't weaken that.
- 3.13 rather than the newest 3.14 on purpose: nothing here needs 3.14, and
  the bundle can't be tested from the dev environment, so the
  more-exercised branch is the right hedge.
- `start.bat` leads its failure message with "did you actually extract the
  zip", because browsing inside a zip without unpacking is the single most
  common way this goes wrong on Windows.

### Never test for Python with `where python` on Windows

This bit us on a clean machine. Windows ships a stub named `python.exe` (an
"App execution alias", under WindowsApps) that is **on PATH even when Python
is not installed**. Run it and it prints:

    Python was not found; run without arguments to install from the Microsoft
    Store, or disable this shortcut from Settings > Apps > Advanced app
    settings > App execution aliases.

`where python` finds that stub and returns success. The old `start.bat` took
that as "Python is here", ran the stub, and jumped straight to its exit —
so the fallback to `py` never ran and the person never saw our own error
message explaining what to do. It looked like the launcher was broken.

`:probe` in `start.bat` now checks two things per candidate: that the name
exists (`where`, purely to keep "not recognized" noise off the screen), and
that running it actually reports a version starting with `Python 3`. The stub
says "Python was not found", which deliberately does not match, and a Python 2
install is correctly rejected by the same test. `py` is tried before `python`
because the launcher is a real executable and is never aliased.

If you ever touch the Python-detection logic: presence on PATH is not
evidence that something runs.

### The Windows blind spot

Development and automated testing have happened on Linux, with no way to
run anything on Windows from there. Every Windows-specific assumption in this project has to
be verified by a human running it, and two have already been wrong in ways
every automated check passed: the mDNS loopback test (see above) and the
`where python` stub. Assume the next one is lurking too. The only real gate
on the distributed bundle is extracting it on a machine that has never had
Python installed and double-clicking it.

**That gate has been passed** (2026-09-18): the bundle built by
`make-bundle.bat` was extracted and run on a separate Windows machine with no
Python installed, and the server started. The embeddable-runtime approach is
confirmed working end to end, not just in theory.

## State shape (`defaultState()`)

```js
{
  started, name, startingLife, life, accent, icon,
  mana: {W,U,B,R,G,C},
  tokens: [{id, name, count}],             // named, broadcast, no cap
  creatures: [{id, power, toughness}],     // unnamed, broadcast, each axis independently
                                            // signed/negative (e.g. -1/-1, or asymmetric +1/+0)
  commanderDamage: {}                      // opponentId -> {name, accent, amount}, LOCAL ONLY
}
```

`loadState()` merges saved JSON over `defaultState()`, so adding a new field
to `defaultState()` is enough for old saved games to pick up the default
value — no migration code needed. Keep doing it that way.

**Live-sync backward compatibility is a separate concern from local
migration.** `creatures` used to be `{id, count}` (a single net value); it's
now `{id, power, toughness}`. `migrateCreatures()` upgrades a player's own
saved `localStorage` state on load, same as always. But because this app
polls *other players' live devices* over the network (`latestPlayers`), a
shape change like this also has to keep reading data broadcast by anyone
who hasn't refreshed to the new code yet — that's a second, independent
compatibility surface a purely-local app wouldn't have. `creaturePT(c)` is
the defensive reader for that: it accepts either shape and always returns
`{power, toughness}`, falling back to a symmetric reading of the old
`count` field. **Anything that reads creature data from `latestPlayers` /
broadcast (as opposed to `state.creatures`, which is always the current
shape after `loadState()`) must go through `creaturePT()`, never touch
`.count` or assume `.power`/`.toughness` exist directly.** The next time a
per-creature (or similarly shared) data shape changes, follow this same
two-part pattern: a `migrate*()` for your own saved state, and a defensive
reader for anything coming from another device's snapshot.

## Established UI patterns — reuse these, don't invent new ones

- **Collapsible section**: a `<button class="section-toggle">` in the `<h2>`
  toggling a `.hidden` class on a wrapper div, backed by a `localStorage`
  boolean (see `CMDR_COLLAPSED_KEY` / `MANA_COLLAPSED_KEY` and their
  `apply*Collapsed()` functions). Commander Damage defaults collapsed, Mana
  Pool defaults open — default to whichever state a section is *usually*
  in for a normal game.
- **Modal**: `.modal-backdrop.hidden` wrapping a `.modal`, toggled by adding
  removing `.hidden`. Used for anything that's a rare, deliberate action
  (icon choice, dice roll, rename) — not for anything adjusted repeatedly
  mid-turn. That distinction came up explicitly when deciding *not* to put
  Creature Counters behind a modal-to-create — creation needed to be a
  single tap on the main screen, not a modal open/close, because it happens
  often during a game.
- **Repeating row/chip list with add + remove**: tokens (`.token-row`) and
  creature counters (`.creature-chip`) both follow: an `xUid()` id
  generator, an array on `state`, a `render*()` function that clears and
  rebuilds the DOM from the array, `+`/`−` handlers that mutate then call
  `saveState()` + `render*()`, and a `✕` delete handler that filters the
  array by id. Copy this pattern for the next repeating-thing feature
  rather than reinventing it.
- **Empty hint**: `.empty-hint.hidden` shown/hidden alongside the list, one
  italic sentence telling the player what to do.
- **Accent theming**: never hardcode a player's color. `applyAccent()` sets
  `--accent` and, via `lightenColor()`, `--accent-light` as CSS custom
  properties on `<html>`; everything else references `var(--accent)` /
  `var(--accent-light)`. Don't add a new hardcoded hex for "the accent
  color, but lighter" — use `lightenColor()`.
- **Touch targets**: buttons that get tapped repeatedly during play
  (mana/token/creature/commander +/−, section toggles) should be at least
  ~36–40px. This was a deliberate fix this round after the originals ran
  smaller; don't regress it for new repeating controls.
- **Defeat detection** (`isDefeated()`) currently checks life ≤ 0, a token
  literally named "Poison" reaching 10, or 21+ commander damage from one
  opponent. It's visual-only (grays out the card, no hard lock). If a new
  stat should ever contribute to defeat, it goes here — but note this is a
  bookkeeping *hint*, not enforcement, on purpose.

## Testing

Five test scripts ship in the folder. All are stdlib or
already-installed-deps only, and all are meant to be run by hand:

- **`test_static.py`** — the static-file allowlist. Starts its own server
  on a spare port, checks the app and every file in `assets/` are served,
  and that docs, tests, tools, directory paths and traversal attempts all
  404. Standard library only.
- **`test_mdns.py`** — the mDNS responder (see above). Run it on the
  Windows host to find out whether the responder actually binds there.
- **`test_qr.py`** — both QR encoders. Round-trips them through
  `qr_roundtrip.py` and asserts the JS and Python matrices are identical.
  Standard library only, so this one runs on the Windows host too; node and
  OpenCV are used if present and skipped if not. Re-run it after touching
  either encoder.
- **`qr_roundtrip.py`** — the independent decoder the tests judge by. It
  deliberately does not reuse the encoder's placement code, because reusing
  it would let a placement bug cancel out and pass.
- **`test_share.py <port>`** — Playwright end-to-end for the share modal,
  including reading the QR back out of the live canvas pixels. Takes a port;
  use a fresh one (see below).
- **`test_tabletop.py <port>`** — Playwright end-to-end for Tabletop View
  and power/toughness counters, with two browser contexts as two players:
  symmetric and per-axis adjustment, the counter reaching the other
  player's Table card and Tabletop seat, drag-to-seat snapping and
  persistence, and loading an old `{id, count}` save. Takes a fresh port.
- **`test_pet.py <port>`** — Playwright end-to-end for the table pet. One
  player watches Tabletop View while the other loses life and goes out.
  Reads the goblin's sheet frame back from its `background-position`, so
  it checks what's on screen without test hooks: one swing per burst of
  taps, none for a −3/+3 wash, a 4–5s fall, swings dropped while it's
  down, and the loop stopping outside Tabletop View. Takes a fresh port;
  it runs about 40s because the settle and fall timings are real.

Playwright runs against a locally-running `server.py`, with
`args=['--no-sandbox']`. The Playwright tests use the Chromium at
`/opt/pw-browsers/chromium` when that exists (the dev container this was
built in) and Playwright's own browser otherwise. A few hard-won
gotchas worth not re-learning the hard way:

- **Always restart the server on a fresh port before a test run.** The
  in-memory `PLAYERS` dict isn't cleared between runs, so reusing a port (or
  even reusing player names on the same port) picks up "ghost players" from
  a previous run — most often shows up as icon-uniqueness checks failing or
  a second player unexpectedly already existing.
- **Combining `pkill`/process-killing with other commands in one bash call
  intermittently produces exit code 144** in this environment. Kill the
  server as its own isolated command, then run the next command
  separately.
- **`page.click(..., force=True)` does not fire on a genuinely disabled
  native `<button disabled>`** in Chromium — force only bypasses
  visibility/actionability checks, not the browser's native disabled-click
  suppression. Test the real enabling condition instead of forcing through
  it.
- Multi-context tests (`browser.new_context()` per simulated player) are
  the way to test broadcast/sync behavior — single-page tests can't catch
  cross-player bugs.
- **Once a component renders into more than one place on the page** (e.g.
  creature-chip markup now renders into both `#creatureList` and
  `#ttSelfCreatures`), any selector built on that component's class alone
  (`.creature-chip.add button`) becomes ambiguous — Playwright will resolve
  it against whichever match it finds, which may be the hidden copy, and
  fail with a confusing "element is not visible" timeout rather than a
  clear "multiple matches" error. Scope the selector to the specific
  container id (`#creatureList .creature-chip.add`) instead. This already
  bit the older creature-counter tests once Tabletop View reused the same
  chip markup — worth checking for on every future shared-component change.

## Seeing a change on the host

The server reads files fresh off disk on every request (no caching), so
once changed bytes are actually on disk, a plain browser refresh is enough;
no server restart needed for HTML/CSS/JS changes. A restart *is* needed
only if `server.py` itself changed, or to clear the in-memory player table.

If you edit on one machine and copy files to the host, check the copy
landed (size, hash, or grep for something unique to the change) before
testing on phones. A sync that reported success while the old file was
still on disk has already cost a debugging session here.

## Feature history (context for "why does it work this way")

Roughly in build order, for context on decisions already made:

- Life counter with tap-zones (±1 per side) and quick ±1/±5 buttons, undo
  (one step back).
- Mana pool (WUBRG + Colorless), collapsible, defaults open. A compact
  numbers-only summary lives under the life total regardless of whether the
  full pool is expanded, so you're never missing your own pool at a
  glance.
- Tokens: named, freeform, quick-add chips for common types
  (`QUICK_TOKENS`) plus custom text entry. Common types get a fixed dot
  color (`TOKEN_COLORS`) so they're visually distinct; anything custom uses
  the player's accent color. (Section was originally "Tokens & Counters" —
  renamed once Creature Counters became its own section, since "Counters"
  no longer described anything living here.)
- The Table: shared view of everyone else, collapsed card (icon/name/life)
  by default, tap to expand for mana/tokens/creature counters. "Away" tag
  after 8s (`AWAY_SECONDS`) without a poll.
- Commander Damage: per-opponent row, **local only, not broadcast** —
  personal bookkeeping. Collapsible, defaults collapsed (not every game is
  Commander).
- Dice/coin roller: the one thing that's broadcast as a transient event
  rather than steady state (`rollStatus`), shown as a fading banner on both
  the roller's own screen and everyone else's Table card.
- Icon picker: 6 fixed icons, table-wide uniqueness enforced at setup time
  by querying `/api/players` before the player has joined the table.
- Per-player accent color + `lightenColor()` for a derived light variant,
  applied everywhere via CSS custom properties rather than hardcoded per
  swatch.
- Ready-to-run Windows bundle: Python's embeddable runtime shipped
  alongside the app so the recipient installs nothing. Drove the removal of
  the last third-party dependency (`qrcode`), which was replaced by a Python
  port of the encoder already in `index.html`.
- Share modal: a QR code and a `Text the link` button on both the sign-in
  screen and the Table header, so whoever's already playing can get the
  next person in without anyone walking to the host computer. Backed by
  `GET /api/join` so the address shared is always the one that resolves.
- `mtg.local`: an mDNS responder in `server.py` so the join address can be
  spoken across a room instead of read off the host's screen. Chosen over
  the alternatives (relying on the Windows hostname, which is inconsistent
  from phones; a fixed router IP plus a printed QR, which is still worth
  doing and is documented in the README).
- Static allowlist and public repo: the server stopped serving the whole
  folder (see "What the server will serve"), the sprite sheet moved into
  `assets/` with its CC-BY credits, and the project got an MIT license.
- Creature Counters: unnamed counters, 2–3 typical per player, broadcast to
  the table but tucked behind the same tap-to-expand as mana/tokens (not on
  the collapsed card) — deliberately lower-touch than Tokens (no name
  field, default value on add) because these get created and adjusted much
  more often mid-turn. Started as a single net scalar (symmetric +N/+N or
  -N/-N only), then became full independent power/toughness
  (`{id, power, toughness}` — see the State Shape section above for the
  backward-compat story). Display is always the full "+P/+T" text (e.g.
  "+2/+3", "-1/-1", "+1/0") via `formatSigned()` (a leading "+" only when
  positive; "0" and negative values print their own sign) — each half
  rendered as its own `<span>` so it can be colored a warning color
  independently when negative (`fillPTSpans()`, reused by the interactive
  chip, the read-only Tabletop chip, and nowhere else needs it since the
  Table-card summary is plain text). Interaction is two-tier to keep the
  common case fast: collapsed, the chip shows the text plus one symmetric
  +/− pair that moves both power and toughness together (covers ordinary
  +1/+1 and -1/-1 counters in one tap); tapping the "+P/+T" text itself
  toggles a per-chip expanded state (`expandedCreatureIds`, in-memory only,
  mirrors the `expandedIds` pattern used for Table cards — never persisted
  or broadcast) which swaps in two independent PWR/TGH rows, each with
  their own +/−, for the asymmetric case, and the chip only grows wider
  while expanded so it stays visually minimal at rest.
- Tabletop View: a second, condensed rendering of the same live state, not
  a separate mode of the app. Your life card becomes a fullscreen `.tt-self`
  box (content bottom-anchored, same tap-left/right ±1 as the standard life
  card, creature counters shown with the exact same chip markup/behavior as
  the standard screen — see `renderCreatureListInto()`, which renders into
  both `#creatureList` and `#ttSelfCreatures` from one chip-builder so the
  two stay identical by construction). Opponents render as small read-only
  `.tt-player` cards (name, life, creature counters only — no mana/tokens,
  and no Commander damage since that's local-only and never reaches another
  device's `latestPlayers` anyway) positioned at one of 12 fixed compass
  slots (`TT_SLOTS` — expanded from an original 8 once playtesting found
  the layout cramped along a phone's long/vertical axis; the extra 4 slots
  are hi/lo points along the left and right edges specifically, not more
  N/S density) around the arena, snapped-to via drag (pointer events, see
  `attachTabletopDrag()`), not freely placed — that was a deliberate choice
  over free placement, revisit only if playtesting wants it looser. While a
  drag is in progress, `showSnapMarkers()` renders a dashed marker at every
  slot in `#ttSnapMarkers` and `updateSnapMarkerHighlight()` highlights
  whichever one is nearest the pointer on every move, so it's obvious where
  a card will land before you let go; `hideSnapMarkers()` clears them on
  drop. Both the on/off mode (`TABLETOP_MODE_KEY`) and the seating layout
  (`TT_POSITIONS_KEY`, keyed by opponent player id) are local-only, never
  part of `pushSnapshot()` — this is your own read of the physical table,
  not something to sync to anyone else's phone. A render guard
  (`ttDraggingId`) skips rebuilding the opponents' DOM while a drag is in
  progress, since the 1.5s poll would otherwise yank a card out from under
  an in-progress drag. Note: changing `TT_SLOTS`'s index scheme (as the
  8→12 expansion did) silently re-maps any already-saved
  `TT_POSITIONS_KEY` indices to different physical spots — not a crash,
  just a one-time "huh, everyone moved" the next time someone opens
  Tabletop View after an update like this; worth a heads-up if it ever
  matters for real usage, not just dev testing.
- Tabletop View, round 2 — defeated indicator + creature-row overflow fix:
  playtesting surfaced two issues once real games actually got to a
  defeated player and a heavily-countered creature.
  - **Defeated indicator**: `.tt-self` and `.tt-player` previously only
    dimmed via the `defeated` class's `filter:grayscale()/brightness()` —
    same mechanism as the standard screen's card, but the standard screen
    also has an explicit "☠ Defeated" text tag, and Tabletop View didn't.
    Added a `.tt-defeated-stamp` (🪦 icon + jagged small-caps label,
    rotated like a stamp) — one copy hardcoded into `#ttSelf`'s markup
    (shown via `.tt-self.defeated .tt-defeated-stamp{display:flex}`), and
    one built into every opponent card's template string in
    `renderTabletopOpponents()` (shown the same way off the card's own
    `.defeated` class). No new JS state — it's pure CSS visibility keyed
    off the class that was already being toggled by `isDefeated()`.
    The player-card version is deliberately positioned at `top:40%` (not
    50%) so its rotated badge sits over the life number rather than
    bleeding into the creature-counter rows below it — worth rechecking
    that offset if the card's internal layout changes again.
  - **Creature-row overflow on edge-positioned cards**: `.tt-player` had
    only `min-width:104px`, no `max-width`. Since it's absolutely
    positioned with only `left`/`top` set (no `right`), the browser's
    shrink-to-fit width algorithm sizes it based on the *available space
    from its anchor point to the containing block's far edge* — which is
    huge for a card anchored near the left edge and tiny for one anchored
    near the right edge. That's why a row of 4 creature chips used to stay
    on one line (and run off-screen, clipped invisibly by
    `#tabletopView`'s `overflow:hidden`) on the left, but wrapped to 2×2
    (and looked fine) on the right — the same content, wrapping
    differently, purely from which edge it was closest to. Fix: added
    `max-width:130px` to `.tt-player`, which caps it consistently
    regardless of anchor position, so the same content always wraps the
    same way everywhere. Also nudged the lateral `TT_SLOTS` values in a
    bit further from the true edge (17/18 and 82/83 instead of 14/16 and
    84/86) as a safety margin so a maxed-out card centered on those slots
    doesn't still clip. If chips ever need to grow (e.g. wider text, more
    per player), re-check this max-width and the slot margins together —
    they were tuned as a pair against a 390px-wide test viewport, not
    derived from a formula.
- Rejoined fork: on Sep 12–13 development split. One line added Tabletop
  View and power/toughness counters, the other (started from an older copy)
  added the share modal, QR, `mtg.local` and the bundle. Only half of each
  reached the host folder, so for a while the running app had Tabletop View
  but no share modal while the docs described the reverse. Merged back into
  one `index.html`; `test_tabletop.py` and `test_share.py` together cover
  both lines so a repeat shows up as a test failure.
- Table pet: a goblin (`#ttPet`, the "Table pet" section of the script)
  that wanders the Tabletop View arena, swings when anyone loses life and
  falls down when anyone goes out. Decisions worth keeping:
  - **Not synced, on purpose.** The earlier plan was a shared seed plus a
    behaviour state so every phone showed the same goblin in the same spot.
    Dropped once "roughly the same" was judged fine: each phone wanders its
    own goblin, and reactions come from `petObserve()` diffing life and
    `isDefeated()` against the last observation. That data already reaches
    every phone, so the goblins react at roughly the same moments with no
    server change and no new snapshot field. Don't add sync unless someone
    actually wants identical positions.
  - **One swing per burst.** Every change restarts a per-player 2s timer
    (`PET_SETTLE_MS`, deliberately longer than `POLL_MS` so an opponent's
    burst split across two polls is still one swing). It only swings if
    the player is still below where the burst started, so a mis-tap and
    correction does nothing. A fall cancels that player's pending swing,
    and swings are ignored while the goblin is down.
  - **The first sighting of a player only records a baseline**, so joining,
    reloading or opening Tabletop View never sets anything off. Life going
    up (undo, reset, new game) is never a reaction.
  - **Tabletop View only**, and the animation loop runs only while it's
    open (`petStart()`/`petStop()` from `applyTabletopMode()`). Reactions
    that come due while it's closed are dropped, not queued.
  - **On by default, off per phone.** The 👺 button in Tabletop View's
    top-right corner (`PET_ENABLED_KEY`, local-only like the Tabletop mode
    flag). It's icon-sized on purpose: a full "Goblin: on" label reached
    into the top of the +1 tap zone, and `test_tabletop.py`'s +1 tap landed
    on it. Keep anything added to that corner as small.
- One server per port on Windows: `ThreadingHTTPServer` used to set
  `allow_reuse_address`, which on Windows lets a second server bind a port
  that's already being listened on, silently. Double-clicking `start.bat`
  twice gave two servers on :8000 with two separate tables, and phones
  split between them at random. Windows now binds with
  `SO_EXCLUSIVEADDRUSE`, so the second copy fails with a plain message
  saying the counter is probably already running. Verified that a
  restart straight after stopping still binds. `start.bat` passes its
  arguments through, so `start.bat 8001` picks another port.
  - **Rendering** is a CSS sprite: one 72×64 cell as a background, scaled
    2× with `image-rendering:pixelated`, `pointer-events:none` so it never
    blocks the life tap zones, z-index 1 so it walks behind opponent cards.
    `PET_OFFSETS` is a per-frame table that moves each frame's legs anchor
    to x=36 and feet to y=58, because the artist drew forward travel inside
    each cell. It's the same correction the sprite inspector computes;
    regenerate it if the sheet changes.
  - **Sheet layout, confirmed at 3× on this build** (the earlier handoff
    readings of rows 0 and 2 were backwards): row 0 faces the viewer, row
    1 faces right, row 2 faces away, row 3 faces left. Every one of those
    rows is an 8-frame walk then a 3-frame attack (`PET_ROWS`). Row 4
    (44–48) is stand, crouch, tumble onto its head, used for the fall and
    played in reverse to get up. The swing faces the player who lost life:
    toward their seat, or down toward you for your own life.

## Conventions checklist for the next feature

- Does it need its own `*Uid()` id generator + array on `state`, or is it a
  single value? Follow the existing pattern for whichever shape it is.
- Does it belong in `pushSnapshot()` (shared with the table) or stay local
  like Commander damage? Decide this explicitly, don't default to
  broadcasting everything.
- If shared, does it need to be visible on the *collapsed* Table card, or
  is tap-to-expand fine? Only put something on the collapsed card if
  knowing it matters to *other* players' decisions in the moment (this is
  why Creature Counters stayed behind the tap and life/name/icon didn't).
- Add the field to `defaultState()` with a sensible default — no migration
  step needed beyond that.
- New buttons that get tapped repeatedly mid-game: keep them ≥ ~36–40px.
- New collapsible section: default it open or closed based on how often a
  *typical* game at this table actually uses it, not a generic default.
- After building: run (or write) a Playwright check for it, verify with a
  fresh server per the gotchas above, then update `README.md` (player-
  facing) and this file (if the pattern or workflow itself changed).
