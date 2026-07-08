#!/usr/bin/env python
"""Refresh loop — обновява дисплея(ите) на интервал.

CLAUDE_USAGE_TARGET: turing | smalltv | both (default turing).
В `both` режим ЕДИН процес дърпа /usage веднъж и рисува на двата дисплея —
така не удвояваме виканиятa към endpoint-а (по-малко 429).

Цикъл: fetch (реален /usage + ccusage) -> render към всеки backend -> sleep.
Всеки backend има НЕЗАВИСИМ error handling — ако единият падне, другият продължава.

ВАЖНО: Turing backend-ът убива protected TURMO.exe -> пусни процеса **elevated**
(autostart task с highest privileges). SmallTV (HTTP) не иска elevation. Виж README.
"""
import os
import subprocess
import sys
import time
from datetime import datetime

try:
    # line-buffered + utf-8 -> логовете излизат веднага (важно за autostart лога)
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
except (AttributeError, ValueError):
    pass

import serial  # noqa: E402
from serial.tools.list_ports import comports  # noqa: E402

import ccusage_client as cc  # noqa: E402
import session_client as sc  # noqa: E402
import usage_client as uc  # noqa: E402

INTERVAL = int(os.environ.get("CLAUDE_USAGE_INTERVAL", "60"))
SETTLE_SECONDS = int(os.environ.get("CLAUDE_USAGE_SETTLE", "4"))  # MCU boot след replug
# Screensaver (Turing only): screen off през нощните часове ИЛИ когато няма активен
# ccusage 5h блок (не си кодил наскоро). Часовете са в local time.
SLEEP_START = int(os.environ.get("CLAUDE_USAGE_SLEEP_START", "22"))
SLEEP_END = int(os.environ.get("CLAUDE_USAGE_SLEEP_END", "7"))


def _should_sleep(snap, now: datetime) -> bool:
    """True когато Turing трябва да е ScreenOff (нощ ИЛИ без активна сесия).

    При snap=None (ccusage грешка) не гадаем: оставяме дисплея буден, за да не
    угасне при преходни ccusage failures.
    """
    h = now.hour
    is_night = (h >= SLEEP_START or h < SLEEP_END) if SLEEP_START > SLEEP_END \
        else (SLEEP_START <= h < SLEEP_END)
    return is_night or (snap is not None and not snap.has_active_block)


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


def _resolve_port():
    """Намира COM порта на дисплея по VID/PID/serial. None ако е изключен.

    Преглед ПРЕДИ да конструираме LCD-то — иначе библиотечният openSerial прави
    os._exit(0) (твърд kill, нехванаем) когато портът липсва/е зает.
    """
    override = os.environ.get("CLAUDE_USAGE_COM_PORT")
    if override and override != "AUTO":
        return override
    for p in comports():
        if p.serial_number == "USB35INCHIPSV2" or (p.vid == 0x1A86 and p.pid == 0x5722):
            return p.device
    return None


def _ensure_free(port: str) -> bool:
    """Проверява че портът се отваря (свободен е). При зает -> убива TURMO и пробва пак."""
    for attempt in range(2):
        try:
            serial.Serial(port, 115200, timeout=1, rtscts=True).close()
            return True
        except serial.SerialException as exc:
            if attempt == 0 and any(s in str(exc) for s in ("Access is denied", "PermissionError", "denied")):
                print(f"[run] {port} зает — убивам TURMO и пробвам пак", file=sys.stderr)
                kill_turmo()
                time.sleep(1)
                continue
            print(f"[run] {port} не се отваря: {exc}", file=sys.stderr)
            return False
    return False


def _snapshot():
    """ccusage session данни (best-effort)."""
    try:
        return cc.fetch_snapshot()
    except cc.CcusageError as exc:
        print(f"[run] ccusage недостъпен: {exc}", file=sys.stderr)
        return None


def _session():
    """Context tokens на най-скорошно активната Claude Code сесия (best-effort, fail-soft)."""
    try:
        return sc.fetch()
    except Exception as exc:  # jsonl parsing / IO — never take down the loop
        print(f"[run] session недостъпен: {exc}", file=sys.stderr)
        return None


