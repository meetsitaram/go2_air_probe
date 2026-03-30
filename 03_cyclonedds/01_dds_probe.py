#!/usr/bin/env python3
"""
STEP 03 — CycloneDDS Direct Topic Probe
─────────────────────────────────────────
Tries to subscribe to Go2 DDS topics directly using unitree_sdk2_python
(the official Unitree SDK, CycloneDDS-based).

On Go2 Air this is NOT expected to work out of the box — DDS is only
accessible on the internal network that EDU exposes over Ethernet.
Run this anyway to confirm and document what you get.

Run:
    python 03_cyclonedds/01_dds_probe.py --mode lan --interface eth0
    python 03_cyclonedds/01_dds_probe.py --mode sta --ip 192.168.1.42

What to expect on Go2 Air:
    ❌  Likely no messages — CycloneDDS multicast doesn't reach you over WiFi
    ✅  Messages received — you're either on LAN, have firmware access, or
        the router is forwarding multicast (unusual but possible)

Note: This script is Linux-only (unitree_sdk2_python requirement).
"""

import sys
import os
import time
import platform
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.common import (
    base_parser, go2_ip_for_mode,
    header, ok, fail, warn, info,
)

if platform.system() != "Linux":
    print("⚠️  CycloneDDS (unitree_sdk2_python) is Linux-only.")
    print("   Skipping this step on non-Linux platform.")
    sys.exit(0)

try:
    from unitree_sdk2py.core.channel import ChannelSubscriber, ChannelFactoryInitialize
    from unitree_sdk2py.idl.unitree_go.msg.dds_ import WirelessController_
    from unitree_sdk2py.idl.unitree_go.msg.dds_ import SportModeState_
    SDK_OK = True
except ImportError:
    SDK_OK = False


PROBE_DURATION = 10

TOPICS = {
    "rt/wirelesscontroller": WirelessController_ if SDK_OK else None,
    "rt/sportmodestate":     SportModeState_ if SDK_OK else None,
}


def main():
    args = base_parser("Step 03 — CycloneDDS direct topic probe").parse_args()
    header(f"STEP 03 — CycloneDDS Probe  [{args.mode.upper()} mode]")

    if not SDK_OK:
        fail("unitree_sdk2py not installed or import failed.")
        info("Install: pip install unitree_sdk2py")
        info("Note: Linux only.")
        sys.exit(1)

    interface = args.interface
    info(f"Initialising CycloneDDS on interface: {interface}")
    info("(Domain ID 0 — matches the real robot default)\n")

    try:
        ChannelFactoryInitialize(0, interface)
        ok("ChannelFactory initialised")
    except Exception as e:
        fail(f"ChannelFactory init failed: {e}")
        warn("Make sure the network interface name is correct (e.g. eth0, wlan0, enp3s0)")
        warn("Run: ip link show   to list interfaces")
        sys.exit(1)

    received = {t: 0 for t in TOPICS}
    subs = []

    for topic, msg_type in TOPICS.items():
        if msg_type is None:
            continue
        def make_cb(t):
            def cb(msg):
                received[t] += 1
                if received[t] == 1:
                    ok(f"First message on {t}")
                    _print_msg_summary(t, msg)
            return cb
        try:
            sub = ChannelSubscriber(topic, msg_type)
            sub.Init(make_cb(topic), 10)
            subs.append(sub)
            info(f"Subscribed to {topic}")
        except Exception as e:
            warn(f"Failed to subscribe to {topic}: {e}")

    info(f"\nListening for {PROBE_DURATION}s ...\n")
    time.sleep(PROBE_DURATION)

    header("CycloneDDS Summary")
    any_received = False
    for topic, count in received.items():
        if count > 0:
            ok(f"{topic}  →  {count} messages")
            any_received = True
        else:
            fail(f"{topic}  →  0 messages")

    if not any_received:
        warn("\nNo DDS messages received. This is expected for Go2 Air over WiFi.")
        warn("DDS multicast is typically blocked by WiFi routers and only works on")
        warn("a direct Ethernet connection (Go2 EDU rear port).")
        info("\nYour Go2 Air data access path is via WebRTC (Step 02). That's fine.")
    else:
        ok("\nDDS topics are accessible! You have direct SDK access.")

    info("\nNext: python 04_highlevel_api/01_sport_commands.py --mode " + args.mode +
         (f" --ip {args.ip}" if args.ip else ""))


def _print_msg_summary(topic: str, msg):
    """Print a brief human-readable summary of the first received message."""
    try:
        if "wirelesscontroller" in topic:
            print(f"    lx={msg.lx:.2f}  ly={msg.ly:.2f}  "
                  f"rx={msg.rx:.2f}  ry={msg.ry:.2f}  keys=0x{msg.keys:04X}")
        elif "sportmodestate" in topic:
            imu = msg.imu_state
            print(f"    RPY: [{imu.rpy[0]:.3f}, {imu.rpy[1]:.3f}, {imu.rpy[2]:.3f}]")
            print(f"    velocity: [{msg.velocity[0]:.3f}, {msg.velocity[1]:.3f}, {msg.velocity[2]:.3f}]")
        else:
            print(f"    {str(msg)[:200]}")
    except Exception:
        print(f"    (could not parse message)")


if __name__ == "__main__":
    main()
