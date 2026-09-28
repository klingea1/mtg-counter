#!/usr/bin/env python3
"""
Tiny local web server for the MTG Counter app — serves the app itself and
a small in-memory JSON API so everyone at the table can see each other's
life, mana, and tokens live.

Run this on the computer you want to act as the "host" (the one that
stays on the table / on the wifi). Everyone else opens the printed
address on their own phone's browser, on the SAME wifi network. Each
phone keeps its own counter, and can see everyone else's too.

This also answers to the name `mtg.local` on the local network (mDNS /
Bonjour), so players can type `http://mtg.local:8000` instead of an IP
address. That works on iPhones and iPads, which resolve `.local` names
natively. It does NOT work on Android, which sends the name to the
router's DNS and gets nowhere — confirmed on a real device, and not
something this server can fix. So the numeric address is still printed,
and is still what the QR code points at.

Usage:
    python3 server.py            (defaults to port 8000)
    python3 server.py 9000       (custom port)

    MTG_MDNS_NAME=table.local python3 server.py     (rename mtg.local)
    MTG_MDNS_NAME=off python3 server.py             (disable mDNS entirely)

No third-party dependencies — everything here is Python's standard
library, so there's nothing to install.
"""

import http.server
import socketserver
import socket
import struct
import sys
import os
import json
import time
import threading
import posixpath
import urllib.parse

PORT = 8000
if len(sys.argv) > 1:
    try:
        PORT = int(sys.argv[1])
    except ValueError:
        print("Port must be a number, e.g. python3 server.py 8000")
        sys.exit(1)

# Serve the folder this script lives in, regardless of where it's launched from.
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# In-memory "the table" state: playerId -> last-known snapshot.
# Nothing here is written to disk — it lives only as long as the server runs,
# which is exactly right for a single game night.
PLAYERS = {}
PLAYERS_LOCK = threading.Lock()
API_PREFIX = "/api/players"
JOIN_PATH = "/api/join"

# The only static files the server will hand out: the app itself, and anything
# under assets/. Everything else in this folder (docs, tests, build tooling,
# whatever else someone keeps next to it) is 404 to phones on the wifi.
PUBLIC_FILES = {"/", "/index.html"}
PUBLIC_DIR = "/assets/"


