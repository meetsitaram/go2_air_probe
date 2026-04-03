#!/usr/bin/env python3
"""
STEP 02f — Voxel Point Cloud Debug
────────────────────────────────────
Subscribes to rt/utlidar/voxel_map_compressed using the NATIVE decoder
(not libvoxel), which returns actual XYZ world-frame point cloud coords.

Based on the official example:
  unitree_webrtc_connect/examples/go2/data_channel/lidar/lidar_stream.py

Run:
    python 02_webrtc/06_voxel_debug.py --mode sta --ip 192.168.1.133
"""

import sys
import os
import asyncio
import json
import math
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.common import base_parser, header, ok, fail, warn, info

try:
    from unitree_webrtc_connect.webrtc_driver import UnitreeWebRTCConnection, WebRTCConnectionMethod
    from unitree_webrtc_connect.constants import RTC_TOPIC
except ImportError:
    print("unitree_webrtc_connect not installed.")
    sys.exit(1)


DURATION = 10


def build_connection(args):
    if args.mode == "ap":
        return UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalAP)
    else:
        ip = args.ip or "192.168.123.161"
        return UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalSTA, ip=ip)


async def run(args):
    header(f"STEP 02f — Voxel Point Cloud Debug  [{args.mode.upper()} mode]")
    info("Using NATIVE decoder (LZ4 → bit array → XYZ world coords)\n")

    samples = []
    robot_poses = []

    def on_voxel(msg):
        d = msg.get("data", msg)
        if isinstance(d, str):
            d = json.loads(d)

        decoded = d.get("data", None)
        meta = {
            "resolution": d.get("resolution"),
            "origin": d.get("origin"),
            "width": d.get("width"),
        }

        if decoded is not None and len(samples) < 5:
            samples.append({"meta": meta, "decoded": decoded})

    def on_pose(msg):
        d = msg.get("data", msg)
        if isinstance(d, str):
            d = json.loads(d)
        pose_wrapper = d.get("pose", d)
        pos = pose_wrapper.get("position", {})
        ori = pose_wrapper.get("orientation", {})
        if isinstance(pos, dict) and len(robot_poses) < 10:
            w = ori.get("w", 1.0)
            x = ori.get("x", 0.0)
            y = ori.get("y", 0.0)
            z = ori.get("z", 0.0)
            siny = 2.0 * (w * z + x * y)
            cosy = 1.0 - 2.0 * (y * y + z * z)
            yaw = math.atan2(siny, cosy)
            robot_poses.append({
                "x": pos.get("x", 0),
                "y": pos.get("y", 0),
                "z": pos.get("z", 0),
                "yaw": yaw,
            })

    conn = build_connection(args)
    await asyncio.wait_for(conn.connect(), timeout=15)
    ok("Connected")

    # Switch to native decoder (returns actual XYZ points, not mesh)
    conn.datachannel.set_decoder(decoder_type='native')
    ok("Switched to NATIVE decoder")

    try:
        await conn.datachannel.disableTrafficSaving(True)
        ok("Traffic saving disabled")
    except Exception as e:
        warn(f"Could not disable traffic saving: {e}")

    # Turn on lidar (as per official example)
    conn.datachannel.pub_sub.publish_without_callback("rt/utlidar/switch", "on")
    ok("Published lidar switch ON")

    conn.datachannel.pub_sub.subscribe("rt/utlidar/voxel_map_compressed", on_voxel)
    conn.datachannel.pub_sub.subscribe(RTC_TOPIC["ROBOTODOM"], on_pose)

    info(f"\nCollecting data for {DURATION}s ...\n")
    await asyncio.sleep(DURATION)
    await conn.disconnect()

    if robot_poses:
        rp = robot_poses[-1]
        ok(f"Robot pose: x={rp['x']:.3f}  y={rp['y']:.3f}  z={rp['z']:.3f}  "
           f"yaw={math.degrees(rp['yaw']):.1f}°")
    else:
        warn("No robot pose received")

    if not samples:
        fail("No voxel data received!")
        return

    header(f"Point Cloud Analysis ({len(samples)} samples)")

    for idx, s in enumerate(samples[:3]):
        meta = s["meta"]
        decoded = s["decoded"]

        info(f"\n--- Sample {idx} ---")
        info(f"  Meta: resolution={meta['resolution']}  "
             f"origin={meta['origin']}  width={meta['width']}")

        info(f"  Decoded keys: {list(decoded.keys())}")

        points = decoded.get("points", None)
        if points is None:
            warn("  No 'points' key in decoded data")
            for k, v in decoded.items():
                info(f"    {k}: type={type(v).__name__}, "
                     f"len={len(v) if hasattr(v, '__len__') else '?'}")
            continue

        if isinstance(points, np.ndarray):
            info(f"  Points: shape={points.shape}  dtype={points.dtype}")
        else:
            info(f"  Points: type={type(points).__name__}  len={len(points)}")

        if len(points) == 0:
            warn("  Empty point cloud!")
            continue

        pts = np.asarray(points)
        if pts.ndim == 1:
            pts = pts.reshape(-1, 3)

        info(f"  X range: [{pts[:,0].min():.3f}, {pts[:,0].max():.3f}]")
        info(f"  Y range: [{pts[:,1].min():.3f}, {pts[:,1].max():.3f}]")
        info(f"  Z range: [{pts[:,2].min():.3f}, {pts[:,2].max():.3f}]")

        info(f"\n  First 10 points:")
        for i in range(min(10, len(pts))):
            info(f"    [{i}] x={pts[i,0]:.3f}  y={pts[i,1]:.3f}  z={pts[i,2]:.3f}")

        if robot_poses:
            rp = robot_poses[-1]
            dists = np.sqrt(
                (pts[:,0] - rp['x'])**2 +
                (pts[:,1] - rp['y'])**2
            )
            info(f"\n  2D distance from robot:")
            info(f"    min={dists.min():.3f}m  max={dists.max():.3f}m  "
                 f"mean={dists.mean():.3f}m")
            info(f"    Points within 1m: {np.sum(dists < 1.0)}")
            info(f"    Points within 3m: {np.sum(dists < 3.0)}")

            # Height relative to robot
            rel_z = pts[:,2] - rp['z']
            info(f"\n  Height relative to robot (z - robot_z):")
            info(f"    min={rel_z.min():.3f}m  max={rel_z.max():.3f}m")
            obstacle_band = (rel_z >= 0.05) & (rel_z <= 0.6)
            info(f"    Points in obstacle band (0.05-0.6m): {np.sum(obstacle_band)}")

    info("\nDone.")


def main():
    args = base_parser("Step 02f — Voxel debug").parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
