#!/usr/bin/env python3
"""
STEP 02d — Scan All WebRTC Topics
──────────────────────────────────
Discovers every topic the Go2 publishes over its WebRTC data channel.

Three strategies run in parallel:
  1. RAW TAP — monkey-patch the data channel to log EVERY incoming message
     (before topic filtering). Shows ALL topics and message types.
  2. MASS SUBSCRIBE — subscribe to every known RTC_TOPIC and report which
     ones actually produce data.
  3. SPORT API POLL — call GetState (1034) and SwitchJoystick (1027) to
     probe request/response topics.

Run:
    python 02_webrtc/04_scan_webrtc_topics.py --mode sta --ip 192.168.1.133
    python 02_webrtc/04_scan_webrtc_topics.py --mode ap
"""

import sys
import os
import asyncio
import json
import time
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.common import base_parser, header, ok, fail, warn, info

try:
    from unitree_webrtc_connect.webrtc_driver import (
        UnitreeWebRTCConnection,
        WebRTCConnectionMethod,
    )
    from unitree_webrtc_connect.constants import RTC_TOPIC, SPORT_CMD
except ImportError:
    print("❌  unitree_webrtc_connect not installed. Run: pip install unitree_webrtc_connect")
    sys.exit(1)


PROBE_DURATION = 20  # seconds — long enough to press several buttons

# All known topic strings from the library
ALL_TOPICS = {name: topic for name, topic in RTC_TOPIC.items()}


def build_connection(args):
    if args.mode == "ap":
        return UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalAP)
    else:
        ip = args.ip or "192.168.123.161"
        return UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalSTA, ip=ip)