def get_lan_ip():
    """Best-effort discovery of this machine's LAN IP address."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Doesn't actually send anything — just asks the OS which local
        # interface it would use to reach an external address.
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


# ---------------------------------------------------------------------------
# mDNS responder — lets phones reach the host as `mtg.local` instead of an IP
# ---------------------------------------------------------------------------
#
# This is a deliberately minimal single-purpose mDNS responder: it answers
# A-record queries for exactly one name and does nothing else. It is NOT a
# general Bonjour implementation — no service discovery, no PTR/SRV/TXT, no
# probing for name conflicts. That's fine for a kitchen table; if some other
# device on the network already claims the same name, both will answer and
# whoever the phone hears first wins. Pick a different MTG_MDNS_NAME if that
# ever actually happens.
#
# Everything in here fails soft. The numeric address always works, so an mDNS
# problem (port in use, firewall, odd network adapter) must never stop the
# game from starting — it just prints why and carries on.

MDNS_GROUP = "224.0.0.251"
MDNS_PORT = 5353
MDNS_NAME = os.environ.get("MTG_MDNS_NAME", "mtg.local").strip()
MDNS_TTL = 120                       # seconds phones may cache the answer

MDNS_READY = threading.Event()       # set once we know whether it came up
MDNS_STATUS = "off"                  # human-readable, printed by main()
MDNS_JOINED = []                     # interface IPs the group was joined on
# Counters, so a "mtg.local doesn't work" report can be narrowed down without
# guessing: packets seen at all, queries that were for us, answers sent.
MDNS_STATS = {"packets": 0, "queries": 0, "answers": 0}

_IP_CACHE = {"ip": None, "at": 0.0}


def local_ipv4s():
    """Every IPv4 address this machine has, best effort. Used to join the
    multicast group on all of them rather than guessing which adapter the
    table is on."""
    ips = []
    try:
        primary = get_lan_ip()
        if primary and primary != "127.0.0.1":
            ips.append(primary)
    except Exception:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addr = info[4][0]
            if addr not in ips and addr != "127.0.0.1":
                ips.append(addr)
    except Exception:
        pass
    return ips


def get_lan_ip_cached(max_age=30.0):
    """`get_lan_ip()` with a short cache — the responder needs the current IP
    on every answer, and laptops do change networks mid-session."""
    now = time.time()
    if _IP_CACHE["ip"] is None or now - _IP_CACHE["at"] > max_age:
        _IP_CACHE["ip"] = get_lan_ip()
        _IP_CACHE["at"] = now
    return _IP_CACHE["ip"]


def _encode_name(name):
    """Dotted name -> DNS wire-format length-prefixed labels."""
    out = b""
    for label in name.split("."):
        if label:
            raw = label.encode("utf-8")[:63]
            out += struct.pack("!B", len(raw)) + raw
    return out + b"\x00"


def _decode_name(data, offset):
    """Read a DNS name starting at `offset`. Handles compression pointers.
    Returns (name, offset_just_past_the_name), or (None, None) if malformed."""
    labels = []
    after = None
    hops = 0
    while True:
        if offset >= len(data):
            return None, None
        length = data[offset]
        if length & 0xC0 == 0xC0:                 # compression pointer
            if offset + 1 >= len(data):
                return None, None
            if after is None:
                after = offset + 2
            offset = ((length & 0x3F) << 8) | data[offset + 1]
            hops += 1
            if hops > 10:                         # pointer loop — give up
                return None, None
            continue
        if length == 0:
            if after is None:
                after = offset + 1
            break
        offset += 1
        if offset + length > len(data):
            return None, None
        labels.append(data[offset:offset + length].decode("utf-8", "replace"))
        offset += length
    return ".".join(labels), after


def _mdns_asks_for_us(data):
    """If `data` is a query for MDNS_NAME, return (query_id, unicast_wanted).
    Otherwise return None."""
    if len(data) < 12:
        return None
    query_id, flags, qdcount = struct.unpack("!3H", data[:6])
    if flags & 0x8000:                  # QR bit set — it's someone's answer
        return None
    offset = 12
    for _ in range(qdcount):
        name, offset = _decode_name(data, offset)
        if name is None or offset + 4 > len(data):
            return None
        qtype, qclass = struct.unpack("!HH", data[offset:offset + 4])
        offset += 4
        if (name.lower() == MDNS_NAME.lower()
                and qtype in (1, 255)            # A, or ANY
                and (qclass & 0x7FFF) == 1):     # class IN
            # Top bit of qclass is mDNS's "please answer me directly" flag.
            return query_id, bool(qclass & 0x8000)
    return None


def _mdns_a_response(query_id, ip):
    """A response packet carrying one A record for MDNS_NAME."""
    # QR=1 (response), AA=1 (authoritative); no question echoed back, 1 answer.
    header = struct.pack("!6H", query_id, 0x8400, 0, 1, 0, 0)
    answer = (
        _encode_name(MDNS_NAME)
        # type A, class IN with the cache-flush bit set, ttl, 4 bytes of rdata
        + struct.pack("!HHIH", 1, 0x8001, MDNS_TTL, 4)
        + socket.inet_aton(ip)
    )
    return header + answer


def _mdns_socket(ip):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # Port 5353 is shared by design — Bonjour (which iTunes and some printer
    # software install on Windows) may already be sitting on it, and that's
    # fine as long as everyone sets these.
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except (AttributeError, OSError):
        pass          # Windows has no SO_REUSEPORT; SO_REUSEADDR shares there
    sock.bind(("", MDNS_PORT))

    # Join the group on EVERY local interface, not just the one the default
    # route points at. A Windows laptop routinely has wifi, ethernet, and
    # virtual adapters from VPN/VM/remote-desktop software; picking one and
    # guessing wrong means the responder is up but never hears a thing, which
    # is a miserable failure to debug. Joining all of them costs nothing.
    del MDNS_JOINED[:]
    for candidate in local_ipv4s():
        try:
            mreq = socket.inet_aton(MDNS_GROUP) + socket.inet_aton(candidate)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            MDNS_JOINED.append(candidate)
        except OSError:
            pass          # adapter is down, or already joined — not fatal
    if not MDNS_JOINED:
        # Nothing specific worked; let the OS pick.
        mreq = socket.inet_aton(MDNS_GROUP) + socket.inet_aton("0.0.0.0")
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        MDNS_JOINED.append("0.0.0.0")

    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF,
                        socket.inet_aton(ip))
    except OSError:
        pass
    sock.settimeout(2.0)
    return sock


def mdns_serve_forever():
    """Answer `MDNS_NAME` queries until the process exits. Runs on a daemon
    thread; never raises into the caller."""
    global MDNS_STATUS

    if not MDNS_NAME or MDNS_NAME.lower() in ("off", "none", "false"):
        MDNS_STATUS = "off"
        MDNS_READY.set()
        return

    try:
        sock = _mdns_socket(get_lan_ip_cached())
    except OSError as exc:
        MDNS_STATUS = "unavailable (%s)" % exc
        MDNS_READY.set()
        return

    MDNS_STATUS = "ok"
    MDNS_READY.set()

    # Announce unprompted a couple of times so anything already listening
    # refreshes its cache without having to ask first.
    for _ in range(2):
        try:
            sock.sendto(_mdns_a_response(0, get_lan_ip_cached()),
                        (MDNS_GROUP, MDNS_PORT))
        except OSError:
            break
        time.sleep(1)

    while True:
        try:
            data, addr = sock.recvfrom(4096)
        except socket.timeout:
            continue
        except OSError:
            time.sleep(1)
            continue
        try:
            MDNS_STATS["packets"] += 1
            asked = _mdns_asks_for_us(data)
            if not asked:
                continue
            MDNS_STATS["queries"] += 1
            query_id, unicast = asked
            reply = _mdns_a_response(query_id, get_lan_ip_cached())
            if unicast:
                # Some clients only listen for the direct reply. Send this
                # first, and keep the two sends independent so a multicast
                # problem can't swallow the direct answer.
                try:
                    sock.sendto(reply, addr)
                except OSError:
                    pass
            try:
                sock.sendto(reply, (MDNS_GROUP, MDNS_PORT))
            except OSError:
                pass
            MDNS_STATS["answers"] += 1
        except Exception:
            # A malformed packet from some other device on the LAN should
            # never take the responder down.
            continue


def is_public_path(raw_path):
    """True if `raw_path` (as sent by the browser) names a file we serve.

    Decoded and normalised before checking, so `/assets/../server.py` and its
    percent-encoded spellings land outside assets/ and are refused. Directory
    paths under assets/ are refused too, so there are no listings.
    """
    path = urllib.parse.unquote(urllib.parse.urlsplit(raw_path).path)
    if "\\" in path or "\x00" in path:
        return False
    if path in PUBLIC_FILES:
        return True
    norm = posixpath.normpath(path)
    return (path.startswith(PUBLIC_DIR) and not path.endswith("/")
            and norm == path and len(norm) > len(PUBLIC_DIR))


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Keep the console readable — skip per-request logging.
        pass

    def send_head(self):
        # SimpleHTTPRequestHandler would serve anything in the folder, with
        # directory listings. Covers both GET and HEAD.
        if not is_public_path(self.path):
            self.send_error(404)
            return None
        return super().send_head()

    def list_directory(self, path):
        # Belt and braces: "/" resolves to index.html, and nothing else that
        # passes is_public_path is a directory, but never list one regardless.
        self.send_error(404)
        return None

    def _send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == API_PREFIX or self.path == API_PREFIX + "/":
            with PLAYERS_LOCK:
                self._send_json(PLAYERS)
            return
        if self.path == JOIN_PATH:
            # The address to hand to the next player. This deliberately does
            # NOT echo back whatever host the asking phone used: someone who
            # joined via mtg.local would otherwise pass mtg.local on to an
            # Android phone that can't resolve it. The numeric address is the
            # one that always works, so that's the one we share.
            ip = get_lan_ip_cached()
            self._send_json({
                "ip": ip,
                "port": PORT,
                "url": "http://%s:%d" % (ip, PORT),
                "name": MDNS_NAME if MDNS_STATUS == "ok" else None,
                "nameUrl": ("http://%s:%d" % (MDNS_NAME, PORT)
                            if MDNS_STATUS == "ok" else None),
            })
            return
        return super().do_GET()

    def do_POST(self):
        if self.path.startswith(API_PREFIX + "/"):
            player_id = self.path[len(API_PREFIX) + 1:]
            if not player_id or len(player_id) > 100:
                self._send_json({"error": "invalid player id"}, 400)
                return
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                data = json.loads(raw.decode("utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("expected an object")
            except Exception:
                self._send_json({"error": "invalid json body"}, 400)
                return
            data["lastSeen"] = time.time()
            with PLAYERS_LOCK:
                PLAYERS[player_id] = data
            self._send_json({"ok": True})
            return
        self.send_response(404)
        self.end_headers()

    def do_DELETE(self):
        if self.path.startswith(API_PREFIX + "/"):
            player_id = self.path[len(API_PREFIX) + 1:]
            with PLAYERS_LOCK:
                PLAYERS.pop(player_id, None)
            self._send_json({"ok": True})
            return
        self.send_response(404)
        self.end_headers()


class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    # On Windows SO_REUSEADDR means something else: it lets a second server bind
    # a port another server is already listening on, with no error. Two copies
    # then split the phones between two separate tables. Windows gets exclusive
    # use instead, so a second copy fails and says so. Elsewhere it only allows
    # a quick restart after stopping, which is what we want.
    allow_reuse_address = os.name != "nt"

    def server_bind(self):
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


# ---------------------------------------------------------------------------
# QR encoder
# ---------------------------------------------------------------------------
#
# This is a line-for-line port of the encoder in index.html, and test_qr.py
# asserts the two produce byte-identical module matrices so they can't drift.
# It exists here so the console QR needs no third-party package: the
# distributed bundle runs on Python's embeddable runtime, which ships without
# pip, so an optional dependency could never be installed there.
#
# Same narrow scope as the JS version: byte mode, error correction level M,
# versions 1-3 (42 bytes max, single block, no interleaving). See the QR
# section of PROJECT.md before extending it.

_QR_VERSIONS = [
    # (modules per side, data codewords, ec codewords, alignment centre)
    (21, 16, 10, 0),
    (25, 28, 16, 18),
    (29, 44, 26, 22),
]

# Pre-computed 15-bit format strings for EC level M, masks 0-7.
_QR_FORMAT_M = [0x5412, 0x5125, 0x5E7C, 0x5B4B, 0x45F9, 0x40CE, 0x4F97, 0x4AA0]

_QR_EXP = [0] * 256
_QR_LOG = [0] * 256


def _qr_build_tables():
    x = 1
    for i in range(255):
        _QR_EXP[i] = x
        _QR_LOG[x] = i
        x <<= 1
        if x & 0x100:
            x ^= 0x11D          # GF(256) primitive polynomial
    _QR_EXP[255] = _QR_EXP[0]


_qr_build_tables()


def _qr_mul(a, b):
    if a == 0 or b == 0:
        return 0
    return _QR_EXP[(_QR_LOG[a] + _QR_LOG[b]) % 255]


def _qr_gen_poly(ec_len):
    poly = [1]
    for i in range(ec_len):
        nxt = [0] * (len(poly) + 1)
        for j, coeff in enumerate(poly):
            nxt[j] ^= coeff                                 # multiply by x
            nxt[j + 1] ^= _qr_mul(coeff, _QR_EXP[i])
        poly = nxt
    return poly


def _qr_ec_codewords(data, ec_len):
    gen = _qr_gen_poly(ec_len)
    res = [0] * ec_len
    for byte in data:
        factor = byte ^ res[0]
        res.pop(0)
        res.append(0)
        for j in range(ec_len):
            res[j] ^= _qr_mul(gen[j + 1], factor)
    return res


def _qr_mask_at(mask, row, col):
    if mask == 0:
        return (row + col) % 2 == 0
    if mask == 1:
        return row % 2 == 0
    if mask == 2:
        return col % 3 == 0
    if mask == 3:
        return (row + col) % 3 == 0
    if mask == 4:
        return (row // 2 + col // 3) % 2 == 0
    if mask == 5:
        return (row * col) % 2 + (row * col) % 3 == 0
    if mask == 6:
        return ((row * col) % 2 + (row * col) % 3) % 2 == 0
    return ((row + col) % 2 + (row * col) % 3) % 2 == 0


def _qr_place_finder(m, size, row, col):
    for r in range(-1, 8):
        for c in range(-1, 8):
            rr, cc = row + r, col + c
            if not (0 <= rr < size and 0 <= cc < size):
                continue
            on = ((0 <= r <= 6 and c in (0, 6)) or
                  (0 <= c <= 6 and r in (0, 6)) or
                  (2 <= r <= 4 and 2 <= c <= 4))
            m[rr][cc] = on


def _qr_matrix_for(size, align, codewords, mask):
    m = [[None] * size for _ in range(size)]

    _qr_place_finder(m, size, 0, 0)
    _qr_place_finder(m, size, size - 7, 0)
    _qr_place_finder(m, size, 0, size - 7)

    for i in range(8, size - 8):                    # timing patterns
        m[6][i] = (i % 2 == 0)
        m[i][6] = (i % 2 == 0)

    if align:                                       # versions 2 and 3 only
        for r in range(-2, 3):
            for c in range(-2, 3):
                m[align + r][align + c] = max(abs(r), abs(c)) != 1

    for i in range(9):                              # reserve format-info areas
        if m[8][i] is None:
            m[8][i] = False
        if m[i][8] is None:
            m[i][8] = False
    for i in range(8):
        if m[8][size - 1 - i] is None:
            m[8][size - 1 - i] = False
        if m[size - 1 - i][8] is None:
            m[size - 1 - i][8] = False

    # data, snaking up and down two columns at a time from the bottom right
    inc, row, bit_index, byte_index = -1, size - 1, 7, 0
    col = size - 1
    while col > 0:
        if col == 6:                                # skip the timing column
            col -= 1
        while True:
            for off in range(2):
                if m[row][col - off] is None:
                    dark = False
                    if byte_index < len(codewords):
                        dark = (codewords[byte_index] >> bit_index) & 1 == 1
                    if _qr_mask_at(mask, row, col - off):
                        dark = not dark
                    m[row][col - off] = dark
                    bit_index -= 1
                    if bit_index == -1:
                        byte_index += 1
                        bit_index = 7
            row += inc
            if row < 0 or row >= size:
                row -= inc
                inc = -inc
                break
        col -= 2

    fmt = _QR_FORMAT_M[mask]                        # format info, written twice
    for i in range(15):
        bit = ((fmt >> i) & 1) == 1
        if i < 6:
            m[i][8] = bit
        elif i < 8:
            m[i + 1][8] = bit
        else:
            m[size - 15 + i][8] = bit

        if i < 8:
            m[8][size - i - 1] = bit
        elif i < 9:
            m[8][15 - i] = bit
        else:
            m[8][14 - i] = bit
    m[size - 8][8] = True                           # the always-dark module

    return m


def _qr_penalty(m):
    size = len(m)
    score = 0

    for line in [m[r] for r in range(size)] + [[m[r][c] for r in range(size)]
                                               for c in range(size)]:
        run, last = 1, line[0]
        for value in line[1:]:
            if value == last:
                run += 1
            else:
                if run >= 5:
                    score += 3 + (run - 5)
                run, last = 1, value
        if run >= 5:
            score += 3 + (run - 5)

    for r in range(size - 1):                       # 2x2 blocks of one colour
        for c in range(size - 1):
            v = m[r][c]
            if m[r][c + 1] == v and m[r + 1][c] == v and m[r + 1][c + 1] == v:
                score += 3

    p1 = [True, False, True, True, True, False, True, False, False, False, False]
    p2 = [False, False, False, False, True, False, True, True, True, False, True]
    for line in [m[r] for r in range(size)] + [[m[r][c] for r in range(size)]
                                               for c in range(size)]:
        for start in range(size - 10):
            window = line[start:start + 11]
            if window == p1 or window == p2:        # finder-like patterns
                score += 40

    dark = sum(1 for r in range(size) for c in range(size) if m[r][c])
    pct = (dark * 100.0) / (size * size)
    score += int(abs(pct - 50) // 5) * 10

    return score


def qr_matrix(text):
    """Return a list of rows of booleans (True = dark module), or None if
    `text` is longer than version 3 holds (42 bytes)."""
    data_bytes = list(text.encode("utf-8"))
    spec = None
    for size, data_cw, ec_cw, align in _QR_VERSIONS:
        # 2 codewords of overhead: 4-bit mode + 8-bit length + 4-bit terminator
        if len(data_bytes) + 2 <= data_cw:
            spec = (size, data_cw, ec_cw, align)
            break
    if spec is None:
        return None
    size, data_cw, ec_cw, align = spec

    bits = []

    def push(value, length):
        for k in range(length - 1, -1, -1):
            bits.append((value >> k) & 1)

    push(4, 4)                          # byte mode
    push(len(data_bytes), 8)            # character count (8 bits for v1-9)
    for byte in data_bytes:
        push(byte, 8)
    for _ in range(4):                  # terminator
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
    pad_index = 0
    while len(data) < data_cw:
        data.append(0xEC if pad_index % 2 == 0 else 0x11)
        pad_index += 1

    codewords = data + _qr_ec_codewords(data, ec_cw)

    best, best_score = None, None
    for mask in range(8):
        candidate = _qr_matrix_for(size, align, codewords, mask)
        score = _qr_penalty(candidate)
        if best_score is None or score < best_score:
            best, best_score = candidate, score
    return best


def _qr_console_lines(matrix, quiet=4):
    """Render `matrix` as text, two module rows per line.

    Light modules are drawn bright and dark modules are left as the console
    background, because Windows consoles are dark by default and a scanner
    needs the light parts to be the bright ones. Half-block characters pack
    two module rows into each line, which keeps a version 3 code to 19 lines
    so the whole thing stays on screen above the prompt.
    """
    size = len(matrix)
    width = size + quiet * 2
    grid = [[False] * width for _ in range(quiet)]
    for row in matrix:
        grid.append([False] * quiet + list(row) + [False] * quiet)
    grid.extend([[False] * width for _ in range(quiet)])
    if len(grid) % 2:
        grid.append([False] * width)

    glyph = {(False, False): "█",   # both light  -> full block
             (False, True): "▀",    # top light   -> upper half block
             (True, False): "▄",    # bottom light-> lower half block
             (True, True): " "}          # both dark   -> console background
    lines = []
    for y in range(0, len(grid), 2):
        top, bottom = grid[y], grid[y + 1]
        lines.append("".join(glyph[(top[x], bottom[x])] for x in range(width)))
    return lines


def print_qr(url):
    """Print a scannable QR code for `url` to the console."""
    try:
        matrix = qr_matrix(url)
        if matrix is None:
            return
        for line in _qr_console_lines(matrix):
            print(" " + line)
    except Exception:
        # A console that can't render block characters shouldn't stop a game.
        # The address above works on its own, and the app has its own QR.
        pass


def main():
    ip = get_lan_ip_cached()
    hostname = socket.gethostname()
    phone_url = f"http://{ip}:{PORT}"
    name_url = f"http://{MDNS_NAME}:{PORT}"

    # Start the responder before the web server so the name is claimed by the
    # time anyone can possibly connect.
    threading.Thread(target=mdns_serve_forever, daemon=True).start()
    MDNS_READY.wait(2.0)

    try:
        server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    except OSError as exc:
        print("")
        print(f" Could not start on port {PORT}: {exc.strerror or exc}")
        print("")
        print(" Most likely MTG Counter is already running in another window.")
        print(" Use that one, or close it and start again.")
        print("")
        print(" If something else needs this port, pick another number:")
        print(f"   start.bat {PORT + 1}        (Windows)")
        print(f"   ./start.sh {PORT + 1}       (Mac/Linux)")
        print(f" and use :{PORT + 1} instead of :{PORT} in the address on every phone.")
        sys.exit(1)

    with server as httpd:
        print("=" * 52)
        print(" MTG Counter is running")
        print("=" * 52)
        print(f" On this computer:   http://localhost:{PORT}")
        print(f" On phones/tablets:  {phone_url}")
        if MDNS_STATUS == "ok":
            print(f" Or type instead:    {name_url}")
        print()
        print(" Everyone connects to the SAME address above, on the")
        print(" same wifi network. Each device keeps its own life,")
        print(" mana, and token counts — and can see everyone else's")
        print(" at the table too.")
        if MDNS_STATUS == "ok":
            print()
            print(f" {MDNS_NAME} is easier to say across a room and works")
            print(" on iPhones and iPads. Android does NOT resolve .local")
            print(" names — Android players should scan the QR code, or use")
            print(" the numeric address, which always works everywhere.")
        elif MDNS_STATUS != "off":
            print()
            print(f" ({MDNS_NAME} is unavailable: {MDNS_STATUS})")
            print(" Windows Firewall may need to allow Python on UDP 5353.")
            print(" The addresses above work regardless.")
        print()
        print(" Scan to join:")
        print_qr(phone_url)          # always the numeric address — it can't fail to resolve
        print(f" (hostname: {hostname})")
        print(" Press Ctrl+C to stop the server.")
        print("=" * 52)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopping server. Thanks for playing!")


if __name__ == "__main__":
    main()
