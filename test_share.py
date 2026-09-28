#!/usr/bin/env python3
"""End-to-end check of the share modal, against a real running server.

The important assertion is the last one: read the QR back out of the page's
own canvas pixels and decode it with `qr_roundtrip.py`, which shares no code
with either encoder. If that round-trips, the feature works for the thing it
exists to do. (It deliberately doesn't use OpenCV's detector, which can't find
some perfectly valid symbols; see the QR section of PROJECT.md.)

Usage: python3 test_share.py <port>   (use a FRESH port, see PROJECT.md)
"""
import importlib.util
import json
import os
import sys
import urllib.request

from playwright.sync_api import sync_playwright

import qr_roundtrip

PORT = int(sys.argv[1])
BASE = "http://127.0.0.1:%d" % PORT
PINNED_CHROMIUM = "/opt/pw-browsers/chromium"

# server.py reads its port from argv at import time, so take our own argument
# before handing it a clean one.
_spec = importlib.util.spec_from_file_location("mtgserver", "server.py")
_srv = importlib.util.module_from_spec(_spec)
sys.argv = ["server.py"]
_spec.loader.exec_module(_srv)

failures = []


def check(label, got, want):
    if got == want:
        print("  PASS  %s" % label)
    else:
        print("  FAIL  %s\n        got:  %r\n        want: %r" % (label, got, want))
        failures.append(label)


def ok(label, condition, detail=""):
    if condition:
        print("  PASS  %s" % label)
    else:
        print("  FAIL  %s %s" % (label, detail))
        failures.append(label)


print("\n-- /api/join --")
join = json.loads(urllib.request.urlopen(BASE + "/api/join").read().decode())
print("  %s" % json.dumps(join))
ok("returns a numeric url", join["url"].startswith("http://") and join["ip"] in join["url"])
check("port matches the running server", join["port"], PORT)
ok("url is not localhost (it has to work from another device)",
   "localhost" not in join["url"] and "127.0.0.1" not in join["url"])

with sync_playwright() as p:
    # The dev container ships Chromium at a fixed path; anywhere else, use
    # whatever `playwright install chromium` put in place.
    launch = {"args": ["--no-sandbox"]}
    if os.path.exists(PINNED_CHROMIUM):
        launch["executable_path"] = PINNED_CHROMIUM
    browser = p.chromium.launch(**launch)
    page = browser.new_context(viewport={"width": 390, "height": 844}).new_page()
    page.goto(BASE, wait_until="networkidle")

    print("\n-- setup screen --")
    ok("share button is on the sign-in screen", page.is_visible("#setupShareBtn"))
    ok("modal starts hidden", not page.is_visible("#shareModal"))

    page.click("#setupShareBtn")
    page.wait_for_selector("#shareModal:not(.hidden)", timeout=4000)
    ok("modal opens", page.is_visible("#shareModal"))

    shown = page.inner_text("#shareUrl")
    check("modal shows the host's address, not this browser's", shown, join["url"])

    href = page.get_attribute("#shareUrl", "href")
    ok("the address is a real link (long-press to copy)", href.rstrip("/") == join["url"].rstrip("/"),
       "href=%r" % href)

    sms = page.get_attribute("#shareSms", "href")
    ok("sms link is an sms: url", sms.startswith("sms:"), "href=%r" % sms)
    ok("sms body carries the join url", join["url"].replace(":", "%3A").replace("/", "%2F") in sms,
       "href=%r" % sms)
    print("        sms href: %s" % sms)

    dims = page.evaluate(
        "() => { const c = document.getElementById('shareQr');"
        " return {w: c.width, h: c.height}; }")
    ok("QR canvas was actually drawn", dims["w"] > 100 and dims["w"] == dims["h"],
       "dims=%r" % dims)
    print("        canvas: %dx%d px" % (dims["w"], dims["h"]))

    if join.get("nameUrl"):
        ok("mtg.local is offered as an alternative", page.is_visible("#shareAlt"))
        print("        alt line: %r" % page.inner_text("#shareAlt"))
    else:
        ok("alt line hidden when mDNS is off", not page.is_visible("#shareAlt"))

    page.screenshot(path="share-modal.png")

    print("\n-- read the QR back out of the canvas pixels --")
    shot = page.evaluate("""() => {
      const c = document.getElementById('shareQr');
      const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
      const px = [];
      for (let i = 0; i < d.length; i += 4) px.push(d[i] < 128 ? 1 : 0);
      return {w: c.width, px: px};
    }""")

    quiet = 4
    expected = _srv.qr_matrix(join["url"])
    modules = len(expected) + quiet * 2
    scale = shot["w"] // modules
    ok("canvas is an exact whole number of modules (%d x %dpx)" % (modules, scale),
       scale * modules == shot["w"], "width=%d" % shot["w"])

    sampled = []
    for r in range(len(expected)):
        row = []
        for c in range(len(expected)):
            y = (r + quiet) * scale + scale // 2
            x = (c + quiet) * scale + scale // 2
            row.append(bool(shot["px"][y * shot["w"] + x]))
        sampled.append(row)

    ok("canvas pixels match the encoder's matrix",
       sampled == [list(r) for r in expected])
    try:
        decoded, mask = qr_roundtrip.decode(sampled)
        check("the QR on screen decodes to the join url", decoded, join["url"])
        print("        (version %d, mask %d)" % ((len(expected) - 17) // 4, mask))
    except ValueError as exc:
        ok("the QR on screen decodes", False, str(exc))

    page.click("#shareClose")
    ok("Close hides the modal", not page.is_visible("#shareModal"))

    print("\n-- in-game invite button --")
    page.fill("#playerName", "Sam")
    page.click("#iconPickerBtn")
    page.wait_for_selector("#iconModal:not(.hidden)")
    page.click("#iconGrid button:not([disabled])")
    page.click("#startBtn")
    page.wait_for_selector("#main:not(.hidden)", timeout=4000)
    ok("entered the table", page.is_visible("#tableSection"))
    ok("Invite button is in the Table header", page.is_visible("#tableShareBtn"))

    page.click("#tableShareBtn")
    page.wait_for_selector("#shareModal:not(.hidden)", timeout=4000)
    ok("invite opens the same modal mid-game", page.is_visible("#shareModal"))
    check("same address mid-game", page.inner_text("#shareUrl"), join["url"])
    page.screenshot(path="share-modal-ingame.png")
    page.click("#shareClose")

    print("\n-- nothing else broke --")
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.click("#plus1")
    page.wait_for_timeout(300)
    check("life counter still works", page.inner_text("#lifeValue"), "41")
    page.click("#rollBtn")
    page.wait_for_selector("#rollModal:not(.hidden)")
    ok("roll modal still opens", page.is_visible("#rollModal"))
    page.click("#rollCloseBtn")
    ok("no uncaught page errors", not errors, str(errors))

    browser.close()

print("")
if failures:
    print("%d FAILED: %s" % (len(failures), failures))
    sys.exit(1)
print("all checks passed")
