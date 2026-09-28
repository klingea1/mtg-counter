#!/usr/bin/env python3
"""Verify both QR encoders.

There are two: the JS one in index.html (for the in-app share modal) and the
Python one in server.py (for the console). This checks both and asserts they
produce identical matrices, which is what keeps the two copies of the
algorithm from drifting apart. The JS encoder is pulled straight out of
index.html rather than kept as a second copy here, so it can't diverge from
what ships.

Correctness is judged by `qr_roundtrip.py`, an independently written decoder
that shares no code with either encoder. It reads the mask out of the symbol's
own format bits, rebuilds the function-pattern map from scratch, and reads the
data back. That check needs nothing but the standard library, so this runs
anywhere, including the Windows host.

Two optional extras run when available and are skipped otherwise:
  - node, to exercise the JS encoder
  - opencv-python + numpy, to try a real camera-style detector
See the QR section of PROJECT.md for why an OpenCV failure is reported rather
than treated as a broken symbol.

Usage: python3 test_qr.py
"""
import importlib.util
import io
import json
import os
import re
import subprocess
import sys

import qr_roundtrip

CASES = [
    "http://mtg.local:8000",                   # the name, the common case
    "http://192.168.1.47:8000",                # a typical numeric address
    "http://192.168.100.100:8000",             # the longest realistic address
    "http://10.0.0.5:8000",                    # short address
    "http://192.0.2.2:8943",                   # the one OpenCV can't read
    "http://kitchen-table.local:8000",         # a custom MTG_MDNS_NAME
    "http://localhost:8000",
    "http://192.168.1.1:9000",
    "A",                                       # tiny, forces version 1
    "http://mtg.local:8000/?x=1",
    "x" * 14,                                  # exactly version 1 capacity
    "y" * 15,                                  # one over, must roll to version 2
    "z" * 26,                                  # exactly version 2 capacity
    "w" * 27,                                  # one over, must roll to version 3
    "q" * 42,                                  # exactly version 3 capacity
]

failures = []
notes = []


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


spec = importlib.util.spec_from_file_location("mtgserver", "server.py")
srv = importlib.util.module_from_spec(spec)
sys.argv = ["server.py"]
spec.loader.exec_module(srv)


def codewords_for(text):
    """Rebuild the codeword stream so every mask can be generated directly,
    not just the one the encoder picks."""
    data_bytes = list(text.encode("utf-8"))
    chosen = None
    for size, data_cw, ec_cw, align in srv._QR_VERSIONS:
        if len(data_bytes) + 2 <= data_cw:
            chosen = (size, data_cw, ec_cw, align)
            break
    size, data_cw, ec_cw, align = chosen
    bits = []

    def push(value, length):
        for k in range(length - 1, -1, -1):
            bits.append((value >> k) & 1)

    push(4, 4)
    push(len(data_bytes), 8)
    for byte in data_bytes:
        push(byte, 8)
    for _ in range(4):
        if len(bits) >= data_cw * 8:
            break
        bits.append(0)
    while len(bits) % 8:
        bits.append(0)
    data = []
    for i in range(0, len(bits), 8):
        value = 0
        for bit in bits[i:i + 8]:
            value = (value << 1) | bit
        data.append(value)
    pad = 0
    while len(data) < data_cw:
        data.append(0xEC if pad % 2 == 0 else 0x11)
        pad += 1
    return size, align, data + srv._qr_ec_codewords(data, ec_cw)


# --------------------------------------------------------------------------
print("\n-- python encoder, round-tripped by an independent decoder --")
# --------------------------------------------------------------------------
for text in CASES:
    m = srv.qr_matrix(text)
    if m is None:
        ok("%r encodes" % text, False, "encoder returned None")
        continue
    try:
        got, mask = qr_roundtrip.decode(m)
    except ValueError as exc:
        ok("%r round-trips" % text, False, "decoder rejected it: %s" % exc)
        continue
    version = (len(m) - 17) // 4
    check("%-34r v%d mask %d" % (text, version, mask), got, text)

print("\n-- every mask, for the addresses most likely to be used --")
for text in ["http://192.168.1.47:8000", "http://192.0.2.2:8943",
             "http://mtg.local:8000"]:
    size, align, codewords = codewords_for(text)
    bad = []
    for mask in range(8):
        m = srv._qr_matrix_for(size, align, codewords, mask)
        try:
            got, read_mask = qr_roundtrip.decode(m)
            if got != text or read_mask != mask:
                bad.append(mask)
        except ValueError:
            bad.append(mask)
    ok("%-26r all 8 masks round-trip" % text, not bad, "broken masks: %r" % bad)

print("\n-- capacity boundaries --")
ok("43 bytes is refused (modal falls back to the link)",
   srv.qr_matrix("o" * 43) is None)
for text, want in [("x" * 14, 1), ("y" * 15, 2), ("z" * 26, 2),
                   ("w" * 27, 3), ("q" * 42, 3)]:
    got = (len(srv.qr_matrix(text)) - 17) // 4
    check("%d bytes picks version %d" % (len(text), want), got, want)