async def run(args):
    header(f"STEP 02d — Scan All WebRTC Topics  [{args.mode.upper()} mode]")
    info(f"Will listen for {PROBE_DURATION}s with three strategies.\n")
    info("⚠️  Close the Unitree phone app before running.\n")

    conn = build_connection(args)

    try:
        await asyncio.wait_for(conn.connect(), timeout=15)
    except asyncio.TimeoutError:
        fail("WebRTC connection timed out.")
        sys.exit(1)
    except Exception as e:
        fail(f"Connection failed: {e}")
        sys.exit(1)

    if not conn.isConnected:
        fail("WebRTC not connected.")
        sys.exit(1)

    ok("WebRTC connected\n")

    # ── Strategy 1: Raw data channel tap ──────────────────────────────────
    header("Strategy 1 — Raw Data Channel Tap")
    info("Monkey-patching data channel to intercept ALL messages.\n")

    raw_messages = []
    raw_topics_seen = defaultdict(int)
    raw_types_seen = defaultdict(int)

    dc = conn.datachannel

    def raw_log(parsed):
        """Log a parsed JSON message from the data channel."""
        ts = time.time()
        topic = parsed.get("topic", "<no topic>")
        msg_type = parsed.get("type", "<no type>")
        raw_topics_seen[topic] += 1
        raw_types_seen[msg_type] += 1
        raw_messages.append({
            "time": ts,
            "topic": topic,
            "type": msg_type,
            "keys": list(parsed.keys()),
            "data_preview": str(parsed.get("data", ""))[:200],
        })

    # Wrap pub_sub.run_resolve to see every parsed JSON message
    original_run_resolve = dc.pub_sub.run_resolve

    def patched_run_resolve(data):
        if isinstance(data, dict):
            raw_log(data)
        return original_run_resolve(data)

    dc.pub_sub.run_resolve = patched_run_resolve

    # Wrap deal_array_buffer to count binary messages
    if hasattr(dc, 'deal_array_buffer'):
        original_deal_array_buffer = dc.deal_array_buffer

        def patched_deal_array_buffer(data):
            ts = time.time()
            if isinstance(data, bytes):
                raw_messages.append({
                    "time": ts,
                    "binary": True,
                    "length": len(data),
                    "header_hex": data[:16].hex(),
                })
            return original_deal_array_buffer(data)

        dc.deal_array_buffer = patched_deal_array_buffer

    ok("Raw tap installed — intercepting all messages.\n")

    # ── Strategy 2: Mass subscribe ────────────────────────────────────────
    header("Strategy 2 — Mass Subscribe (all known topics)")

    topic_counts = defaultdict(int)
    topic_first_msg = {}

    def make_handler(topic_name, topic_str):
        def handler(msg):
            topic_counts[topic_str] += 1
            if topic_str not in topic_first_msg:
                topic_first_msg[topic_str] = msg
                ok(f"  [{topic_name}] First message on {topic_str}")
                try:
                    preview = json.dumps(msg, indent=2)
                    if len(preview) > 300:
                        preview = preview[:300] + " ..."
                except Exception:
                    preview = str(msg)[:300]
                print(f"      {preview}\n")
        return handler

    subscribed = 0
    for name, topic in sorted(ALL_TOPICS.items()):
        try:
            dc.pub_sub.subscribe(topic, make_handler(name, topic))
            subscribed += 1
        except Exception as e:
            warn(f"  Could not subscribe to {topic}: {e}")

    ok(f"Subscribed to {subscribed} topics.\n")
    info("Waiting for data ...\n")

    # ── Strategy 3: Sport API polling ─────────────────────────────────────
    header("Strategy 3 — Sport API Queries")

    async def try_sport_query(api_name, api_id):
        info(f"  Querying {api_name} (API ID {api_id}) ...")
        try:
            resp = await asyncio.wait_for(
                dc.pub_sub.publish_request_new(
                    RTC_TOPIC["SPORT_MOD"],
                    {"api_id": api_id},
                ),
                timeout=5,
            )
            ok(f"  {api_name} response:")
            try:
                preview = json.dumps(resp, indent=2)
                if len(preview) > 500:
                    preview = preview[:500] + " ..."
            except Exception:
                preview = str(resp)[:500]
            print(f"      {preview}\n")
            return resp
        except asyncio.TimeoutError:
            warn(f"  {api_name} — no response (timed out)")
            return None
        except Exception as e:
            warn(f"  {api_name} — error: {e}")
            return None

    await try_sport_query("GetState", SPORT_CMD.get("GetState", 1034))
    await try_sport_query("SwitchJoystick", SPORT_CMD.get("SwitchJoystick", 1027))

    # ── Collect data for the main listening period ────────────────────────
    header("Listening Phase")
    info(f"Collecting data for {PROBE_DURATION}s ...")
    info("Collecting ...\n")

    start = time.time()
    last_count_report = start
    while time.time() - start < PROBE_DURATION:
        await asyncio.sleep(1)
        elapsed = int(time.time() - start)
        # Periodic status
        if time.time() - last_count_report >= 5:
            last_count_report = time.time()
            total_raw = len(raw_messages)
            total_sub = sum(topic_counts.values())
            info(f"  [{elapsed}s] raw={total_raw} msgs, subscribed={total_sub} msgs, "
                 f"topics seen={len(raw_topics_seen)}")

    await conn.disconnect()

    # ── Results ───────────────────────────────────────────────────────────
    header("Results — Raw Data Channel Tap")
    if raw_topics_seen:
        info(f"Total distinct topics seen: {len(raw_topics_seen)}\n")
        for topic, count in sorted(raw_topics_seen.items(), key=lambda x: -x[1]):
            marker = "🎮 " if "controller" in topic.lower() or "wireless" in topic.lower() or "joystick" in topic.lower() else "   "
            print(f"  {marker}{topic:50s}  {count:5d} messages")
        print()
    else:
        warn("No raw messages intercepted — tap may not have hooked correctly.\n")

    if raw_types_seen:
        info("Message types seen:")
        for t, c in sorted(raw_types_seen.items(), key=lambda x: -x[1]):
            print(f"      {t:20s}  {c:5d}")
        print()

    # Check for any binary messages
    binary_msgs = [m for m in raw_messages if m.get("binary")]
    if binary_msgs:
        info(f"Binary messages received: {len(binary_msgs)}")
        for bm in binary_msgs[:5]:
            print(f"      len={bm['length']}, header={bm['header_hex']}")
        print()

    header("Results — Mass Subscribe")
    active = {t: c for t, c in topic_counts.items() if c > 0}
    if active:
        info(f"Topics with data: {len(active)} / {subscribed}\n")
        for topic, count in sorted(active.items(), key=lambda x: -x[1]):
            name = next((n for n, t in ALL_TOPICS.items() if t == topic), "?")
            print(f"     [{name:30s}] {topic:50s}  {count:5d} msgs")
    else:
        warn("No subscribed topics received data.")
    print()

    silent = [t for t in ALL_TOPICS.values() if t not in active]
    if silent:
        info(f"Silent topics: {len(silent)}")
        for t in sorted(silent):
            print(f"      {t}")
    print()

    # Show any unknown/unexpected topics (not in RTC_TOPIC)
    known_topic_strs = set(ALL_TOPICS.values())
    unknown = {t: c for t, c in raw_topics_seen.items()
               if t not in known_topic_strs and t != "<no topic>"}
    if unknown:
        header("Unknown Topics (not in RTC_TOPIC constants)")
        ok("Found topics NOT in the library's constants — could be firmware extras:")
        for t, c in sorted(unknown.items(), key=lambda x: -x[1]):
            print(f"      {t:50s}  {c:5d} messages")
            for m in raw_messages:
                if m.get("topic") == t:
                    print(f"        keys: {m.get('keys', [])}")
                    print(f"        data: {m.get('data_preview', 'n/a')[:200]}")
                    break


def main():
    args = base_parser("Step 02d — Scan all WebRTC topics").parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
