"""
Compact live market display for the terminal.
Overwrites its own output in-place using ANSI cursor movement.
"""
from __future__ import annotations
import sys

# ANSI colour codes
G  = "\033[32m"   # green
A  = "\033[33m"   # amber
R  = "\033[31m"   # red
D  = "\033[90m"   # dim
B  = "\033[1m"    # bold
X  = "\033[0m"    # reset
EL = "\033[K"     # erase to end of line

_prev_lines = 0
_WIDTH = 58


def _row(text: str = "") -> str:
    return f"\r{text}{EL}"


def render(status: dict):
    global _prev_lines

    markets     = status.get("active_markets", [])
    running     = status.get("running", False)
    last_action = status.get("last_action", "")
    last_error  = status.get("last_error", "")
    tick        = status.get("tick_count", 0)

    lines: list[str] = []

    dot   = f"{G}●{X}" if running else f"{R}●{X}"
    mode  = f"{G}LIVE{X}" if status.get("production") else f"{A}SIM{X}"
    lines.append(_row(f"  {dot} {B}POLYBOT{X} {mode}  {D}tick {tick}{X}"))
    lines.append(_row(f"  {D}{'─' * _WIDTH}{X}"))

    if not markets:
        lines.append(_row(f"  {D}waiting for markets …{X}"))
    else:
        lines.append(_row(
            f"  {D}{'TIME':>5}  {'UP ASK':>7}  {'DN ASK':>7}  "
            f"{'FAV':>4}  {'@ PRICE':>7}  STATUS{X}"
        ))
        for m in markets:
            rem     = m["remaining"]
            mm, ss  = divmod(rem, 60)
            timer   = f"{mm:02d}:{ss:02d}"

            up  = m["up_ask"]
            dn  = m["down_ask"]
            fav = "UP" if up >= dn else "DN"
            fp  = max(up, dn)
            sc  = G if fav == "UP" else R

            if m["bet_placed"] and m.get("flagged_side"):
                badge = f"{G}{B}BET ✓{X}"
            elif m["bet_placed"]:
                badge = f"{D}skip{X}"
            elif m["flagged"]:
                badge = f"{A}FLAGGED{X}"
            elif rem > 125:
                badge = f"{D}early{X}"
            elif rem > 95:
                badge = f"{D}watching{X}"
            else:
                badge = f"{D}past window{X}"

            lines.append(_row(
                f"  {A}{timer}{X}  "
                f"{G}{up:.3f}{X}  "
                f"{R}{dn:.3f}{X}  "
                f"{sc}{fav:>4}{X}  "
                f"{sc}{fp:.3f}{X}  "
                f"{badge}"
            ))

    lines.append(_row(f"  {D}{'─' * _WIDTH}{X}"))

    if last_error:
        lines.append(_row(f"  {R}ERR {last_error[:50]}{X}"))
    if last_action:
        lines.append(_row(f"  {D}{last_action[:55]}{X}"))

    # Move cursor up over previous block and overwrite
    if _prev_lines:
        sys.stdout.write(f"\033[{_prev_lines}A")

    sys.stdout.write("\n".join(lines) + "\n")
    sys.stdout.flush()
    _prev_lines = len(lines)
