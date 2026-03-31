#!/usr/bin/env python3
"""
STEP 05b — Xbox Controller
────────────────────────────
Maps an Xbox / compatible USB gamepad to the Unitree Go2 wireless controller.
Joystick axes and all buttons are forwarded over WebRTC at 20 Hz.

Xbox → Unitree mapping:
  Left stick          → left joystick  (lx, ly)  — walk / strafe
  Right stick         → right joystick (rx, ry)  — yaw / look
  LB                  → L1
  RB                  → R1
  LT (analog trigger) → L2
  RT (analog trigger) → R2
  A                   → A
  B                   → B
  X                   → X
  Y                   → Y
  Start / Menu        → Start
  Back / View         → Select
  D-pad Up            → Up
  D-pad Down          → Down
  D-pad Left          → Left
  D-pad Right         → Right
  Left stick click    → F1  (good for arm trigger)
  Right stick click   → F2

Safety:
  Dangerous combos (Damp, Jump, Pounce, Running) are blocked by default.
  With --allow-all, blocked combos require a 3-vibration countdown (3…2…1…go)
  before they are sent — release buttons during the countdown to cancel.
  Emergency stop: hold LB+LT+RB+RT + any face button through a 3-vibration
  countdown (always active). Release to cancel.
  Vibration feedback: 3 pulses for e-stop and --allow-all countdowns,
  single buzz when a combo is blocked.

Run:
    python 05_custom_controller/02_xbox_controller.py --mode sta --ip 192.168.1.133
    python 05_custom_controller/02_xbox_controller.py --mode ap --dry-run
    python 05_custom_controller/02_xbox_controller.py --mode sta --ip 192.168.1.133 --allow-all
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
    from unitree_webrtc_connect.webrtc_driver import (
        UnitreeWebRTCConnection,
        WebRTCConnectionMethod,
    )
    from unitree_webrtc_connect.constants import RTC_TOPIC, SPORT_CMD
    WEBRTC_OK = True
except ImportError:
    WEBRTC_OK = False

try:
    import evdev
    EVDEV_OK = True
except ImportError:
    EVDEV_OK = False


# ── Unitree button bitmasks (from unitree_legged_sdk joystick.h) ──────────────
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

# evdev button codes → Unitree bitmask
# BTN_A/B/X/Y codes match the Xbox face button labels
BUTTON_MAP = {
    304: KEY_A,       # BTN_SOUTH / BTN_A
    305: KEY_B,       # BTN_EAST  / BTN_B
    307: KEY_X,       # BTN_NORTH / BTN_X
    308: KEY_Y,       # BTN_WEST  / BTN_Y
    310: KEY_L1,      # BTN_TL  (LB)
    311: KEY_R1,      # BTN_TR  (RB)
    312: KEY_L2,      # BTN_TL2 (LT digital)
    313: KEY_R2,      # BTN_TR2 (RT digital)
    314: KEY_SELECT,  # BTN_SELECT (Back / View)
    315: KEY_START,   # BTN_START  (Menu)
    317: KEY_F1,      # BTN_THUMBL (Left stick click)
    318: KEY_F2,      # BTN_THUMBR (Right stick click)
}

# ── Safety: blocked combos and emergency stop ─────────────────────────────────
# (combo_mask, strip_mask, description)
# When keys & combo_mask == combo_mask, strip_mask bits are cleared before sending.
BLOCKED_COMBOS = [
    (KEY_L2 | KEY_B,     KEY_B,     "Damp (LT+B) — motors go limp, robot collapses"),
    (KEY_R1 | KEY_A,     KEY_A,     "Jump Forward (RB+A)"),
    (KEY_R1 | KEY_X,     KEY_X,     "Pounce (RB+X)"),
    (KEY_L2 | KEY_START, KEY_START, "Running mode (LT+Start) — high speed"),
]

ALL_SHOULDERS = KEY_L1 | KEY_L2 | KEY_R1 | KEY_R2
ANY_FACE      = KEY_A  | KEY_B  | KEY_X  | KEY_Y

# Vibration countdown — 3 pulses before allowing a dangerous combo (--allow-all)
COUNTDOWN_SECS = 1.8
PULSE_TIMES    = [0.0, 0.6, 1.2]   # seconds after combo first detected
PULSE_MS       = 250               # vibration duration per pulse

# Analog stick config — Xbox Wireless Controller reports 0-65535
STICK_CENTER = 32768
STICK_DEADZONE = 4096
STICK_RANGE = 32768.0

# Analog trigger config — 0-1023, treat as L2/R2 button above threshold
TRIGGER_THRESHOLD = 300
TRIGGER_MAX = 1023.0


class ControllerState:
    def __init__(self):
        self.lx = 0.0
        self.ly = 0.0
        self.rx = 0.0
        self.ry = 0.0
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


def normalize_stick(raw: int) -> float:
    """Convert raw stick value (0–65535, center 32768) to ±1.0 with deadzone."""
    centered = raw - STICK_CENTER
    if abs(centered) < STICK_DEADZONE:
        return 0.0
    sign = 1.0 if centered > 0 else -1.0
    magnitude = (abs(centered) - STICK_DEADZONE) / (STICK_RANGE - STICK_DEADZONE)
    return sign * min(1.0, magnitude)


class RumbleHelper:
    """Manages a single FF_RUMBLE effect for haptic feedback on the gamepad."""

    def __init__(self, device):
        self.device = device
        self.effect_id = None
        try:
            caps = device.capabilities()
            if (evdev.ecodes.EV_FF, 21) not in caps and evdev.ecodes.EV_FF not in caps:
                return
            effect = evdev.ff.Effect(
                evdev.ecodes.FF_RUMBLE, -1, 0,
                evdev.ff.Trigger(0, 0),
                evdev.ff.Replay(PULSE_MS, 0),
                evdev.ff.EffectType(
                    ff_rumble_effect=evdev.ff.Rumble(
                        strong_magnitude=0xFFFF, weak_magnitude=0xFFFF,
                    )
                ),
            )
            self.effect_id = device.upload_effect(effect)
        except Exception:
            pass

    @property
    def available(self):
        return self.effect_id is not None

    def pulse(self):
        if self.effect_id is not None:
            try:
                self.device.write(evdev.ecodes.EV_FF, self.effect_id, 1)
            except Exception:
                pass

    def stop(self):
        if self.effect_id is not None:
            try:
                self.device.write(evdev.ecodes.EV_FF, self.effect_id, 0)
            except Exception:
                pass

    def cleanup(self):
        self.stop()
        if self.effect_id is not None:
            try:
                self.device.erase_effect(self.effect_id)
            except Exception:
                pass


def print_state(state: ControllerState):
    s = state.to_dict()
    pressed = []
    for name, mask in [
        ("L1", KEY_L1), ("L2", KEY_L2), ("R1", KEY_R1), ("R2", KEY_R2),
        ("A", KEY_A), ("B", KEY_B), ("X", KEY_X), ("Y", KEY_Y),
        ("F1", KEY_F1), ("F2", KEY_F2),
        ("Start", KEY_START), ("Select", KEY_SELECT),
        ("Up", KEY_UP), ("Down", KEY_DOWN), ("Left", KEY_LEFT), ("Right", KEY_RIGHT),
    ]:
        if s["keys"] & mask:
            pressed.append(name)

    sys.stdout.write(
        f"\r  LX:{s['lx']:+.2f} LY:{s['ly']:+.2f} | "
        f"RX:{s['rx']:+.2f} RY:{s['ry']:+.2f} | "
        f"Buttons: {', '.join(pressed) if pressed else 'none'}          "
    )
    sys.stdout.flush()


def check_device_permissions():
    """Check if any /dev/input/event* devices exist but are unreadable."""
    import glob
    import grp
    all_events = sorted(glob.glob("/dev/input/event*"))
    if not all_events:
        return None
    unreadable = []
    for path in all_events:
        if not os.access(path, os.R_OK):
            unreadable.append(path)
    if not unreadable:
        return None

    user = os.environ.get("USER", "unknown")
    try:
        input_gid = grp.getgrnam("input").gr_gid
        user_groups = os.getgroups()
        in_input_group = input_gid in user_groups
    except KeyError:
        in_input_group = False

    return {
        "total": len(all_events),
        "unreadable": len(unreadable),
        "in_input_group": in_input_group,
        "user": user,
    }


def find_gamepad():
    """Find the first gamepad/joystick among evdev input devices."""
    for path in evdev.list_devices():
        device = evdev.InputDevice(path)
        caps = device.capabilities()
        has_abs = evdev.ecodes.EV_ABS in caps
        has_key = evdev.ecodes.EV_KEY in caps
        if has_abs and has_key:
            key_codes = [k if isinstance(k, int) else k[0] for k in caps[evdev.ecodes.EV_KEY]]
            if 304 in key_codes:  # BTN_SOUTH / BTN_A — present on all gamepads
                return device
    return None


def validate_gamepad(device):
    """Check that the gamepad has the expected Xbox-style buttons and axes.

    Returns a list of warning strings (empty = all good).
    """
    caps = device.capabilities()
    warnings = []

    # Check buttons
    key_codes = set()
    if evdev.ecodes.EV_KEY in caps:
        for k in caps[evdev.ecodes.EV_KEY]:
            key_codes.add(k if isinstance(k, int) else k[0])

    expected_buttons = {
        304: "A (BTN_SOUTH)",
        305: "B (BTN_EAST)",
        307: "X (BTN_NORTH)",
        308: "Y (BTN_WEST)",
        310: "LB (BTN_TL)",
        311: "RB (BTN_TR)",
        314: "Back (BTN_SELECT)",
        315: "Start (BTN_START)",
        317: "L-stick click (BTN_THUMBL)",
        318: "R-stick click (BTN_THUMBR)",
    }
    missing_buttons = {code: name for code, name in expected_buttons.items()
                       if code not in key_codes}
    if missing_buttons:
        names = ", ".join(missing_buttons.values())
        warnings.append(f"Missing buttons: {names}")

    # Check axes
    abs_codes = set()
    if evdev.ecodes.EV_ABS in caps:
        for item in caps[evdev.ecodes.EV_ABS]:
            code = item[0] if isinstance(item, tuple) else item
            abs_codes.add(code)

    # Left stick (ABS_X, ABS_Y) — required
    if evdev.ecodes.ABS_X not in abs_codes or evdev.ecodes.ABS_Y not in abs_codes:
        warnings.append("Missing left stick axes (ABS_X / ABS_Y)")

    # Right stick — accept either ABS_Z/ABS_RZ or ABS_RX/ABS_RY
    has_right_zrz = evdev.ecodes.ABS_Z in abs_codes and evdev.ecodes.ABS_RZ in abs_codes
    has_right_rxry = evdev.ecodes.ABS_RX in abs_codes and evdev.ecodes.ABS_RY in abs_codes
    if not has_right_zrz and not has_right_rxry:
        warnings.append("Missing right stick axes (expected ABS_Z/ABS_RZ or ABS_RX/ABS_RY)")

    # D-pad
    if evdev.ecodes.ABS_HAT0X not in abs_codes or evdev.ecodes.ABS_HAT0Y not in abs_codes:
        warnings.append("Missing D-pad axes (ABS_HAT0X / ABS_HAT0Y)")

    # Controller name check
    name_lower = device.name.lower()
    known_names = ["xbox", "microsoft", "x-box"]
    if not any(kn in name_lower for kn in known_names):
        warnings.append(
            f"Controller '{device.name}' may not be Xbox-compatible — "
            f"button/axis mapping could be wrong"
        )

    return warnings


def gamepad_loop(device: evdev.InputDevice, state: ControllerState, stop_event: threading.Event):
    """Read evdev gamepad events and update controller state."""
    EV_ABS = evdev.ecodes.EV_ABS
    EV_KEY = evdev.ecodes.EV_KEY

    for event in device.read_loop():
        if stop_event.is_set():
            break

        if event.type == EV_KEY and event.code in BUTTON_MAP:
            state.set_button(BUTTON_MAP[event.code], event.value == 1)

        elif event.type == EV_ABS:
            code, val = event.code, event.value

            # Left stick
            if code == evdev.ecodes.ABS_X:
                state.set_axis("lx", normalize_stick(val))
            elif code == evdev.ecodes.ABS_Y:
                state.set_axis("ly", -normalize_stick(val))  # Y inverted

            # Right stick (Xbox BT uses ABS_Z / ABS_RZ for right stick)
            elif code == evdev.ecodes.ABS_Z:
                state.set_axis("rx", normalize_stick(val))
            elif code == evdev.ecodes.ABS_RZ:
                state.set_axis("ry", -normalize_stick(val))  # Y inverted
            # Some drivers use ABS_RX / ABS_RY instead
            elif code == evdev.ecodes.ABS_RX:
                state.set_axis("rx", normalize_stick(val))
            elif code == evdev.ecodes.ABS_RY:
                state.set_axis("ry", -normalize_stick(val))

            # Analog triggers
            elif code == evdev.ecodes.ABS_BRAKE:   # LT
                state.set_button(KEY_L2, val > TRIGGER_THRESHOLD)
            elif code == evdev.ecodes.ABS_GAS:     # RT
                state.set_button(KEY_R2, val > TRIGGER_THRESHOLD)

            # D-pad
            elif code == evdev.ecodes.ABS_HAT0Y:
                state.set_button(KEY_UP,   val == -1)
                state.set_button(KEY_DOWN, val == 1)
            elif code == evdev.ecodes.ABS_HAT0X:
                state.set_button(KEY_LEFT,  val == -1)
                state.set_button(KEY_RIGHT, val == 1)

        print_state(state)


def send_loop(conn, state: ControllerState, stop_event: threading.Event,
              dry_run: bool, loop, allow_all: bool, rumble=None,
              speed_limit: float = 1.0):
    """Continuously send controller state to Go2 at ~20 Hz."""
    import asyncio
    SEND_RATE = 0.05  # 20 Hz
    sent = 0
    blocked_warned = set()
    estop_sent = False
    estop_cd = None  # countdown state: {start, pulses_fired}
    was_start = False    # track Start button press for walk mode vibration

    # Countdown state for --allow-all mode: desc → {start, pulses_fired}
    countdowns = {}
    armed_combos = set()  # combos that completed countdown and are being sent

    def _clamp(v):
        return max(-speed_limit, min(speed_limit, v))

    while not stop_event.is_set():
        s = state.to_dict()
        if speed_limit < 1.0:
            s["lx"] = _clamp(s["lx"])
            s["ly"] = _clamp(s["ly"])
            s["rx"] = _clamp(s["rx"])
            s["ry"] = _clamp(s["ry"])
        keys = s["keys"]

        # ── Emergency stop: L1+L2+R1+R2 + any face button ────────────
        if (keys & ALL_SHOULDERS) == ALL_SHOULDERS and (keys & ANY_FACE):
            if not estop_sent:
                if estop_cd is None:
                    estop_cd = {"start": time.monotonic(), "pulses_fired": 0}
                    sys.stdout.write("\n")
                    warn("E-STOP: hold for 3…2…1… (release to cancel)")

                elapsed = time.monotonic() - estop_cd["start"]
                for i, pt in enumerate(PULSE_TIMES):
                    if estop_cd["pulses_fired"] <= i and elapsed >= pt:
                        if rumble:
                            rumble.pulse()
                        estop_cd["pulses_fired"] = i + 1
                        remaining = len(PULSE_TIMES) - estop_cd["pulses_fired"]
                        label = f"  {remaining + 1}…" if remaining > 0 else ""
                        sys.stdout.write(f"\r{label}   ")
                        sys.stdout.flush()

                if elapsed >= COUNTDOWN_SECS:
                    sys.stdout.write("\n")
                    warn("EMERGENCY STOP — sending Damp (all motors off)")
                    if not dry_run:
                        try:
                            asyncio.run_coroutine_threadsafe(
                                _async_sport_cmd(conn, SPORT_CMD.get("Damp", 1001)),
                                loop,
                            ).result(timeout=2)
                        except Exception:
                            pass
                    estop_sent = True

            s["keys"] = 0
            s["lx"] = s["ly"] = s["rx"] = s["ry"] = 0.0
            countdowns.clear()
            armed_combos.clear()
        else:
            estop_sent = False
            estop_cd = None

            if allow_all:
                # ── Countdown mode: 3-2-1-go before allowing dangerous combos ──
                active_descs = set()
                for combo_mask, strip_mask, desc in BLOCKED_COMBOS:
                    if (keys & combo_mask) != combo_mask:
                        continue
                    active_descs.add(desc)

                    if desc in armed_combos:
                        continue  # already past countdown, let it through

                    if desc not in countdowns:
                        countdowns[desc] = {"start": time.monotonic(), "pulses_fired": 0}
                        sys.stdout.write("\n")
                        warn(f"ARMED: {desc} — hold for 3…2…1…")

                    cd = countdowns[desc]
                    elapsed = time.monotonic() - cd["start"]

                    for i, pt in enumerate(PULSE_TIMES):
                        if cd["pulses_fired"] <= i and elapsed >= pt:
                            if rumble:
                                rumble.pulse()
                            cd["pulses_fired"] = i + 1
                            remaining = len(PULSE_TIMES) - cd["pulses_fired"]
                            label = f"  {remaining + 1}…" if remaining > 0 else "  GO!"
                            sys.stdout.write(f"\r{label}   ")
                            sys.stdout.flush()

                    if elapsed < COUNTDOWN_SECS:
                        keys &= ~strip_mask  # still counting, strip this combo
                    else:
                        armed_combos.add(desc)
                        sys.stdout.write("\n")
                        ok(f"SENT: {desc}")

                # Reset countdowns for released combos
                released = [d for d in list(countdowns) if d not in active_descs]
                for d in released:
                    del countdowns[d]
                    armed_combos.discard(d)
                s["keys"] = keys
            else:
                # ── Blocklist: strip and warn ─────────────────────────────
                for combo_mask, strip_mask, desc in BLOCKED_COMBOS:
                    if (keys & combo_mask) == combo_mask:
                        keys &= ~strip_mask
                        if desc not in blocked_warned:
                            blocked_warned.add(desc)
                            sys.stdout.write("\n")
                            warn(f"BLOCKED: {desc}  (use --allow-all to override)")
                            if rumble:
                                rumble.pulse()
                s["keys"] = keys

        # ── Walk mode vibration: single buzz on Start press ─────────
        start_pressed = bool(s["keys"] & KEY_START)
        if rumble and start_pressed and not was_start:
            rumble.pulse()
        was_start = start_pressed

        if not dry_run:
            try:
                msg = json.dumps({
                    "type": "msg",
                    "topic": "rt/wirelesscontroller",
                    "data": s,
                })
                asyncio.run_coroutine_threadsafe(
                    _async_send(conn, msg), loop
                ).result(timeout=1)
                sent += 1
            except Exception as e:
                if sent == 0:
                    warn(f"Send failed: {e}")
        time.sleep(SEND_RATE)


async def _async_send(conn, msg):
    conn.datachannel.channel.send(msg)


async def _async_sport_cmd(conn, api_id):
    await conn.datachannel.pub_sub.publish_request_new(
        RTC_TOPIC["SPORT_MOD"],
        {"api_id": api_id},
    )


async def async_connect(conn):
    import asyncio
    await asyncio.wait_for(conn.connect(), timeout=15)
    if not conn.isConnected:
        raise ConnectionError("WebRTC connected but data channel did not open")


def main():
    import asyncio
    import logging
    # Suppress noisy asyncio "Task was destroyed" warnings on shutdown
    logging.getLogger("asyncio").setLevel(logging.CRITICAL)

    p = base_parser("Step 05b — Xbox controller")
    p.add_argument("--dry-run", action="store_true",
                   help="Show controller input without connecting to robot")
    p.add_argument("--allow-all", action="store_true",
                   help="Disable safety blocklist (allow all button combos)")
    p.add_argument("--speed-limit", type=float, default=1.0, metavar="0.0-1.0",
                   help="Cap joystick output (default: 1.0 = full speed)")
    args = p.parse_args()
    args.speed_limit = max(0.0, min(1.0, args.speed_limit))

    header(f"STEP 05b — Xbox Controller  [{args.mode.upper()} mode]"
           + ("  [DRY RUN]" if args.dry_run else ""))

    if not WEBRTC_OK:
        fail("unitree_webrtc_connect not installed.")
        info("Install: pip install unitree_webrtc_connect")
        sys.exit(1)

    if not EVDEV_OK:
        fail("'evdev' library not installed.")
        info("Install: pip install evdev")
        sys.exit(1)

    device = find_gamepad()
    if not device:
        perms = check_device_permissions()
        if perms and not perms["in_input_group"]:
            fail("Gamepad not detected — likely a permissions issue.")
            info(f"Found {perms['total']} input devices but {perms['unreadable']} are unreadable.")
            info(f"User '{perms['user']}' is NOT in the 'input' group. Fix with:")
            info(f"  sudo usermod -aG input {perms['user']}")
            info("  Then log out and back in (or reboot).")
        elif perms and perms["in_input_group"]:
            fail("No gamepad detected (permissions OK — is the controller connected?).")
            info("Connect an Xbox controller (USB or Bluetooth) and try again.")
            info("Check with: cat /proc/bus/input/devices | grep -A4 'Xbox'")
        else:
            fail("No gamepad detected.")
            info("Connect an Xbox controller (USB or Bluetooth) and try again.")
        sys.exit(1)

    ok(f"Gamepad found: {device.name}  ({device.path})")

    rumble = RumbleHelper(device)
    if rumble.available:
        ok("Vibration feedback enabled (force-feedback supported)")
    else:
        warn("Vibration feedback unavailable (controller has no FF_RUMBLE)")

    validation_warnings = validate_gamepad(device)
    if validation_warnings:
        warn("Controller validation issues:")
        for w in validation_warnings:
            warn(f"  • {w}")
        info("The script will still run, but some inputs may not work correctly.")
        info("This script is designed for Xbox controllers. If using a different")
        info("gamepad, check axis/button codes with:")
        info(f"  python -c \"import evdev; d=evdev.InputDevice('{device.path}'); print(d.capabilities(verbose=True))\"")
        info("")

    info("")
    info("Xbox → Unitree mapping:")
    info("  Left stick       → walk / strafe (lx, ly)")
    info("  Right stick      → yaw / look   (rx, ry)")
    info("  LB / RB          → L1 / R1")
    info("  LT / RT          → L2 / R2")
    info("  A / B / X / Y    → A / B / X / Y")
    info("  Start / Back     → Start / Select")
    info("  D-pad            → Up / Down / Left / Right")
    info("  L-stick click    → F1 (arm trigger)")
    info("  R-stick click    → F2")
    info("  Ctrl+C           → quit")

    # Speed limit
    info("")
    if args.speed_limit < 1.0:
        warn(f"Speed limit: {args.speed_limit:.0%} (joystick output capped)")
    else:
        info("Speed limit: OFF (use --speed-limit 0.5 to cap at 50%)")

    # Safety info
    info("")
    if args.allow_all:
        warn("SAFETY: blocklist OFF (--allow-all) — dangerous combos require")
        warn("  a 3-vibration countdown.  Release buttons to cancel.")
    else:
        ok("Safety blocklist ACTIVE — the following combos are blocked:")
        for _, _, desc in BLOCKED_COMBOS:
            info(f"    {desc}")
        info("  Pass --allow-all to enable them with a vibration countdown.")
    info("")
    ok("Emergency stop: hold LB+LT+RB+RT + any face button (A/B/X/Y)")
    info("  3-vibration countdown, then sends Damp. Release to cancel.\n")

    state = ControllerState()
    stop_event = threading.Event()

    conn = None
    loop = asyncio.new_event_loop()

    if not args.dry_run:
        if args.mode == "ap":
            conn = UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalAP)
        else:
            ip = go2_ip_for_mode(args)
            conn = UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalSTA, ip=ip)

        MAX_RETRIES = 3
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                info(f"Connecting to Go2 (attempt {attempt}/{MAX_RETRIES}) ...")
                loop.run_until_complete(async_connect(conn))
                ok("WebRTC connected — forwarding gamepad input\n")
                break
            except (asyncio.TimeoutError, ConnectionError, Exception) as e:
                if attempt < MAX_RETRIES:
                    warn(f"Connection attempt {attempt} failed: {e}")
                    info("Waiting 5s before retry (WebRTC cooldown) ...")
                    time.sleep(5)
                    # Re-create connection object for clean retry
                    if args.mode == "ap":
                        conn = UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalAP)
                    else:
                        conn = UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalSTA, ip=ip)
                    loop.close()
                    loop = asyncio.new_event_loop()
                else:
                    fail(f"WebRTC connection failed after {MAX_RETRIES} attempts: {e}")
                    info("Make sure the Unitree phone app is closed.")
                    info("Wait ~10 seconds after any previous connection, then try again.")
                    sys.exit(1)

        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
    else:
        info("[DRY RUN] — not connecting to robot\n")

    send_thread = threading.Thread(
        target=send_loop,
        args=(conn, state, stop_event, args.dry_run, loop, args.allow_all,
              rumble, args.speed_limit),
        daemon=True,
    )
    send_thread.start()

    try:
        gamepad_loop(device, state, stop_event)
    except KeyboardInterrupt:
        stop_event.set()

    print()
    info("Stopped.")
    rumble.cleanup()

    if not args.dry_run and conn:
        try:
            asyncio.run_coroutine_threadsafe(conn.disconnect(), loop).result(timeout=5)
        except Exception:
            pass
        loop.call_soon_threadsafe(loop.stop)

    header("Xbox Controller Summary")
    info("L-stick click (F1) and R-stick click (F2) are free for custom triggers.")
    info("They are not used by default Go2 locomotion.\n")


if __name__ == "__main__":
    main()
