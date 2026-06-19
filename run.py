#!/usr/bin/env python
"""Refresh loop — обновява дисплея на интервал.

Цикъл: fetch (реален /usage + ccusage) -> render -> sleep. Resilient:
- временна грешка (network/ccusage/usage) -> лог + продължава (дисплеят пази стария кадър)
- serial проблем -> reconnect следващия цикъл
- COM5 зает (TURMO се върнал) -> убива TURMO и reconnect-ва

ВАЖНО: за да може да убива TURMO.exe (protected процес), пусни го **elevated**
(autostart task с highest privileges). Виж README.
"""
import os
import subprocess
import sys
import time

try:
    # line-buffered + utf-8 -> логовете излизат веднага (важно за autostart лога)
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
except (AttributeError, ValueError):
    pass

import ccusage_client as cc  # noqa: E402
import display as d  # noqa: E402
import usage_client as uc  # noqa: E402

INTERVAL = int(os.environ.get("CLAUDE_USAGE_INTERVAL", "60"))


def kill_turmo() -> None:
    """Убива Turing vendor app-а, ако държи COM5 (иска elevation за protected процес)."""
    try:
        r = subprocess.run(["taskkill", "/F", "/IM", "TURMO.exe"],
                           capture_output=True, text=True)
        if r.returncode == 0:
            print("[run] TURMO.exe killed")
        elif "not found" not in (r.stderr + r.stdout).lower() and "168" not in r.stderr:
            print(f"[run] TURMO kill не успя (elevated ли си?): {r.stderr.strip()[:120]}",
                  file=sys.stderr)
    except FileNotFoundError:
        pass  # не-Windows / няма taskkill


def _fetch():
    usage = uc.fetch_usage()
    snap = None
    try:
        snap = cc.fetch_snapshot()
    except cc.CcusageError as exc:
        print(f"[run] ccusage недостъпен: {exc}", file=sys.stderr)
    return usage, snap


def main() -> int:
    print(f"[run] старт — интервал {INTERVAL}s")
    kill_turmo()
    lcd = None
    try:
        while True:
            try:
                if lcd is None:
                    lcd = d.connect()
                usage, snap = _fetch()
                d.render(lcd, usage, snap)
                print(f"[run] обновено: 5h {usage.five_hour.utilization:.0f}% "
                      f"wk {usage.seven_day.utilization:.0f}%")
            except uc.UsageError as exc:
                print(f"[run] usage грешка (пропускам цикъл): {exc}", file=sys.stderr)
            except Exception as exc:  # serial/render -> reconnect
                msg = str(exc)
                print(f"[run] цикъл грешка: {type(exc).__name__}: {msg[:160]}", file=sys.stderr)
                try:
                    if lcd:
                        lcd.closeSerial()
                except Exception:
                    pass
                lcd = None
                if any(s in msg for s in ("Access is denied", "PermissionError", "could not open")):
                    kill_turmo()  # COM5 зает -> TURMO се е върнал
            time.sleep(INTERVAL)
    except KeyboardInterrupt:
        print("\n[run] спрян")
    finally:
        try:
            if lcd:
                lcd.closeSerial()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
