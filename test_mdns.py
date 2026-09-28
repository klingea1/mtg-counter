#!/usr/bin/env python3
"""Throwaway verification for the mDNS responder in server.py.

Part 1 exercises the wire-format helpers directly (no sockets).
Part 2 starts the real responder thread and sends it a genuine mDNS query
over UDP, then checks the answer that comes back.
"""
import importlib.util
import socket
import struct
import sys
import threading
import time

spec = importlib.util.spec_from_file_location("mtgserver", "server.py")
srv = importlib.util.module_from_spec(spec)
sys.argv = ["server.py"]
spec.loader.exec_module(srv)

failures = []


def check(label, got, want):
    if got == want:
        print("  PASS  %s" % label)
    else:
        print("  FAIL  %s\n        got:  %r\n        want: %r" % (label, got, want))
        failures.append(label)


def build_query(name, qtype=1, qclass=1, query_id=0x1234):
    header = struct.pack("!6H", query_id, 0x0000, 1, 0, 0, 0)
    return header + srv._encode_name(name) + struct.pack("!HH", qtype, qclass)


print("\n-- wire format --")

check("encode mtg.local",
      srv._encode_name("mtg.local"),
      b"\x03mtg\x05local\x00")

check("decode round-trips",
      srv._decode_name(srv._encode_name("mtg.local"), 0),
      ("mtg.local", 11))

# A compression pointer at offset 11 pointing back at the name at offset 0.
compressed = srv._encode_name("mtg.local") + b"\xc0\x00"
check("decode follows a compression pointer",
      srv._decode_name(compressed, 11),
      ("mtg.local", 13))

check("decode rejects a pointer loop",
      srv._decode_name(b"\xc0\x00", 0),
      (None, None))

check("decode rejects a truncated label",
      srv._decode_name(b"\x10ab", 0),
      (None, None))

check("query for our name matches",
      srv._mdns_asks_for_us(build_query("mtg.local")),
      (0x1234, False))

check("ANY query matches",
      srv._mdns_asks_for_us(build_query("mtg.local", qtype=255)),
      (0x1234, False))

check("unicast bit is reported",
      srv._mdns_asks_for_us(build_query("mtg.local", qclass=0x8001)),
      (0x1234, True))

check("name match is case-insensitive",
      srv._mdns_asks_for_us(build_query("MTG.Local")),
      (0x1234, False))

check("someone else's name is ignored",
      srv._mdns_asks_for_us(build_query("printer.local")),
      None)

check("AAAA query is ignored (we only serve A)",
      srv._mdns_asks_for_us(build_query("mtg.local", qtype=28)),
      None)

check("a response packet is not treated as a question",
      srv._mdns_asks_for_us(
          struct.pack("!6H", 1, 0x8400, 1, 0, 0, 0)
          + srv._encode_name("mtg.local") + struct.pack("!HH", 1, 1)),
      None)

check("garbage is ignored", srv._mdns_asks_for_us(b"\x00\x01\x02"), None)
check("empty packet is ignored", srv._mdns_asks_for_us(b""), None)

# Multi-question query: ours is second, so the loop has to walk past the first.
two = (struct.pack("!6H", 0x4321, 0x0000, 2, 0, 0, 0)
       + srv._encode_name("other.local") + struct.pack("!HH", 1, 1)
       + srv._encode_name("mtg.local") + struct.pack("!HH", 1, 1))
check("finds our name in a multi-question query",
      srv._mdns_asks_for_us(two),
      (0x4321, False))

resp = srv._mdns_a_response(0x1234, "192.168.1.47")
rid, flags, qd, an, ns, ar = struct.unpack("!6H", resp[:12])
check("response header", (rid, flags, qd, an, ns, ar), (0x1234, 0x8400, 0, 1, 0, 0))
rname, off = srv._decode_name(resp, 12)
rtype, rclass, rttl, rdlen = struct.unpack("!HHIH", resp[off:off + 10])
check("answer name", rname, "mtg.local")
check("answer is an A record, IN + cache-flush", (rtype, rclass), (1, 0x8001))
check("answer ttl and rdlength", (rttl, rdlen), (120, 4))
check("answer address", socket.inet_ntoa(resp[off + 10:off + 14]), "192.168.1.47")


print("\n-- live socket --")

# Who holds port 5353 before we start? A plain bind with no SO_REUSEADDR fails
# if another mDNS service already has it, which on Windows is almost always
# Apple's Bonjour (installed by iTunes, Adobe apps, and some printer drivers).
# Sharing the port with it is fine and expected — this is here so the result
# below can be read correctly, not because it's a problem.
_probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    _probe.bind(("", srv.MDNS_PORT))
    print("  port 5353 before we started: free")
    PORT_SHARED = False
except OSError:
    print("  port 5353 before we started: already in use by another mDNS "
          "service (Bonjour, most likely) — sharing it")
    PORT_SHARED = True
finally:
    _probe.close()

