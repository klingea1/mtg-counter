#!/usr/bin/env python3
"""End-to-end check of the table pet, the goblin in Tabletop View.

Two browser contexts act as two players. Sam watches in Tabletop View while Riley
loses life and eventually goes out, because the reactions that matter are to
another phone's changes arriving through the poll, not just your own taps.

The goblin's current sheet frame is read back from its background-position, so
the checks see what a player would see without any test hooks in index.html.
Frames 8-10 of each 11-frame row are the attack; 44-48 are the fall.

Usage: python3 test_pet.py <port>   (use a FRESH port, see PROJECT.md)
"""
import os
import sys

from playwright.sync_api import sync_playwright

PORT = int(sys.argv[1])
BASE = "http://127.0.0.1:%d" % PORT
PINNED_CHROMIUM = "/opt/pw-browsers/chromium"

failures = []


def ok(label, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + label + ("" if cond or not detail else "  (" + detail + ")"))
    if not cond:
        failures.append(label)


def check(label, got, want):
    ok(label, got == want, "got %r, want %r" % (got, want))


def join(page, name):
    page.goto(BASE, wait_until="networkidle")
    page.fill("#playerName", name)
    page.click("#iconPickerBtn")
    page.wait_for_selector("#iconModal:not(.hidden)")
    page.click("#iconGrid button:not([disabled])")
    page.click("#startBtn")
    page.wait_for_selector("#main:not(.hidden)", timeout=4000)


# Logs every frame change as {t, f}. Transform changes every animation frame, so
# only entries where the frame itself changed are kept.
RECORD = """() => {
  const pet = document.getElementById('ttPet');
  window.__petLog = [];
  new MutationObserver(() => {
    const m = /(-?\\d+)px (-?\\d+)px/.exec(pet.style.backgroundPosition);
    if (!m) return;
    const f = Math.round(-m[2] / 64) * 11 + Math.round(-m[1] / 72);
    const log = window.__petLog;
    if (!log.length || log[log.length - 1].f !== f) log.push({t: performance.now(), f: f});
  }).observe(pet, {attributes: true, attributeFilter: ['style']});
}"""


def log_since(page, t0):
    return page.evaluate("t0 => window.__petLog.filter(e => e.t >= t0)", t0)


def now(page):
    return page.evaluate("() => performance.now()")


def swings(log):
    """Attack starts: entries on frame 8 of a walking row."""
    return [e for e in log if e["f"] < 44 and e["f"] % 11 == 8]


def tap(page, sel):
    box = page.locator(sel).bounding_box()
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + 40)


