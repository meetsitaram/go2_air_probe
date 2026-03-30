#!/usr/bin/env python3
"""
STEP 01 — Network Connectivity Probe
─────────────────────────────────────
Tests whether your computer can reach the Go2 at all, and which
connection method works: WiFi hotspot (AP), home router (STA), or
direct LAN cable.

Run:
    python 01_network_probe.py --mode ap          # connected to Go2 hotspot
    python 01_network_probe.py --mode sta --ip 192.168.1.42
    python 01_network_probe.py --mode lan --interface eth0

What to expect on Go2 Air:
    AP mode  → should PASS (Go2 hotspot is always on)
    STA mode → should PASS if you've added Go2 to your WiFi via the app
    LAN mode → likely FAIL unless you have EDU or have applied a firmware patch
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.common import (
    base_parser, go2_ip_for_mode,
    ping, tcp_reachable,
    header, ok, fail, warn, info,
)


# ── Known Go2 service ports ──────────────────────────────────────────────────
WEBRTC_SIGNALLING_PORT = 8081   # WebRTC signalling server
WEB_CONSOLE_PORT       = 9000   # Go2 web console (EDU)
SSH_PORT               = 22     # SSH (EDU / unlocked firmware)


def main():
    args = base_parser("Step 01 — Network connectivity probe").parse_args()
    target_ip = go2_ip_for_mode(args)

    header(f"STEP 01 — Network Probe  [{args.mode.upper()} mode]  target: {target_ip}")

    # ── 1. Ping ──────────────────────────────────────────────────────────────
    info(f"Pinging {target_ip} ...")
    if ping(target_ip):
        ok(f"Ping to {target_ip} succeeded — Go2 is reachable on the network")
    else:
        fail(
            f"Ping to {target_ip} failed.\n"
            "       Possible causes:\n"
            "         • Not connected to Go2's WiFi hotspot (AP mode)\n"
            "         • Go2 not added to your router (STA mode)\n"
            "         • Your computer IP not set to 192.168.123.99/24 (LAN mode)\n"
            "         • Go2 is off or still booting (wait ~30s after power on)"
        )
        sys.exit(1)

    # ── 2. WebRTC signalling port ─────────────────────────────────────────────
    info(f"Checking WebRTC signalling port {WEBRTC_SIGNALLING_PORT} ...")
    if tcp_reachable(target_ip, WEBRTC_SIGNALLING_PORT):
        ok(f"Port {WEBRTC_SIGNALLING_PORT} open — WebRTC API is available")
    else:
        warn(
            f"Port {WEBRTC_SIGNALLING_PORT} not reachable.\n"
            "       WebRTC may still work (some firmware versions use a different handshake).\n"
            "       Proceed to Step 02 and see if the connection succeeds."
        )

    # ── 3. Web console (EDU / Pro indicator) ─────────────────────────────────
    info(f"Checking web console port {WEB_CONSOLE_PORT} ...")
    if tcp_reachable(target_ip, WEB_CONSOLE_PORT):
        ok(f"Port {WEB_CONSOLE_PORT} open — Go2 web console accessible (EDU/Pro indicator)")
    else:
        info(f"Port {WEB_CONSOLE_PORT} not open — normal for Go2 Air")

    # ── 4. SSH ────────────────────────────────────────────────────────────────
    info(f"Checking SSH port {SSH_PORT} ...")
    if tcp_reachable(target_ip, SSH_PORT):
        ok(f"Port {SSH_PORT} open — SSH available (EDU or unlocked firmware)")
    else:
        info(f"Port {SSH_PORT} not open — normal for Go2 Air (no SSH access)")

    # ── Summary ───────────────────────────────────────────────────────────────
    header("Summary")
    info("Go2 is reachable. Proceed to:")
    info("  Step 02 — python 02_webrtc/01_webrtc_connect.py --mode " + args.mode +
         (f" --ip {args.ip}" if args.ip else ""))


if __name__ == "__main__":
    main()
