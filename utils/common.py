"""
utils/common.py — shared helpers for all probe scripts
"""

import argparse
import socket
import subprocess
import sys
import time


# ──────────────────────────────────────────────
# ANSI colours for terminal output
# ──────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"


def ok(msg: str):
    print(f"{GREEN}  ✅  PASS{RESET}  {msg}")

def fail(msg: str):
    print(f"{RED}  ❌  FAIL{RESET}  {msg}")

def warn(msg: str):
    print(f"{YELLOW}  ⚠️   WARN{RESET}  {msg}")

def info(msg: str):
    print(f"{CYAN}  ℹ️   INFO{RESET}  {msg}")

def header(title: str):
    bar = "─" * 60
    print(f"\n{BOLD}{bar}{RESET}")
    print(f"{BOLD}  {title}{RESET}")
    print(f"{BOLD}{bar}{RESET}")


# ──────────────────────────────────────────────
# Standard CLI argument parser
# ──────────────────────────────────────────────
def base_parser(description: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=description)
    p.add_argument(
        "--mode",
        choices=["ap", "sta", "lan"],
        default="sta",
        help=(
            "ap  = connected to Go2's own WiFi hotspot (GO2-XXXXXX)\n"
            "sta = Go2 and your computer on same home/lab router\n"
            "lan = direct Ethernet cable to Go2 rear port (EDU / firmware unlock)"
        ),
    )
    p.add_argument(
        "--ip",
        default="192.168.1.133",
        help="Go2 IP address (required for --mode sta). "
             "Find it in the app: Device → Data → STA Network: wlan0",
    )
    p.add_argument(
        "--serial",
        default=None,
        help="Go2 serial number (optional, used for STA auto-discovery). "
             "Format: B42D2000XXXXXXXX",
    )
    p.add_argument(
        "--interface",
        default="eth0",
        help="Network interface name for LAN/CycloneDDS mode (default: eth0)",
    )
    return p


# ──────────────────────────────────────────────
# Network helpers
# ──────────────────────────────────────────────
GO2_AP_IP   = "192.168.12.1"   # Go2's IP when YOU are connected to its hotspot
GO2_LAN_IP  = "192.168.123.161"  # Go2's typical IP on direct LAN

def go2_ip_for_mode(args) -> str:
    if args.mode == "ap":
        return GO2_AP_IP
    elif args.mode == "sta":
        if not args.ip:
            fail("--mode sta requires --ip <GO2_IP>")
            sys.exit(1)
        return args.ip
    elif args.mode == "lan":
        return GO2_LAN_IP
    return GO2_AP_IP


def ping(host: str, count: int = 3, timeout: int = 2) -> bool:
    """Returns True if host responds to ping."""
    try:
        cmd = ["ping", "-c", str(count), "-W", str(timeout), host]
        result = subprocess.run(cmd, capture_output=True)
        return result.returncode == 0
    except FileNotFoundError:
        # Windows
        cmd = ["ping", "-n", str(count), "-w", str(timeout * 1000), host]
        result = subprocess.run(cmd, capture_output=True)
        return result.returncode == 0


def tcp_reachable(host: str, port: int, timeout: float = 3.0) -> bool:
    """Returns True if a TCP connection can be established."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def wait_for_data(flag_container, label: str, timeout: float = 8.0) -> bool:
    """Poll flag_container['received'] until True or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if flag_container.get("received"):
            return True
        time.sleep(0.2)
    return False
