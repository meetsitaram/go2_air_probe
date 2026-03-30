# Go2 Air — Step-by-Step Hardware Probe

A skeleton repo for systematically probing what is accessible on the **Unitree Go2 Air**
from an external computer (laptop or companion computer on the robot's back).

Run each step in order. Each script is self-contained, prints clear PASS/FAIL output,
and tells you what to try next.

---

## Setup

### 1. System dependencies

```bash
# Linux (Debian / Ubuntu)
sudo apt update && sudo apt install -y portaudio19-dev

# macOS
brew install portaudio
```

### 2. Create a virtual environment and install packages

```bash
uv venv            # creates .venv in the repo root
uv pip install -r requirements.txt
```

Or without `uv`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> **Note:** `unitree_sdk2_python` (CycloneDDS) only works on Linux.
> `unitree_webrtc_connect` works on Linux, Mac, and Windows.

---

## Steps

| Step | Folder | What it tests |
|------|--------|---------------|
| 01 | `01_network/` | Can you reach the Go2 at all? WiFi hotspot vs LAN cable |
| 02 | `02_webrtc/` | Can you open a WebRTC connection and read live data? |
| 03 | `03_cyclonedds/` | Can you access DDS topics directly? (Linux + EDU/firmware) |
| 04 | `04_highlevel_api/` | Can you send movement commands (move, sit, stand)? |
| 05 | `05_virtual_controller/` | Can you inject controller button presses from your computer? |

---

## Connection Modes

### WiFi Hotspot (AP Mode) — works on all models
The Go2 broadcasts its own WiFi network named `GO2-XXXXXX`.
Connect your computer to that network, then run scripts with `--mode ap`.

### Home Router (STA Mode) — works on all models
Connect Go2 to your home WiFi via the Unitree app.
Both your computer and the Go2 are on the same network.
Find the Go2's IP in the app: **Device → Data → Automatic Machine Inspection → STA Network: wlan0**
Run scripts with `--mode sta --ip <GO2_IP>`.

### Direct LAN Cable (Ethernet) — EDU only by default
Connect Ethernet cable to the rear port of the Go2.
Set your computer's IP to `192.168.123.99`, mask `255.255.255.0`.
Run scripts with `--mode lan --interface eth0` (or whatever your interface is named).

---

## Tested Results — Go2 Air (March 2026)

Tested over **WiFi STA mode** (Go2 connected to home router) using
`unitree_webrtc_connect` v2.0.4.

### What works

| Capability | Topic / Channel | Rate | Notes |
|-----------|----------------|------|-------|
| Network ping | ICMP | — | STA mode confirmed; LAN unreliable on Air |
| WebRTC connection | data channel | — | Connects in ~1s, data channel validated |
| IMU + motor state | `rt/lf/lowstate` | ~1 Hz | RPY angles, motor positions, temperatures |
| Robot pose (odometry) | `rt/utlidar/robot_pose` | ~19 Hz | Position (x,y,z) + orientation quaternion in `odom` frame |
| LiDAR health | `rt/utlidar/lidar_state` | ~5 Hz | Software version, rotation speed (~12,900 RPM), error state |
| Camera video | WebRTC video channel | ~12.5 fps | 1280×720 H.264; use `conn.video.add_track_callback()` |
| Sport commands | `rt/api/sport/request` | on demand | See **Sport Commands** section below |
| Motion mode switching | `rt/api/motion_switcher/request` | on demand | Read current mode, switch between `normal` / `ai` / etc. |

### What does NOT work on Air

| Capability | Topic | Notes |
|-----------|-------|-------|
| Sport mode state | `rt/sportmodestate` | No messages; likely EDU/Pro only via DDS |
| Wireless controller (read) | `rt/wirelesscontroller` | No messages; controller input not exposed over WebRTC |
| LiDAR point cloud | `rt/utlidar/voxel_map_compressed` | No data; LiDAR runs internally but point cloud not streamed |
| Virtual controller injection | `rt/wirelesscontroller` (write) | Data channel accepts messages but firmware ignores them |
| Direct LAN (Ethernet) | 192.168.123.161 | Responds briefly then drops; not usable on Air without firmware mod |
| CycloneDDS topics | DDS over LAN | Requires EDU or firmware unlock |

### Sport Commands — Tested on Go2 Air

All sport commands are sent via `publish_request_new` on the `rt/api/sport/request` topic.
Commands that take parameters use `{"x": ..., "y": ..., "z": ...}` as a JSON string.

**Parameter key convention:** The Go2 firmware expects `x`, `y`, `z` keys (matching the
CycloneDDS SDK), **not** descriptive names like `roll`/`pitch`/`yaw`. Commands sent with
wrong keys are silently ignored.

#### Confirmed working

| Command | API ID | Parameters | Description |
|---------|--------|-----------|-------------|
| `StandUp` | 1004 | none | Stand up from crouched position |
| `StandDown` | 1005 | none | Crouch / lie down |
| `BalanceStand` | 1002 | none | Enter active balancing mode (required for Euler, Move, BodyHeight) |
| `StopMove` | 1003 | none | Stop all movement |
| `Euler` | 1007 | `x`=roll, `y`=pitch, `z`=yaw (radians) | Tilt body in place — feet stay planted. Requires BalanceStand. |
| `Move` | 1008 | `x`=fwd vel, `y`=lateral vel, `z`=yaw vel (m/s, rad/s) | Walk / step-turn. `x=0,y=0,z=±0.5` turns in place. Requires BalanceStand. Send repeatedly (~2 Hz) for sustained motion. |
| `BodyHeight` | 1013 | `data`=height offset (m) | Adjust standing height. Acts as offset from default (~30.5 cm). Only raises slightly (+1.5 cm at +0.10); cannot lower below default. Requires BalanceStand. |

#### Notes on tested commands

- **Euler does NOT work while crouched (StandDown)** — the command is silently ignored.
  Sequence must be: `StandUp` → `BalanceStand` → `Euler`.
- **Move** is a velocity command. Send it repeatedly (every ~500 ms) for continuous motion.
  A single send produces a brief movement then the robot stops. Use `StopMove` to halt.
- **BodyHeight** only provides a small upward offset from the default standing height.
  To fully lower the robot, use `StandDown` instead.

#### All available sport command IDs (from `unitree_webrtc_connect`)

| Command | API ID | | Command | API ID |
|---------|--------|-|---------|--------|
| Damp | 1001 | | BalanceStand | 1002 |
| StopMove | 1003 | | StandUp | 1004 |
| StandDown | 1005 | | RecoveryStand | 1006 |
| Euler | 1007 | | Move | 1008 |
| Sit | 1009 | | RiseSit | 1010 |
| SwitchGait | 1011 | | Trigger | 1012 |
| BodyHeight | 1013 | | FootRaiseHeight | 1014 |
| SpeedLevel | 1015 | | Hello | 1016 |
| Stretch | 1017 | | TrajectoryFollow | 1018 |
| ContinuousGait | 1019 | | Content | 1020 |
| Wallow | 1021 | | Dance1 | 1022 |
| Dance2 | 1023 | | GetBodyHeight | 1024 |
| GetFootRaiseHeight | 1025 | | GetSpeedLevel | 1026 |
| SwitchJoystick | 1027 | | Pose | 1028 |
| Scrape | 1029 | | FrontFlip | 1030 |
| FrontJump | 1031 | | FrontPounce | 1032 |
| WiggleHips | 1033 | | GetState | 1034 |
| EconomicGait | 1035 | | FingerHeart | 1036 |
| StandOut | 1039 | | LeftFlip | 1042 |
| RightFlip | 1043 | | BackFlip | 1044 |
| LeadFollow | 1045 | | FreeWalk | 1045 |
| Standup | 1050 | | CrossWalk | 1051 |
| Handstand | 1301 | | CrossStep | 1302 |
| OnesidedStep | 1303 | | Bound | 1304 |
| MoonWalk | 1305 | | — | — |

> Not all commands are available on Go2 Air — many (flips, handstand, etc.) require
> Go2 Pro/EDU hardware or specific firmware versions. Unsupported commands are silently ignored.

---

### API notes

The `unitree_webrtc_connect` v2.0.4 API is **fully async**:

```python
import asyncio
from unitree_webrtc_connect.webrtc_driver import UnitreeWebRTCConnection, WebRTCConnectionMethod
from unitree_webrtc_connect.constants import RTC_TOPIC, SPORT_CMD

async def main():
    conn = UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalSTA, ip="192.168.1.133")
    await conn.connect()

    # Subscribe to data
    conn.datachannel.pub_sub.subscribe("rt/lf/lowstate", lambda msg: print(msg))

    # Send sport command
    await conn.datachannel.pub_sub.publish_request_new(
        RTC_TOPIC["SPORT_MOD"],
        {"api_id": SPORT_CMD["StandUp"]}
    )

    # Camera frames
    async def on_video(track):
        while True:
            frame = await track.recv()  # av.VideoFrame
    conn.video.add_track_callback(on_video)

    await asyncio.sleep(10)
    await conn.disconnect()

asyncio.run(main())
```

Key imports come from `unitree_webrtc_connect.webrtc_driver`, **not** the
top-level package (which only contains monkey-patches for aioice/aiortc).

---

## Important Notes

- **Only one WebRTC client at a time** — close the Unitree phone app before running these scripts.
- **Cooldown between connections** — wait ~5 seconds after disconnecting before reconnecting, or the data channel may fail to open.
- **Port 8081 errors are normal** — the library tries a legacy HTTP endpoint first, then falls back to multicast discovery. The `Connection refused` errors on port 8081 can be ignored.
- CycloneDDS topics (`rt/wirelesscontroller`, `rt/sportmodestate` etc.) are confirmed on EDU. On Air they are not accessible.
- Scripts are read-only probes unless you explicitly run the movement tests in step 04.