class TuringDriver:
    """Serial Turing дисплей: preflight + connect + reconnect + TURMO kill."""

    def __init__(self):
        import display as d
        self.d = d
        self.lcd = None
        kill_turmo()  # разчисти порта при старт

    def tick(self, usage, snap, session) -> None:
        for _ in range(4):  # позволи няколко чисти reconnect-а в рамките на тика
            try:
                if self.lcd is None:
                    port = _resolve_port()
                    if port is None:
                        print("[run] turing: дисплеят не е намерен — пропускам", file=sys.stderr)
                        return
                    if not _ensure_free(port):
                        return
                    time.sleep(SETTLE_SECONDS)  # MCU boot след replug
                    self.lcd = self.d.connect(port)
                # screensaver: пропускаме render когато screen е off (спестява serial трафик
                # и запазва MCU-то от излишни bitmap-и до чер екран)
                if _should_sleep(snap, datetime.now()):
                    if not getattr(self.lcd, "_screen_off", False):
                        self.lcd.ScreenOff()
                        self.lcd._screen_off = True
                        print("[run] turing: screensaver ON")
                    return
                if getattr(self.lcd, "_screen_off", False):
                    self.lcd.ScreenOn()
                    self.lcd._screen_off = False
                    self.lcd._dash_base = False  # force full redraw при събуждане
                    print("[run] turing: screensaver OFF")
                self.d.render(self.lcd, usage, snap, session)
                if getattr(self.lcd, "_needs_reinit", False):
                    self._drop()
                    print("[run] turing: serial reopen — чист reconnect", file=sys.stderr)
                    continue  # чист reconnect веднага, в същия тик
                if usage:
                    ctx_s = f" ctx {session.tokens // 1000}K" if session else ""
                    print(f"[run] turing: 5h {usage.five_hour.utilization:.0f}% "
                          f"wk {usage.seven_day.utilization:.0f}%{ctx_s}")
                else:
                    print("[run] turing: кадър без usage данни (--)")
                return
            except Exception as exc:  # serial/render -> reconnect следващия тик
                msg = str(exc)
                print(f"[run] turing грешка: {type(exc).__name__}: {msg[:140]}", file=sys.stderr)
                self._drop()
                if any(s in msg for s in ("Access is denied", "PermissionError", "could not open")):
                    kill_turmo()
                return

    def _drop(self):
        try:
            if self.lcd:
                self.lcd.closeSerial()
        except Exception:
            pass
        self.lcd = None


class SmallTvDriver:
    """SmallTV HTTP дисплей (WiFi). Без serial/TURMO/elevation."""

    def __init__(self):
        import display_smalltv as backend
        self.backend = backend
        self.handle = None

    def tick(self, usage, snap, session) -> None:
        try:
            if self.handle is None:
                self.handle = self.backend.connect()  # cleanup + theme=3 + autoplay off
            self.backend.render(self.handle, usage, snap, session)
            if usage:
                print(f"[run] smalltv: 5h {usage.five_hour.utilization:.0f}% "
                      f"wk {usage.seven_day.utilization:.0f}%")
            else:
                print("[run] smalltv: кадър без usage данни (--)")
        except self.backend.SmallTvError as exc:
            print(f"[run] smalltv мрежова грешка (reconnect): {exc}", file=sys.stderr)
            self.handle = None
        except Exception as exc:
            print(f"[run] smalltv грешка: {type(exc).__name__}: {str(exc)[:140]}", file=sys.stderr)
            self.handle = None


def _loop(drivers) -> int:
    last_usage = None  # кеш — на usage грешка (429/мрежа) рисуваме последното добро
    try:
        while True:
            try:
                last_usage = uc.fetch_usage()
            except uc.UsageError as exc:
                print(f"[run] usage грешка (рисувам кеш/--): {exc}", file=sys.stderr)
            snap = _snapshot()
            session = _session()
            for drv in drivers:  # всеки backend независимо; един падне -> другият върви
                drv.tick(last_usage, snap, session)
            time.sleep(INTERVAL)
    except KeyboardInterrupt:
        print("\n[run] спрян")
    return 0


def main() -> int:
    target = os.environ.get("CLAUDE_USAGE_TARGET", "turing").lower()
    print(f"[run] target={target} — интервал {INTERVAL}s")
    if target == "smalltv":
        drivers = [SmallTvDriver()]
    elif target == "both":
        drivers = [TuringDriver(), SmallTvDriver()]
    else:
        drivers = [TuringDriver()]
    return _loop(drivers)


if __name__ == "__main__":
    sys.exit(main())
