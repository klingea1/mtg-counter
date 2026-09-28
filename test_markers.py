#!/usr/bin/env python3
"""End-to-end check of table markers: monarch, initiative, day/night, city's blessing.

Two browser contexts act as two players, because the point of the feature is
that both phones agree: the server owns monarch, initiative and day/night, so
a change on one phone (or two phones tapping at once) has to land the same way
on both. City's blessing is per player and rides the normal snapshot instead.

Usage: python3 test_markers.py <port>   (use a FRESH port, see PROJECT.md)
"""
import os
import sys

from playwright.sync_api import sync_playwright

PORT = int(sys.argv[1])
BASE = "http://127.0.0.1:%d" % PORT
PINNED_CHROMIUM = "/opt/pw-browsers/chromium"
POLL = 2500  # one 1.5s poll cycle plus slack

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


def badges(page, sel):
    return page.eval_on_selector_all(sel + " .mk-badge", "els => els.map(e => e.textContent)")


def chip(page, row, name):
    return page.locator("#%s .marker-chip" % row, has_text=name)


def server_table(page):
    return page.request.get(BASE + "/api/table").json()


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
    a.wait_for_timeout(POLL)
    ids = a.evaluate("() => localStorage.getItem('mtg-counter-player-id')"), \
        b.evaluate("() => localStorage.getItem('mtg-counter-player-id')")

    print("\n-- the section --")
    check("nothing held at the start", server_table(a), {"monarch": None, "initiative": None, "dayNight": None})
    ok("collapsed by default", not a.is_visible("#markersBody"))
    a.click("#markersToggleBtn")
    b.click("#markersToggleBtn")
    ok("opens", a.is_visible("#markersBody"))
    check("you, then everyone else, can be handed the monarch",
          a.eval_on_selector_all("#monarchChips .marker-chip", "els => els.map(e => e.textContent)"),
          ["You", "Riley"])

    print("\n-- monarch --")
    chip(a, "monarchChips", "Riley").click()
    a.wait_for_timeout(300)
    check("server records the holder", server_table(a)["monarch"], ids[1])
    check("badge on Riley's Table card, straight away", badges(a, "#tableList .table-card"), ["Monarch"])
    check("header summary names them", a.inner_text("#markersSummary"), "Monarch: Riley")
    b.wait_for_timeout(POLL)
    check("Riley's own phone shows it by their name", badges(b, "#youBadges"), ["Monarch"])
    ok("and marks it on Riley's own chip", "on" in b.get_attribute("#monarchChips .marker-chip >> nth=0", "class"))
    check("Riley's summary says it's them", b.inner_text("#markersSummary"), "Monarch: You")

    chip(b, "monarchChips", "Sam").click()
    b.wait_for_timeout(300)
    a.wait_for_timeout(POLL)
    check("anyone can hand it on", badges(a, "#youBadges"), ["Monarch"])
    check("and the old holder loses it", badges(b, "#youBadges"), [])

    chip(a, "monarchChips", "You").click()
    a.wait_for_timeout(300)
    check("tapping the holder clears it", server_table(a)["monarch"], None)

    print("\n-- two phones tap at once --")
    for _ in range(3):
        # Start each round with nobody holding it, so both taps are claims. (If one
        # phone already held it, its tap would mean "give it up" instead.)
        a.request.post(BASE + "/api/table", data={"monarch": None})
        a.wait_for_timeout(POLL)
        a.evaluate("() => document.querySelector('#monarchChips .marker-chip').click()")
        b.evaluate("() => document.querySelector('#monarchChips .marker-chip').click()")
        a.wait_for_timeout(POLL)
        held = server_table(a)["monarch"]
        ok("the server settles on one holder", held in ids, "held %r" % held)
        a_sees = a.inner_text("#markersSummary")
        b_sees = b.inner_text("#markersSummary")
        want_a = "Monarch: You" if held == ids[0] else "Monarch: Riley"
        want_b = "Monarch: You" if held == ids[1] else "Monarch: Sam"
        ok("and both phones agree who it is", (a_sees, b_sees) == (want_a, want_b),
           "Sam sees %r, Riley sees %r" % (a_sees, b_sees))
    a.request.post(BASE + "/api/table", data={"monarch": None})

    print("\n-- initiative --")
    chip(a, "initiativeChips", "Riley").click()
    chip(a, "monarchChips", "Riley").click()
    a.wait_for_timeout(300)
    check("both on one player", badges(a, "#tableList .table-card"), ["Monarch", "Initiative"])
    a.click("#tabletopToggleBtn")
    a.wait_for_timeout(POLL)
    check("badges on their Tabletop seat too", badges(a, "#ttOpponents .tt-player"), ["Monarch", "Initiative"])

    print("\n-- day and night --")
    ok("no day/night shown until it starts", not a.is_visible("#ttDayNight"))
    b.locator("#dayNightChips .marker-chip", has_text="Day").click()
    b.wait_for_timeout(300)
    check("Table header shows day", b.inner_text("#tableDayNight"), "☀️")
    a.wait_for_timeout(POLL)
    check("the other phone's Tabletop View shows it", a.inner_text("#ttDayNight"), "☀️")
    b.locator("#dayNightChips .marker-chip", has_text="Night").click()
    a.wait_for_timeout(POLL)
    check("switches to night", a.inner_text("#ttDayNight"), "🌙")
    check("the day/night tag doesn't take taps",
          a.eval_on_selector("#ttDayNight", "e => getComputedStyle(e).pointerEvents"), "none")

    print("\n-- city's blessing --")
    b.click("#blessingBtn")
    check("button says you have it", b.inner_text("#blessingBtn"), "✓ You have it")
    check("badge by your own name, next to the others", badges(b, "#youBadges"),
          ["Monarch", "Initiative", "Blessing"])
    a.wait_for_timeout(POLL)
    check("everyone else sees it on your seat", badges(a, "#ttOpponents .tt-player"),
          ["Monarch", "Initiative", "Blessing"])
    ok("it's in the snapshot, not the table record", "citysBlessing" not in server_table(a))

    print("\n-- clearing --")
    a.click("#tabletopExitBtn")
    b.click("#resetBtn")
    b.click("#confirmOk")
    b.wait_for_timeout(300)
    check("Reset clears your own blessing", badges(b, "#youBadges"), ["Monarch", "Initiative"])

    b.click("#newGameBtn")
    b.click("#confirmOk")
    a.wait_for_timeout(POLL)
    check("a holder who leaves takes nothing with them",
          {k: v for k, v in server_table(a).items() if k != "dayNight"}, {"monarch": None, "initiative": None})
    check("summary shows only what's left", a.inner_text("#markersSummary"), "Night")

    chip(a, "monarchChips", "You").click()
    a.wait_for_timeout(300)
    a.click("#clearMarkersBtn")
    ok("clearing asks first", a.is_visible("#confirmModal"))
    a.click("#confirmOk")
    a.wait_for_timeout(300)
    check("Clear table markers resets everything", server_table(a),
          {"monarch": None, "initiative": None, "dayNight": None})
    ok("and the day/night tag goes away", not a.is_visible("#tableDayNight"))

    print("\n-- the server refuses nonsense --")
    for label, body in [("an unknown player", {"monarch": "nobody"}),
                        ("a made-up time of day", {"dayNight": "dusk"}),
                        ("a field it doesn't know", {"storm": 3})]:
        r = a.request.post(BASE + "/api/table", data=body)
        check("rejects " + label, r.status, 400)
    check("and nothing changed", server_table(a), {"monarch": None, "initiative": None, "dayNight": None})

    ok("no uncaught page errors", not errors, str(errors))
    browser.close()

print("")
if failures:
    print("%d FAILED: %s" % (len(failures), failures))
    sys.exit(1)
print("all checks passed")
