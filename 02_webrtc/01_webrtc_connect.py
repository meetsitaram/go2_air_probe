#!/usr/bin/env python3
"""
STEP 02a — WebRTC Connection Test
───────────────────────────────────
Tests whether a WebRTC connection to the Go2 can be established and
whether the data channel is open and alive.

Run:
    python 02_webrtc/01_webrtc_connect.py --mode ap
    python 02_webrtc/01_webrtc_connect.py --mode sta --ip 192.168.1.42

What to expect on Go2 Air:
    ✅  Connection established — WebRTC is the primary API for Air/Pro
    ❌  Connection refused — close the Unitree phone app first (only 1 client at a time)
"""

import sys
import os
import asyncio
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.common import (
    base_parser, go2_ip_for_mode,
    header, ok, fail, warn, info,
)

try:
    from unitree_webrtc_connect.webrtc_driver import UnitreeWebRTCConnection, WebRTCConnectionMethod
except ImportError:
    print("❌  unitree_webrtc_connect not installed. Run: pip install unitree_webrtc_connect")
    sys.exit(1)


def build_connection(args):
    """Build the appropriate WebRTC connection based on CLI args."""
    if args.mode == "ap":
        info("Connecting in AP mode (Go2 hotspot) ...")
        return UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalAP)
    elif args.mode == "sta":
        ip = go2_ip_for_mode(args)
        if args.serial:
            info(f"Connecting in STA mode via serial {args.serial} ...")
            return UnitreeWebRTCConnection(
                WebRTCConnectionMethod.LocalSTA,
                serialNumber=args.serial
            )
        else:
            info(f"Connecting in STA mode via IP {ip} ...")
            return UnitreeWebRTCConnection(
                WebRTCConnectionMethod.LocalSTA,
                ip=ip
            )
    elif args.mode == "lan":
        warn("LAN mode uses CycloneDDS, not WebRTC. See Step 03 for DDS probing.")
        warn("Attempting STA-style WebRTC connection to LAN IP anyway ...")
        ip = go2_ip_for_mode(args)
        return UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalSTA, ip=ip)


async def run(args):
    header(f"STEP 02a — WebRTC Connection  [{args.mode.upper()} mode]")
    info("⚠️  Make sure the Unitree phone app is DISCONNECTED before running this.")
    info("    Only one WebRTC client can be connected at a time.\n")

    conn = build_connection(args)
    if conn is None:
        sys.exit(1)

    try:
        await asyncio.wait_for(conn.connect(), timeout=15)
    except asyncio.TimeoutError:
        fail("Connection timed out after 15 seconds")
        warn("Try: close phone app, reconnect to Go2 WiFi, retry")
        sys.exit(1)
    except Exception as e:
        fail(f"Connection failed: {e}")
        warn("Common fixes:\n"
             "  • Close the Unitree Go app on your phone\n"
             "  • Make sure Go2 is powered on and reachable\n"
             "  • Wait 30s after powering on the Go2")
        sys.exit(1)

    if conn.isConnected:
        ok("WebRTC fully connected and validated!")
    else:
        warn("connect() returned but isConnected is False — partial connection")

    info("\nNext step: probe live data topics")
    info("  python 02_webrtc/02_webrtc_data.py --mode " + args.mode +
         (f" --ip {args.ip}" if args.ip else ""))

    await conn.disconnect()


def main():
    args = base_parser("Step 02a — WebRTC connection test").parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
