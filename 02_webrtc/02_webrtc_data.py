#!/usr/bin/env python3
"""
STEP 02b — WebRTC Live Data Topics
────────────────────────────────────
Subscribes to key data topics over the WebRTC data channel and prints
whatever arrives. Runs for 10 seconds then summarises what was received.

Topics probed:
    rt/lf/lowstate         — IMU, battery, foot forces (low frequency)
    rt/sportmodestate      — position, velocity, odometry, IMU
    rt/wirelesscontroller  — controller joystick + button states

Run:
    python 02_webrtc/02_webrtc_data.py --mode ap
    python 02_webrtc/02_webrtc_data.py --mode sta --ip 192.168.1.42

Tip: Press buttons on the physical controller while this runs to see
     the wirelesscontroller topic light up.
"""

import sys
import os
import asyncio
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.common import (
    base_parser, header, ok, fail, warn, info,
)

try:
    from unitree_webrtc_connect.webrtc_driver import UnitreeWebRTCConnection, WebRTCConnectionMethod
except ImportError:
    print("❌  unitree_webrtc_connect not installed. Run: pip install unitree_webrtc_connect")
    sys.exit(1)


TOPICS = [
    "rt/lf/lowstate",
    "rt/sportmodestate",
    "rt/wirelesscontroller",
]

PROBE_DURATION = 12  # seconds


def build_connection(args):
    if args.mode == "ap":
        return UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalAP)
    elif args.mode in ("sta", "lan"):
        ip = args.ip or "192.168.123.161"
        return UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalSTA, ip=ip)


async def run(args):
    header(f"STEP 02b — WebRTC Data Topics  [{args.mode.upper()} mode]")
    info(f"Will listen for {PROBE_DURATION}s and report what arrives.\n")
    info("⚠️  Close the Unitree phone app before running.\n")

    received = {t: [] for t in TOPICS}

    conn = build_connection(args)

    try:
        await asyncio.wait_for(conn.connect(), timeout=15)
    except asyncio.TimeoutError:
        fail("Could not connect via WebRTC (timed out). Run Step 02a first to diagnose.")
        sys.exit(1)
    except Exception as e:
        fail(f"Connection failed: {e}")
        sys.exit(1)

    if not conn.isConnected:
        fail("Could not connect via WebRTC. Run Step 02a first to diagnose.")
        sys.exit(1)

    ok("WebRTC connected — subscribing to topics ...\n")

    def make_handler(topic):
        def handler(msg):
            received[topic].append(msg)
            if len(received[topic]) == 1:
                ok(f"First message on {topic}:")
                try:
                    preview = json.dumps(msg, indent=2)[:400]
                except Exception:
                    preview = str(msg)[:400]
                print(f"    {preview}\n")
        return handler

    for topic in TOPICS:
        conn.datachannel.pub_sub.subscribe(topic, make_handler(topic))
        info(f"Subscribed to {topic}")

    info(f"\nListening for {PROBE_DURATION}s ... (press controller buttons now!)\n")
    await asyncio.sleep(PROBE_DURATION)

    await conn.disconnect()

    header("Data Topic Summary")
    for topic, msgs in received.items():
        if msgs:
            ok(f"{topic}  →  {len(msgs)} messages received")
        else:
            fail(f"{topic}  →  no messages received")

    info("\nIf wirelesscontroller shows 0 messages, try pressing buttons on the")
    info("physical controller while the script is running.\n")
    info("Next: python 02_webrtc/03_webrtc_camera.py --mode " + args.mode +
         (f" --ip {args.ip}" if args.ip else ""))


def main():
    args = base_parser("Step 02b — WebRTC data topics probe").parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
