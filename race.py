#!/usr/bin/env python3
"""Concurrency experiment used to expose Phantom Fob freshness/checksum behavior.

The script races legitimate /press requests and prints the resulting fob CAN frames.
It does not enumerate or disclose the missing UNLOCK opcode.

Usage:
    python3 race.py TARGET_IP --fob-id 12A
"""

import argparse
import json
import re
import socket
import threading
import time
import urllib.request
from collections import defaultdict

FRAME_RE = re.compile(
    rb"< frame ([0-9A-Fa-f]+) ([0-9.]+) ([0-9A-Fa-f]+) >"
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("target")
    parser.add_argument("--fob-id", default="12A")
    parser.add_argument("--bus", default="vcan0")
    parser.add_argument("--can-port", type=int, default=29536)
    parser.add_argument("--web-port", type=int, default=8080)
    parser.add_argument("--requests", type=int, default=32)
    args = parser.parse_args()

    fob_id = args.fob_id.upper()
    web = f"http://{args.target}:{args.web_port}"
    frames = []
    frame_lock = threading.Lock()

    sock = socket.create_connection((args.target, args.can_port), timeout=5)
    sock.settimeout(1)
    print("hello:", sock.recv(1024))
    sock.sendall(f"< open {args.bus} >".encode())
    print("open :", sock.recv(1024))
    sock.sendall(b"< rawmode >")
    print("raw  :", sock.recv(1024))

    def reader() -> None:
        buf = b""
        while True:
            try:
                data = sock.recv(65535)
                if not data:
                    return
                buf += data
                while True:
                    match = FRAME_RE.search(buf)
                    if not match:
                        if len(buf) > 100000:
                            buf = buf[-10000:]
                        break
                    can_id = match.group(1).decode().upper()
                    if can_id == fob_id:
                        with frame_lock:
                            frames.append((time.time(), match.group(3).decode().lower()))
                    buf = buf[match.end():]
            except socket.timeout:
                continue

    threading.Thread(target=reader, daemon=True).start()

    def press(button: str, barrier: threading.Barrier) -> None:
        barrier.wait()
        req = urllib.request.Request(
            web + "/press",
            data=json.dumps({"button": button}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                response.read()
        except Exception as exc:
            print(button, "ERROR", exc)

    base = ["LOCK", "HORN", "IMMOB_ARM", "IMMOB_DISARM"]
    buttons = [base[i % len(base)] for i in range(args.requests)]
    barrier = threading.Barrier(len(buttons) + 1)
    threads = [threading.Thread(target=press, args=(b, barrier)) for b in buttons]

    print(f"[+] Starting {len(threads)} simultaneous /press requests")
    start = time.time()
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()
    time.sleep(1)

    with frame_lock:
        captured = [payload for ts, payload in frames if ts >= start - 0.1]

    print(f"\nCaptured {fob_id} frames:")
    for payload in captured:
        print(" ", " ".join(payload[i:i+2] for i in range(0, len(payload), 2)))

    groups = defaultdict(list)
    for payload in captured:
        counter = payload[0:2]
        command = payload[2:4]
        groups[counter].append((command, payload))

    print("\nDuplicate visible counters:")
    found = False
    for counter, values in groups.items():
        if len(values) > 1:
            found = True
            print(f"\nCOUNTER {counter}")
            for command, payload in values:
                print(
                    f"  cmd={command}  "
                    + " ".join(payload[i:i+2] for i in range(0, len(payload), 2))
                )
    if not found:
        print("  None -- counter updates appear serialized.")

    sock.close()


if __name__ == "__main__":
    main()
