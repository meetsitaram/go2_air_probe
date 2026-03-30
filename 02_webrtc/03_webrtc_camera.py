#!/usr/bin/env python3
"""
STEP 02c — WebRTC Camera & LiDAR
──────────────────────────────────
Tests whether the Go2's front camera video stream and LiDAR data
are accessible over WebRTC.

Camera: comes in as an H.264 video stream on the WebRTC video channel.
LiDAR:  state and robot pose come as data channel subscriptions;
        point cloud comes as binary data decoded by the library's
        built-in LibVoxelDecoder.

Run:
    python 02_webrtc/03_webrtc_camera.py --mode ap
    python 02_webrtc/03_webrtc_camera.py --mode sta --ip 192.168.1.133

What to expect on Go2 Air:
    Camera:            ✅  1280x720 @ ~12 fps via WebRTC video channel
    LiDAR state:       ✅  rt/utlidar/lidar_state (~5 Hz)
    Robot pose:        ✅  rt/utlidar/robot_pose (~19 Hz)
    LiDAR point cloud: via binary data channel (LibVoxelDecoder)
"""

import sys
import os
import asyncio
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.common import (
    base_parser, header, ok, fail, warn, info,
)

try:
    from unitree_webrtc_connect.webrtc_driver import UnitreeWebRTCConnection, WebRTCConnectionMethod
    from unitree_webrtc_connect.constants import RTC_TOPIC
except ImportError:
    print("❌  unitree_webrtc_connect not installed. Run: pip install unitree_webrtc_connect")
    sys.exit(1)


PROBE_DURATION = 15

LIDAR_TOPICS = [
    RTC_TOPIC["ULIDAR"],          # rt/utlidar/voxel_map
    RTC_TOPIC["ULIDAR_ARRAY"],    # rt/utlidar/voxel_map_compressed
    RTC_TOPIC["ULIDAR_STATE"],    # rt/utlidar/lidar_state
    RTC_TOPIC["ROBOTODOM"],       # rt/utlidar/robot_pose
]


def build_connection(args):
    if args.mode == "ap":
        return UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalAP)
    else:
        ip = args.ip or "192.168.123.161"
        return UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalSTA, ip=ip)


async def run(args):
    header(f"STEP 02c — Camera & LiDAR  [{args.mode.upper()} mode]")
    info("⚠️  Close the Unitree phone app before running.\n")

    state = {
        "camera_frames": 0,
    }
    lidar_received = {t: 0 for t in LIDAR_TOPICS}

    conn = build_connection(args)

    try:
        await asyncio.wait_for(conn.connect(), timeout=15)
    except asyncio.TimeoutError:
        fail("WebRTC connection timed out. See Step 02a for diagnosis.")
        sys.exit(1)
    except Exception as e:
        fail(f"Connection failed: {e}")
        sys.exit(1)

    if not conn.isConnected:
        fail("WebRTC connection failed. See Step 02a for diagnosis.")
        sys.exit(1)

    ok("WebRTC connected\n")

    # Video track callback
    async def on_video_track(track):
        info("Video track received — reading frames ...")
        while True:
            try:
                frame = await track.recv()
                state["camera_frames"] += 1
                if state["camera_frames"] == 1:
                    ok(f"First camera frame! size={frame.width}x{frame.height}")
            except Exception:
                break

    conn.video.add_track_callback(on_video_track)

    # Enable LiDAR data
    try:
        await conn.datachannel.disableTrafficSaving(True)
    except Exception as e:
        warn(f"Could not disable traffic saving: {e}")

    # Subscribe to LiDAR topics
    def make_handler(topic):
        def handler(msg):
            lidar_received[topic] += 1
            if lidar_received[topic] == 1:
                ok(f"First message on {topic}")
        return handler

    for topic in LIDAR_TOPICS:
        conn.datachannel.pub_sub.subscribe(topic, make_handler(topic))
        info(f"Subscribed to {topic}")

    # Enable video channel
    try:
        conn.video.switchVideoChannel(True)
        info("Video channel enabled")
    except Exception as e:
        warn(f"Could not switch video channel: {e}")

    info(f"\nCollecting data for {PROBE_DURATION}s ...\n")
    await asyncio.sleep(PROBE_DURATION)

    await conn.disconnect()

    header("Camera & LiDAR Summary")

    if state["camera_frames"] > 0:
        fps = state["camera_frames"] / PROBE_DURATION
        ok(f"Camera: {state['camera_frames']} frames received (~{fps:.1f} fps)")
    else:
        fail("Camera: no frames received")

    for topic, count in lidar_received.items():
        if count > 0:
            hz = count / PROBE_DURATION
            ok(f"{topic}  →  {count} messages (~{hz:.1f} Hz)")
        else:
            fail(f"{topic}  →  no messages received")

    info("\nNext: python 03_cyclonedds/01_dds_probe.py --mode " + args.mode +
         (f" --ip {args.ip}" if args.ip else ""))


def main():
    args = base_parser("Step 02c — WebRTC camera & LiDAR probe").parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
