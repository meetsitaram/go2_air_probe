#!/usr/bin/env python3
"""
STEP 05a — Keyboard Controller
────────────────────────────────
Simulates the Unitree wireless controller from your computer keyboard.
Your keypresses are sent to the Go2 as if they came from the physical controller.

This lets you:
  • Control the robot without the physical controller
  • Use unused buttons (F1, F2, etc.) to trigger SO-101 arm actions
  • Test button-based state machines in your code

Keyboard map (while script is running):
  W / S       → left joystick Y (forward / back)
  A / D       → left joystick X (left / right)
  ← / →       → right joystick X (yaw left / right)
  ↑ / ↓       → right joystick Y
  1           → L1
  2           → L2
  3           → R1
  4           → R2
  Q           → A button
  E           → B button
  Z           → X button
  C           → Y button
  F           → F1 (custom — good for arm trigger)
  G           → F2 (custom)
  ESC / Ctrl+C → quit

⚠️  SAFETY: Robot will respond to joystick inputs. Keep clear.

Run:
    python 05_custom_controller/01_keyboard_controller.py --mode ap
    python 05_custom_controller/01_keyboard_controller.py --mode ap --dry-run
"""

import sys
import os
import time
import threading
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.common import (
    base_parser, go2_ip_for_mode,
    header, ok, fail, warn, info,
)

try:
    from unitree_webrtc_connect.webrtc_driver import UnitreeWebRTCConnection, WebRTCConnectionMethod
    WEBRTC_OK = True
except ImportError:
    WEBRTC_OK = False

try:
    import termios
    import tty
    TERMIOS_OK = True
except ImportError:
    TERMIOS_OK = False  # Windows


# ── Button bitmasks (from unitree_legged_sdk joystick.h xKeySwitchUnion) ──────
KEY_R1     = 0x0001
KEY_L1     = 0x0002
KEY_START  = 0x0004
KEY_SELECT = 0x0008
KEY_R2     = 0x0010
KEY_L2     = 0x0020
KEY_F1     = 0x0040
KEY_F2     = 0x0080
KEY_A      = 0x0100
KEY_B      = 0x0200
KEY_X      = 0x0400
KEY_Y      = 0x0800
KEY_UP     = 0x1000
KEY_RIGHT  = 0x2000
KEY_DOWN   = 0x4000
KEY_LEFT   = 0x8000


class ControllerState:
    def __init__(self):
        self.lx = 0.0   # left joystick X
        self.ly = 0.0   # left joystick Y
        self.rx = 0.0   # right joystick X
        self.ry = 0.0   # right joystick Y
        self.keys: int = 0
        self.lock = threading.Lock()

    def to_dict(self):
        with self.lock:
            return {
                "lx": self.lx,
                "ly": self.ly,
                "rx": self.rx,
                "ry": self.ry,
                "keys": self.keys,
            }

    def set_button(self, mask: int, pressed: bool):
        with self.lock:
            if pressed:
                self.keys |= mask
            else:
                self.keys &= ~mask

    def set_axis(self, axis: str, value: float):
        with self.lock:
            setattr(self, axis, max(-1.0, min(1.0, value)))


JOYSTICK_STEP = 0.3   # increment per keypress