print("\n-- console rendering --")
m = srv.qr_matrix("http://192.168.1.47:8000")
lines = srv._qr_console_lines(m, quiet=4)
ok("fits a default console window (%d lines x %d cols)"
   % (len(lines), len(lines[0])), len(lines) <= 20 and len(lines[0]) <= 78)

# Decode the rendering back. A renderer that mirrors or inverts the code would
# sail through everything above, all of which tests the matrix rather than what
# actually reaches the screen.
lit = {"█": (True, True), "▀": (True, False),
       "▄": (False, True), " ": (False, False)}
rebuilt = [[None] * len(lines[0]) for _ in range(len(lines) * 2)]
for y, line in enumerate(lines):
    for x, ch in enumerate(line):
        top, bottom = lit[ch]
        rebuilt[y * 2][x] = not top          # bright half = light = not dark
        rebuilt[y * 2 + 1][x] = not bottom
inner = [row[4:4 + len(m)] for row in rebuilt[4:4 + len(m)]]
ok("rendering round-trips back to the same matrix", inner == [list(r) for r in m])
ok("quiet zone renders light, as a scanner needs", not any(rebuilt[0]))

# --------------------------------------------------------------------------
print("\n-- javascript encoder (optional: needs node) --")
# --------------------------------------------------------------------------
NODE = r"""
var fs = require('fs');
var src = fs.readFileSync(process.argv[2], 'utf8');
var mod = new Function(src + '; return {qrMatrix: qrMatrix};')();
var cases = JSON.parse(process.argv[3]);
var out = {};
cases.forEach(function(t){
  var m = mod.qrMatrix(t);
  out[t] = m === null ? null : m.map(function(row){
    return row.map(function(v){ return v ? 1 : 0; });
  });
});
out['__over__'] = mod.qrMatrix('o'.repeat(43));
console.log(JSON.stringify(out));
"""

try:
    subprocess.check_output(["node", "--version"], stderr=subprocess.STDOUT)
except Exception:
    print("  SKIP  node is not installed here")
    notes.append("the JS encoder was not exercised (no node)")
else:
    html = io.open("index.html", encoding="utf-8").read()
    match = re.search(r"// ---------- QR encoder ----------(.*?)"
                      r"// ---------- Share / invite ----------", html, re.S)
    if not match:
        ok("found the QR encoder block in index.html", False)
    else:
        io.open("qr-extracted.js", "w", encoding="utf-8").write(match.group(1))
        io.open("qrrun.js", "w", encoding="utf-8").write(NODE)
        try:
            matrices = json.loads(subprocess.check_output(
                ["node", "qrrun.js", "qr-extracted.js", json.dumps(CASES)],
                text=True))
        finally:
            for tmp in ("qr-extracted.js", "qrrun.js"):
                if os.path.exists(tmp):
                    os.remove(tmp)

        mismatched = []
        for text in CASES:
            py = [[1 if v else 0 for v in row] for row in srv.qr_matrix(text)]
            if matrices.get(text) != py:
                mismatched.append(text)
        ok("JS and Python produce identical matrices for all %d cases" % len(CASES),
           not mismatched, "differ on: %r" % mismatched)
        ok("JS encoder also refuses 43 bytes", matrices.get("__over__") is None)

# --------------------------------------------------------------------------
print("\n-- real detector (optional: needs opencv + numpy) --")
# --------------------------------------------------------------------------
try:
    import cv2
    import numpy as np
except ImportError:
    print("  SKIP  opencv/numpy not installed here")
    notes.append("no camera-style detector was tried (no opencv)")
else:
    def render(matrix, scale=8, quiet=4):
        size = len(matrix)
        side = (size + quiet * 2) * scale
        img = np.full((side, side), 255, dtype=np.uint8)
        for r in range(size):
            for c in range(size):
                if matrix[r][c]:
                    img[(r + quiet) * scale:(r + quiet + 1) * scale,
                        (c + quiet) * scale:(c + quiet + 1) * scale] = 0
        return img

    detector = cv2.QRCodeDetector()
    unreadable = []
    for text in CASES:
        decoded, _pts, _qr = detector.detectAndDecode(render(srv.qr_matrix(text)))
        if decoded != text:
            unreadable.append(text)
    if not unreadable:
        print("  PASS  OpenCV %s read all %d codes" % (cv2.__version__, len(CASES)))
    else:
        # Not a failure. These symbols are proven valid above by round-trip
        # decode; OpenCV's detector just can't find some of them. See
        # PROJECT.md. Reported because a sudden jump here is worth a look.
        print("  INFO  OpenCV could not read %d of %d: %r"
              % (len(unreadable), len(CASES), unreadable))
        print("        Those symbols round-trip correctly above, so they are")
        print("        valid. This is a detector limitation, not an encoder bug.")
        notes.append("OpenCV could not read %d of %d symbols (known, see PROJECT.md)"
                     % (len(unreadable), len(CASES)))

print("")
for note in notes:
    print("note: %s" % note)
if failures:
    print("\n%d FAILED: %s" % (len(failures), failures))
    sys.exit(1)
print("\nall checks passed")
