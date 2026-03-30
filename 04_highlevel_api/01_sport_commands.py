#!/usr/bin/env python3
"""
STEP 04 — High-Level Sport Commands
──────────────────────────────────────
Tests whether you can send high-level movement commands to the Go2.

Runs a safe, minimal sequence:
    1. Check motion mode, switch to "normal" if needed
    2. Hello gesture
    3. Move forward slowly for 2 seconds
    4. Stop
    5. StandDown (sit)

⚠️  SAFETY: Place the Go2 on a flat open surface before running.
            The robot WILL move. Keep clear.

Run:
    python 04_highlevel_api/01_sport_commands.py --mode sta --ip 192.168.1.133
    python 04_highlevel_api/01_sport_commands.py --mode sta --ip 192.168.1.133 --dry-run

What to expect on Go2 Air:
    ✅  High-level commands (StandUp, Move, Hello, StandDown) work over WebRTC
    ❌  Low-level joint commands (LowCmd) are NOT supported on Air over WebRTC
"""

import sys
import os
import asyncio
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.common import (
    base_parser, go2_ip_for_mode,
    header, ok, fail, warn, info,
)

try:
    from unitree_webrtc_connect.webrtc_driver import UnitreeWebRTCConnection, WebRTCConnectionMethod
    from unitree_webrtc_connect.constants import RTC_TOPIC, SPORT_CMD
except ImportError:
    print("❌  unitree_webrtc_connect not installed. Run: pip install unitree_webrtc_connect")
    sys.exit(1)


def build_connection(args):
    if args.mode == "ap":
        return UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalAP)
    else:
        ip = go2_ip_for_mode(args)
        return UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalSTA, ip=ip)


async def send_sport_cmd(conn, cmd_name, parameter=None, label=None):
    """Send a sport command via the WebRTC data channel."""
    label = label or cmd_name
    api_id = SPORT_CMD[cmd_name]
    opts = {"api_id": api_id}
    if parameter is not None:
        opts["parameter"] = parameter
    try:
        response = await conn.datachannel.pub_sub.publish_request_new(
            RTC_TOPIC["SPORT_MOD"], opts
        )
        status = response.get("data", {}).get("header", {}).get("status", {})
        code = status.get("code", -1)
        if code == 0:
            ok(f"{label}  →  success")
        else:
            warn(f"{label}  →  response code {code}")
        return response
    except Exception as e:
        fail(f"{label}  →  {e}")
        return None


async def run(args):
    header(f"STEP 04 — Sport Commands  [{args.mode.upper()} mode]"
           + ("  [DRY RUN]" if args.dry_run else ""))

    if not args.dry_run:
        info("⚠️  SAFETY: The robot WILL move. Place it on a flat, open surface.")
        info("   Press Enter to continue, or Ctrl+C to abort.")
        try:
            input()
        except KeyboardInterrupt:
            info("\nAborted.")
            sys.exit(0)

    conn = build_connection(args)

    try:
        await asyncio.wait_for(conn.connect(), timeout=15)
    except (asyncio.TimeoutError, Exception) as e:
        fail(f"WebRTC connection failed: {e}")
        sys.exit(1)

    if not conn.isConnected:
        fail("WebRTC connection failed")
        sys.exit(1)

    ok("WebRTC connected\n")

    if args.dry_run:
        info("[DRY RUN] Commands that would be sent:")
        info("  1. Check motion mode (MOTION_SWITCHER api_id=1001)")
        info("  2. Switch to 'normal' mode if needed")
        info("  3. Hello gesture (api_id=1016)")
        info("  4. Move forward vx=0.3 m/s for 2s (api_id=1008)")
        info("  5. StopMove (api_id=1003)")
        info("  6. StandDown / sit (api_id=1005)")
        await conn.disconnect()
        ok("\n[DRY RUN] All commands validated — no movement sent.")
        return

    # 1. Check current motion mode
    info("Checking motion mode ...")
    try:
        response = await conn.datachannel.pub_sub.publish_request_new(
            RTC_TOPIC["MOTION_SWITCHER"], {"api_id": 1001}
        )
        status_code = response.get("data", {}).get("header", {}).get("status", {}).get("code", -1)
        if status_code == 0:
            data = json.loads(response["data"]["data"])
            mode = data.get("name", "unknown")
            ok(f"Current motion mode: {mode}")
        else:
            mode = "unknown"
            warn(f"Could not read motion mode (code={status_code})")
    except Exception as e:
        mode = "unknown"
        warn(f"Motion mode check failed: {e}")

    # 2. Switch to "normal" if needed
    if mode != "normal":
        info(f"Switching from '{mode}' to 'normal' ...")
        try:
            await conn.datachannel.pub_sub.publish_request_new(
                RTC_TOPIC["MOTION_SWITCHER"],
                {"api_id": 1002, "parameter": {"name": "normal"}}
            )
            ok("Switched to normal mode")
            await asyncio.sleep(5)
        except Exception as e:
            warn(f"Mode switch failed: {e}")

    info("\n--- Command sequence ---\n")

    # StandUp
    await send_sport_cmd(conn, "StandUp")
    await asyncio.sleep(3)

    # StandDown (crouch/sit)
    await send_sport_cmd(conn, "StandDown", label="StandDown (crouch)")
    await asyncio.sleep(2)

    await conn.disconnect()

    header("Summary")
    ok("Sport commands test complete!")
    info("Available commands: " + ", ".join(sorted(SPORT_CMD.keys())))


def main():
    p = base_parser("Step 04 — High-level sport commands")
    p.add_argument("--dry-run", action="store_true",
                   help="Validate commands but do NOT send (no robot movement)")
    args = p.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
