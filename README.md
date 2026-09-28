# MTG Counter

A life, mana, and token counter for Magic: the Gathering, built to run on
your own wifi so every player can use their own phone as their own
counter, no app install required — and see everyone else's stats too.

## How it works

One computer (yours) runs a tiny local web server. Everyone at the table
connects to that computer's address from their own phone's browser, over
the same wifi network — by scanning a QR code printed in the console, or
by typing in `http://mtg.local:8000`, a nickname the server answers to so
nobody has to read an IP address off a screen in another room.
Each phone runs its own independent counter — but life, mana, and tokens
sync live to the server, so everyone at the table can see everyone
else's current stats too, right on their own screen.

Works for 1 to 4+ players; each person just needs a browser.

This started as a counter for one regular playgroup and is shared as-is
for friends who asked. It's tuned to how that table plays, not built as a
general-purpose product.

MTG Counter is an unofficial fan project. It is not affiliated with,
endorsed by or sponsored by Wizards of the Coast. Magic: The Gathering is a
trademark of Wizards of the Coast LLC.

## Running it (Windows)

You need a 64-bit Windows 10 or 11 computer on the same wifi as the phones.

The easiest way is the **ready-to-run** download: grab
`MTG-Counter-Windows.zip` from the
[latest release](https://github.com/klingea1/mtg-counter/releases/latest).
There's nothing to install:

1. Right-click the zip, choose **Extract All**, and open the extracted
   folder. Don't skip this — Windows lets you look inside a zip without
   unpacking it, and nothing will run from in there.
2. Double-click **start.bat**.
3. Windows will probably warn you, because the file came from the
   internet and isn't signed by a company. If you see **"Windows
   protected your PC"**, click **More info**, then **Run anyway**. If you
   see **"Open File – Security Warning"**, click **Run**. This happens
   the first time only.
4. A console window opens with a QR code and the addresses. Leave that
   window open; it *is* the server. Closing it stops the game.
5. The first time, Windows Firewall may ask whether to allow Python.
   Allow it on **Private** networks, or the phones can't connect.

That version carries its own copy of Python in the `python` folder, so
it doesn't touch anything else on the computer and doesn't need admin
rights. Nothing is installed and nothing is left behind if you delete
the folder.

If you cloned the repo or downloaded the source (no `python` folder), you'll
need [Python](https://www.python.org/downloads/) 3.8 or newer installed
first — check **"Add python.exe to PATH"** during setup, as it's easy to
miss and nothing works without it. Then double-click **start.bat** the
same way.

**If it says the port is already in use**, the counter is most likely
already running in another console window: use that one, or close it and
start again. If some other program needs port 8000, start on a different
port by opening a Command Prompt in the folder and running
`start.bat 8001`, then use `:8001` instead of `:8000` in the address on
every phone.

## Running it (Mac/Linux)

There's no ready-to-run download for Mac or Linux; you run it from the
source with your own Python.

1. Get the files: download **Source code (zip)** from the
   [latest release](https://github.com/klingea1/mtg-counter/releases/latest)
   and unzip it, or `git clone https://github.com/klingea1/mtg-counter.git`.
2. Check you have Python 3.8 or newer: run `python3 --version` in
   Terminal. On a Mac without it, that command offers to install Apple's
   command line developer tools, which include Python. Say yes, wait for
   it to finish, and run the check again. On Linux, install `python3`
   from your package manager if it's missing.
3. In Terminal, go to the folder and start it:

   ```
   cd path/to/mtg-counter
   bash start.sh
   ```

   (`./start.sh` also works if the file kept its permissions through the
   unzip; `bash start.sh` always does.) You can also run
   `python3 server.py` directly.
4. On a Mac, the first time, macOS may ask whether Python should accept
   incoming network connections. Click **Allow**, or the phones can't
   connect.

Leave the Terminal window open while you play; press **Ctrl+C** to stop.
To use a port other than 8000, add it to the end: `bash start.sh 8001`.

## Connecting phones

1. Make sure every phone is on the **same wifi network** as the host
   computer (not cellular data).
2. Scan the QR code printed in the console, or open a browser and type
   in either address printed there — `http://192.168.x.x:8000` (always
   works) or `http://mtg.local:8000` (easier to say out loud).
3. Each player enters their name, sets their starting life, picks an
   accent color, and chooses an icon (tap "Choose Icon" — each player's
   icon is unique at the table, so any already claimed by someone else
   shows grayed out), then taps **Enter the Table**. Your chosen color
   carries through the whole screen — life number, buttons, highlights —
   not just the setup swatches.

If a phone can't connect:

- Use the numeric `http://192.168.x.x:8000` address. It always works,
  even when `mtg.local` doesn't.
- Double-check it's on the same wifi network (guest networks often
  isolate devices from each other, so try the main network).
- Windows may prompt to allow Python through the firewall the first time
  you run it. Allow access on "Private" networks.
- Some routers block device-to-device traffic ("AP/client isolation").
  If that's on, this won't work until it's turned off in the router
  settings.

**On Android**, `mtg.local` will show "This site can't be reached /
DNS_PROBE_FINISHED_NXDOMAIN". That's normal. Scan the QR code, or get
the link texted to you from a phone that's already in. Two other things
are worth a try, both free and both depending on your router:

- **The host computer's own name.** Many routers register the names of
  the devices connected to them, so `http://<your-pc-name>:8000` may
  just work. The server prints its own name as `(hostname: ...)` when it
  starts. Try it once from an Android phone; if it works, it works for
  everyone, and it's the shortest thing to say out loud.
- **A static entry in your router.** If your router lets you add a local
  DNS or "host" entry, point a short name like `mtg` at the host
  computer's address. Then `http://mtg:8000` works on every phone,
  Android included.

## Using the counter

- **Life**: tap the left or right half of the big life card for −1/+1,
  or use the −5/−1/+1/+5 buttons underneath. A row of colored numbers
  under the life total shows your current mana pool at a glance — one
  number per color you're actually holding (colors at zero are left out
  entirely), so you don't have to scroll down to see your own pool.
- **Undo**: the "↺ Undo" button in the corner of the life card reverses
  your last life or mana change — one step back, mostly there to save
  the −5 button from itself. It goes gray again once used, or once you
  make a different change.
- **Defeated**: your life card (and your card on everyone else's Table
  view) automatically marks you as defeated — grayed out with a "☠
  Defeated" tag — if your life hits 0, a token literally named "Poison"
  reaches 10, or you take 21+ Commander damage from a single opponent.
  It's a visual flag only; nothing locks, in case you need to correct a
  number afterward. In Tabletop View, defeat shows up as a tombstone
  stamp across your own screen or across a defeated opponent's card,
  instead of the strikethrough tag.
- **The Table**: shows everyone else currently at the table — their
  icon, name, accent color, and life total at a glance. Tap a player's
  card to expand it and see their mana pool, tokens and creature
  counters too. A player
  who hasn't synced in a few seconds (backgrounded their phone, wifi
  hiccup) shows as "away" but their last-known stats stay visible.
