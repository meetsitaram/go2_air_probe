#!/usr/bin/env python3
"""
run_all.py — Run all probe steps in sequence (dry-run safe)
─────────────────────────────────────────────────────────────
Runs steps 01-04 in order and produces a final capability report.
Step 05 (custom controller) is interactive and skipped here.

Run:
    python run_all.py --mode ap
    python run_all.py --mode sta --ip 192.168.1.42
    python run_all.py --mode ap --dry-run   # skip movement commands
"""

import sys
import os
import subprocess
import argparse

ROOT = os.path.dirname(__file__)

STEPS = [
    ("01 — Network",      "01_network/01_network_probe.py"),
    ("02a — WebRTC conn", "02_webrtc/01_webrtc_connect.py"),
    ("02b — WebRTC data", "02_webrtc/02_webrtc_data.py"),
    ("02c — Camera/LiDAR","02_webrtc/03_webrtc_camera.py"),
    ("03 — CycloneDDS",   "03_cyclonedds/01_dds_probe.py"),
    ("04 — Sport cmds",   "04_highlevel_api/01_sport_commands.py"),
]

GREEN = "\033[92m"
RED   = "\033[91m"
RESET = "\033[0m"
BOLD  = "\033[1m"


def main():
    p = argparse.ArgumentParser(description="Run all probe steps")
    p.add_argument("--mode", choices=["ap", "sta", "lan"], default="ap")
    p.add_argument("--ip", default=None)
    p.add_argument("--interface", default="eth0")
    p.add_argument("--dry-run", action="store_true",
                   help="Pass --dry-run to movement scripts (no robot motion)")
    args = p.parse_args()

    results = {}

    for label, script in STEPS:
        print(f"\n{BOLD}{'='*60}{RESET}")
        print(f"{BOLD}Running: {label}{RESET}")
        print(f"{BOLD}{'='*60}{RESET}\n")

        cmd = [sys.executable, os.path.join(ROOT, script), "--mode", args.mode]
        if args.ip:
            cmd += ["--ip", args.ip]
        if args.interface:
            cmd += ["--interface", args.interface]
        if args.dry_run and "sport" in script:
            cmd += ["--dry-run"]

        ret = subprocess.run(cmd)
        results[label] = ret.returncode == 0

    # ── Final report ──────────────────────────────────────────────────────────
    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}  FINAL CAPABILITY REPORT — Go2 Air [{args.mode.upper()} mode]{RESET}")
    print(f"{BOLD}{'='*60}{RESET}\n")

    for label, passed in results.items():
        icon = f"{GREEN}✅ PASS{RESET}" if passed else f"{RED}❌ FAIL{RESET}"
        print(f"  {icon}  {label}")

    print(f"\n  Step 05 (Custom Controller) — run manually:")
    print(f"    python 05_custom_controller/01_keyboard_controller.py --mode {args.mode}"
          + (f" --ip {args.ip}" if args.ip else ""))
    print()


if __name__ == "__main__":
    main()
