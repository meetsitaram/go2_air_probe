#!/usr/bin/env python3
"""
06_audio/01_audio_probe.py — Probe Go2 audio capabilities over WebRTC

Tests:
  1. Enable audio channel and listen for microphone frames
  2. Query stored audio file list and play mode
  3. Upload a test beep WAV, play it, then clean up
  4. Subscribe to player state stream

Usage:
  python 01_audio_probe.py --mode sta --ip 192.168.1.133
"""

import asyncio
import base64
import hashlib
import json
import logging
import math
import os
import struct
import sys
import wave

logging.basicConfig(level=logging.FATAL)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.common import ok, fail, warn, info, header, base_parser, go2_ip_for_mode
from unitree_webrtc_connect.webrtc_driver import (
    UnitreeWebRTCConnection,
    WebRTCConnectionMethod,
)
from unitree_webrtc_connect.constants import RTC_TOPIC, AUDIO_API


# ──────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────

async def audio_request(conn, api_id, parameter=None):
    """Send an audiohub request and return the response."""
    return await conn.datachannel.pub_sub.publish_request_new(
        RTC_TOPIC.get("AUDIO_HUB_REQ", "rt/api/audiohub/request"),
        {"api_id": api_id, "parameter": json.dumps(parameter or {})},
    )


def make_beep(path, freq=440, duration=1.5, sample_rate=44100, amplitude=0.9):
    """Generate a short sine-wave WAV file."""
    n_samples = int(sample_rate * duration)
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        for i in range(n_samples):
            val = int(amplitude * 32767 * math.sin(2 * math.pi * freq * i / sample_rate))
            wf.writeframes(struct.pack("<h", val))


def get_field(item, *keys):
    """Look up a field trying both UPPER and lower case keys."""
    for k in keys:
        if k in item:
            return item[k]
        if k.upper() in item:
            return item[k.upper()]
        if k.lower() in item:
            return item[k.lower()]
    return ""


# ──────────────────────────────────────────────────────────
# Main probe
# ──────────────────────────────────────────────────────────

async def main(ip: str):
    conn = UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalSTA, ip=ip)
    await asyncio.wait_for(conn.connect(), timeout=15)
    ok("Connected")

    play_states = []
    def on_play_state(msg):
        play_states.append(msg)
    conn.datachannel.pub_sub.subscribe(
        RTC_TOPIC.get("AUDIO_HUB_PLAY_STATE", "rt/audiohub/player/state"),
        on_play_state,
    )

    # ── 1. Audio channel & microphone ────────────────────
    header("1. Audio channel & microphone")
    try:
        conn.audio.switchAudioChannel(True)
        ok("Audio channel enabled")
    except Exception as e:
        fail(f"Could not enable audio channel: {e}")

    audio_frames = []
    async def on_audio_frame(frame):
        audio_frames.append(frame)
    conn.audio.add_track_callback(on_audio_frame)

    info("Listening for microphone frames (5 s)...")
    await asyncio.sleep(5)
    if audio_frames:
        f = audio_frames[0]
        ok(f"Received {len(audio_frames)} frames "
           f"(format={f.format.name}, rate={f.sample_rate})")
    else:
        warn("No microphone frames received")

    # ── 2. Query audio list & play mode ──────────────────
    header("2. Query audio list & play mode")
    try:
        resp = await asyncio.wait_for(
            audio_request(conn, AUDIO_API["GET_AUDIO_LIST"]), timeout=5
        )
        data_str = resp.get("data", {}).get("data", "{}") if isinstance(resp, dict) else "{}"
        parsed = json.loads(data_str) if isinstance(data_str, str) else data_str
        audio_list = parsed.get("audio_list", [])
        ok(f"Audio list: {len(audio_list)} file(s)")
        for item in audio_list:
            info(f"  {json.dumps(item, default=str)[:200]}")
    except asyncio.TimeoutError:
        warn("GET_AUDIO_LIST timed out")
        audio_list = []
    except Exception as e:
        fail(f"GET_AUDIO_LIST error: {e}")
        audio_list = []

    try:
        resp = await asyncio.wait_for(
            audio_request(conn, AUDIO_API["GET_PLAY_MODE"]), timeout=5
        )
        data_str = resp.get("data", {}).get("data", "{}") if isinstance(resp, dict) else "{}"
        parsed = json.loads(data_str) if isinstance(data_str, str) else data_str
        ok(f"Play mode: {parsed.get('play_mode', 'unknown')}")
    except asyncio.TimeoutError:
        warn("GET_PLAY_MODE timed out")

    # ── 3. Upload, play, and delete a test beep ──────────
    header("3. Upload & play test beep (440 Hz, 1.5 s)")
    beep_path = "/tmp/go2_test_beep.wav"
    make_beep(beep_path)
    with open(beep_path, "rb") as f:
        raw = f.read()
    md5 = hashlib.md5(raw).hexdigest()
    b64 = base64.b64encode(raw).decode()
    chunks = [b64[i : i + 4096] for i in range(0, len(b64), 4096)]
    info(f"Uploading {len(chunks)} chunks ({len(raw)} bytes)...")

    for i, chunk in enumerate(chunks, 1):
        await audio_request(conn, AUDIO_API["UPLOAD_AUDIO_FILE"], {
            "file_name": "test_beep",
            "file_type": "wav",
            "file_size": len(raw),
            "current_block_index": i,
            "total_block_number": len(chunks),
            "block_content": chunk,
            "current_block_size": len(chunk),
            "file_md5": md5,
            "create_time": int(asyncio.get_event_loop().time() * 1000),
        })
        await asyncio.sleep(0.05)
    ok("Upload complete")

    await asyncio.sleep(1)
    resp = await asyncio.wait_for(
        audio_request(conn, AUDIO_API["GET_AUDIO_LIST"]), timeout=5
    )
    data_str = resp.get("data", {}).get("data", "{}") if isinstance(resp, dict) else "{}"
    parsed = json.loads(data_str) if isinstance(data_str, str) else data_str
    audio_list = parsed.get("audio_list", [])

    if not audio_list:
        fail("Upload failed — audio list is still empty")
        await conn.disconnect()
        return

    item = audio_list[0]
    uid = get_field(item, "unique_id")
    name = get_field(item, "custom_name")
    ok(f'Found "{name}" — UUID: {uid}')

    info("Playing — listen to robot speaker...")
    await audio_request(conn, AUDIO_API["SELECT_START_PLAY"], {"unique_id": uid})
    await asyncio.sleep(5)

    if play_states:
        last_data = play_states[-1].get("data", "{}")
        state = json.loads(last_data) if isinstance(last_data, str) else last_data
        ok(f'Player: {state.get("play_state")}, is_playing={state.get("is_playing")}')
        cur = state.get("current_audio_custom_name", "")
        if cur:
            info(f"  Currently playing: {cur}")
    else:
        warn("No player state updates received")

    info("Deleting test file...")
    await audio_request(conn, AUDIO_API["SELECT_DELETE"], {"unique_id": uid})
    ok(f'Deleted "{name}"')

    # ── 4. Summary ───────────────────────────────────────
    header("Audio Probe Summary")
    info(f"Microphone frames:     {len(audio_frames)}")
    info(f"Player state messages: {len(play_states)}")
    info(f"Audio upload+play:     {'PASS' if play_states else 'UNKNOWN'}")

    await conn.disconnect()


if __name__ == "__main__":
    parser = base_parser("Probe Go2 audio capabilities over WebRTC")
    args = parser.parse_args()
    ip = go2_ip_for_mode(args)
    asyncio.run(main(ip))