- **Icons**: pick one of six marks (sword, shield, dragon, skull, crown,
  flame) when you join, so you're recognizable at a glance next to your
  name and on the Table. Each icon can only belong to one player at a
  time — once someone's claimed one, it shows grayed out and labeled
  "Taken" for everyone else setting up.
- **Commander Damage**: a row per opponent at the table, tracking damage
  *you've taken* from their commander (the traditional 21-to-lose
  count). This is personal bookkeeping — each player logs their own
  incoming damage, and it isn't broadcast to anyone else's screen. A
  row turns red and gets a "Lethal" tag at 21. The section is
  collapsed by default (tap "▸ Show" in its header to expand it) since
  not every game needs it — your choice is remembered on this device,
  so it stays out of the way for non-Commander games without you
  having to collapse it every time.
- **Mana Pool**: each color (W/U/B/R/G/Colorless) has its own +/−
  counter. "Clear All" empties the pool in one tap — handy at the end of
  a step or phase. Shown by default; tap "▾ Hide" in its header if you'd
  rather not deal with per-color tracking (the small colored numbers
  under your life total still show your current pool either way) —
  your choice is remembered on this device.
- **Creature Counters**: a quick way to track +1/+1, -1/-1, or any other
  power/toughness counters on a couple of creatures at once without naming
  them — tap the dashed "+" chip to spin up a new counter (it starts at
  +1/+1). The chip shows the full power/toughness, like "+2/+2" or "-1/-1".
  Its own +/− adjusts power and toughness together, for the common
  symmetric case — into negative numbers too, if a creature's been shrunk
  more than it's been grown. Tap the number itself to expand the chip and
  reveal separate PWR and TGH controls, for creatures with an asymmetric
  boost like "+1/+0" — the chip only grows while you're actually using it,
  and collapses back down out of the way otherwise. Each half is colored a
  warning color independently once it goes negative, so "+2/-1" is easy to
  read at a glance. There's no name field on purpose, since you can already
  see which creature is which on the table in front of you. Unlike
  Commander damage, creature counters *are* shared with the table — anyone
  can tap your card on the Table view to expand it and see them, right
  alongside your mana pool and tokens. Tap the ✕ on a chip to remove it
  once a creature dies or the counter's no longer relevant.