def get_char_unix():
    """Read a single character from stdin (Unix/Mac)."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        # Handle escape sequences (arrow keys)
        if ch == '\x1b':
            ch2 = sys.stdin.read(1)
            if ch2 == '[':
                ch3 = sys.stdin.read(1)
                return '\x1b[' + ch3
            return ch
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def print_state(state: ControllerState):
    s = state.to_dict()
    pressed = []
    for name, mask in [
        ("L1", KEY_L1), ("L2", KEY_L2), ("R1", KEY_R1), ("R2", KEY_R2),
        ("A", KEY_A), ("B", KEY_B), ("X", KEY_X), ("Y", KEY_Y),
        ("F1", KEY_F1), ("F2", KEY_F2),
        ("Up", KEY_UP), ("Down", KEY_DOWN), ("Left", KEY_LEFT), ("Right", KEY_RIGHT),
    ]:
        if s["keys"] & mask:
            pressed.append(name)

    sys.stdout.write(
        f"\r  LX:{s['lx']:+.1f} LY:{s['ly']:+.1f} | "
        f"RX:{s['rx']:+.1f} RY:{s['ry']:+.1f} | "
        f"Buttons: {pressed if pressed else 'none'}    "
    )
    sys.stdout.flush()


def keyboard_loop(state: ControllerState, stop_event: threading.Event):
    """Read keyboard and update controller state."""
    if not TERMIOS_OK:
        warn("Raw keyboard input not available on Windows.")
        warn("Use arrow keys / WASD not available — only button simulation.")
        return

    while not stop_event.is_set():
        try:
            ch = get_char_unix()
        except Exception:
            break

        # Quit
        if ch in ('\x1b', '\x03', 'q'):
            stop_event.set()
            break

        # Joystick axes — toggle on/off
        if ch == 'w':
            state.set_axis("ly", 1.0)
        elif ch == 's':
            state.set_axis("ly", -1.0)
        elif ch == 'a':
            state.set_axis("lx", -1.0)
        elif ch == 'd':
            state.set_axis("lx", 1.0)
        elif ch == '\x1b[A':   # up arrow
            state.set_axis("ry", 1.0)
        elif ch == '\x1b[B':   # down arrow
            state.set_axis("ry", -1.0)
        elif ch == '\x1b[C':   # right arrow
            state.set_axis("rx", 1.0)
        elif ch == '\x1b[D':   # left arrow
            state.set_axis("rx", -1.0)

        # Release axes on space
        elif ch == ' ':
            for ax in ("lx", "ly", "rx", "ry"):
                state.set_axis(ax, 0.0)

        # Buttons (toggle)
        elif ch == '1': state.set_button(KEY_L1, not (state.keys & KEY_L1))
        elif ch == '2': state.set_button(KEY_L2, not (state.keys & KEY_L2))
        elif ch == '3': state.set_button(KEY_R1, not (state.keys & KEY_R1))
        elif ch == '4': state.set_button(KEY_R2, not (state.keys & KEY_R2))
        elif ch == 'e': state.set_button(KEY_A, not (state.keys & KEY_A))
        elif ch == 'r': state.set_button(KEY_B, not (state.keys & KEY_B))
        elif ch == 'z': state.set_button(KEY_X, not (state.keys & KEY_X))
        elif ch == 'c': state.set_button(KEY_Y, not (state.keys & KEY_Y))
        elif ch == 'f': state.set_button(KEY_F1, not (state.keys & KEY_F1))
        elif ch == 'g': state.set_button(KEY_F2, not (state.keys & KEY_F2))

        print_state(state)


def send_loop(conn, state: ControllerState, stop_event: threading.Event, dry_run: bool, loop):
    """Continuously send controller state to Go2 at ~20 Hz."""
    import asyncio
    SEND_RATE = 0.05  # 20 Hz
    sent = 0
    while not stop_event.is_set():
        s = state.to_dict()
        if not dry_run:
            try:
                msg = json.dumps({
                    "type": "msg",
                    "topic": "rt/wirelesscontroller",
                    "data": s
                })
                asyncio.run_coroutine_threadsafe(
                    _async_send(conn, msg), loop
                ).result(timeout=1)
                sent += 1
            except Exception as e:
                if sent == 0:
                    warn(f"Send failed: {e}")
                    warn("Virtual controller injection may not be supported via WebRTC.")
        time.sleep(SEND_RATE)


async def _async_send(conn, msg):
    conn.datachannel.channel.send(msg)


async def async_connect(conn):
    """Connect to Go2 via async WebRTC."""
    import asyncio
    await asyncio.wait_for(conn.connect(), timeout=15)


def main():
    p = base_parser("Step 05a — Keyboard controller")
    p.add_argument("--dry-run", action="store_true",
                   help="Show what would be sent without actually sending")
    args = p.parse_args()

    header(f"STEP 05a — Keyboard Controller  [{args.mode.upper()} mode]"
           + ("  [DRY RUN]" if args.dry_run else ""))

    if not WEBRTC_OK:
        fail("unitree_webrtc_connect not installed.")
        info("Install: pip install unitree_webrtc_connect")
        sys.exit(1)

    info("Keyboard controls:")
    info("  W/S/A/D     = left joystick (forward/back/left/right)")
    info("  Arrow keys  = right joystick")
    info("  SPACE       = release all axes (stop)")
    info("  1/2/3/4     = L1/L2/R1/R2 (toggle)")
    info("  E/R/Z/C     = A/B/X/Y (toggle)")
    info("  F/G         = F1/F2 — use these for arm triggers!")
    info("  Q or ESC    = quit\n")

    state = ControllerState()
    stop_event = threading.Event()

    # Connect
    if args.mode == "ap":
        conn = UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalAP)
    else:
        ip = go2_ip_for_mode(args)
        conn = UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalSTA, ip=ip)

    import asyncio
    loop = asyncio.new_event_loop()

    if not args.dry_run:
        try:
            loop.run_until_complete(async_connect(conn))
            ok("WebRTC connected — starting keyboard control\n")
        except Exception as e:
            fail(f"WebRTC connection failed: {e}")
            sys.exit(1)

        # Keep the event loop running in a background thread
        loop_thread = threading.Thread(
            target=loop.run_forever,
            daemon=True
        )
        loop_thread.start()
    else:
        info("[DRY RUN] — not connecting to robot\n")

    # Start send thread
    send_thread = threading.Thread(
        target=send_loop,
        args=(conn, state, stop_event, args.dry_run, loop),
        daemon=True
    )
    send_thread.start()

    # Keyboard loop (blocks until quit)
    try:
        keyboard_loop(state, stop_event)
    except KeyboardInterrupt:
        stop_event.set()

    print()  # newline after carriage-return output
    info("Stopped.")

    if not args.dry_run:
        asyncio.run_coroutine_threadsafe(conn.disconnect(), loop).result(timeout=5)
        loop.call_soon_threadsafe(loop.stop)

    header("Keyboard Controller Summary")
    info("F1 / F2 buttons are good candidates for custom arm triggers.")
    info("They are not used by default Go2 locomotion, so you can safely")
    info("listen for them in your arm control code:\n")
    info("  if msg['keys'] & 0x0100:  # F1 pressed")
    info("      trigger_arm_action()")


if __name__ == "__main__":
    main()
