# Smart Speed Ramp System

**Status: planned, not yet implemented**

**Chosen approach: Option B (quadratic ease-in), ON by default.**

## Implementation

File: `05_custom_controller/02_xbox_controller.py`

### CLI Arguments

- `--no-ramp` -- disable the ramp entirely (instant full speed, current behavior)
- `--ramp-time SECONDS` -- ramp duration (default: `2.0`)
- `--ramp-curve POWER` -- curve exponent (default: `2.0` = quadratic; `1.0` = linear; `3.0` = more gentle)

Default invocation (ramp ON at 2s quadratic):

```
python 02_xbox_controller.py --mode sta --ip 192.168.1.133
```

Disable ramp:

```
python 02_xbox_controller.py --mode sta --ip 192.168.1.133 --no-ramp
```

### Ramp Logic in `send_loop`

Applied after the existing `speed_limit` clamp, before sending:

```python
# Ramp state
ramp_start = None   # time.monotonic() when sticks first move

# Each cycle:
moving = any(v != 0.0 for v in [s["lx"], s["ly"], s["rx"], s["ry"]])
if moving:
    if ramp_start is None:
        ramp_start = time.monotonic()
    t = min(1.0, (time.monotonic() - ramp_start) / ramp_time)
    multiplier = 0.2 + 0.8 * (t ** ramp_curve)  # starts at 20%, ramps to 100%
    s["lx"] *= multiplier
    s["ly"] *= multiplier
    s["rx"] *= multiplier
    s["ry"] *= multiplier
else:
    ramp_start = None  # reset on return to idle
```

The ramp resets every time all sticks return to center, so each new movement starts slow.

### Startup Output

When ramp is active:

```
  INFO  Speed ramp: 2.0s ease-in (use --no-ramp to disable)
```

When disabled:

```
  INFO  Speed ramp: OFF
```

### TODO

- [ ] Add CLI args: `--no-ramp`, `--ramp-time`, `--ramp-curve`
- [ ] Add ramp multiplier computation in `send_loop` using quadratic ease-in
- [ ] Display ramp settings in startup output