- **Tokens**: add any token by name (Treasure,
  Clue, Poison, a 2/2 Zombie army, Experience counters, whatever your
  game needs) with the quick-add chips or the custom text field. Each
  gets its own +/− and can be removed with the ✕. The common token
  types (Treasure, Clue, Food, Blood, Poison, Experience, Energy) each
  get their own dot color, so they're easy to tell apart at a glance;
  anything custom just uses your accent color.
- **Roll**: the 🎲 Roll button opens a quick dice roller (d4–d20) and a
  coin flip — handy for deciding turn order or resolving a random
  effect. A banner flashes across the bottom of your life card while
  the die is "rolling," then shows the result for a few seconds before
  fading. Unlike Commander damage, rolls *are* shared — everyone else
  at the table sees the same "so-and-so is rolling…" / "so-and-so
  rolled 14 on a d20" message on that player's Table card, so a roll
  for turn order or an effect is visible to the whole table.
- **Table Markers**: who's the monarch, who has the initiative, whether
  it's day or night, and who has the city's blessing. Collapsed by
  default; the header lists what's in play, so you can see at a glance
  without opening it. Tap a player's name under Monarch or Initiative to
  hand it to them — you can hand it to anyone, not just yourself, since
  it usually moves because of what someone else did. Tap whoever has it
  to take it off the table. Day and Night work the same way. If two
  people tap at the same moment, the one that reaches the server last
  wins, and every phone shows the same answer within a couple of
  seconds. A player who leaves the table gives up anything they held.
  **Clear table markers** clears monarch, initiative and day/night for
  everyone, for the start of a new game.

  City's blessing is different, because everyone can have it at once:
  tap **You don't have it** to mark that you've got it. It's yours to set,
  like your life total, and Reset or New Game clears it.

  Whoever holds a marker gets a small badge under their name, on your
  own screen, on their Table card, and on their seat in Tabletop View.
  Day or night shows as ☀️ or 🌙 in the Table header and in the top corner
  of Tabletop View.
- **Rename**: tap "✎ Rename" next to your name at any point mid-game to
  change how you appear to everyone else at the table.
- **Reset** clears life, mana, tokens, creature counters, commander
  damage and your city's blessing back to the start of the current game
  (keeps your starting life total and table visibility). It only touches
  your own counter; the table's markers have their own clear button. **New Game** wipes everything, including starting life,
  and leaves the table until you tap "Enter the Table" again.

## Tabletop View

Tap "🗺️ Tabletop" next to your name to switch to a condensed, spatial view
built for actually playing rather than scrolling — your life card fills the
whole screen, with everyone else at the table shown as small cards floating
around it. Tap "✕ Exit" (top-left) to go back to the normal screen any time;
switching is instant and doesn't touch your game state.

Your own info sits anchored at the bottom of the screen, since that's where
you are relative to your phone. Tap the left or right half of the screen for
−1/+1 to your life, same as the normal life card. Your creature counters
(see above) show just above your life total, with the same add/+/−/✕
controls as the normal screen — everything else (mana, tokens, Commander
damage) stays on the standard screen, reachable by exiting Tabletop View.

Everyone else shows up as a small card with their name, any table markers
they hold, their life total, and creature counters (shown as full
power/toughness, like "+1/+2") — read-only,
since that's their own device's data, not yours to change. If several
counters are on the board at once, the card wraps them onto extra rows
rather than running off the edge of the screen, however you've positioned
that card. A defeated opponent's card gets a tombstone stamp across it —
same idea as the "☠ Defeated" tag on the standard screen, just sized to fit
a small card.

Drag a card to wherever that person is actually sitting relative to you;
while you're dragging, dashed markers appear at every spot you can drop
onto, and the one closest to your finger lights up solid so you can see
exactly where you'll land. It snaps to the nearest of 12 spots around the
screen — extra spots are clustered along the left and right edges, since
that's where a phone screen actually has the room, sitting taller than it
is wide. Where you put people is remembered per-player on your device
only — nobody else's phone is affected, and it's not tied to any particular
game, so once you've arranged your regular group it should stay put game
after game (matched by who they are, not where they happened to sit down
first).

