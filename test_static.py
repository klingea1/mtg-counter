#!/usr/bin/env python3
"""
Checks that server.py serves the app and assets/, and nothing else.

Phones on the wifi should be able to load index.html and anything under
assets/. They should NOT be able to read the docs, tests, build tooling or
anything else that happens to sit in this folder, and there should be no
directory listings.

Standard library only. Starts its own server on a spare port and stops it.

    python3 test_static.py
"""

import os
import socket
import subprocess
import sys
import time
import http.client

HERE = os.path.dirname(os.path.abspath(__file__))

failures = []


def ok(label, cond):
    print(("  PASS  " if cond else "  FAIL  ") + label)
    if not cond:
        failures.append(label)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def request(port, path, method="GET"):
    # http.client sends the path exactly as given, so traversal attempts
    # reach the server unmodified.
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request(method, path)
    r = conn.getresponse()
    body = r.read()
    conn.close()
    return r.status, body


port = free_port()
env = dict(os.environ, MTG_MDNS_NAME="off")
proc = subprocess.Popen([sys.executable, os.path.join(HERE, "server.py"), str(port)],
                        cwd=HERE, env=env,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)

    print("Served:")
    status, body = request(port, "/")
    ok("/ serves the app", status == 200 and b"<html" in body.lower())
    ok("/?x=1 serves the app", request(port, "/?x=1")[0] == 200)
    ok("/index.html serves the app", request(port, "/index.html")[0] == 200)
    ok("HEAD / works", request(port, "/", "HEAD")[0] == 200)
    ok("/api/players answers", request(port, "/api/players")[0] == 200)
    ok("/api/join answers", request(port, "/api/join")[0] == 200)

    assets = [f for f in os.listdir(os.path.join(HERE, "assets"))
              if os.path.isfile(os.path.join(HERE, "assets", f))]
    for f in assets:
        ok("/assets/%s is served" % f, request(port, "/assets/" + f)[0] == 200)

    print("Refused:")
    for path in ["/server.py", "/README.md", "/PROJECT.md", "/LICENSE",
                 "/test_static.py", "/start.bat", "/make-bundle.ps1",
                 "/tools/sprite-inspector/index.html",
                 "/assets/", "/assets", "/tools/", "/build/",
                 "/assets/../server.py", "/assets/%2e%2e/server.py",
                 "/assets/..%2fserver.py", "/assets/%2E%2E%2Fserver.py",
                 "/assets/..\\server.py", "/assets//../server.py",
                 "/%2e%2e/%2e%2e/etc/passwd", "/assets/nope.png"]:
        ok("%s is 404" % path, request(port, path)[0] == 404)
    ok("HEAD /server.py is 404", request(port, "/server.py", "HEAD")[0] == 404)
finally:
    proc.terminate()
    proc.wait(5)

print()
if failures:
    print("%d FAILED: %s" % (len(failures), failures))
    sys.exit(1)
print("All passed.")
