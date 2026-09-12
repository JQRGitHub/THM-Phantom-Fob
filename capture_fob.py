#!/usr/bin/env python3
"""Correlate Phantom Fob web-button presses with nearby CAN frames.

This script intentionally does not solve or enumerate the missing UNLOCK opcode.

Usage:
    python3 capture_fob.py TARGET_IP
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
    rb"< frame ([0-9A-Fa-f]+) ([0-9.]+) ([0-9A-Fa-f]*) >"
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("target")
    parser.add_argument("--bus", default="vcan0")
    parser.add_argument("--can-port", type=int, default=29536)
    parser.add_argument("--web-port", type=int, default=8080)
    parser.add_argument("--window", type=float, default=0.35)
    args = parser.parse_args()

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
                    with frame_lock:
                        frames.append(
                            (
                                time.time(),
                                match.group(1).decode().upper(),
                                match.group(3).decode().lower(),
                            )
                        )
                    buf = buf[match.end():]
            except socket.timeout:
                continue

    threading.Thread(target=reader, daemon=True).start()

    def press(button: str) -> None:
        data = json.dumps({"button": button}).encode()
        req = urllib.request.Request(
            web + "/press",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        start = time.time()
        print(f"\n============== {button} ==============")
        with urllib.request.urlopen(req, timeout=3) as response:
            print(response.read().decode())

        time.sleep(args.window)
        end = time.time()

        with frame_lock:
            nearby = [f for f in frames if start - 0.05 <= f[0] <= end]

        by_id = defaultdict(list)
        for _, can_id, payload in nearby:
            by_id[can_id].append(payload)

        for can_id in sorted(by_id):
            vals = by_id[can_id]
            unique = list(dict.fromkeys(vals))
            # Highlight relatively quiet or low-diversity IDs around the action.
            if len(vals) <= 5 or len(unique) <= 4:
                print(f"{can_id}: count={len(vals):2} unique={unique[:10]}")

    print("\nCollecting idle baseline...")
    time.sleep(2)

    for button in ["LOCK", "HORN", "IMMOB_ARM", "IMMOB_DISARM"]:
        press(button)
        time.sleep(1)

    sock.close()


if __name__ == "__main__":
    main()