A goblin wanders around the middle of the table. It walks behind the
player cards and never gets in the way of a tap. When anyone loses life,
you included, it waits a moment for the tapping to stop, then swings its
sword toward that player, once per hit rather than once per tap. When
someone goes out, it falls flat on its head for a few seconds, then picks
itself up and carries on. Each phone has its own goblin, so they won't be
standing in the same spot on everyone's screen, but they react to the same
things. He's on by default. Tap 👺 in the top-right corner to send him away
on your phone only; tap it again to bring him back. Your phone remembers
the choice.

## Notes on how sync works

There's no login or room code — everyone who connects to the same server
is automatically at the same table. Stats sync roughly every 1.5 seconds
(a simple, dependency-free approach well suited to a handful of phones on
one wifi network). Nothing is saved to disk: the table's state lives only
in the server's memory while it's running, and resets when you stop and
restart the server. Each phone also keeps its own local copy of its
counter (in the browser), so a page refresh won't lose your own progress.
Commander damage stays local to each device — it's personal bookkeeping,
not part of what's synced to the table. So does where you've dragged
people to in Tabletop View. Dice/coin rolls, on the other
hand, are synced, so the whole table can see when someone rolls and
what they got.

Monarch, initiative and day/night are the one exception to "each phone
owns its own stats": they belong to the whole table, so the server keeps
them and every phone asks it for changes. That's what makes two
simultaneous taps come out the same on every screen. They reset with the
server, like everything else.

## Joining without the QR code

The QR code is the fastest way in, but it only helps if you can see the
host computer's screen. Three things cover the case where the host PC is
in another room:

- **Show the code off a phone that's already in.** Tap "Show the join
  code" on the sign-in screen, or "Invite" in the Table section once
  you're playing, and the same QR code appears on your own phone for the
  person next to you to scan. That's usually the easiest answer: the
  first player scans off the host, the second scans off the first, and
  nobody else has to leave the table. The same panel has a **Text the
  link** button that opens your messages app with the address filled in,
  for anyone who'd rather just get it in the group chat.
- **`http://mtg.local:8000`** — the server answers to this name on your
  local network, so you can say it across a room instead of reading out
  an IP address. **iPhones and iPads only.** Android phones don't resolve
  `.local` names at all (they send the name to your router's DNS, which
  has never heard of it, and give up), so Android players should scan the
  QR code or use the numeric address. This is an Android limitation, not
  something the server can fix.
- The first time you run it, Windows Firewall may ask to allow Python
  again (this uses UDP port 5353 in addition to the web port) — allow it
  on "Private" networks. If you skip it, `mtg.local` won't work but
  everything else still will.

If you want to stop the server answering to that name, or use a
different one, set `MTG_MDNS_NAME` before starting it:

```
set MTG_MDNS_NAME=kitchen.local
python server.py
```

Use `MTG_MDNS_NAME=off` to turn it off entirely.

A third option, if you play in the same spot every week: give the host
computer a fixed address in your router settings (usually called a "DHCP
reservation"), then print the QR code once and tape it inside a deck box.
It'll keep working forever, with nothing to type at all.

## The QR code

The console prints a scannable QR code next to the address when the
server starts. There's nothing to install for it and it works offline —
the code is generated by the server itself.

If your console can't draw the block characters it's made of, the code
is skipped and everything else still works. The app has its own QR code
anyway (see above), which is the one to use once somebody's in.

## Files

- `index.html`: the counter app itself (no build step, just static
  HTML/CSS/JS)
- `server.py`: the local server. Serves the app and a small in-memory
  JSON API (`/api/players/<id>`) that powers the shared Table view,
  answers to the name `mtg.local` on your network, and draws the console
  QR code. Python standard library only, no packages to install, works
  with no internet connection. It serves `index.html` and the `assets/`
  folder and nothing else, so the rest of the folder isn't readable from
  the wifi.
- `start.bat` / `start.sh`: one-click launchers for Windows / Mac/Linux
- `assets/`: images for the app (the Tabletop View goblin). These have
  their own licenses, listed in `assets/CREDITS.md`.
- `python\`: only in the ready-to-run download, a self-contained copy
  of Python. Safe to ignore; delete the whole folder to uninstall.

For people working on the code:

- `PROJECT.md`: how it's built and why, and the conventions to follow
- `test_*.py`, `qr_roundtrip.py`: tests, run by hand (see `PROJECT.md`)
- `make-bundle.bat` / `make-bundle.ps1`: builds the ready-to-run zip
- `tools/sprite-inspector/`: a standalone tool for working on sprite
  sheets. Not part of the app.

## License

The code is MIT licensed, see `LICENSE`. The art in `assets/` is not
covered by that license; see `assets/CREDITS.md` for each file's license
and attribution.
