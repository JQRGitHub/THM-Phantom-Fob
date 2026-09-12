#!/usr/bin/env python3
"""Minimal socketcand CAN watcher for the Phantom Fob CTF.

Usage:
    python3 watch_can.py TARGET_IP [--bus vcan0] [--ids 12A,429]

If --ids is omitted, all CAN frames are printed.
"""

import argparse
import re
import socket

FRAME_RE = re.compile(
    rb"< frame ([0-9A-Fa-f]+) ([0-9.]+) ([0-9A-Fa-f]+) >"
)


def recv_reply(sock: socket.socket) -> bytes:
    return sock.recv(1024)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", help="CTF target IP or hostname")
    parser.add_argument("--port", type=int, default=29536)
    parser.add_argument("--bus", default="vcan0")
    parser.add_argument(
        "--ids",
        help="Comma-separated CAN IDs to display, e.g. 12A,429. Omit for all.",
    )
    args = parser.parse_args()

    wanted = None
    if args.ids:
        wanted = {x.strip().upper() for x in args.ids.split(",") if x.strip()}

    sock = socket.create_connection((args.target, args.port), timeout=5)
    sock.settimeout(None)

    print("hello:", repr(recv_reply(sock)))
    sock.sendall(f"< open {args.bus} >".encode())
    print("open :", repr(recv_reply(sock)))
    sock.sendall(b"< rawmode >")
    print("raw  :", repr(recv_reply(sock)))

    print("\nWatching CAN traffic. Ctrl-C to stop.\n")

    buf = b""
    try:
        while True:
            data = sock.recv(65535)
            if not data:
                break
            buf += data

            while True:
                match = FRAME_RE.search(buf)
                if not match:
                    if len(buf) > 65536:
                        buf = buf[-4096:]
                    break

                can_id = match.group(1).decode().upper()
                timestamp = match.group(2).decode()
                payload = match.group(3).decode().lower()

                if wanted is None or can_id in wanted:
                    spaced = " ".join(payload[i:i+2] for i in range(0, len(payload), 2))
                    print(f"{timestamp}  {can_id:>3}  {spaced}", flush=True)

                buf = buf[match.end():]
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()


if __name__ == "__main__":
    main()
