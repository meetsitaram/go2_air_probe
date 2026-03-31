#!/usr/bin/env bash
cd "$(dirname "$0")"
IP="${1:-192.168.1.133}"
shift 2>/dev/null
source .venv/bin/activate && python 05_custom_controller/02_xbox_controller.py --mode sta --ip "$IP" "$@"
