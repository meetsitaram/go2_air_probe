#!/usr/bin/env python3
"""
STEP 02e — LiDAR Point Cloud Probe
────────────────────────────────────
Tests whether the Go2 Air exposes voxel map / point cloud data over WebRTC.

Subscribes to all known utlidar topics (including voxel_map and
voxel_map_compressed) and reports which ones produce data, at what rate,
and what the payload looks like.

Run:
    python 02_webrtc/05_lidar_pointcloud_probe.py --mode ap
    python 02_webrtc/05_lidar_pointcloud_probe.py --mode sta --ip 192.168.1.133

What to check:
    rt/utlidar/robot_pose           — should be ~19 Hz (already confirmed)
    rt/utlidar/lidar_state          — should be ~5 Hz (already confirmed)
    rt/utlidar/voxel_map            — point cloud: UNKNOWN on Go2 Air
    rt/utlidar/voxel_map_compressed — point cloud: UNKNOWN on Go2 Air
"""

import sys
import os
import asyncio
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.common import base_parser, header, ok, fail, warn, info

try:
    from unitree_webrtc_connect.webrtc_driver import UnitreeWebRTCConnection, WebRTCConnectionMethod
    from unitree_webrtc_connect.constants import RTC_TOPIC
except ImportError:
    print("unitree_webrtc_connect not installed. Run: pip install unitree_webrtc_connect")
    sys.exit(1)


TOPICS = [
    RTC_TOPIC["ROBOTODOM"],        # rt/utlidar/robot_pose
    RTC_TOPIC["ULIDAR_STATE"],     # rt/utlidar/lidar_state
    RTC_TOPIC["ULIDAR"],           # rt/utlidar/voxel_map
    RTC_TOPIC["ULIDAR_ARRAY"],     # rt/utlidar/voxel_map_compressed
    RTC_TOPIC["ULIDAR_SWITCH"],    # rt/utlidar/switch
]

DURATION = 15


def build_connection(args):
    if args.mode == "ap":
        return UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalAP)
    else:
        ip = args.ip or "192.168.123.161"
        return UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalSTA, ip=ip)


async def run(args):
    header(f"STEP 02e — LiDAR Point Cloud Probe  [{args.mode.upper()} mode]")
    info("Checks which utlidar topics produce data on this Go2.\n")

    counts = {t: 0 for t in TOPICS}
    sample_keys = {}

    def make_handler(topic):
        def handler(msg):
            counts[topic] += 1
            if counts[topic] == 1:
                ok(f"First message on {topic}")
                d = msg.get("data", msg)
                if isinstance(d, dict):
                    sample_keys[topic] = list(d.keys())[:15]
                else:
                    sample_keys[topic] = [f"type={type(d).__name__}, len={len(d) if hasattr(d, '__len__') else '?'}"]
        return handler

    conn = build_connection(args)

    try:
        await asyncio.wait_for(conn.connect(), timeout=15)
    except Exception as e:
        fail(f"Connection failed: {e}")
        return

    ok("WebRTC connected\n")

    try:
        await conn.datachannel.disableTrafficSaving(True)
        ok("Traffic saving disabled (enables LiDAR data channels)")
    except Exception as e:
        warn(f"Could not disable traffic saving: {e}")

    info("")
    for topic in TOPICS:
        conn.datachannel.pub_sub.subscribe(topic, make_handler(topic))
        info(f"Subscribed to {topic}")

    info(f"\nListening for {DURATION}s ...\n")
    await asyncio.sleep(DURATION)

    await conn.disconnect()

    header("Results")
    for topic in TOPICS:
        c = counts[topic]
        hz = c / DURATION if c > 0 else 0
        keys = ", ".join(sample_keys.get(topic, []))

        if c > 0:
            ok(f"{topic}")
            info(f"    {c} messages  (~{hz:.1f} Hz)")
            if keys:
                info(f"    Keys: {keys}")
        else:
            fail(f"{topic}  —  no messages received")

    info("")
    voxel_ok = counts.get(RTC_TOPIC["ULIDAR"], 0) > 0
    voxel_comp_ok = counts.get(RTC_TOPIC["ULIDAR_ARRAY"], 0) > 0

    if voxel_ok or voxel_comp_ok:
        ok("Point cloud data IS available on this Go2!")
        info("  You can subscribe to voxel_map for obstacle detection.")
    else:
        warn("Point cloud data NOT available on this Go2 Air.")
        info("  Obstacle detection will need to rely on stall detection")
        info("  or the Go2's built-in avoidance.")


def main():
    args = base_parser("Step 02e — LiDAR point cloud probe").parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
