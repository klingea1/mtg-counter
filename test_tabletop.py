#!/usr/bin/env python3
"""End-to-end check of Tabletop View and power/toughness creature counters.

Two browser contexts act as two players at the same table, because the
interesting failures here are cross-player: one phone's counters showing up
wrong (or not at all) on another phone's Table card or Tabletop seat.

Also covers the {id, count} -> {id, power, toughness} migration: a saved game
from before asymmetric counters has to load as a symmetric counter, not break.

Usage: python3 test_tabletop.py <port>   (use a FRESH port, see PROJECT.md)
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


def own_chips(page):
    return page.eval_on_selector_all(
        "#creatureList .creature-chip:not(.add) .cnt",
        "els => els.map(e => e.textContent)")


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

    print("\n-- power/toughness counters --")
    a.click("#creatureList .creature-chip.add button")
    check("new counter starts at +1/+1", own_chips(a), ["+1/+1"])
    a.click('#creatureList .creature-chip:not(.add) [data-act="plus"]')
    check("symmetric + moves both axes", own_chips(a), ["+2/+2"])

    a.click('#creatureList .creature-chip:not(.add) [data-act="toggle"]')
    ok("tapping the value expands PWR/TGH controls",
       a.is_visible("#creatureList .creature-chip.expanded .pt-axes"))
    for _ in range(3):
        a.click('#creatureList .creature-chip:not(.add) [data-act="pminus"]')
    a.click('#creatureList .creature-chip:not(.add) [data-act="tplus"]')
    check("axes move independently, power can go negative", own_chips(a), ["-1/+3"])
    ok("negative power is marked", a.is_visible("#creatureList .cnt .pt-p.pt-neg"))

    print("\n-- the other phone sees it --")
    b.wait_for_timeout(2500)   # one poll cycle and change
    b.click("#tableList .table-card .table-card-top")
    b.wait_for_selector("#tableList .table-card-detail:not(.hidden)")
    check("Table card shows the asymmetric counter",
          b.inner_text("#tableList .t-creatures"), "Creature counters: -1/+3")

    print("\n-- Tabletop View --")
    ok("Tabletop starts hidden", not b.is_visible("#tabletopView"))
    b.click("#tabletopToggleBtn")
    b.wait_for_selector("#tabletopView:not(.hidden)")
    ok("Tabletop opens", b.is_visible("#tabletopView"))
    seat = "#ttOpponents .tt-player"
    check("the other player has a seat", b.locator(seat).count(), 1)
    check("seat shows their name", b.inner_text(seat + " .tt-p-name"), "Sam")
    check("seat shows their counter", b.inner_text(seat + " .tt-p-chip").replace("\n", ""), "-1/+3")

    before = b.inner_text("#ttLifeValue")
    box = b.locator("#ttLifePlusTap").bounding_box()
    b.mouse.click(box["x"] + box["width"] / 2, box["y"] + 40)
    check("tapping the right side is +1 life", int(b.inner_text("#ttLifeValue")), int(before) + 1)
    check("main life total agrees", b.inner_text("#lifeValue"), b.inner_text("#ttLifeValue"))

    start = b.eval_on_selector(seat, "e => ({top: e.style.top, left: e.style.left})")
    sb = b.locator(seat).bounding_box()
    vw = 390
    b.mouse.move(sb["x"] + sb["width"] / 2, sb["y"] + sb["height"] / 2)
    b.mouse.down()
    b.mouse.move(vw * 0.18, 844 * 0.50, steps=12)   # toward the W slot
    b.mouse.up()
    b.wait_for_timeout(200)
    end = b.eval_on_selector(seat, "e => ({top: e.style.top, left: e.style.left})")
    ok("dragging moves the seat", end != start, "%r -> %r" % (start, end))
    check("and it snaps to the W slot", end, {"top": "50%", "left": "17%"})
    saved = b.evaluate("() => localStorage.getItem('mtg-counter-tabletop-positions')")
    ok("seat is remembered on this device", saved is not None and "9" in saved, "saved=%r" % saved)

    b.reload(wait_until="networkidle")
    b.wait_for_timeout(2000)
    ok("Tabletop mode survives a reload", b.is_visible("#tabletopView"))
    check("seat position survives a reload",
          b.eval_on_selector(seat, "e => ({top: e.style.top, left: e.style.left})"),
          {"top": "50%", "left": "17%"})
    b.click("#tabletopExitBtn")
    ok("Exit returns to the normal screen", not b.is_visible("#tabletopView"))

    print("\n-- old saved games still load --")
    a.evaluate("""() => {
      const s = JSON.parse(localStorage.getItem('mtg-counter-state-v2'));
      s.creatures = [{id: 'old1', count: 3}];
      localStorage.setItem('mtg-counter-state-v2', JSON.stringify(s));
    }""")
    a.reload(wait_until="networkidle")
    check("a saved {count: 3} loads as +3/+3", own_chips(a), ["+3/+3"])

    print("\n-- share still reachable --")
    ok("Invite button still in the Table header", a.is_visible("#tableShareBtn"))
    a.click("#tableShareBtn")
    a.wait_for_selector("#shareModal:not(.hidden)", timeout=4000)
    ok("share modal opens", a.is_visible("#shareModal"))

    ok("no uncaught page errors", not errors, str(errors))
    browser.close()

print("")
if failures:
    print("%d FAILED: %s" % (len(failures), failures))
    sys.exit(1)
print("all checks passed")