with sync_playwright() as p:
    launch = {"args": ["--no-sandbox"]}
    if os.path.exists(PINNED_CHROMIUM):
        launch["executable_path"] = PINNED_CHROMIUM
    browser = p.chromium.launch(**launch)
    vp = {"viewport": {"width": 390, "height": 844}}
    a = browser.new_context(**vp).new_page()
    b = browser.new_context(**vp).new_page()
    errors = []
    for pg in (a, b):
        pg.on("pageerror", lambda e: errors.append(str(e)))

    join(a, "Sam")
    join(b, "Riley")

    print("\n-- the goblin lives in Tabletop View --")
    ok("no goblin on the normal screen", not a.is_visible("#ttPet"))
    a.click("#tabletopToggleBtn")
    a.wait_for_selector("#tabletopView:not(.hidden)")
    a.evaluate(RECORD)
    a.wait_for_timeout(2500)   # a couple of polls, so both players have a baseline
    ok("goblin is visible in Tabletop View", a.is_visible("#ttPet"))
    check("goblin never takes a tap", a.eval_on_selector("#ttPet", "e => getComputedStyle(e).pointerEvents"), "none")
    img_ok = a.evaluate("""() => new Promise(r => { const i = new Image();
      i.onload = () => r(i.naturalWidth === 792 && i.naturalHeight === 320); i.onerror = () => r(false);
      i.src = 'assets/goblinsword_fixed.png'; })""")
    ok("the server hands out the sprite sheet", img_ok)

    t0 = now(a)
    a.wait_for_timeout(4000)
    log = log_since(a, t0)
    walked = [e for e in log if e["f"] < 44 and e["f"] % 11 < 8]
    ok("it walks on its own", len(walked) > 5, "%d walk frames in 4s" % len(walked))
    check("and nothing has set it off yet", len(swings(log_since(a, 0))), 0)
    box = a.locator("#ttPet").bounding_box()
    feet_x = box["x"] + 36 * 2
    feet_y = box["y"] + 58 * 2
    ok("it stays inside the arena", 0 < feet_x < 390 and 0 < feet_y < 844 * 0.7,
       "feet at %.0f,%.0f" % (feet_x, feet_y))

    print("\n-- another player loses life --")
    t0 = now(a)
    for _ in range(7):
        b.click("#minus1")
    a.wait_for_timeout(6000)   # poll + 2s settle + the swing itself
    check("tapping down 7 is one swing, not seven", len(swings(log_since(a, t0))), 1)

    print("\n-- your own life --")
    t0 = now(a)
    for _ in range(3):
        tap(a, "#ttLifeMinusTap")
    for _ in range(3):
        tap(a, "#ttLifePlusTap")
    a.wait_for_timeout(3500)
    check("down 3 then back up 3 is no swing", len(swings(log_since(a, t0))), 0)

    t0 = now(a)
    tap(a, "#ttLifeMinusTap")
    tap(a, "#ttLifeMinusTap")
    a.wait_for_timeout(3500)
    s = swings(log_since(a, t0))
    check("losing your own life is one swing", len(s), 1)
    ok("and it swings facing you (row 0)", bool(s) and s[0]["f"] == 8, "frame %r" % (s[0]["f"] if s else None))

    print("\n-- another player goes out --")
    t0 = now(a)
    while int(b.inner_text("#lifeValue")) > 0:
        b.click("#minus5")
    a.wait_for_timeout(3000)   # poll, then partway through the fall
    tap(a, "#ttLifeMinusTap")  # this swing comes due while the goblin is still down
    a.wait_for_timeout(6000)
    log = log_since(a, t0)
    fs = [e["f"] for e in log]
    ok("the goblin falls down", all(f in fs for f in (44, 45, 46, 47, 48)), "frames %r" % fs)
    down = next((e for e in log if e["f"] == 48), None)
    up = next((e for e in log if down and e["t"] > down["t"] and e["f"] == 47), None)
    held = (up["t"] - down["t"]) / 1000 if down and up else None
    ok("stays down 4-5 seconds", held is not None and 4.4 <= held <= 5.2, "held %r s" % held)
    during = [e for e in swings(log) if down and up and down["t"] <= e["t"] <= up["t"]]
    check("a swing that comes due while it's down is dropped", len(during), 0)
    after = [e for e in log if up and e["t"] > up["t"] and e["f"] < 44]
    ok("then gets back up and walks again", len(after) > 0)
    check("going out is a fall, not a swing", len([e for e in swings(log) if not down or e["t"] < down["t"]]), 0)

    print("\n-- turning him off --")
    check("on by default", a.get_attribute("#ttPetToggleBtn", "aria-label"), "Goblin on")
    a.click("#ttPetToggleBtn")
    check("button says off", a.get_attribute("#ttPetToggleBtn", "aria-label"), "Goblin off")
    ok("goblin hidden", not a.is_visible("#ttPet"))
    t0 = now(a)
    a.wait_for_timeout(1500)
    check("and not animating", len(log_since(a, t0)), 0)
    a.reload(wait_until="networkidle")
    a.wait_for_selector("#tabletopView:not(.hidden)")
    check("off survives a reload", a.get_attribute("#ttPetToggleBtn", "aria-label"), "Goblin off")
    ok("still hidden after reload", not a.is_visible("#ttPet"))
    ok("other phones keep theirs", b.evaluate("() => localStorage.getItem('mtg-counter-pet-enabled')") is None)
    a.click("#ttPetToggleBtn")
    a.evaluate(RECORD)
    t0 = now(a)
    a.wait_for_timeout(1500)
    ok("back on, he's back", a.is_visible("#ttPet") and len(log_since(a, t0)) > 0)

    print("\n-- back to the normal screen --")
    a.click("#tabletopExitBtn")
    a.wait_for_timeout(300)
    ok("goblin hidden again", not a.is_visible("#ttPet"))
    t0 = now(a)
    a.wait_for_timeout(1500)
    check("and it stops animating", len(log_since(a, t0)), 0)

    ok("no uncaught page errors", not errors, str(errors))
    browser.close()

print("")
if failures:
    print("%d FAILED: %s" % (len(failures), failures))
    sys.exit(1)
print("all checks passed")
