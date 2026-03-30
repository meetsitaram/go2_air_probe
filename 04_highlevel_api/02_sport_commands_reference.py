#!/usr/bin/env python3
"""
STEP 04b — Available Sport Commands Reference
───────────────────────────────────────────────
Lists all known high-level sport commands with their API IDs and
parameters. Does NOT send any commands — purely informational.

Run:
    python 04_highlevel_api/02_sport_commands_reference.py
"""

header_text = """
╔══════════════════════════════════════════════════════════════════╗
║        Go2 High-Level Sport Commands Reference                   ║
║        Source: Unitree SDK SportClient                           ║
╚══════════════════════════════════════════════════════════════════╝

These commands work on Go2 Air via WebRTC (high-level only).

Via SDK (SportClient):              Via WebRTC data channel:
  client.StandUp()                    api_id: 1004
  client.StandDown()                  api_id: 1005
  client.BalanceStand()               api_id: 1006
  client.RecoveryStand()              api_id: 1009
  client.Move(vx, vy, vyaw)          api_id: 1008  params: {x, y, z}
  client.StopMove()                   api_id: 1003
  client.Sit()                        api_id: 1010
  client.RiseSit()                    api_id: 1011
  client.Hello()                      api_id: 1016
  client.Stretch()                    api_id: 1017
  client.WaveHand()                   api_id: 1018
  client.Dance1()                     api_id: 1021
  client.Dance2()                     api_id: 1022
  client.FrontFlip()                  api_id: 1019
  client.FrontJump()                  api_id: 1020
  client.SpeedLevel(level)           api_id: 1007  level: 0=slow, 1=normal, 2=fast
  client.SwitchGait(gait)            api_id: 1002  gait: 0=idle, 1=trot, 2=run

Move() parameters:
  vx:   forward/backward  (m/s)  positive = forward,  range: -1.0 to 1.0
  vy:   left/right        (m/s)  positive = left,     range: -0.6 to 0.6
  vyaw: yaw rotation (rad/s)     positive = turn left, range: -1.5 to 1.5

Example usage in Python:

    from unitree_sdk2py.go2.sport.sport_client import SportClient
    client = SportClient()
    client.Init()

    client.StandUp()
    client.Move(0.5, 0.0, 0.0)   # walk forward at 0.5 m/s
    client.Move(0.0, 0.0, 0.5)   # rotate left
    client.StopMove()
    client.StandDown()

NOT available on Go2 Air (EDU only):
  - LowCmd (joint-level motor control)
  - Foot force sensors
  - Custom gait programming
"""

print(header_text)