threading.Thread(target=srv.mdns_serve_forever, daemon=True).start()
srv.MDNS_READY.wait(3.0)
print("  responder status:  %s" % srv.MDNS_STATUS)
print("  joined the group on: %s" % (", ".join(srv.MDNS_JOINED) or "nothing"))
print("  will answer with:  %s" % srv.get_lan_ip_cached())


def multicast_query(name, query_id, timeout=4.0):
    """Ask the way a phone asks: send to the multicast group and listen for
    the direct reply. Sending to 127.0.0.1 instead would be testing something
    Windows doesn't define — when two processes share a UDP port, only one of
    them receives a unicast packet, and which one is anybody's guess."""
    lan = srv.get_lan_ip_cached()
    c = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    c.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    c.bind(("", 0))
    c.settimeout(timeout)
    for opt, val in ((socket.IP_MULTICAST_IF, socket.inet_aton(lan)),
                     (socket.IP_MULTICAST_LOOP, 1)):
        try:
            c.setsockopt(socket.IPPROTO_IP, opt, val)
        except OSError:
            pass
    # qclass 0x8001 = class IN with the "answer me directly" bit set.
    c.sendto(build_query(name, qclass=0x8001, query_id=query_id),
             (srv.MDNS_GROUP, srv.MDNS_PORT))
    try:
        data, _addr = c.recvfrom(4096)
        return data
    except socket.timeout:
        return None
    finally:
        c.close()


if srv.MDNS_STATUS != "ok":
    print("  SKIP  live query (the responder did not bind here)")
else:
    time.sleep(2.5)          # let the startup announcements go out first
    before = dict(srv.MDNS_STATS)
    data = multicast_query("mtg.local", 0x7777)
    after = dict(srv.MDNS_STATS)

    if data is None:
        heard = after["packets"] > before["packets"]
        answered = after["answers"] > before["answers"]
        check("a multicast query gets an answer", "timed out", "a response packet")
        print("")
        if answered:
            print("        The responder DID hear the query and sent a reply, but")
            print("        this test socket never received it. Something is dropping")
            print("        inbound UDP on the way back — Windows Firewall is the")
            print("        usual culprit. Allow python.exe on Private networks.")
        elif heard:
            print("        The responder saw packets but did not recognise the")
            print("        query. That would be a parsing bug — please report the")
            print("        counters below.")
        else:
            print("        The responder heard NOTHING at all. Either inbound UDP")
            print("        5353 is blocked (Windows Firewall, allow python.exe on")
            print("        Private networks), or the group was joined on the wrong")
            print("        adapter — check the list above against your actual wifi")
            print("        address from `ipconfig`.")
        print("        counters: %r -> %r" % (before, after))
        print("")
    else:
        rid, flags, qd, an, ns, ar = struct.unpack("!6H", data[:12])
        check("multicast response id echoes the query", rid, 0x7777)
        check("response is an authoritative answer", (flags, an), (0x8400, 1))
        rname, off = srv._decode_name(data, 12)
        rtype, rclass, rttl, rdlen = struct.unpack("!HHIH", data[off:off + 10])
        ip = socket.inet_ntoa(data[off + 10:off + 14])
        check("answer name", rname, "mtg.local")
        check("answer type/class", (rtype, rclass), (1, 0x8001))
        check("answer carries this host's LAN ip", ip, srv.get_lan_ip_cached())
        print("        (answered with %s)" % ip)

    # A query for a name that isn't ours must get no reply at all.
    stray = multicast_query("someone-else-entirely.local", 0x2222, timeout=2.0)
    check("no reply to another device's name",
          "silence" if stray is None else "got a reply", "silence")

    # Loopback unicast is informational only: with the port shared, Windows
    # delivers such a packet to exactly one of the bound sockets and does not
    # promise it will be ours. A failure here on Windows means nothing.
    loop = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    loop.settimeout(2.0)
    loop.bind(("127.0.0.1", 0))
    loop.sendto(build_query("mtg.local", qclass=0x8001, query_id=0x3333),
                ("127.0.0.1", srv.MDNS_PORT))
    try:
        loop.recvfrom(4096)
        print("  INFO  loopback unicast query also answered")
    except socket.timeout:
        print("  INFO  loopback unicast query went unanswered — expected when "
              "the port is shared, not a failure")
    finally:
        loop.close()

print("\n-- end to end, through this machine's own resolver --")
try:
    resolved = socket.gethostbyname(srv.MDNS_NAME)
    print("  %s resolves to %s here" % (srv.MDNS_NAME, resolved))
except Exception:
    print("  This machine cannot resolve %s itself." % srv.MDNS_NAME)
    print("  On Windows that is expected unless Bonjour is installed: Windows")
    print("  has an mDNS responder but not a general .local client. It says")
    print("  nothing about whether an iPhone can resolve it.")
print("  The test that actually matters: open http://%s:8000 in Safari on an"
      % srv.MDNS_NAME)
print("  iPhone that is on the same wifi, with the server running.")

print("")
if failures:
    print("%d FAILED: %s" % (len(failures), ", ".join(failures)))
    sys.exit(1)
print("all checks passed")
